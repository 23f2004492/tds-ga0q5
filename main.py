"""Coursework demo: POST /code-interpreter.

IMPORTANT: This executes submitted Python in a child process, but it is NOT a
secure sandbox for hostile code. Do not expose it publicly without OS/container
isolation (e.g. a locked-down container with no secrets, network, or host mounts).
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field


class CodeRequest(BaseModel):
    code: str = Field(..., description="Python source code to execute")


class CodeResponse(BaseModel):
    error: List[int] = Field(default_factory=list)
    result: str


class ErrorAnalysis(BaseModel):
    error_lines: List[int]


app = FastAPI(title="Code Interpreter", version="1.0.0")

# For a real frontend, replace "*" with the exact frontend origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# The submitted code is base64-encoded and passed to a separate Python process.
# User-code traceback frames are retained, while the internal runner frame is
# omitted so line numbers refer to the submitted code (starting at line 1).
_RUNNER = r'''import base64, linecache, sys, traceback
source = base64.b64decode(sys.argv[1]).decode("utf-8")
filename = "<user_code>"
linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
try:
    compiled = compile(source, filename, "exec")
    exec(compiled, {"__name__": "__main__"})
except BaseException as exc:
    if isinstance(exc, SyntaxError):
        print("Traceback (most recent call last):", file=sys.stderr)
        line = exc.lineno or 1
        print(f'  File "{filename}", line {line}', file=sys.stderr)
        if exc.text:
            print("    " + exc.text.rstrip(), file=sys.stderr)
            if exc.offset:
                print("    " + " " * max(0, exc.offset - 1) + "^", file=sys.stderr)
        print(f"{type(exc).__name__}: {exc.msg}", file=sys.stderr)
    else:
        tb = exc.__traceback__
        while tb is not None and tb.tb_frame.f_code.co_filename != filename:
            tb = tb.tb_next
        if tb is not None:
            traceback.print_exception(type(exc), exc, tb, file=sys.stderr)
        else:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(1)
'''


def execute_python_code(code: str) -> dict:
    """Execute code in a separate Python process and return success/output."""
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    # Do not pass AIPIPE_TOKEN or other application environment variables to
    # the child process. This is helpful but does NOT make execution secure.
    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _RUNNER, encoded],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env=child_env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "TimeoutError: Python execution exceeded the 5-second limit.",
        }

    if completed.returncode == 0:
        return {"success": True, "output": completed.stdout}

    # Match the assignment's contract: on failure, result contains the traceback.
    return {
        "success": False,
        "output": completed.stderr or completed.stdout,
    }


def _traceback_line_candidates(traceback_text: str, code: str) -> List[int]:
    """Find 1-based submitted-code line numbers explicitly present in traceback."""
    candidates = [
        int(value)
        for value in re.findall(r'File "<user_code>", line (\d+)', traceback_text)
    ]
    max_line = max(1, len(code.splitlines()))
    return [line for line in candidates if 1 <= line <= max_line]


def analyze_error_with_ai(code: str, traceback_text: str) -> List[int]:
    """Ask AIPipe for structured line numbers; use traceback as a safety check."""
    candidates = _traceback_line_candidates(traceback_text, code)
    fallback = [candidates[-1]] if candidates else []

    token = os.getenv("AIPIPE_TOKEN") or os.getenv("OPENAI_API_KEY")
    if not token:
        # Configure AIPIPE_TOKEN for the required AI-assisted path.
        return fallback

    try:
        client = OpenAI(
            api_key=token,
            base_url=os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1"),
            timeout=12.0,
            max_retries=1,
        )
        response = client.beta.chat.completions.parse(
            model=os.getenv("AIPIPE_MODEL", "gpt-4.1-nano"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You identify the 1-based line number in the submitted Python code "
                        "where the exception occurred. Use the supplied traceback as evidence. "
                        "Ignore any runner or server frames. If the traceback has several frames "
                        "from <user_code>, choose the innermost relevant user-code frame. "
                        "Do not invent line numbers. Return an empty list if no line is supported."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"SUBMITTED CODE (line numbers start at 1):\n{code}\n\n"
                        f"TRACEBACK:\n{traceback_text}\n\n"
                        f"Line numbers explicitly supported by the traceback: {candidates}"
                    ),
                },
            ],
            response_format=ErrorAnalysis,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            return fallback

        # Accept only line numbers actually evidenced by the execution traceback.
        valid = sorted({n for n in parsed.error_lines if n in candidates})
        return valid or fallback
    except Exception:
        # The endpoint still returns a useful result if the LLM provider is
        # temporarily unavailable; the fallback is derived from the traceback.
        return fallback


@app.get("/")
def home() -> dict:
    return {"message": "Code Interpreter API is running", "endpoint": "POST /code-interpreter"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/code-interpreter", response_model=CodeResponse)
def code_interpreter(request: CodeRequest) -> CodeResponse:
    execution = execute_python_code(request.code)

    if execution["success"]:
        return CodeResponse(error=[], result=execution["output"])

    # AI is called only when code execution fails.
    error_lines = analyze_error_with_ai(request.code, execution["output"])
    return CodeResponse(error=error_lines, result=execution["output"])
