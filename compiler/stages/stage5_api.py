import json
from compiler.llm import call_llm
from compiler.ir.models import IntermediateRepresentation

SYSTEM_PROMPT = """You are an API Schema Compiler.
You receive an IR and database schema, and produce a complete REST API schema.

Rules:
- Output ONLY a raw JSON object. No explanation, no markdown, no backticks.
- Generate CRUD endpoints for every entity (GET list, GET by id, POST, PUT, DELETE).
- Every endpoint "table" field must exactly match a table name from db_schema.
- request_fields and response_fields must exactly match column names from that table.
- required_roles must exactly match role ids from the IR.
- Paths use kebab-case plural nouns e.g. /contacts, /users.

Output this exact JSON structure:
{
  "endpoints": [
    {
      "id": "unique_endpoint_id",
      "method": "GET|POST|PUT|PATCH|DELETE",
      "path": "/resource/{id}",
      "description": "what this endpoint does",
      "table": "db_table_name",
      "required_roles": ["role_id"],
      "request_fields": ["column_name"],
      "response_fields": ["column_name"],
      "auth_required": true
    }
  ]
}"""


def generate_api_schema(ir: IntermediateRepresentation, db_schema: dict) -> dict:
    payload = json.dumps({
        "ir": json.loads(ir.model_dump_json()),
        "db_schema": db_schema
    }, indent=2)

    api_schema = call_llm(SYSTEM_PROMPT, f"Generate API schema:\n{payload}")

    # ── Defensive: unwrap if nested ───────────────────────────────────────
    api_schema = _unwrap_to_endpoints(api_schema)

    if "endpoints" not in api_schema:
        print("  ⚠ Stage 5: 'endpoints' key missing — inserting empty list")
        api_schema["endpoints"] = []

    if not api_schema["endpoints"]:
        print("  ⚠ Stage 5: API schema has no endpoints")

    # ── Defensive: normalize endpoints + fix table name mismatches ────────
    db_tables = {t["name"] for t in db_schema.get("tables", [])}
    # Build a singular→plural map for auto-correction
    # e.g. model writes "user" but table is "users"
    singular_to_plural = {t.rstrip("s"): t for t in db_tables}
    singular_to_plural.update({t: t for t in db_tables})  # exact match wins

    valid_role_ids = {r["id"] for r in json.loads(ir.model_dump_json()).get("roles", [])}

    seen_ids: set[str] = set()
    for ep in api_schema["endpoints"]:
        # ── Guarantee every endpoint has a stable id ──────────────────────────
        # Build from method + path if missing; deduplicate with a counter suffix.
        if not ep.get("id"):
            method = ep.get("method", "GET").lower()
            path = ep.get("path", "").strip("/").replace("/", "-").replace("{", "").replace("}", "")
            base_id = f"{path}-{method}" if path else f"ep-{method}-unnamed"
            candidate = base_id
            counter = 2
            while candidate in seen_ids:
                candidate = f"{base_id}-{counter}"
                counter += 1
            ep["id"] = candidate
            print(f"  ⚠ Stage 5: endpoint missing 'id' — assigned '{ep['id']}'")
        seen_ids.add(ep["id"])
        ep.setdefault("required_roles", [])
        ep.setdefault("request_fields", [])
        ep.setdefault("response_fields", [])
        ep.setdefault("auth_required", True)

        # Auto-correct table name: if not in db_tables, try singular→plural
        table = ep.get("table", "")
        if table not in db_tables:
            corrected = singular_to_plural.get(table)
            if corrected:
                print(f"  ⚠ Stage 5: endpoint '{ep['id']}' table '{table}' → auto-corrected to '{corrected}'")
                ep["table"] = corrected
            else:
                print(f"  ⚠ Stage 5: endpoint '{ep['id']}' references unknown table '{table}' (no correction found)")

        # Warn about unknown roles (don't crash)
        for role in ep.get("required_roles", []):
            if role not in valid_role_ids:
                print(f"  ⚠ Stage 5: endpoint '{ep['id']}' uses unknown role '{role}'")

    return api_schema


def _unwrap_to_endpoints(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    if "endpoints" in data:
        return data
    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict) and "endpoints" in inner:
            print(f"  ⚠ Stage 5: unwrapping nested key '{next(iter(data.keys()))}'")
            return inner
    return data


if __name__ == "__main__":
    from compiler.stages.stage1_intent import extract_intent
    from compiler.stages.stage2_domain import build_domain
    from compiler.stages.stage4_db import generate_db_schema

    prompt = "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
    intent = extract_intent(prompt)
    ir = build_domain(intent)
    db = generate_db_schema(ir)
    api = generate_api_schema(ir, db)
    print("Stage 5 output:")
    print(json.dumps(api, indent=2))