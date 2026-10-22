"""
One-command runner for Bengaluru Water Network Digital Twin.
Launches both FastAPI backend (port 8000) and Vite frontend (port 5173).
"""

import sys
import os
import subprocess
import time
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
FRONTEND_DIR = ROOT_DIR / "frontend"

def main():
    print("=" * 70)
    print("   BENGALURU WATER NETWORK DIGITAL TWIN — UNIFIED RUNNER")
    print("=" * 70)
    print(f"[1/3] Root Directory: {ROOT_DIR}")
    print(f"[2/3] Virtual Environment Python: {VENV_PYTHON}")

    if not VENV_PYTHON.exists():
        print(f"[ERROR] Virtual environment python not found at {VENV_PYTHON}")
        print("Please run: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt")
        sys.exit(1)

    print("\n[3/3] Starting Services concurrently...")
    
    # 1. Start FastAPI Backend
    backend_cmd = [
        str(VENV_PYTHON),
        "-m", "uvicorn",
        "backend.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ]
    print("  -> Launching FastAPI Backend on http://127.0.0.1:8000")
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # 2. Start Vite Frontend
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

    time.sleep(3.0)
    webbrowser.open("http://localhost:5180")
    print("\n[SUCCESS] Both services running!")
    print("  • Frontend UI: http://localhost:5180")
    print("  • FastAPI API Documentation: http://127.0.0.1:8000/docs")
    print("\nPress Ctrl+C in this terminal to stop both services.\n")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nTerminating services...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Done.")

if __name__ == "__main__":
    main()
