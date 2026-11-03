"""
comserial — serial-port helpers shared by ignoAPI and autocom.

These are the parts that were debugged against awkward real hardware and must
behave identically in both programs:

  * list_com_ports   -- enumerate ports, EXCLUDING Bluetooth. A paired phone
                        creates Incoming and Outgoing COM ports that block for
                        ~30s on open; scanning them once hung ignoAPI's start.
  * _cc_probe_port   -- send a probe string and see if the device answers OK,
                        holding DTR/RTS low and waiting for the board to boot
                        (an ESP32 reboots when its port is opened).
  * _cc_read_latest  -- split a stream into the LATEST complete reading,
                        tolerating devices that use spaces rather than newlines.
  * _cc_encode_command / _cc_decode -- hex-or-text on the wire.
  * _cc_explain      -- turn a pyserial error into something actionable.

Kept in one module because two copies of this is how the reader in one program
starts behaving differently from the reader in the other.
"""
import re
import time

CC_LISTEN_CMD = "0x01"

CC_MAX_BUF = 8192

CC_PROBE_READ_S = 1.5
CC_PROBE_SETTLE_S = 2.0
CC_PROBE_TRIES = 2
CC_PROBE_REPLY_RE = re.compile(r"^\s*ok\s*$", re.I | re.M)


def list_com_ports():
    """Available serial ports, e.g. ['COM3', 'COM8']. Empty list if pyserial
    is missing or nothing is plugged in — the modal shows a free-text field in
    that case rather than blocking the user."""
    try:
        import serial.tools.list_ports
        return [p.device for p in serial.tools.list_ports.comports()]
    except Exception as e:
        print(f"[ignoAPI] could not enumerate COM ports: {e}")
        return []


def _cc_read_latest(ser, holder):
    """Ensures only the absolute latest single reading is processed,
    discarding any piled-up backlog."""
    try:
        n = ser.in_waiting or 0
    except Exception:
        n = 0

    chunk = ser.read(n) if n > 0 else ser.read(1)
    if not chunk:
        if holder.get("buf"):
            stranded = holder["buf"]
            holder["buf"] = b""
            return _cc_decode(stranded), 0
        return None, 0

    buf = holder.get("buf", b"") + chunk
    if len(buf) > CC_MAX_BUF:
        buf = buf[-CC_MAX_BUF:]

    if b"\n" in buf or b"\r" in buf:
        lines = [l for l in buf.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n") if l.strip()]
        if lines:
            holder["buf"] = b"" if buf.endswith(b"\n") else lines[-1]
            return _cc_decode(lines[-1]), len(chunk)

    holder["buf"] = buf
    return None, len(chunk)


def _cc_encode_command(command):
    """'0x41' -> b'A';  '41 42' -> b'AB';  anything else -> raw ASCII + CRLF.

    Hex is the common case for instrument protocols, so it is detected first;
    a plain text command still works for line-based devices.
    """
    c = command.strip()
    try:
        if c.lower().startswith("0x"):
            return bytes.fromhex(c[2:].replace(" ", ""))
        stripped = c.replace(" ", "")
        if stripped and len(stripped) % 2 == 0 and all(ch in "0123456789abcdefABCDEF" for ch in stripped):
            return bytes.fromhex(stripped)
    except ValueError:
        pass
    return (c + "\r\n").encode("utf-8", errors="replace")


def _cc_decode(data):
    """Bytes -> a value worth storing. Printable text is kept as text;
    anything else is stored as hex so binary protocols are still readable."""
    try:
        txt = data.decode("utf-8").strip()
        if txt and all(32 <= ord(ch) < 127 or ch in "\t" for ch in txt):
            return txt
    except UnicodeDecodeError:
        pass
    return data.hex()


def _cc_explain(exc, port):
    """Turn a pyserial exception into something actionable.

    'PermissionError(13, Access is denied)' on Windows almost never means a
    permissions problem — it means the port is ALREADY OPEN in another
    program (a second ignoAPI, a terminal, Arduino IDE, the phone-bridge app),
    because Windows COM ports are exclusive-access.
    """
    msg = str(exc)
    low = msg.lower()
    if "permissionerror" in low or "access is denied" in low or "errno 13" in low:
        return (
            f"PORT BUSY — {port} is already open in another program "
            f"(close the other app / second ignoAPI, then Reconnect). [{msg}]"
        )
    if "filenotfounderror" in low or ("could not open port" in low and "system cannot find" in low):
        return f"PORT NOT FOUND — {port} is not plugged in. [{msg}]"
    return msg


def _cc_probe_port(port, probe, baud, read_s=None):
    """Send `probe` to one port and report whether it answered OK.

    Returns (matched, reply_text). Never raises -- a port that is busy, absent
    or owned by something else is a miss, not an error.

    Timings are overridable from ignoAPI: cc_probe_settle, cc_probe_read,
    cc_probe_tries. Shorten the settle once you know your board does not
    auto-reset; a scan costs roughly (settle + read) per port.
    """
    if read_s is None:
        read_s = CC_PROBE_READ_S
    settle = CC_PROBE_SETTLE_S
    tries = CC_PROBE_TRIES

    try:
        import serial
    except Exception as e:
        return False, f"pyserial missing ({e})"

    ser = None
    last = ""
    try:
        ser = serial.Serial(
            port=port, baudrate=int(baud), timeout=read_s, write_timeout=2.0
        )
        for lname in ("dtr", "rts"):
            try:
                setattr(ser, lname, False)
            except Exception:
                pass

        if settle > 0:
            time.sleep(settle)

        payload = _cc_encode_command(probe)
        for attempt in range(tries):
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass

            ser.write(payload)
            deadline = time.time() + read_s
            buf = b""
            while time.time() < deadline:
                n = 0
                try:
                    n = ser.in_waiting or 0
                except Exception:
                    pass
                chunk = ser.read(n) if n else ser.read(1)
                if chunk:
                    buf += chunk
                    _t = buf.decode("utf-8", errors="replace").replace("\r", "\n")
                    if CC_PROBE_REPLY_RE.search(_t):
                        break

            try:
                last = buf.decode("utf-8", errors="replace").strip()
            except Exception:
                last = repr(buf)

            for line in [l.strip() for l in last.replace("\r", "\n").split("\n")]:
                if CC_PROBE_REPLY_RE.match(line):
                    return True, line

            if attempt + 1 < tries:
                time.sleep(0.2)

        return False, last
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
