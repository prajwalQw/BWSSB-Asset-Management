import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.security.audit import audit_logger, AuditLogger
from backend.app.bridge.ignoapi_bridge import bridge

client = TestClient(app)

def test_admin_login_success():
    resp = client.post("/api/v1/security/auth/login", json={
        "username": "admin",
        "password": "Bwssb@2026!Admin"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["role"] == "admin"
    assert "access_token" in resp.cookies

def test_login_invalid_password_fails():
    resp = client.post("/api/v1/security/auth/login", json={
        "username": "admin",
        "password": "WrongPassword123"
    })
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.json()["detail"]

def test_audit_chain_integrity():
    # Record events
    audit_logger.record(who="test_operator", what="VALVE_SIMULATED_TEST", from_where="127.0.0.1", details={"valve_id": "V-01"})
    result = audit_logger.verify_chain()
    assert result["valid"] is True
    assert result["total_records"] >= 1
    assert len(result["head_hash"]) == 64

def test_audit_chain_tamper_detection(tmp_path):
    # Create isolated test logger
    test_db = tmp_path / "tamper_test.db"
    tamper_logger = AuditLogger(db_path=test_db)
    tamper_logger.record(who="user1", what="ACTION_1", from_where="127.0.0.1")
    tamper_logger.record(who="user2", what="ACTION_2", from_where="127.0.0.1")
    
    # Verify chain initially valid
    assert tamper_logger.verify_chain()["valid"] is True
    
    # Tamper with the first record in the SQLite database
    import sqlite3
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE audit_log SET what = 'TAMPERED_ACTION' WHERE id = 1")
    conn.commit()
    conn.close()
    
    # Verify chain now detects tampering
    tampered_result = tamper_logger.verify_chain()
    assert tampered_result["valid"] is False
    assert "Hash mismatch" in tampered_result.get("error", "")

def test_bridge_read_only_protection():
    # Verify field control is blocked and raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        bridge.write_variable("motor_speed", 1500)
    assert "Field control is intentionally unavailable" in str(exc_info.value)
    
    with pytest.raises(PermissionError) as exc_info2:
        bridge.set_actuator("valve_1", "OPEN")
    assert "Field control is intentionally unavailable" in str(exc_info2.value)

    with pytest.raises(PermissionError) as exc_info3:
        bridge.send_command("write_speed", 1200)
    assert "Field control is intentionally unavailable" in str(exc_info3.value)

def test_security_status_endpoint():
    resp = client.get("/api/v1/security/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_enabled"] is True
    assert "admin" in data["rbac_roles"]
    assert data["audit_chain_valid"] is True
    assert data["field_control_mode"] == "READ_ONLY_PASSIVE"
    assert data["rate_limiting"] is True

def test_security_headers_present():
    resp = client.get("/healthz")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in resp.headers
