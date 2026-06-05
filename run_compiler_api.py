from pathlib import Path

import uvicorn


ROOT = Path(__file__).parent


if __name__ == "__main__":
    uvicorn.run(
        "compiler_api:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[
            str(ROOT / "compiler"),
            str(ROOT / "validators"),
            str(ROOT / "repair_engine"),
            str(ROOT / "runtime"),
        ],
        reload_excludes=[
            "output/*",
            "output/**/*",
            "frontend/node_modules/*",
            "frontend/dist/*",
            "venv/*",
            "__pycache__/*",
        ],
    )
