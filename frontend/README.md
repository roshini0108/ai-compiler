# AI Application Compiler Frontend

React, Vite, TypeScript, and Tailwind UI for the existing FastAPI compiler backend.

## Backend contract

- Health check: `GET http://localhost:8000/health`
- Compile stream: `POST http://localhost:8000/compile`
- Request body: `{ "prompt": "Build a CRM..." }`
- Response: `text/event-stream` with JSON payloads inside `data:` frames.

The frontend uses `fetch()` with `ReadableStream` parsing because the backend accepts a POST body. Browser `EventSource` only supports GET.

## Run

```bash
cd frontend
npm install
npm run dev
```

Start the backend from the project root in another terminal:

```bash
uvicorn compiler_api:app --reload --port 8000
```

Open `http://localhost:5173`.

Set `VITE_API_BASE_URL` in `.env` if your FastAPI server runs on another URL.
