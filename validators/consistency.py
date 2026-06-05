from compiler.ir.models import IntermediateRepresentation


def validate_all(
    ir: IntermediateRepresentation,
    db_schema: dict,
    api_schema: dict,
    rbac: dict
) -> dict:
    """
    Runs all 4 validation layers.
    Returns a report with errors and warnings.
    """
    errors = []
    warnings = []

    errors += _validate_db(ir, db_schema)
    errors += _validate_api(db_schema, api_schema)
    errors += _validate_rbac(ir, api_schema, rbac)
    warnings += _validate_warnings(ir, api_schema)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": f"{len(errors)} errors, {len(warnings)} warnings"
    }


def _validate_db(ir: IntermediateRepresentation, db_schema: dict) -> list:
    errors = []
    db_table_names = {t["name"] for t in db_schema["tables"]}
    ir_entity_ids = {e.id for e in ir.entities}

    # Every IR entity should have a corresponding table
    for entity in ir.entities:
        # Check plural snake_case version exists
        expected_table = entity.id + "s"
        if entity.id not in db_table_names and expected_table not in db_table_names:
            errors.append({
                "layer": "db",
                "type": "missing_table",
                "node": entity.id,
                "message": f"Entity '{entity.id}' has no corresponding DB table",
                "repair_scope": "db"
            })

    # Check FK references resolve
    for table in db_schema["tables"]:
        for col in table["columns"]:
            ref = col.get("references")
            if ref:
                if "(" in ref and ")" in ref:
                    ref_table = ref.split("(")[0]
                else:
                    ref_table = ref.split(".")[0] if "." in ref else ref
                if ref_table not in db_table_names:
                    print("DB TABLES:", db_table_names)
                    print("REF:", ref)
                    print("REF_TABLE:", ref_table)
                    errors.append({
                        "layer": "db",
                        "type": "broken_fk",
                        "node": f"{table['name']}.{col['name']}",
                        "message": f"FK references non-existent table: {ref_table}",
                        "repair_scope": "db"
                    })

    return errors


def _validate_api(db_schema: dict, api_schema: dict) -> list:
    errors = []
    db_tables = {t["name"]: {c["name"] for c in t["columns"]} for t in db_schema["tables"]}

    # Debug: print every table's columns so column-loss is immediately visible
    for tname, cols in db_tables.items():
        print(f"  [consistency] table '{tname}' columns: {sorted(cols)}")

    for endpoint in api_schema["endpoints"]:
        # ── Guard: ensure endpoint has an id before any access ───────────────
        # After repair, qwen2.5:3b may return endpoint objects without "id".
        # Synthesize one from method+path so validation can continue.
        if "id" not in endpoint:
            method = endpoint.get("method", "UNKNOWN").lower()
            path = endpoint.get("path", "unknown").replace("/", "_").strip("_")
            endpoint["id"] = f"ep_{method}_{path}"
            print(f"  [consistency] WARNING: endpoint missing 'id' — assigned synthetic id '{endpoint['id']}'")

        ep_id = endpoint["id"]
        table_name = endpoint.get("table")

        # Table must exist
        if table_name not in db_tables:
            errors.append({
                "layer": "api",
                "type": "missing_table_ref",
                "node": ep_id,
                "message": f"Endpoint '{ep_id}' references unknown table '{table_name}'",
                "repair_scope": "api"
            })
            continue

        table_cols = db_tables[table_name]

        # Response fields must exist as columns
        for field in endpoint.get("response_fields", []):
            if field not in table_cols:
                errors.append({
                    "layer": "api",
                    "type": "missing_column_ref",
                    "node": ep_id,
                    "message": f"Endpoint '{ep_id}' response_field '{field}' not in table '{table_name}'",
                    "repair_scope": "api"
                })

        # Request fields must exist as columns
        for field in endpoint.get("request_fields", []):
            if field not in table_cols:
                errors.append({
                    "layer": "api",
                    "type": "missing_column_ref",
                    "node": ep_id,
                    "message": f"Endpoint '{ep_id}' request_field '{field}' not in table '{table_name}'",
                    "repair_scope": "api"
                })

    return errors


def _validate_rbac(ir: IntermediateRepresentation, api_schema: dict, rbac: dict) -> list:
    errors = []
    ir_role_ids = {r.id for r in ir.roles}
    api_endpoint_ids = {ep["id"] for ep in api_schema["endpoints"]}
    covered_endpoints = {p["endpoint_id"] for p in rbac.get("policies", [])}

    # Every endpoint must have at least one policy
    for ep_id in api_endpoint_ids:
        if ep_id not in covered_endpoints:
            errors.append({
                "layer": "rbac",
                "type": "uncovered_endpoint",
                "node": ep_id,
                "message": f"Endpoint '{ep_id}' has no RBAC policy",
                "repair_scope": "rbac"
            })

    # Every policy role must be a real role
    for policy in rbac.get("policies", []):
        if policy["role_id"] not in ir_role_ids:
            errors.append({
                "layer": "rbac",
                "type": "unknown_role",
                "node": policy["id"],
                "message": f"Policy references unknown role: {policy['role_id']}",
                "repair_scope": "rbac"
            })

    return errors


def _validate_warnings(ir: IntermediateRepresentation, api_schema: dict) -> list:
    warnings = []

    # Warn if no authentication endpoint exists
    auth_paths = [ep["path"] for ep in api_schema["endpoints"] if "login" in ep["path"] or "auth" in ep["path"]]
    if not auth_paths:
        warnings.append({
            "layer": "api",
            "type": "missing_auth_endpoint",
            "message": "No login/auth endpoint found in API schema"
        })

    return warnings