"""
compiler_api.py
Place this in your ai-compiler/ root folder (same level as compiler/).
Run with: uvicorn compiler_api:app --reload --port 8000
"""
import json
import sys
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Make sure ai-compiler modules are importable
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="AI Compiler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompileRequest(BaseModel):
    prompt: str


def event(type_: str, data: dict) -> str:
    payload = {"type": type_, **data}
    return f"data: {json.dumps(payload)}\n\n"


def run_pipeline(prompt: str):
    """
    Synchronous generator that yields SSE strings.
    Each yield is immediately flushed to the client.
    """
    try:
        # ── Stage 1: Intent Extraction ─────────────────────────
        yield event("stage_start", {"stage": 1, "label": "Intent Extraction"})
        from compiler.stages.stage1_intent import extract_intent
        intent = extract_intent(prompt)
        yield event("stage_done", {
            "stage": 1,
            "label": "Intent Extraction",
            "output": intent.model_dump()
        })

        # ── Stage 2: Domain → IR ───────────────────────────────
        yield event("stage_start", {"stage": 2, "label": "Building IR"})
        from compiler.stages.stage2_domain import build_domain
        ir = build_domain(intent)
        yield event("stage_done", {
            "stage": 2,
            "label": "Building IR",
            "output": json.loads(ir.model_dump_json())
        })

        # ── Stage 3: DB Schema ─────────────────────────────────
        yield event("stage_start", {"stage": 3, "label": "Database Schema"})
        from compiler.stages.stage4_db import generate_db_schema
        db = generate_db_schema(ir)
        yield event("stage_done", {
            "stage": 3,
            "label": "Database Schema",
            "output": db
        })

        # ── Stage 4: API Schema ────────────────────────────────
        yield event("stage_start", {"stage": 4, "label": "API Schema"})
        from compiler.stages.stage5_api import generate_api_schema
        api = generate_api_schema(ir, db)
        yield event("stage_done", {
            "stage": 4,
            "label": "API Schema",
            "output": api
        })

        # ── Stage 5: Auth + RBAC ───────────────────────────────
        yield event("stage_start", {"stage": 5, "label": "Auth & RBAC"})
        from compiler.stages.stage7_auth import generate_rbac
        rbac = generate_rbac(ir, api)
        yield event("stage_done", {
            "stage": 5,
            "label": "Auth & RBAC",
            "output": rbac
        })

        # ── Stage 6: Cross-Layer Validation ───────────────────
        yield event("stage_start", {"stage": 6, "label": "Cross-Layer Validation"})
        from validators.consistency import validate_all
        report = validate_all(ir, db, api, rbac)
        yield event("stage_done", {
            "stage": 6,
            "label": "Cross-Layer Validation",
            "output": report
        })

        # ── Stage 7: Repair (only if errors) ──────────────────
        if report["errors"]:
            yield event("stage_start", {"stage": 7, "label": "Repair Engine"})
            from repair_engine.regenerator import repair
            db, api, rbac = repair(report, ir, db, api, rbac)
            report = validate_all(ir, db, api, rbac)
            yield event("stage_done", {
                "stage": 7,
                "label": "Repair Engine",
                "output": {
                    "repaired": True,
                    "errors_fixed": len(report["errors"]),
                    "remaining_errors": len(report["errors"])
                }
            })
        else:
            yield event("stage_skip", {"stage": 7, "label": "Repair Engine"})

        # ── Stage 8: Generate Runtime ──────────────────────────
        yield event("stage_start", {"stage": 8, "label": "Generating Runtime"})
        from runtime.fastapi_gen.generator import generate_fastapi
        generate_fastapi(db, api, rbac, app_name=ir.app_name)

        # Read generated files
        generated_files = {}
        output_dir = Path("output")
        if output_dir.exists():
            for f in sorted(output_dir.rglob("*.py")):
                rel = str(f.relative_to(output_dir))
                try:
                    generated_files[rel] = f.read_text(encoding="utf-8")
                except Exception:
                    pass

        yield event("stage_done", {
            "stage": 8,
            "label": "Generating Runtime",
            "output": {"files_generated": list(generated_files.keys())}
        })

        # ── Complete ───────────────────────────────────────────
        yield event("complete", {
            "ir":              json.loads(ir.model_dump_json()),
            "db_schema":       db,
            "api_schema":      api,
            "rbac":            rbac,
            "validation":      report,
            "generated_files": generated_files,
            "app_name":        ir.app_name,
        })

    except Exception as e:
        import traceback
        yield event("error", {
            "message": str(e),
            "detail":  traceback.format_exc()[-800:]
        })


@app.post("/compile")
def compile_endpoint(req: CompileRequest):
    return StreamingResponse(
        run_pipeline(req.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        }
    )


@app.get("/health")
def health():
    return {"status": "ok", "model": "qwen2.5:3b", "ready": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)