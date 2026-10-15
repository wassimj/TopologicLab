"""Reserve an available loopback port before starting the workspace."""
import os
import socket
from pathlib import Path


def reserve_port(preferred=8017):
    for port in (preferred, 0):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
            listener.setblocking(False)
            return listener
        except OSError as exc:
            listener.close()
            if port == 0 or (exc.errno not in (48, 98, 10048) and getattr(exc, "winerror", None) != 10048):
                raise
    raise RuntimeError("Could not reserve a local port.")


if __name__ == "__main__":
    import uvicorn

    os.environ.setdefault("TOPOLOGICPY_CORE_BACKEND", "pythonocc")
    from topologicpy.Core import Core
    try:
        engine = Core.Backend()
    except ImportError as exc:
        raise SystemExit(f"{exc}\nActivate your existing topologicpy-occ8 Conda environment and run python launch.py. The app does not create environments or install packages.") from exc
    print("TopologicLab", flush=True)
    print(f"Geometry engine: {type(engine).__name__}", flush=True)
    os.chdir(Path(__file__).resolve().parent)
    listener = reserve_port()
    port = listener.getsockname()[1]
    if port != 8017:
        print(f"Port 8017 is already in use; using available port {port}.", flush=True)
    print(f"Open http://127.0.0.1:{port}/ in your browser. Press Ctrl+C to stop.", flush=True)
    try:
        uvicorn.Server(uvicorn.Config("backend.app:app", host="127.0.0.1", port=port)).run(sockets=[listener])
    finally:
        listener.close()
