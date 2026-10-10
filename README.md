# Code Interpreter API (coursework demo)

## 1. Install

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure AIPipe

Create/get a token at https://aipipe.org/login. Set it in your terminal; do not paste it into `main.py` or commit it to Git.

Windows PowerShell:

```powershell
$env:AIPIPE_TOKEN="YOUR_TOKEN_HERE"
$env:AIPIPE_MODEL="gpt-4.1-nano"
```

macOS/Linux:

```bash
export AIPIPE_TOKEN="YOUR_TOKEN_HERE"
export AIPIPE_MODEL="gpt-4.1-nano"
```

The app uses `https://aipipe.org/openai/v1` by default. You can override it with `OPENAI_BASE_URL` if needed.

## 3. Run locally

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` to test `POST /code-interpreter`.

Successful test body:

```json
{"code":"x = 5\ny = 10\nprint(x + y)"}
```

Expected response:

```json
{"error": [], "result": "15\n"}
```

Error test body:

```json
{"code":"x = 10\ny = 0\nresult = x / y"}
```

Expected shape (the traceback text is returned in `result`):

```json
{"error": [3], "result": "Traceback (most recent call last):\\n  File \\"<user_code>\\", line 3, in <module>\\nZeroDivisionError: division by zero\\n"}
```

## 4. Endpoint URL

When running locally, the full endpoint is:

`http://127.0.0.1:8000/code-interpreter`

A remote evaluator cannot reach your localhost. Deploy to a hosting service first, then submit:

`https://YOUR-DEPLOYED-DOMAIN/code-interpreter`

## Security note

This is an assignment-oriented example, not a production-grade sandbox. A subprocess and timeout do not isolate hostile Python from the host OS. Do not expose it to the public internet without proper OS/container sandboxing (no host mounts, no credentials in the execution environment, restricted network/syscalls/resources, and a non-privileged user).

## 5. Deploy for a remote evaluator (Render example)

A remote grader cannot call your `127.0.0.1` URL. To obtain a public endpoint:

1. Upload `main.py`, `requirements.txt`, and `render.yaml` to a GitHub repository.
2. In Render, create a new Blueprint from that repository, or create a Web Service and set the commands below.
3. Add `AIPIPE_TOKEN` as a secret/environment variable in Render's dashboard. Never put the token in GitHub or in the source code.
4. Wait for the service to finish deploying. Open `https://YOUR-SERVICE.onrender.com/health`; it should return `{"status":"ok"}`.
5. Submit `https://YOUR-SERVICE.onrender.com/code-interpreter` as the endpoint URL.

If creating the service manually, use:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment variables: `AIPIPE_TOKEN` = your AIPipe token; `AIPIPE_MODEL` = `gpt-4.1-nano`

Render's official FastAPI instructions use the same build/start-command pattern: https://render.com/docs/deploy-fastapi

## Security warning

A subprocess plus a timeout is **not** a hardened security boundary. This demo is for coursework and controlled testing only. A genuinely public service that executes arbitrary code needs a proper OS/container sandbox with a non-privileged user, no secrets or host mounts, restricted networking, CPU/memory/process limits, and appropriate syscall restrictions.
