import json
from compiler.llm import call_llm
from compiler.ir.models import IntermediateRepresentation

SYSTEM_PROMPT = """You are a Database Schema Compiler.
You receive an Intermediate Representation and produce a PostgreSQL database schema.

Rules:
- Output ONLY a raw JSON object. No explanation, no markdown, no backticks.
- Every table must have a primary key column named exactly "id" with "primary": true.
- The primary key column must ALWAYS be named "id", never "user_id", "contact_id", etc.
- All foreign key "references" values must match a table name that exists in the schema.
- Use only these pg_type values: UUID, VARCHAR(255), TEXT, INTEGER, FLOAT, BOOLEAN, TIMESTAMP, JSONB
- Include indexes for foreign key columns.
- Table names must be plural snake_case: users, contacts, payments, subscriptions.

Output this exact JSON structure:
{
  "tables": [
    {
      "name": "users",
      "entity_id": "user",
      "columns": [
        {"name": "id", "pg_type": "UUID", "primary": true, "unique": true, "nullable": false, "default": null, "references": null}
      ],
      "indexes": []
    }
  ],
  "migrations": ["CREATE TABLE users (id UUID PRIMARY KEY, ...);"]
}"""


def generate_db_schema(ir: IntermediateRepresentation) -> dict:
    payload = ir.model_dump_json(indent=2)
    db_schema = call_llm(SYSTEM_PROMPT, f"Generate database schema for this IR:\n{payload}")

    db_schema = _unwrap_to_tables(db_schema)

    if "tables" not in db_schema:
        print("  ⚠ Stage 4: 'tables' key missing — inserting empty list")
        db_schema["tables"] = []
    db_schema.setdefault("migrations", [])

    # ── Normalize tables ──────────────────────────────────────────────────────
    for table in db_schema["tables"]:
        table.setdefault("entity_id", "")
        table.setdefault("columns", [])
        table.setdefault("indexes", [])

        for col in table["columns"]:
            col.setdefault("primary", False)
            col.setdefault("unique", False)
            col.setdefault("nullable", True)
            col.setdefault("default", None)
            col.setdefault("references", None)

        # ── Fix: rename {table}_id PK column to "id" ─────────────────────────
        # qwen2.5:3b names the PK "contact_id", "user_id" etc. instead of "id".
        # This breaks Stage 5 which looks for "id" in response_fields.
        table_singular = table.get("name", "").rstrip("s")  # users→user, contacts→contact
        for col in table["columns"]:
            if col.get("name") == f"{table_singular}_id" and col.get("primary"):
                print(f"  ⚠ Stage 4: renaming PK '{col['name']}' → 'id' in table '{table['name']}'")
                col["name"] = "id"
            # Also catch exact entity_id pattern: contact_id in contacts table
            entity_id = table.get("entity_id", "")
            if col.get("name") == f"{entity_id}_id" and col.get("primary"):
                print(f"  ⚠ Stage 4: renaming PK '{col['name']}' → 'id' in table '{table['name']}'")
                col["name"] = "id"

        # If still no PK, promote the first column named 'id'
        has_pk = any(c.get("primary") for c in table["columns"])
        if not has_pk:
            id_cols = [c for c in table["columns"] if c.get("name") == "id"]
            if id_cols:
                id_cols[0]["primary"] = True
                print(f"  ⚠ Stage 4: promoted 'id' column to PK in table '{table.get('name')}'")
            else:
                print(f"  ⚠ Stage 4: table '{table.get('name')}' still has no PK")

    # ── Sync FK references on model-generated tables ─────────────────────────
    # qwen2.5:3b sets type=uuid + ref_entity on FK fields but never sets
    # "references" on the DB column.  Build a lookup from IR entity fields
    # and patch any column whose name matches a known FK field.
    db_schema = _sync_fk_references(db_schema, ir)

    # ── Ensure every IR entity has a table ───────────────────────────────────
    db_schema = _inject_missing_tables(db_schema, ir)

    # ── Ensure every IR field exists as a column in its table ────────────────
    # LLM sometimes generates a table but drops columns (e.g. users table loses
    # email/password_hash/role).  This pass adds any missing columns back.
    db_schema = _fill_missing_columns(db_schema, ir)

    errors = _validate_db_schema(db_schema)
    if errors:
        print(f"  ⚠ Stage 4: {len(errors)} schema issue(s):")
        for err in errors:
            print(f"    - {err}")

    return db_schema


def _sync_fk_references(db_schema: dict, ir: IntermediateRepresentation) -> dict:
    """
    For model-generated tables, patch missing "references" on FK columns.
    The IR has ref_entity on fields with type uuid/ref — use that to derive
    the referenced table name and set it on the corresponding DB column.
    """
    _PLURALS = {"user": "users", "contact": "contacts",
                "payment": "payments", "subscription": "subscriptions"}

    # Build: entity_id -> {field_id -> referenced_table}
    fk_map: dict[str, dict[str, str]] = {}
    for entity in ir.entities:
        for field in entity.fields:
            ref_entity = getattr(field, "ref_entity", None)
            if ref_entity and field.id not in ("id",):
                ref_table = _PLURALS.get(ref_entity, ref_entity + "s")
                fk_map.setdefault(entity.id, {})[field.id] = ref_table

    # Apply to DB tables
    for table in db_schema["tables"]:
        entity_id = table.get("entity_id", "")
        fks = fk_map.get(entity_id, {})
        for col in table["columns"]:
            col_name = col.get("name", "")
            if col_name in fks and not col.get("references"):
                col["references"] = fks[col_name]
                if col_name not in table.get("indexes", []):
                    table.setdefault("indexes", []).append(col_name)
                print(f"  ℹ Stage 4: set references on {table['name']}.{col_name} → {fks[col_name]}")

    return db_schema


def _inject_missing_tables(db_schema: dict, ir: IntermediateRepresentation) -> dict:
    """
    For every entity in the IR, ensure a table exists.
    If the model skipped an entity, inject a minimal table.
    """
    existing = {t["name"] for t in db_schema["tables"]}
    # Also index by entity_id
    existing_by_entity = {t.get("entity_id", "") for t in db_schema["tables"]}

    for entity in ir.entities:
        plural_name = entity.id.rstrip("s") + "s" if not entity.id.endswith("s") else entity.id
        # Handle irregular plurals
        _PLURALS = {"payment": "payments", "subscription": "subscriptions",
                    "user": "users", "contact": "contacts"}
        plural_name = _PLURALS.get(entity.id, plural_name)

        if plural_name not in existing and entity.id not in existing_by_entity:
            print(f"  ℹ Stage 4 injection: adding missing table '{plural_name}' for entity '{entity.id}'")
            columns = [
                {"name": "id", "pg_type": "UUID", "primary": True, "unique": True, "nullable": False, "default": None, "references": None},
                {"name": "created_at", "pg_type": "TIMESTAMP", "primary": False, "unique": False, "nullable": False, "default": None, "references": None},
            ]
            # Add entity fields as columns
            for field in entity.fields:
                if field.id in ("id", "created_at"):
                    continue
                pg_type = _map_type(field.type)
                ref = None
                # Detect FK: type is "ref" OR type is "uuid" with a ref_entity set
                ref_entity = getattr(field, "ref_entity", None)
                is_fk = field.type == "ref" or (field.type == "uuid" and ref_entity)
                if is_fk and ref_entity:
                    _PLURALS2 = {"user": "users", "contact": "contacts", "payment": "payments", "subscription": "subscriptions"}
                    ref = _PLURALS2.get(ref_entity, ref_entity + "s")
                    pg_type = "UUID"  # FKs are always UUID
                columns.append({
                    "name": field.id,
                    "pg_type": pg_type,
                    "primary": False,
                    "unique": getattr(field, "unique", False),
                    "nullable": not getattr(field, "required", True),
                    "default": getattr(field, "default", None),
                    "references": ref,
                })
            db_schema["tables"].append({
                "name": plural_name,
                "entity_id": entity.id,
                "columns": columns,
                "indexes": [c["name"] for c in columns if c.get("references")],
            })
            existing.add(plural_name)

    return db_schema


def _fill_missing_columns(db_schema: dict, ir: IntermediateRepresentation) -> dict:
    """
    For each IR entity, ensure its fields exist as columns in the corresponding table.
    This repairs the case where the LLM generates a table but silently drops columns.
    Only *adds* columns — never removes or modifies existing ones.
    """
    _PLURALS = {"payment": "payments", "subscription": "subscriptions",
                "user": "users", "contact": "contacts"}

    # Build a lookup: table_name -> table dict (mutable reference)
    table_by_name = {t["name"]: t for t in db_schema["tables"]}
    # Also index by entity_id for tables the LLM named correctly
    table_by_entity = {t.get("entity_id", ""): t for t in db_schema["tables"] if t.get("entity_id")}

    for entity in ir.entities:
        plural_name = _PLURALS.get(entity.id, entity.id.rstrip("s") + "s")
        table = table_by_name.get(plural_name) or table_by_entity.get(entity.id)
        if not table:
            continue  # _inject_missing_tables already handles fully absent tables

        existing_col_names = {c["name"] for c in table["columns"]}

        for field in entity.fields:
            if field.id in existing_col_names:
                continue  # already present, leave it alone

            pg_type = _map_type(field.type)
            ref = None
            ref_entity = getattr(field, "ref_entity", None)
            is_fk = field.type == "ref" or (field.type == "uuid" and ref_entity)
            if is_fk and ref_entity:
                ref = _PLURALS.get(ref_entity, ref_entity + "s")
                pg_type = "UUID"

            new_col = {
                "name": field.id,
                "pg_type": pg_type,
                "primary": field.id == "id",
                "unique": getattr(field, "unique", False),
                "nullable": not getattr(field, "required", True),
                "default": getattr(field, "default", None),
                "references": ref,
            }
            table["columns"].append(new_col)
            if ref and field.id not in table.get("indexes", []):
                table.setdefault("indexes", []).append(field.id)
            print(f"  ℹ Stage 4 fill: added missing column '{field.id}' to table '{table['name']}'")

    return db_schema


def _map_type(field_type: str) -> str:
    return {
        "uuid": "UUID", "string": "VARCHAR(255)", "email": "VARCHAR(255)",
        "text": "TEXT", "int": "INTEGER", "integer": "INTEGER",
        "float": "FLOAT", "boolean": "BOOLEAN", "bool": "BOOLEAN",
        "datetime": "TIMESTAMP", "date": "TIMESTAMP", "ref": "UUID",
        "json": "JSONB",
    }.get(field_type.lower(), "VARCHAR(255)")


def _unwrap_to_tables(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    if "tables" in data:
        return data
    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict) and "tables" in inner:
            print(f"  ⚠ Stage 4: unwrapping nested key '{next(iter(data.keys()))}'")
            return inner
    return data


def _validate_db_schema(db_schema: dict) -> list:
    errors = []
    table_names = {t["name"] for t in db_schema.get("tables", [])}
    if not db_schema.get("tables"):
        errors.append("DB schema has no tables")
        return errors
    for table in db_schema["tables"]:
        name = table.get("name", "<unnamed>")
        if not table.get("columns"):
            errors.append(f"Table '{name}' has no columns")
            continue
        if not any(c.get("primary") for c in table["columns"]):
            errors.append(f"Table '{name}' has no primary key")
        for col in table["columns"]:
            ref = col.get("references")
            if ref and ref not in table_names:
                errors.append(f"Table '{name}'.'{col.get('name')}' references unknown table '{ref}'")
    return errors


if __name__ == "__main__":
    from compiler.stages.stage1_intent import extract_intent
    from compiler.stages.stage2_domain import build_domain

    prompt = "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
    intent = extract_intent(prompt)
    ir = build_domain(intent)
    db = generate_db_schema(ir)
    print("Stage 4 output:")
    print(json.dumps(db, indent=2))