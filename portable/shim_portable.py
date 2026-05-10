import os
import sys
from pathlib import Path

import uvicorn


def resolve_port() -> int:
    raw = os.getenv("SHIM_PORT", "8000").strip()
    try:
        port = int(raw)
    except ValueError:
        return 8000
    if 1 <= port <= 65535:
        return port
    return 8000


def main():
    if getattr(sys, "frozen", False):
        runtime_base = Path(sys.executable).resolve().parent / "_internal"
        if str(runtime_base) not in sys.path:
            sys.path.insert(0, str(runtime_base))
        if not os.getenv("SHIM_RUNTIME_BASE"):
            os.environ["SHIM_RUNTIME_BASE"] = str(runtime_base)

    # Import app object directly to avoid ambiguous module-string resolution.
    from src.app.main import app as fastapi_app

    uvicorn.run(fastapi_app, host="0.0.0.0", port=resolve_port(), reload=False)


if __name__ == "__main__":
    main()
