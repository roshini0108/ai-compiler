import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from compiler.stages.stage1_intent import extract_intent
from compiler.stages.stage2_domain import build_domain
from compiler.stages.stage4_db import generate_db_schema
from compiler.stages.stage5_api import generate_api_schema
from compiler.stages.stage7_auth import generate_rbac
from validators.consistency import validate_all
from repair_engine.regenerator import repair
from runtime.fastapi_gen.generator import generate_fastapi


def compile_app(prompt: str, verbose: bool = True) -> dict:
    start = time.time()

    def log(msg):
        if verbose:
            print(msg)

    log("\n" + "=" * 60)
    log("  AI APPLICATION COMPILER")
    log("=" * 60)
    log(f"\nPrompt: {prompt}\n")

    # ── Stage 1: Intent Extraction ───────────────────────────────
    log("Stage 1/7 ── Intent Extraction...")
    intent = extract_intent(prompt)
    log(f"  ✓ Entities: {intent.entities}")
    log(f"  ✓ Roles:    {intent.roles}")
    log(f"  ✓ Features: {intent.features}")

    # ── Stage 2: Domain → IR ─────────────────────────────────────
    log("\nStage 2/7 ── Building Intermediate Representation...")
    ir = build_domain(intent)
    log(f"  ✓ Entities: {[e.id for e in ir.entities]}")
    log(f"  ✓ Roles:    {[r.id for r in ir.roles]}")
    log(f"  ✓ Plans:    {[p.id for p in ir.plans]}")
    log(f"  ✓ Rules:    {len(ir.business_rules)} business rules")

    # ── Stage 4: DB Schema ───────────────────────────────────────
    log("\nStage 4/7 ── Generating Database Schema...")
    db_schema = generate_db_schema(ir)
    log(f"  ✓ Tables: {[t['name'] for t in db_schema['tables']]}")

    # ── Stage 5: API Schema ──────────────────────────────────────
    log("\nStage 5/7 ── Generating API Schema...")
    api_schema = generate_api_schema(ir, db_schema)
    log(f"  ✓ Endpoints: {len(api_schema['endpoints'])} generated")

    # ── Stage 7: Auth + RBAC ─────────────────────────────────────
    log("\nStage 7/7 ── Generating Auth & RBAC...")
    rbac = generate_rbac(ir, api_schema)
    log(f"  ✓ Policies: {len(rbac['policies'])} generated")
    log(f"  ✓ Route guards: {len(rbac['route_guards'])} generated")

    # ── Stage 8: Cross-Layer Validation ─────────────────────────
    log("\nStage 8 ── Cross-Layer Validation...")
    report = validate_all(ir, db_schema, api_schema, rbac)

    if report["errors"]:
        log(f"  ✗ {len(report['errors'])} errors found:")
        for err in report["errors"]:
            log(f"    - [{err['layer'].upper()}] {err['message']}")

        # ── Stage 9: Repair ──────────────────────────────────────
        log("\nStage 9 ── Running Repair Engine...")
        db_schema, api_schema, rbac = repair(report, ir, db_schema, api_schema, rbac)

        # Re-validate after repair
        report = validate_all(ir, db_schema, api_schema, rbac)
        if report["errors"]:
            log(f"  ⚠ {len(report['errors'])} errors remain after repair")
        else:
            log("  ✓ All errors repaired")
    else:
        log(f"  ✓ All validation checks passed")

    if report["warnings"]:
        for w in report["warnings"]:
            log(f"  ⚠ Warning: {w['message']}")

    # ── Stage 10: Executable Config ──────────────────────────────
    log("\nStage 10 ── Generating Executable Application...")
    output_path = generate_fastapi(db_schema, api_schema, rbac, app_name=ir.app_name)

    # Save full config
    app_config = {
        "ir": json.loads(ir.model_dump_json()),
        "db_schema": db_schema,
        "api_schema": api_schema,
        "rbac": rbac,
        "validation_report": report,
        "output_path": output_path
    }
    config_path = Path("output/app_config.json")
    config_path.write_text(json.dumps(app_config, indent=2))

    elapsed = round(time.time() - start, 1)
    log(f"\n{'=' * 60}")
    log(f"  ✓ COMPILATION COMPLETE in {elapsed}s")
    log(f"  ✓ Config saved to: output/app_config.json")
    log(f"  ✓ Server ready:    cd output && uvicorn main:app --reload")
    log(f"  ✓ Docs at:         http://localhost:8000/docs")
    log(f"{'=' * 60}\n")

    return app_config


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Build a CRM with login, contacts, dashboard, "
        "role-based access, and premium plan with payments. "
        "Admins can see analytics."
    )
    compile_app(prompt)
