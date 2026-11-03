"""
init_robot_vars.py — Helper script to initialize robot variables in ignoAPI.exe.

Usage:
  python init_robot_vars.py rob23
  python init_robot_vars.py rob1
"""

import sys
import socket
import json

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8899

def init_vars_for_robot(robot_id: str = "rob23"):
    clean_id = robot_id.strip().lower()
    
    variables = {
        # Global fallback keys
        "c_id": "z1",
        "alarm": "",
        "obstacle": False,
        "error": "",
        "battery_percentage": 100,
        "current_task": "",
        "current_line": 0,
        "status": "IDLE",
        
        # Per-robot prefixed keys
        f"{clean_id}_cid": "z1",
        f"{clean_id}_alarm": "",
        f"{clean_id}_obstacle": False,
        f"{clean_id}_error": "",
        f"{clean_id}_battery": 100,
        f"{clean_id}_current_task": "",
        f"{clean_id}_current_line": 0,
        f"{clean_id}_status": "IDLE",
    }

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect((SERVER_HOST, SERVER_PORT))
        
        for k, v in variables.items():
            req = {"action": "create_or_write", "name": k, "value": v}
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            
        s.close()
        print(f"✅ Successfully initialized ignoAPI variables for '{clean_id}' on {SERVER_HOST}:{SERVER_PORT}")
    except Exception as e:
        print(f"❌ Failed to connect to ignoAPI on {SERVER_HOST}:{SERVER_PORT}: {e}")
        print("Make sure ignoAPI.exe is running first.")

if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "rob23"
    init_vars_for_robot(rid)
