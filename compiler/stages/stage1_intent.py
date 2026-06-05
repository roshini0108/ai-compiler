import json
from compiler.llm import call_llm
from compiler.ir.models import IntentModel

SYSTEM_PROMPT = """You are an Intent Extraction Compiler.

Your job is to extract structured intent from a natural language product description.

Rules:
- Output ONLY a raw JSON object.
- No markdown. No explanation. No backticks.

ENTITY RULES:
- Entities are persistent business data objects that are stored in a database.
- Examples: User, Contact, Order, Product, Invoice, Payment, Subscription.
- NEVER classify pages, screens, dashboards, authentication flows, analytics, reports, or permissions as entities.
- Login is NOT an entity. Dashboard is NOT an entity. Analytics is NOT an entity. Role-based access is NOT an entity.

INFERENCE RULES (always apply these):
- If "login" or "authentication" is mentioned → always add "User" to entities.
- If "payments" or "billing" is mentioned → always add "Payment" to entities.
- If "premium plan" or "subscription" is mentioned → always add "Subscription" to entities.
- If "contacts" is mentioned → always add "Contact" to entities.
- If "admin" role is mentioned → always add "user" to roles (regular user role).

FEATURE RULES:
- Login is a feature. Dashboard is a feature. Analytics is a feature.
- Role-based access is a feature. Reporting is a feature.

INTEGRATION RULES:
- Payments should be an integration.
- Stripe, Razorpay, PayPal, etc. are integrations.

PLANS:
- Extract pricing plans such as free, premium, enterprise.

Output exactly this structure with plain strings in every array (no nested objects):

{
  "entities": ["User", "Contact"],
  "features": ["login", "dashboard"],
  "roles": ["admin", "user"],
  "integrations": ["payments"],
  "constraints": [],
  "plans": ["premium"]
}
"""

# Every key IntentModel expects, with a safe empty default.
_INTENT_DEFAULTS = {
    "entities": [],
    "features": [],
    "roles": [],
    "integrations": [],
    "constraints": [],
    "plans": [],
}

# ── Inference rules applied in post-processing ────────────────────────────────
# These catch what qwen2.5:3b fails to infer from the prompt.
# Key = trigger string to look for in features/integrations/plans (lowercase).
# Value = dict of what to inject into which list if not already present.
_INFERENCE_RULES = [
    # trigger_list, trigger_value,   inject_list,    inject_value
    ("features",     "login",        "entities",     "User"),
    ("features",     "dashboard",    "features",     "dashboard"),
    ("integrations", "payments",     "entities",     "Payment"),
    ("integrations", "payments",     "entities",     "Subscription"),
    ("plans",        None,           "entities",     "Subscription"),  # any plan → Subscription
]


def extract_intent(prompt: str) -> IntentModel:
    data = call_llm(SYSTEM_PROMPT, f"Extract intent from: {prompt}")

    data = _unwrap_if_nested(data)

    for key, default in _INTENT_DEFAULTS.items():
        if key not in data:
            print(f"  ⚠ Stage 1: model omitted '{key}', defaulting to {default}")
            data[key] = default
        elif not isinstance(data[key], list):
            print(f"  ⚠ Stage 1: '{key}' was not a list (got {type(data[key]).__name__}), coercing")
            val = data[key]
            data[key] = list(val) if hasattr(val, "__iter__") and not isinstance(val, str) else [val]

        # Flatten list-of-dicts → list-of-strings (qwen2.5:3b returns structured items)
        data[key] = _flatten_string_list(data[key], key)

    # ── Apply inference rules to fill in what the model missed ───────────────
    data = _apply_inference_rules(data)

    return IntentModel(**data)


def _apply_inference_rules(data: dict) -> dict:
    """
    Injects implied entities/features that qwen2.5:3b consistently misses.

    Rules:
    - login feature   → User entity must exist
    - payments integration → Payment + Subscription entities must exist
    - any plan defined → Subscription entity must exist
    """
    def _contains(lst, value):
        return any(v.lower() == value.lower() for v in lst)

    def _add_if_missing(lst_name, value):
        if not _contains(data[lst_name], value):
            print(f"  ℹ Stage 1 inference: adding '{value}' to '{lst_name}'")
            data[lst_name].append(value)

    features_lower    = [f.lower() for f in data.get("features", [])]
    integrations_lower = [i.lower() for i in data.get("integrations", [])]
    plans             = data.get("plans", [])

    if "login" in features_lower or "authentication" in features_lower:
        _add_if_missing("entities", "User")

    if any("payment" in i for i in integrations_lower):
        _add_if_missing("entities", "Payment")
        _add_if_missing("entities", "Subscription")

    if plans:
        _add_if_missing("entities", "Subscription")

    # Always ensure both admin + user roles exist when admin is mentioned
    roles_lower = [r.lower() for r in data.get("roles", [])]
    if "admin" in roles_lower:
        _add_if_missing("roles", "user")

    return data


def _flatten_string_list(items: list, key: str) -> list:
    """
    Converts a list of dicts to a list of strings.
    qwen2.5:3b returns [{"entity": "Contact"}] instead of ["Contact"].
    """
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            extracted = next(
                (v for v in item.values() if isinstance(v, str) and v.strip()),
                None,
            )
            if extracted:
                print(f"  ⚠ Stage 1: '{key}' item was dict {item} → extracted '{extracted}'")
                result.append(extracted)
            else:
                print(f"  ⚠ Stage 1: '{key}' item was dict with no string value: {item} — skipping")
        else:
            result.append(str(item))
    return result


def _unwrap_if_nested(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            print(f"  ⚠ Stage 1: unwrapping nested key '{next(iter(data.keys()))}'")
            return inner
    return data


if __name__ == "__main__":
    test_prompt = "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
    result = extract_intent(test_prompt)
    print("Stage 1 output:")
    print(result.model_dump_json(indent=2))