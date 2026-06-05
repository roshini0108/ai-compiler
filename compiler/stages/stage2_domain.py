import json
from compiler.llm import call_llm
from compiler.ir.models import IntentModel, IntermediateRepresentation

SYSTEM_PROMPT = """
You are a Domain Modeling Compiler.

You receive a structured intent and must produce a complete Intermediate Representation (IR).

IMPORTANT RULES:
- Output ONLY valid JSON. No markdown. No explanations. No comments.

ID RULES:
- Entity ids must be meaningful lowercase snake_case: user, contact, payment, subscription
- Role ids must be meaningful: admin, user, manager
- Plan ids must be meaningful: free, premium, enterprise
- NEVER use placeholder ids like snake_case_id, entity_id, role_id

ENTITY RULES:
- Model EVERY entity listed in the intent — do not skip any.
- Every entity MUST have: id (uuid, primary=true), created_at (datetime).
- Foreign keys use type="ref" and specify ref_entity.
- The User entity MUST have: id, email, password_hash, role, created_at.
- The Contact entity MUST have: id, first_name, last_name, email, user_id (ref→user), created_at.
- The Payment entity MUST have: id, user_id (ref→user), amount, currency, status, created_at.
- The Subscription entity MUST have: id, user_id (ref→user), plan_id, status, started_at, expires_at, created_at.

INTEGRATION RULES:
- If integrations includes "payments" or "Payments": model Payment and Subscription entities.
- Payment entity represents a single transaction.
- Subscription entity represents an ongoing plan membership.

FEATURE→PAGE RULES:
- If features includes "dashboard": add a dashboard page to pages[].
- If features includes "analytics": add an analytics page to pages[].
- If features includes "login": add login and register pages to pages[].

Return JSON:

{
  "ir_version": "1.0",
  "app_name": "crm_system",
  "domain": "crm",
  "description": "Customer relationship management application",
  "auth_strategy": "jwt",
  "features": ["login", "contacts", "dashboard", "role_based_access"],
  "entities": [
    {
      "id": "user",
      "name": "User",
      "fields": [
        {"id": "id", "name": "ID", "type": "uuid", "required": true, "unique": true, "primary": true, "default": null, "ref_entity": null},
        {"id": "email", "name": "Email", "type": "email", "required": true, "unique": true, "primary": false, "default": null, "ref_entity": null},
        {"id": "password_hash", "name": "Password Hash", "type": "string", "required": true, "unique": false, "primary": false, "default": null, "ref_entity": null},
        {"id": "role", "name": "Role", "type": "string", "required": true, "unique": false, "primary": false, "default": "user", "ref_entity": null},
        {"id": "created_at", "name": "Created At", "type": "datetime", "required": true, "unique": false, "primary": false, "default": null, "ref_entity": null}
      ],
      "relations": []
    }
  ],
  "roles": [{"id": "admin", "name": "Admin", "description": "System administrator", "inherits": null}],
  "plans": [{"id": "premium", "name": "Premium", "price": 9.99, "payment_required": true, "features": ["advanced_access"]}],
  "business_rules": [{"id": "br_001", "description": "Only admins can delete contacts", "applies_to": "contact", "roles": ["admin"], "condition": "User role is admin", "effect": "Allow delete"}],
  "endpoints": [],
  "pages": [{"id": "dashboard", "name": "Dashboard", "route": "/dashboard", "required_roles": ["admin", "user"]}],
  "permissions": []
}
"""

_IR_DEFAULTS = {
    "ir_version": "1.0",
    "app_name": "generated_app",
    "domain": "general",
    "description": "",
    "auth_strategy": "jwt",
    "features": [],
    "entities": [],
    "roles": [],
    "plans": [],
    "business_rules": [],
    "endpoints": [],
    "pages": [],
    "permissions": [],
}

# Canonical entity templates injected when the model omits a known entity.
# These match what a real CRM needs and what the prompt's rules describe.
_ENTITY_TEMPLATES = {
    "user": {
        "id": "user", "name": "User",
        "fields": [
            {"id": "id",            "name": "ID",            "type": "uuid",     "required": True,  "unique": True,  "primary": True,  "default": None, "ref_entity": None},
            {"id": "email",         "name": "Email",         "type": "email",    "required": True,  "unique": True,  "primary": False, "default": None, "ref_entity": None},
            {"id": "password_hash", "name": "Password Hash", "type": "string",   "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "role",          "name": "Role",          "type": "string",   "required": True,  "unique": False, "primary": False, "default": "user","ref_entity": None},
            {"id": "created_at",    "name": "Created At",    "type": "datetime", "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
        ],
        "relations": [],
    },
    "contact": {
        "id": "contact", "name": "Contact",
        "fields": [
            {"id": "id",         "name": "ID",         "type": "uuid",     "required": True,  "unique": True,  "primary": True,  "default": None, "ref_entity": None},
            {"id": "first_name", "name": "First Name", "type": "string",   "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "last_name",  "name": "Last Name",  "type": "string",   "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "email",      "name": "Email",      "type": "email",    "required": True,  "unique": True,  "primary": False, "default": None, "ref_entity": None},
            {"id": "user_id",    "name": "User ID",    "type": "ref",      "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": "user"},
            {"id": "created_at", "name": "Created At", "type": "datetime", "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
        ],
        "relations": [],
    },
    "payment": {
        "id": "payment", "name": "Payment",
        "fields": [
            {"id": "id",         "name": "ID",         "type": "uuid",     "required": True,  "unique": True,  "primary": True,  "default": None, "ref_entity": None},
            {"id": "user_id",    "name": "User ID",    "type": "ref",      "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": "user"},
            {"id": "amount",     "name": "Amount",     "type": "float",    "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "currency",   "name": "Currency",   "type": "string",   "required": True,  "unique": False, "primary": False, "default": "USD","ref_entity": None},
            {"id": "status",     "name": "Status",     "type": "string",   "required": True,  "unique": False, "primary": False, "default": "pending","ref_entity": None},
            {"id": "created_at", "name": "Created At", "type": "datetime", "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
        ],
        "relations": [],
    },
    "subscription": {
        "id": "subscription", "name": "Subscription",
        "fields": [
            {"id": "id",         "name": "ID",         "type": "uuid",     "required": True,  "unique": True,  "primary": True,  "default": None, "ref_entity": None},
            {"id": "user_id",    "name": "User ID",    "type": "ref",      "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": "user"},
            {"id": "plan_id",    "name": "Plan ID",    "type": "string",   "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "status",     "name": "Status",     "type": "string",   "required": True,  "unique": False, "primary": False, "default": "active","ref_entity": None},
            {"id": "started_at", "name": "Started At", "type": "datetime", "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "expires_at", "name": "Expires At", "type": "datetime", "required": False, "unique": False, "primary": False, "default": None, "ref_entity": None},
            {"id": "created_at", "name": "Created At", "type": "datetime", "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
        ],
        "relations": [],
    },
}


def build_domain(intent: IntentModel) -> IntermediateRepresentation:
    payload = json.dumps(intent.model_dump(), indent=2)

    data = call_llm(
        SYSTEM_PROMPT,
        f"Build the IR for this intent:\n{payload}"
    )

    print("\n===== RAW STAGE 2 OUTPUT =====")
    print(json.dumps(data, indent=2))
    print("================================\n")

    data = _unwrap_if_nested(data)

    # Fill missing top-level keys
    for key, default in _IR_DEFAULTS.items():
        if key not in data:
            print(f"  ⚠ Stage 2: model omitted '{key}', defaulting to {repr(default)}")
            data[key] = default

    # Normalize entity fields
    _FIELD_DEFAULTS = {
        "required": False, "unique": False, "primary": False,
        "default": None, "ref_entity": None,
    }
    # Map non-enum types the model invents to valid IR enum values
    _TYPE_MAP = {
        "decimal": "float", "number": "float", "double": "float",
        "int": "integer", "bool": "boolean",
        "varchar": "string", "char": "string", "str": "string",
        "timestamp": "datetime", "date": "datetime",
        "jsonb": "json", "object": "json", "array": "json",
        "foreign_key": "ref", "fk": "ref",
    }
    for entity in data.get("entities", []):
        for field in entity.get("fields", []):
            for fkey, fdefault in _FIELD_DEFAULTS.items():
                if fkey not in field:
                    field[fkey] = fdefault
            # Coerce non-standard types to valid enum values
            raw_type = field.get("type", "string").lower()
            if raw_type in _TYPE_MAP:
                print(f"  ⚠ Stage 2: field '{field.get('id')}' type '{raw_type}' → '{_TYPE_MAP[raw_type]}'")
                field["type"] = _TYPE_MAP[raw_type]
            # Clear ref_entity if type is not "ref"
            if field.get("type") != "ref" and field.get("ref_entity"):
                field["ref_entity"] = None
        entity.setdefault("relations", [])

    # Normalize pages: rename route→path, ensure path always exists
    for page in data.get("pages", []):
        if "path" not in page and "route" in page:
            page["path"] = page.pop("route")
        elif "path" not in page:
            page["path"] = f"/{page.get('id', 'page')}"
        page.setdefault("required_roles", [])

    # Normalize roles / plans / business_rules
    for role in data.get("roles", []):
        role.setdefault("description", "")
        role.setdefault("inherits", None)
    for plan in data.get("plans", []):
        plan.setdefault("price", 0.0)
        plan.setdefault("payment_required", False)
        plan.setdefault("features", [])
    for rule in data.get("business_rules", []):
        rule.setdefault("applies_to", "")
        rule.setdefault("roles", [])
        rule.setdefault("condition", "")
        rule.setdefault("effect", "")

    # ── Inject missing entities from intent ──────────────────────────────────
    # qwen2.5:3b skips entities that weren't in its few-shot example.
    # We check what Stage 1 extracted and inject canonical templates for any
    # entity the model forgot to model.
    data = _inject_missing_entities(data, intent)

    # ── Inject missing roles ──────────────────────────────────────────────────
    data = _inject_missing_roles(data, intent)

    # ── Inject pages for features the model ignored ───────────────────────────
    data = _inject_missing_pages(data, intent)

    return IntermediateRepresentation(**data)


def _inject_missing_entities(data: dict, intent: IntentModel) -> dict:
    """
    For every entity name in the intent, check if Stage 2 modeled it.
    If not, inject the canonical template (or a minimal stub).
    """
    existing_ids = {e["id"].lower() for e in data.get("entities", [])}

    for entity_name in intent.entities:
        entity_id = entity_name.lower().replace(" ", "_")
        if entity_id not in existing_ids:
            template = _ENTITY_TEMPLATES.get(entity_id)
            if template:
                print(f"  ℹ Stage 2 injection: adding '{entity_id}' entity from template")
                data["entities"].append(json.loads(json.dumps(template)))  # deep copy
            else:
                # Minimal stub for unknown entity types
                stub = {
                    "id": entity_id,
                    "name": entity_name,
                    "fields": [
                        {"id": "id",         "name": "ID",         "type": "uuid",     "required": True,  "unique": True,  "primary": True,  "default": None, "ref_entity": None},
                        {"id": "created_at", "name": "Created At", "type": "datetime", "required": True,  "unique": False, "primary": False, "default": None, "ref_entity": None},
                    ],
                    "relations": [],
                }
                print(f"  ℹ Stage 2 injection: adding '{entity_id}' entity as minimal stub")
                data["entities"].append(stub)
            existing_ids.add(entity_id)

    return data


def _inject_missing_roles(data: dict, intent: IntentModel) -> dict:
    existing_role_ids = {r["id"].lower() for r in data.get("roles", [])}
    for role_name in intent.roles:
        role_id = role_name.lower().replace(" ", "_")
        if role_id not in existing_role_ids:
            print(f"  ℹ Stage 2 injection: adding role '{role_id}'")
            data["roles"].append({
                "id": role_id,
                "name": role_name.capitalize(),
                "description": f"{role_name.capitalize()} role",
                "inherits": None,
            })
            existing_role_ids.add(role_id)
    return data


def _inject_missing_pages(data: dict, intent: IntentModel) -> dict:
    """Add pages for features the model ignored."""
    existing_page_ids = {p["id"].lower() for p in data.get("pages", [])}
    features_lower = [f.lower() for f in intent.features]

    _FEATURE_PAGES = {
        "dashboard":        {"id": "dashboard",  "name": "Dashboard",  "path": "/dashboard",  "required_roles": ["admin", "user"]},
        "analytics":        {"id": "analytics",  "name": "Analytics",  "path": "/analytics",  "required_roles": ["admin"]},
        "login":            {"id": "login",      "name": "Login",      "path": "/login",      "required_roles": []},
        "role-based access":{"id": "rbac",       "name": "Access Control", "path": "/admin/roles", "required_roles": ["admin"]},
    }

    for feature, page in _FEATURE_PAGES.items():
        if feature in features_lower and page["id"] not in existing_page_ids:
            print(f"  ℹ Stage 2 injection: adding page '{page['id']}' for feature '{feature}'")
            data["pages"].append(page)
            existing_page_ids.add(page["id"])

    return data


def _unwrap_if_nested(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            print(f"  ⚠ Stage 2: unwrapping nested key '{next(iter(data.keys()))}'")
            return inner
    return data


if __name__ == "__main__":
    from compiler.stages.stage1_intent import extract_intent

    prompt = (
        "Build a CRM with login, contacts, dashboard, "
        "role-based access, and premium plan with payments. "
        "Admins can see analytics."
    )

    intent = extract_intent(prompt)
    ir = build_domain(intent)

    print("\nEntities:")
    for e in ir.entities:
        print(" -", e.id)

    print("\nRoles:")
    for r in ir.roles:
        print(" -", r.id)

    print("\nPlans:")
    for p in ir.plans:
        print(" -", p.id)

    print("\nPages:")
    for p in ir.pages:
        print(" -", p.id if hasattr(p, "id") else p)