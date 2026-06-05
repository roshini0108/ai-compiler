# AI Application Compiler

> Natural Language → Intermediate Representation → Validated Schemas → Executable Application

A compiler-style LLM pipeline that transforms a plain English product description into a fully validated, running FastAPI application with PostgreSQL schema and RBAC policies.

---

## Demo

```bash
python -m compiler.orchestrator "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
```

Output:
```
============================================================
  AI APPLICATION COMPILER
============================================================

Stage 1/7 ── Intent Extraction...
  ✓ Entities: ['User', 'Contact', 'Plan', 'Payment']
  ✓ Roles:    ['admin', 'manager', 'viewer']
  ✓ Features: ['login', 'contacts', 'dashboard', 'payments', 'analytics']

Stage 2/7 ── Building Intermediate Representation...
  ✓ Entities: ['user', 'contact', 'plan', 'payment']
  ✓ Roles:    ['admin', 'manager', 'viewer']

Stage 4/7 ── Generating Database Schema...
  ✓ Tables: ['users', 'contacts', 'plans', 'payments']

Stage 5/7 ── Generating API Schema...
  ✓ Endpoints: 20 generated

Stage 7/7 ── Generating Auth & RBAC...
  ✓ Policies: 60 generated

Stage 8 ── Cross-Layer Validation...
  ✓ All validation checks passed

Stage 10 ── Generating Executable Application...
  ✓ Generated FastAPI app in /output/

============================================================
  ✓ COMPILATION COMPLETE in 18.3s
  ✓ Server ready: cd output && uvicorn main:app --reload
  ✓ Docs at:      http://localhost:8000/docs
============================================================
```

---

## Architecture

```
NL Prompt
    ↓
Stage 1: Intent Extraction      → IntentModel (entities, roles, features)
    ↓
Stage 2: Domain Understanding   → IntermediateRepresentation (IR)
    ↓
Stage 4: DB Schema Generation   → tables, columns, FKs, indexes
    ↓
Stage 5: API Schema Generation  → endpoints, request/response schemas
    ↓
Stage 7: Auth & RBAC Generation → policies, route guards
    ↓
Stage 8: Cross-Layer Validation → dependency graph, consistency checks
    ↓
Stage 9: Repair Engine          → surgical partial regeneration
    ↓
Stage 10: Runtime Generation    → FastAPI server + SQLAlchemy models
```

---

## Setup

```bash
# 1. Clone and enter
git clone <repo> && cd ai-compiler

# 2. Virtual environment
python -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 5. Start PostgreSQL (optional - required for full runtime)
docker run -d --name aidb -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:15
```

---

## Usage

### Compile a single prompt
```bash
python -m compiler.orchestrator "Your product description here"
```

### Run the generated server
```bash
cd output
pip install -r requirements.txt
uvicorn main:app --reload
# Visit http://localhost:8000/docs
```

### Run evaluation suite
```bash
python -m evaluation.runner
```

---

## Project Structure

```
ai-compiler/
├── compiler/
│   ├── ir/models.py          # Pydantic IR — single source of truth
│   └── stages/
│       ├── stage1_intent.py  # NL → structured intent
│       ├── stage2_domain.py  # Intent → full IR
│       ├── stage4_db.py      # IR → DB schema
│       ├── stage5_api.py     # IR + DB → API schema
│       └── stage7_auth.py    # IR + API → RBAC policies
├── validators/
│   └── consistency.py        # 4-layer cross-layer validator
├── repair_engine/
│   └── regenerator.py        # Surgical partial regeneration
├── runtime/
│   └── fastapi_gen/
│       └── generator.py      # Config → FastAPI server code
├── evaluation/
│   └── runner.py             # 10-prompt evaluation harness
└── output/                   # Generated application (git-ignored)
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| LLM | Claude Sonnet | Best JSON faithfulness, long context |
| Temperature | 0.0 | Deterministic schema generation |
| Generation style | Schema-constrained | Strict system prompt + JSON only |
| Repair strategy | Surgical partial regen | Minimal cost, targeted context |
| IR approach | Typed Pydantic models | Single source of truth for all layers |
| Validation | 4-layer stack | Schema → Consistency → RBAC → Runtime |

---

## Evaluation Results

| Metric | Target | Result |
|---|---|---|
| JSON validity rate | ≥ 95% | TBD after eval run |
| Cross-layer consistency | ≥ 85% | TBD |
| Repair success rate | ≥ 80% | TBD |
| Avg latency | < 30s | TBD |

Run `python -m evaluation.runner` to populate results.

---

## Requirements

- Python 3.11+
- Anthropic API key
- PostgreSQL 15+ (optional, for full runtime)
- Docker (recommended)
