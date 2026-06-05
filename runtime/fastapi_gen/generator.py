import os
import json
from pathlib import Path
from jinja2 import Template

OUTPUT_DIR = Path("output")

MAIN_TEMPLATE = """from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

app = FastAPI(title="{{ app_name }} API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

{% for router in routers %}
from routes.{{ router }} import router as {{ router }}_router
app.include_router({{ router }}_router, prefix="/api/v1")
{% endfor %}

@app.get("/health")
def health():
    return {"status": "ok", "app": "{{ app_name }}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

ROUTE_TEMPLATE = """from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import uuid
from datetime import datetime

router = APIRouter(tags=["{{ tag }}"])

# ── Request/Response Models ──────────────────────────────────────────────────

class {{ entity_name }}Base(BaseModel):
{% for field in fields %}    {{ field.name }}: {{ field.py_type }}{% if not field.required %} = None{% endif %}
{% endfor %}

class {{ entity_name }}Response({{ entity_name }}Base):
    id: str
    created_at: datetime

# ── In-memory store (replace with real DB) ──────────────────────────────────

_store: List[dict] = []

# ── Routes ───────────────────────────────────────────────────────────────────

{% for endpoint in endpoints %}
@router.{{ endpoint.method_lower }}("{{ endpoint.path }}")
def {{ endpoint.function_name }}({% if endpoint.has_body %}data: {{ entity_name }}Base, {% endif %}{% if endpoint.has_id %}id: str, {% endif %}):
    \"\"\"{{ endpoint.description }}\"\"\"
{% if endpoint.method == "GET" and not endpoint.has_id %}
    return {"data": _store, "count": len(_store)}
{% elif endpoint.method == "GET" and endpoint.has_id %}
    item = next((x for x in _store if x.get("id") == id), None)
    if not item:
        raise HTTPException(status_code=404, detail="{{ entity_name }} not found")
    return item
{% elif endpoint.method == "POST" %}
    item = data.model_dump()
    item["id"] = str(uuid.uuid4())
    item["created_at"] = datetime.utcnow().isoformat()
    _store.append(item)
    return item
{% elif endpoint.method in ["PUT", "PATCH"] %}
    item = next((x for x in _store if x.get("id") == id), None)
    if not item:
        raise HTTPException(status_code=404, detail="{{ entity_name }} not found")
    item.update(data.model_dump(exclude_unset=True))
    return item
{% elif endpoint.method == "DELETE" %}
    global _store
    _store = [x for x in _store if x.get("id") != id]
    return {"deleted": id}
{% endif %}

{% endfor %}
"""

MODELS_TEMPLATE = """from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

{% for table in tables %}
class {{ table.class_name }}(Base):
    __tablename__ = "{{ table.name }}"

{% for col in table.columns %}    {{ col.name }} = Column({{ col.sa_type }}{% if col.primary %}, primary_key=True, default=lambda: str(uuid.uuid4()){% endif %}{% if col.unique %}, unique=True{% endif %}{% if not col.nullable and not col.primary %}, nullable=False{% endif %}{% if col.default %}, default={{ col.default }}{% endif %})
{% endfor %}

{% endfor %}
"""

PG_TYPE_MAP = {
    "UUID": "UUID(as_uuid=False)",
    "VARCHAR(255)": "String(255)",
    "TEXT": "Text",
    "INTEGER": "Integer",
    "FLOAT": "Float",
    "BOOLEAN": "Boolean",
    "TIMESTAMP": "DateTime(timezone=True), server_default=func.now()",
    "JSONB": "Text",
}

PY_TYPE_MAP = {
    "UUID": "str",
    "VARCHAR(255)": "str",
    "TEXT": "str",
    "INTEGER": "int",
    "FLOAT": "float",
    "BOOLEAN": "bool",
    "TIMESTAMP": "str",
    "JSONB": "dict",
}


def generate_fastapi(db_schema: dict, api_schema: dict, rbac: dict, app_name: str = "App"):
    OUTPUT_DIR.mkdir(exist_ok=True)
    routes_dir = OUTPUT_DIR / "routes"
    routes_dir.mkdir(exist_ok=True)

    # Group endpoints by table
    endpoints_by_table = {}
    for ep in api_schema["endpoints"]:
        table = ep.get("table", "unknown")
        endpoints_by_table.setdefault(table, []).append(ep)

    routers = []

    for table_name, endpoints in endpoints_by_table.items():
        # Build entity name (PascalCase singular)
        entity_name = table_name.rstrip("s").replace("_", " ").title().replace(" ", "")
        router_name = table_name.replace("-", "_")
        routers.append(router_name)

        # Get table columns
        table_def = next((t for t in db_schema["tables"] if t["name"] == table_name), None)
        fields = []
        if table_def:
            for col in table_def["columns"]:
                if col.get("primary"):
                    continue
                fields.append({
                    "name": col["name"],
                    "py_type": PY_TYPE_MAP.get(col["pg_type"].split("(")[0].upper(), "str"),
                    "required": not col.get("nullable", True)
                })

        # Build endpoint context
        ep_context = []
        for ep in endpoints:
            has_id = "{id}" in ep["path"]
            ep_context.append({
                "method": ep["method"],
                "method_lower": ep["method"].lower(),
                "path": ep["path"].replace("/api/v1", "").replace(f"/{table_name}", ""),
                "description": ep.get("description", ""),
                "function_name": f"{ep['method'].lower()}_{router_name}{'_by_id' if has_id else ''}",
                "has_body": ep["method"] in ["POST", "PUT", "PATCH"],
                "has_id": has_id,
            })

        # Render route file
        tmpl = Template(ROUTE_TEMPLATE)
        content = tmpl.render(
            tag=table_name,
            entity_name=entity_name,
            fields=fields,
            endpoints=ep_context
        )
        (routes_dir / f"{router_name}.py").write_text(
    content,
    encoding="utf-8"
)
    # Write SQLAlchemy models
    tables_context = []
    for table in db_schema["tables"]:
        class_name = table["name"].rstrip("s").replace("_", " ").title().replace(" ", "")
        cols = []
        for col in table["columns"]:
            pg_base = col["pg_type"].split("(")[0].upper()
            cols.append({
                "name": col["name"],
                "sa_type": PG_TYPE_MAP.get(pg_base, "String(255)"),
                "primary": col.get("primary", False),
                "unique": col.get("unique", False),
                "nullable": col.get("nullable", True),
                "default": col.get("default"),
            })
        tables_context.append({"name": table["name"], "class_name": class_name, "columns": cols})

    models_tmpl = Template(MODELS_TEMPLATE)
    (OUTPUT_DIR / "models.py").write_text(models_tmpl.render(tables=tables_context))

    # Write main.py
    main_tmpl = Template(MAIN_TEMPLATE)
    (OUTPUT_DIR / "main.py").write_text(main_tmpl.render(
        app_name=app_name,
        routers=routers
    ))

    # Write requirements
    (OUTPUT_DIR / "requirements.txt").write_text(
        "fastapi\nuvicorn\npydantic\nsqlalchemy\npsycopg2-binary\npython-dotenv\n"
    )

    # Write __init__ files
    (OUTPUT_DIR / "__init__.py").write_text("")
    (routes_dir / "__init__.py").write_text("")

    print(f"  ✓ Generated FastAPI app in /output/")
    print(f"  ✓ Routes: {routers}")
    print(f"  → Run with: cd output && uvicorn main:app --reload")

    return str(OUTPUT_DIR)
