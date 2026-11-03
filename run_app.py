"""
One-command runner for Bengaluru Water Network Digital Twin.
Launches FastAPI backend (port 8000) first, verifies health, then launches Vite frontend (port 5180).
This sequential startup guarantees zero ECONNREFUSED proxy errors and zero 502/503 errors in the browser.
"""

import sys
import os
import subprocess
import time
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
FRONTEND_DIR = ROOT_DIR / "frontend"

def free_stray_port(port: int):
    """Clean up any leftover processes listening on target ports from previous runs."""
    if os.name != "nt":
        return
    try:
        cmd = f"netstat -ano -p tcp"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                pid = parts[4]
                if pid and pid != "0" and pid != str(os.getpid()):
                    subprocess.run(["taskkill", "/F", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def kill_process_tree(proc: subprocess.Popen):
    """Cleanly terminate a process and all its child processes on Windows/POSIX."""
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        else:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

def stream_pipe(pipe, prefix: str):
    """Continuously consume and display subprocess output to prevent OS pipe buffer deadlocks."""
    try:
        for line in iter(pipe.readline, ''):
            if not line:
                break
            stripped = line.rstrip()
            if stripped:
                print(f"[{prefix}] {stripped}", flush=True)
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def wait_for_endpoint(url: str, name: str, proc: subprocess.Popen = None, timeout_sec: float = 35.0) -> bool:
    """Poll an HTTP endpoint until it answers with 200 OK or timeout expires."""
    start = time.time()
    last_print = 0.0
    while time.time() - start < timeout_sec:
        if proc and proc.poll() is not None:
            print(f"  [ERROR] {name} process exited prematurely with code {proc.returncode}!", flush=True)
            return False

        elapsed = int(time.time() - start)
        if time.time() - last_print >= 2.0:
            print(f"  -> Waiting for {name} ({elapsed}s elapsed)...", flush=True)
            last_print = time.time()
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BWSSB-HealthCheck/1.0"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status in (200, 301, 302):
                    print(f"  [OK] {name} is responsive and healthy! ({elapsed}s)", flush=True)
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def main():
    print("=" * 70)
    print("   BENGALURU WATER NETWORK DIGITAL TWIN — UNIFIED RUNNER")
    print("=" * 70)
    print(f"[1/4] Root Directory: {ROOT_DIR}")
    print(f"[2/4] Virtual Environment Python: {VENV_PYTHON}")

    python_bin = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    print(f"      Using Python Interpreter: {python_bin}")

    # Ensure ports 8000 and 5180 are clean
    free_stray_port(8000)
    free_stray_port(5180)

    print("\n[3/4] Starting FastAPI Backend...")
    backend_cmd = [
        python_bin,
        "-u",
        "-m", "uvicorn",
        "backend.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ]
    print("  -> Launching FastAPI Backend on http://127.0.0.1:8000")
    backend_env = dict(os.environ, PYTHONUNBUFFERED="1")
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(ROOT_DIR),
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    t_backend = threading.Thread(
        target=stream_pipe,
        args=(backend_proc.stdout, "Backend"),
        daemon=True
    )
    t_backend.start()

    backend_ready = wait_for_endpoint(
        "http://127.0.0.1:8000/docs",
        "FastAPI Backend (port 8000)",
        proc=backend_proc,
        timeout_sec=45.0
    )

    if not backend_ready:
        print("\n[ERROR] FastAPI Backend failed to start. Exiting.")
        kill_process_tree(backend_proc)
        sys.exit(1)

    print("\n[4/4] Starting Vite Frontend...")
    frontend_cmd = "npm run dev"
    print("  -> Launching Vite Frontend on http://localhost:5180")
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=str(FRONTEND_DIR),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    t_frontend = threading.Thread(
        target=stream_pipe,
        args=(frontend_proc.stdout, "Frontend"),
        daemon=True
    )
    t_frontend.start()

    frontend_ready = wait_for_endpoint(
        "http://127.0.0.1:5180/",
        "Vite Frontend (port 5180)",
        proc=frontend_proc,
        timeout_sec=25.0
    )

    if frontend_ready:
        print("\n" + "=" * 70)
        print("  [SUCCESS] All Digital Twin Services are Live and Ready!")
        print("   - Frontend UI:       http://127.0.0.1:5180")
        print("   - Backend Swagger:   http://127.0.0.1:8000/docs")
        print("=" * 70 + "\n")
        webbrowser.open("http://127.0.0.1:5180")
    else:
        print("\n[WARNING] Frontend took longer than expected to initialize.")

    print("Press Ctrl+C in this terminal to stop both services.\n")

    try:
        while True:
            if backend_proc.poll() is not None:
                print(f"[Backend] Process exited unexpectedly with code {backend_proc.returncode}")
                break
            if frontend_proc.poll() is not None:
                print(f"[Frontend] Process exited unexpectedly with code {frontend_proc.returncode}")
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nShutdown requested by user (Ctrl+C)...")
    finally:
        print("Terminating background services cleanly...")
        kill_process_tree(backend_proc)
        kill_process_tree(frontend_proc)
        print("All services stopped.")

if __name__ == "__main__":
    main()
