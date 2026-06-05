# AI Application Compiler

Natural language product idea to validated application blueprint to generated FastAPI runtime.

This project is a compiler-style LLM pipeline. It takes a plain English product description, extracts intent, builds a domain model, generates database/API/RBAC layers, validates cross-layer consistency, repairs issues when needed, and emits a runnable FastAPI application in `output/`.

## Current Stack

- Python
- FastAPI
- Pydantic
- Local LLM via Ollama, currently `qwen2.5:3b`
- React, Vite, TypeScript, Tailwind CSS frontend
- Modular compiler stages

## Pipeline

```text
Prompt
  -> Stage 1: Intent Extraction
  -> Stage 2: Domain / IR Modeling
  -> Stage 3: Database Schema
  -> Stage 4: API Schema
  -> Stage 5: Auth and RBAC
  -> Stage 6: Cross-Layer Validation
  -> Stage 7: Repair Engine, only when validation finds errors
  -> Stage 8: Runtime Generation
```

## Project Structure

```text
ai-compiler/
  compiler/
    ir/models.py
    stages/
      stage1_intent.py
      stage2_domain.py
      stage4_db.py
      stage5_api.py
      stage7_auth.py
  validators/
    consistency.py
  repair_engine/
    regenerator.py
  runtime/
    fastapi_gen/generator.py
  frontend/
    src/
      api/
      components/
      App.tsx
  output/
    Generated FastAPI app
  compiler_api.py
  run_compiler_api.py
```

## Setup

From `D:\ai-compiler`:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` from `.env.example` if needed:

```powershell
Copy-Item .env.example .env
```

Make sure Ollama is running and the local model is available:

```powershell
ollama pull qwen2.5:3b
```

## Run the Backend API

Use the project launcher:

```powershell
python run_compiler_api.py
```

The API runs at:

```text
http://localhost:8000
```

Health check:

```powershell
Invoke-WebRequest http://localhost:8000/health
```

Do not run this from the repo root while compiling:

```powershell
uvicorn compiler_api:app --reload --port 8000
```

The compiler writes generated files into `output/`. Uvicorn's default reload watcher can notice those generated files and restart the API server during a streaming compile response. `run_compiler_api.py` keeps reload enabled for source folders while excluding generated output.

## Run the Frontend

Open a second terminal:

```powershell
cd D:\ai-compiler\frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The frontend connects to `http://localhost:8000` by default. To use another backend URL, create `frontend/.env`:

```text
VITE_API_BASE_URL=http://localhost:8000
```

## API Contract

### `GET /health`

Returns backend readiness and model information.

Example:

```json
{
  "status": "ok",
  "model": "qwen2.5:3b",
  "ready": true
}
```

### `POST /compile`

Request:

```json
{
  "prompt": "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
}
```

Response type:

```text
text/event-stream
```

The backend streams events:

```text
stage_start
stage_done
stage_skip
complete
error
```

The frontend uses `fetch()` plus `ReadableStream` parsing because browser `EventSource` does not support POST bodies.

## CLI Usage

You can still run the compiler directly:

```powershell
python -m compiler.orchestrator "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
```

Generated runtime files are written to `output/`.

## Run the Generated App

After a successful compile:

```powershell
cd D:\ai-compiler\output
pip install -r requirements.txt
uvicorn main:app --reload
```

Generated API docs:

```text
http://localhost:8000/docs
```

## Frontend Features

- Prompt editor
- Backend/model health status
- Stage-by-stage progress timeline
- Live streamed compiler events
- Intermediate JSON output per stage
- Final blueprint viewer
- Generated file viewer/export
- Clean error display
- Responsive layout

## Notes

- `output/` is generated and ignored by git.
- `frontend/node_modules/` and `frontend/dist/` are ignored by git.
- `.env` is ignored by git; `.env.example` is tracked.
- The current frontend is intentionally a client for the existing compiler API. It does not redesign the compiler pipeline.
