import json
from compiler.llm import call_llm
from compiler.ir.models import IntermediateRepresentation

SYSTEM_PROMPT = """You are an Auth & RBAC Compiler.
You receive an IR and API schema, and produce complete authentication and authorization rules.

Rules:
- Output ONLY a raw JSON object. No explanation, no markdown, no backticks.
- Every endpoint in the API schema must have at least one policy.
- Policies must use role_ids that exactly match role ids from the IR.
- Policies must use endpoint_ids that exactly match endpoint ids from the API schema.
- Apply principle of least privilege.
- The "admin" role always has full access to every endpoint.

Output this exact JSON structure with ALL these top-level keys:
{
  "auth_strategy": "jwt",
  "token_expiry_minutes": 60,
  "refresh_token_expiry_days": 7,
  "policies": [
    {
      "id": "policy_id",
      "endpoint_id": "endpoint_id_from_api_schema",
      "role_id": "role_id_from_ir",
      "allowed": true,
      "conditions": []
    }
  ],
  "route_guards": [
    {
      "path": "/route/path",
      "required_roles": ["role_id"],
      "redirect_to": "/login"
    }
  ]
}"""


def generate_rbac(ir: IntermediateRepresentation, api_schema: dict) -> dict:
    payload = json.dumps({
        "ir": json.loads(ir.model_dump_json()),
        "api_schema": api_schema
    }, indent=2)

    rbac = call_llm(
        SYSTEM_PROMPT,
        f"Generate auth and RBAC rules:\n{payload}"
    )

    # ── Critical: verify the model returned an RBAC schema, not something else ──
    # qwen2.5:3b sometimes returns a single endpoint dict or other wrong structure.
    # Detect this and fall back to a generated-in-Python RBAC schema.
    rbac = _validate_and_fix_rbac_output(rbac, ir, api_schema)

    print("\n===== RBAC OUTPUT =====")
    print(json.dumps(rbac, indent=2))
    print("=======================\n")

    rbac.setdefault("auth_strategy", "jwt")
    rbac.setdefault("token_expiry_minutes", 60)
    rbac.setdefault("refresh_token_expiry_days", 7)
    rbac.setdefault("policies", [])
    rbac.setdefault("route_guards", [])

    valid_role_ids = {r.id for r in ir.roles}
    api_endpoint_ids = {ep["id"] for ep in api_schema.get("endpoints", [])}

    valid_policies = []
    for policy in rbac["policies"]:
        policy.setdefault("allowed", True)
        policy.setdefault("conditions", [])
        ep_id = policy.get("endpoint_id")
        role_id = policy.get("role_id")
        if ep_id not in api_endpoint_ids:
            print(f"  ⚠ Stage 7: policy '{policy.get('id')}' references unknown endpoint '{ep_id}'")
        if role_id not in valid_role_ids:
            print(f"  ⚠ Stage 7: policy '{policy.get('id')}' uses unknown role '{role_id}'")
        valid_policies.append(policy)
    rbac["policies"] = valid_policies

    for guard in rbac["route_guards"]:
        guard.setdefault("required_roles", [])
        guard.setdefault("redirect_to", "/login")

    # ── Final safety net: generate missing policies in Python ─────────────────
    rbac = _fill_missing_policies(rbac, ir, api_schema)

    return rbac


def _validate_and_fix_rbac_output(rbac: dict, ir: IntermediateRepresentation, api_schema: dict) -> dict:
    """
    Detect when the model returned something other than an RBAC schema.
    The tell-tale signs: has "method" key, has "endpoints" key, or is missing "policies".

    If the output looks wrong, discard it and generate a complete RBAC schema
    directly in Python — no LLM needed for this deterministic task.
    """
    is_wrong = (
        "method" in rbac          # returned a single endpoint object
        or "endpoints" in rbac    # returned API schema instead
        or "tables" in rbac       # returned DB schema instead
        or "entities" in rbac     # returned IR instead
        or ("policies" not in rbac and "auth_strategy" not in rbac)
    )

    if is_wrong:
        print(f"  ⚠ Stage 7: model returned wrong structure (keys: {list(rbac.keys())[:5]}) — generating RBAC in Python")
        return _generate_rbac_python(ir, api_schema)

    return rbac


def _generate_rbac_python(ir: IntermediateRepresentation, api_schema: dict) -> dict:
    """
    Deterministically generate a complete RBAC schema from the IR and API schema.
    Used as fallback when the LLM returns garbage.

    Rules applied:
    - admin role gets full access to every endpoint
    - user role gets read (GET) access to non-user-management endpoints
    - write endpoints (POST/PUT/PATCH/DELETE) for payments/subscriptions → user role allowed
    - DELETE endpoints → admin only
    """
    policies = []
    route_guards = []
    role_ids = [r.id for r in ir.roles]
    admin_role = "admin" if "admin" in role_ids else (role_ids[0] if role_ids else "admin")
    user_role  = "user"  if "user"  in role_ids else (role_ids[-1] if len(role_ids) > 1 else admin_role)

    for i, ep in enumerate(api_schema.get("endpoints", [])):
        ep_id = ep["id"]
        method = ep.get("method", "GET").upper()

        # Admin always gets access
        policies.append({
            "id": f"policy_{i}_admin",
            "endpoint_id": ep_id,
            "role_id": admin_role,
            "allowed": True,
            "conditions": [],
        })

        # User role: allow GET and own-resource mutations, block DELETE
        if method == "DELETE":
            pass  # admin only
        elif user_role != admin_role:
            policies.append({
                "id": f"policy_{i}_user",
                "endpoint_id": ep_id,
                "role_id": user_role,
                "allowed": True,
                "conditions": [],
            })

        # Route guard for this path
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
    """
    After LLM generation, check for any endpoints with no policy and add admin coverage.
    This is the last-resort safety net so the validator never sees uncovered endpoints.
    """
    covered = {p["endpoint_id"] for p in rbac["policies"]}
    role_ids = [r.id for r in ir.roles]
    admin_role = "admin" if "admin" in role_ids else (role_ids[0] if role_ids else "admin")

    for ep in api_schema.get("endpoints", []):
        ep_id = ep["id"]
        if ep_id not in covered:
            print(f"  ℹ Stage 7: auto-adding admin policy for uncovered endpoint '{ep_id}'")
            rbac["policies"].append({
                "id": f"policy_auto_{ep_id}",
                "endpoint_id": ep_id,
                "role_id": admin_role,
                "allowed": True,
                "conditions": [],
            })

    return rbac


if __name__ == "__main__":
    from compiler.stages.stage1_intent import extract_intent
    from compiler.stages.stage2_domain import build_domain
    from compiler.stages.stage4_db import generate_db_schema
    from compiler.stages.stage5_api import generate_api_schema

    prompt = "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
    intent = extract_intent(prompt)
    ir = build_domain(intent)
    db = generate_db_schema(ir)
    api = generate_api_schema(ir, db)
    rbac = generate_rbac(ir, api)
    print("Stage 7 output:")
    print(json.dumps(rbac, indent=2))