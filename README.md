# PayShield-AI

Trust and governance layer for agentic commerce. PayShield AI uses PayPal
Sandbox only; the deterministic risk/policy/decision engines are authoritative
and are never overridden by the AI assistant.

## Backend setup (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` is the authoritative dependency file. The Ollama integration
uses the official `ollama` Python client (`ollama>=0.4.0,<0.7.0`).

## Run the backend

```powershell
uvicorn backend.main:app --reload
```

## Ollama assistant (optional, advisory only)

Copy `.env.example` to `.env` and set:

```dotenv
OLLAMA_API_KEY=<your-key>
OLLAMA_MODEL=<verified-model-name>
# OLLAMA_BASE_URL=            # defaults to https://ollama.com (key) or http://localhost:11434
```

The model name is read from configuration. If the API key or model is not
configured, if the Ollama host is unreachable, or if the `ollama` package is not
installed, the backend still starts; the assistant reports an unavailable /
advisory-assessment error instead. Check `GET /assistant/provider-health` to
confirm the host is reachable and the configured model is available.

## Tests

```powershell
python -m pytest backend tests -q
```

```powershell
cd frontend; npm test; npm run lint; npm run build
```
