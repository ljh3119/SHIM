import os
import sys
from pathlib import Path
import socket
import webbrowser
from threading import Timer

import uvicorn


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def resolve_port() -> int:
    raw = os.getenv("SHIM_PORT", "8000").strip()
    try:
        preferred_port = int(raw)
    except ValueError:
        preferred_port = 8000
    if not (1 <= preferred_port <= 65535):
        preferred_port = 8000

    # Auto-detect available port starting from preferred_port
    port = preferred_port
    max_port = port + 100
    while port <= max_port:
        if not is_port_in_use(port):
            return port
        port += 1

    return preferred_port


def main():
    if getattr(sys, "frozen", False):
        runtime_base = Path(sys.executable).resolve().parent / "_internal"
        if str(runtime_base) not in sys.path:
            sys.path.insert(0, str(runtime_base))
        if not os.getenv("SHIM_RUNTIME_BASE"):
            os.environ["SHIM_RUNTIME_BASE"] = str(runtime_base)

    # Resolve port with auto-detection
    port = resolve_port()
    os.environ["SHIM_PORT"] = str(port)

    # Automatic browser launch for portable executable
    if getattr(sys, "frozen", False):
        def open_browser():
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception as e:
                print(f"[PORTABLE] Failed to open browser: {e}")
        Timer(1.5, open_browser).start()

    # Import app object directly to avoid ambiguous module-string resolution.
    from src.app.main import app as fastapi_app

    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, reload=False)



if __name__ == "__main__":
    main()
