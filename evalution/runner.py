import json
import time
import traceback
from pathlib import Path

TEST_PROMPTS = [
    {
        "id": "crm",
        "category": "standard",
        "prompt": "Build a CRM with login, contacts, dashboard, role-based access, and premium plan with payments. Admins can see analytics."
    },
    {
        "id": "project_tracker",
        "category": "standard",
        "prompt": "Build a project management tool with tasks, team members, kanban board, and admin dashboard."
    },
    {
        "id": "ecommerce",
        "category": "standard",
        "prompt": "Build an e-commerce store with products, shopping cart, checkout, order history, and admin product management."
    },
    {
        "id": "hr_system",
        "category": "standard",
        "prompt": "Build an HR system with employee profiles, leave requests, manager approvals, and payroll overview."
    },
    {
        "id": "lms",
        "category": "standard",
        "prompt": "Build a learning management system with courses, video lessons, quizzes, and student progress tracking."
    },
    # Edge cases
    {
        "id": "vague",
        "category": "edge_case",
        "prompt": "Build an app for my business."
    },
    {
        "id": "incomplete",
        "category": "edge_case",
        "prompt": "Add payments and user management."
    },
    {
        "id": "implicit_rbac",
        "category": "edge_case",
        "prompt": "Build a dashboard where admins can see everything."
    },
    {
        "id": "complex",
        "category": "edge_case",
        "prompt": "Build a multi-tenant SaaS with organization isolation, per-org billing, SSO login, and a super-admin who can manage all orgs."
    },
    {
        "id": "iot",
        "category": "edge_case",
        "prompt": "Build an IoT dashboard with device telemetry, real-time alerts, time-series charts, and device management."
    }
]


def run_evaluation(prompts: list = None, output_file: str = "evaluation/results.json"):
    from compiler.orchestrator import compile_app

    if prompts is None:
        prompts = TEST_PROMPTS

    results = []
    passed = 0
    failed = 0

    print(f"\nRunning evaluation on {len(prompts)} prompts...\n")
    print(f"{'ID':<20} {'Category':<12} {'Status':<10} {'Time':<8} {'Errors':<8} {'Warnings'}")
    print("-" * 75)

    for test in prompts:
        start = time.time()
        try:
            config = compile_app(test["prompt"], verbose=False)
            elapsed = round(time.time() - start, 1)
            errors = len(config["validation_report"]["errors"])
            warnings = len(config["validation_report"]["warnings"])
            status = "✓ PASS" if errors == 0 else "⚠ WARN"
            if errors == 0:
                passed += 1
            else:
                failed += 1

            results.append({
                "id": test["id"],
                "category": test["category"],
                "status": "pass" if errors == 0 else "warn",
                "elapsed_s": elapsed,
                "errors": errors,
                "warnings": warnings,
                "tables": len(config["db_schema"]["tables"]),
                "endpoints": len(config["api_schema"]["endpoints"]),
                "policies": len(config["rbac"]["policies"]),
            })

        except Exception as e:
            elapsed = round(time.time() - start, 1)
            failed += 1
            results.append({
                "id": test["id"],
                "category": test["category"],
                "status": "fail",
                "elapsed_s": elapsed,
                "errors": -1,
                "warnings": 0,
                "error_detail": str(e)[:200]
            })
            status = "✗ FAIL"
            errors = "N/A"
            warnings = "N/A"

        r = results[-1]
        print(f"{test['id']:<20} {test['category']:<12} {status:<10} {r['elapsed_s']:<8} {str(r['errors']):<8} {r.get('warnings', 0)}")

    # Summary
    total = len(prompts)
    success_rate = round(passed / total * 100, 1)
    avg_time = round(sum(r["elapsed_s"] for r in results) / total, 1)

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate_pct": success_rate,
        "avg_latency_s": avg_time,
        "results": results
    }

    print(f"\n{'─' * 75}")
    print(f"Success rate: {success_rate}% ({passed}/{total})")
    print(f"Avg latency:  {avg_time}s")

    Path(output_file).parent.mkdir(exist_ok=True)
    Path(output_file).write_text(json.dumps(summary, indent=2))
    print(f"Results saved to {output_file}")

    return summary


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_evaluation()
