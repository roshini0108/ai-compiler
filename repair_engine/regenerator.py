import json
from compiler.llm import call_llm
from compiler.ir.models import IntermediateRepresentation

MAX_REPAIR_ITERATIONS = 3


def repair(
    report: dict,
    ir: IntermediateRepresentation,
    db_schema: dict,
    api_schema: dict,
    rbac: dict,
    iteration: int = 1
) -> tuple[dict, dict, dict]:
    """
    Surgical repair: only regenerates the layer(s) with errors.
    Returns updated (db_schema, api_schema, rbac).
    """
    if iteration > MAX_REPAIR_ITERATIONS:
        print(f"  ⚠ Max repair iterations reached. Returning best effort.")
        return db_schema, api_schema, rbac

    errors = report["errors"]
    if not errors:
        return db_schema, api_schema, rbac

    scopes = {}
    for err in errors:
        scope = err.get("repair_scope", "unknown")
        scopes.setdefault(scope, []).append(err)

    print(f"  Repair iteration {iteration}: scopes = {list(scopes.keys())}")

    if "db" in scopes:
        print("  Repairing DB schema...")
        repaired = _repair_db(ir, db_schema, scopes["db"])
        db_schema = _safe_merge_db(db_schema, repaired)

    if "api" in scopes:
        print("  Repairing API schema...")
        repaired = _repair_api(ir, db_schema, api_schema, scopes["api"])
        api_schema = _safe_merge_api(api_schema, repaired)

    if "rbac" in scopes:
        print("  Repairing RBAC...")
        repaired = _repair_rbac(ir, api_schema, rbac, scopes["rbac"])
        rbac = _safe_merge_rbac(rbac, repaired, ir, api_schema)

    from validators.consistency import validate_all
    new_report = validate_all(ir, db_schema, api_schema, rbac)

    if new_report["errors"]:
        print(f"  Still {len(new_report['errors'])} errors. Recursing...")
        return repair(new_report, ir, db_schema, api_schema, rbac, iteration + 1)

    print(f"  ✓ Repair successful after {iteration} iteration(s)")
    return db_schema, api_schema, rbac


# ── Safe merge helpers ────────────────────────────────────────────────────────
# The LLM repair functions may return garbage. These helpers validate the
# structure before accepting the repair, falling back to the original if broken.

def _safe_merge_db(original: dict, repaired) -> dict:
    """Accept repaired DB schema only if it has a valid 'tables' list."""
    if not isinstance(repaired, dict):
        print("  ⚠ Repair: DB repair returned non-dict, keeping original")
        return original
    if "tables" not in repaired or not isinstance(repaired["tables"], list):
        print("  ⚠ Repair: DB repair missing 'tables', keeping original")
        return original
    if len(repaired["tables"]) < len(original.get("tables", [])):
        print(f"  ⚠ Repair: DB repair lost tables ({len(repaired['tables'])} < {len(original['tables'])}), keeping original")
        return original
    repaired.setdefault("migrations", original.get("migrations", []))
    return repaired


def _safe_merge_api(original: dict, repaired) -> dict:
    """Accept repaired API schema only if it has a valid 'endpoints' list."""
    if not isinstance(repaired, dict):
        print("  ⚠ Repair: API repair returned non-dict, keeping original")
        return original
    # Unwrap if model wrapped it
    if "endpoints" not in repaired and len(repaired) == 1:
        inner = next(iter(repaired.values()))
        if isinstance(inner, dict) and "endpoints" in inner:
            repaired = inner
    if "endpoints" not in repaired or not isinstance(repaired["endpoints"], list):
        print("  ⚠ Repair: API repair missing 'endpoints', keeping original")
        return original
    if len(repaired["endpoints"]) == 0 and len(original.get("endpoints", [])) > 0:
        print("  ⚠ Repair: API repair returned empty endpoints, keeping original")
        return original
    # Guarantee every endpoint has an id before it reaches the validator
    # or any downstream function that does ep["id"] directly.
    repaired = _ensure_endpoint_ids(repaired)
    return repaired


def _safe_merge_rbac(original: dict, repaired, ir: IntermediateRepresentation, api_schema: dict) -> dict:
    """
    Accept repaired RBAC only if it looks like a valid RBAC schema.
    If the model returned an endpoint object or other wrong structure,
    fall back to the Python-generated RBAC.
    """
    if not isinstance(repaired, dict):
        print("  ⚠ Repair: RBAC repair returned non-dict, regenerating")
        return _generate_rbac_python(ir, api_schema)

    is_wrong = (
        "method" in repaired
        or "endpoints" in repaired
        or "tables" in repaired
        or "entities" in repaired
        or ("policies" not in repaired and "auth_strategy" not in repaired)
    )
    if is_wrong:
        print(f"  ⚠ Repair: RBAC repair returned wrong structure, regenerating")
        return _generate_rbac_python(ir, api_schema)

    repaired.setdefault("auth_strategy", original.get("auth_strategy", "jwt"))
    repaired.setdefault("token_expiry_minutes", original.get("token_expiry_minutes", 60))
    repaired.setdefault("refresh_token_expiry_days", original.get("refresh_token_expiry_days", 7))
    repaired.setdefault("policies", original.get("policies", []))
    repaired.setdefault("route_guards", original.get("route_guards", []))

    # Final safety net: ensure every endpoint has at least admin coverage
    repaired = _fill_missing_policies(repaired, ir, api_schema)
    return repaired


def _generate_rbac_python(ir: IntermediateRepresentation, api_schema: dict) -> dict:
    """Deterministic RBAC generation — same logic as stage7_auth fallback."""
    policies = []
    route_guards = []
    role_ids = [r.id for r in ir.roles]
    admin_role = "admin" if "admin" in role_ids else (role_ids[0] if role_ids else "admin")
    user_role  = "user"  if "user"  in role_ids else (role_ids[-1] if len(role_ids) > 1 else admin_role)

    for i, ep in enumerate(api_schema.get("endpoints", [])):
        # Use .get() — endpoint may lack "id" if called before normalization
        ep_id = ep.get("id") or ("ep-" + ep.get("method", "GET").lower() + "-" + str(i))
        method = ep.get("method", "GET").upper()

        policies.append({
            "id": f"policy_{i}_admin",
            "endpoint_id": ep_id,
            "role_id": admin_role,
            "allowed": True,
            "conditions": [],
        })

        if method != "DELETE" and user_role != admin_role:
            policies.append({
                "id": f"policy_{i}_user",
                "endpoint_id": ep_id,
                "role_id": user_role,
                "allowed": True,
                "conditions": [],
            })

        path = ep.get("path", "")
        if ep.get("auth_required", True) and path:
            route_guards.append({
                "path": path,
                "required_roles": ep.get("required_roles") or [admin_role, user_role],
                "redirect_to": "/login",
            })

    return {
        "auth_strategy": "jwt",
        "token_expiry_minutes": 60,
        "refresh_token_expiry_days": 7,
        "policies": policies,
        "route_guards": route_guards,
    }


def _fill_missing_policies(rbac: dict, ir: IntermediateRepresentation, api_schema: dict) -> dict:
    covered = {p["endpoint_id"] for p in rbac.get("policies", [])}
    role_ids = [r.id for r in ir.roles]
    admin_role = "admin" if "admin" in role_ids else (role_ids[0] if role_ids else "admin")

    for ep in api_schema.get("endpoints", []):
        ep_id = ep.get("id")
        if not ep_id:
            continue  # skip endpoints with no id — _ensure_endpoint_ids should have run first
        if ep_id not in covered:
            rbac["policies"].append({
                "id": f"policy_auto_{ep_id}",
                "endpoint_id": ep_id,
                "role_id": admin_role,
                "allowed": True,
                "conditions": [],
            })
    return rbac


def _ensure_endpoint_ids(api_schema: dict) -> dict:
    """
    Guarantee every endpoint has a stable unique id.
    qwen2.5:3b sometimes omits "id" from repaired endpoint objects.
    This runs after every API repair before anything touches ep["id"].
    """
    seen: set[str] = set()
    for ep in api_schema.get("endpoints", []):
        if not ep.get("id"):
            method = ep.get("method", "GET").lower()
            path = ep.get("path", "").strip("/").replace("/", "-").replace("{", "").replace("}", "")
            base = f"{path}-{method}" if path else f"ep-{method}-unnamed"
            candidate, n = base, 2
            while candidate in seen:
                candidate = f"{base}-{n}"
                n += 1
            ep["id"] = candidate
            print(f"  ⚠ Repair: endpoint missing 'id' — assigned '{ep['id']}'")
        seen.add(ep["id"])
    return api_schema


# ── LLM repair functions ──────────────────────────────────────────────────────

def _repair_db(ir: IntermediateRepresentation, db_schema: dict, errors: list) -> dict:
    system = """You are fixing errors in a database schema.
Output ONLY the corrected JSON object. No explanation, no markdown, no backticks.
Fix ONLY the listed errors. Do not change anything else."""

    user = f"""Current DB schema:
{json.dumps(db_schema, indent=2)}

IR (source of truth):
{ir.model_dump_json(indent=2)}

Errors to fix:
{json.dumps(errors, indent=2)}

Output the complete corrected DB schema JSON only."""

    return call_llm(system, user)


def _repair_api(
    ir: IntermediateRepresentation,
    db_schema: dict,
    api_schema: dict,
    errors: list
) -> dict:
    system = """You are fixing errors in an API schema.
Output ONLY a JSON object with an "endpoints" key containing a list of endpoint objects.
No explanation, no markdown, no backticks.
Fix ONLY the listed errors. Do not change anything else."""

    user = f"""Current API schema:
{json.dumps(api_schema, indent=2)}

DB schema (source of truth for table/column names):
{json.dumps(db_schema, indent=2)}

Errors to fix:
{json.dumps(errors, indent=2)}

Output the complete corrected API schema JSON only. Must have top-level key "endpoints"."""

    return call_llm(system, user)


def _repair_rbac(
    ir: IntermediateRepresentation,
    api_schema: dict,
    rbac: dict,
    errors: list
) -> dict:
    system = """You are fixing errors in an RBAC policy schema.
Output ONLY a JSON object with keys: auth_strategy, token_expiry_minutes, refresh_token_expiry_days, policies, route_guards.
No explanation, no markdown, no backticks."""

    user = f"""Current RBAC schema:
{json.dumps(rbac, indent=2)}

API schema (source of truth for endpoint ids):
{json.dumps(api_schema, indent=2)}

Valid role ids: {[r.id for r in ir.roles]}

Errors to fix:
{json.dumps(errors, indent=2)}

Output the complete corrected RBAC schema JSON only.
Must have top-level keys: auth_strategy, policies, route_guards."""

    return call_llm(system, user)