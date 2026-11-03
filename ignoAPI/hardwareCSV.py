import csv
import os
import tempfile
import json


def safe_write_csv(csv_file, fieldnames, rows):
    """Write CSV safely using a temp file."""
    try:
        dir_name = os.path.dirname(csv_file) or '.'

        with tempfile.NamedTemporaryFile(mode='w', newline='', dir=dir_name, delete=False) as tmpfile:
            writer = csv.DictWriter(tmpfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            temp_name = tmpfile.name

        os.replace(temp_name, csv_file)

    except Exception as e:
        print(f"Error during safe write to {csv_file}: {e}")


def read_setting(setting_name, csv_file):
    try:
        with open(csv_file, 'r', newline='') as file:
            reader = csv.DictReader(file)

            for row in reader:
                if row.get('Setting') == setting_name:
                    return row.get('Value')

    except FileNotFoundError:
        print(f"File {csv_file} not found.")

    except Exception as e:
        print(f"Error reading setting '{setting_name}': {e}")

    return None


def parse_band(raw):
    """Parse an HSV band CSV value (SPEEDBND / SLOWBND / STOPBND).

    A band value may be:
        - a single range object:   {"low":[h,s,v], "high":[h,s,v]}
        - a list of range objects:  [ {...}, {...} ]   (red needs two,
              because its hue wraps around 0/180)
        - 0 / "0" / "" / "none" / missing -> None  (ABSENCE trigger:
              the role fires when NONE of the other bands are detected).

    Returns:
        None                  -> absence trigger
        [((lo),(hi)), ...]    -> list of (low, high) HSV tuple pairs
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower() in ("0", "", "none", "null"):
        return None
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Bad band JSON {raw!r}: {e} -> treating as absence trigger")
        return None
    if isinstance(obj, dict):
        obj = [obj]
    ranges = []
    for item in obj:
        try:
            lo = tuple(int(v) for v in item["low"])
            hi = tuple(int(v) for v in item["high"])
            if len(lo) != 3 or len(hi) != 3:
                raise ValueError("low/high must each have 3 values")
            ranges.append((lo, hi))
        except (KeyError, TypeError, ValueError) as e:
            print(f"Bad band entry {item!r}: {e} -> skipped")
    return ranges if ranges else None


# -------------------------
# HARDWARE SETTINGS
# -------------------------

RIGHT_MOTOR = int(read_setting('RIGHT_MOTOR', 'Hardware.csv') or 0)
LEFT_MOTOR = int(read_setting('LEFT_MOTOR', 'Hardware.csv') or 0)

RIGHT_TURN = int(read_setting('RIGHT_TURN', 'Hardware.csv') or 0)
LEFT_TURN = int(read_setting('LEFT_TURN', 'Hardware.csv') or 0)

LIFT_MOTOR = int(read_setting('LIFT_MOTOR', 'Hardware.csv') or 0)
DRAG_MOTOR = int(read_setting('DRAG_MOTOR', 'Hardware.csv') or 0)

WHEEL_DIA = float(read_setting('WHEEL_DIA', 'Hardware.csv') or 0)

PPR = int(read_setting('PPR', 'Hardware.csv') or 4000)

RIGHT_MOTOR_GEAR = int(read_setting('RIGHT_GEAR', 'Hardware.csv') or 10)
LEFT_MOTOR_GEAR = int(read_setting('LEFT_GEAR', 'Hardware.csv') or 10)

RIGHT_TURN_GEAR = int(read_setting('RIGHT_TURN_GEAR', 'Hardware.csv') or 0)
LEFT_TURN_GEAR = int(read_setting('LEFT_TURN_GEAR', 'Hardware.csv') or 0)

# CAMERA SETTINGS
FRONT_CAM = int(read_setting('FRONT_CAM', 'Hardware.csv') or 0)
BOTTOM_CAM = int(read_setting('BOTTOM_CAM', 'Hardware.csv') or 0)
CAPTURE_WIDTH = int(read_setting('CAPTURE_WIDTH', 'Hardware.csv') or 480)
CAPTURE_HEIGHT = int(read_setting('CAPTURE_HEIGHT', 'Hardware.csv') or 360)
FPS = int(read_setting('FPS', 'Hardware.csv') or 60)

# LANE DETECTION SETTING
LANE_DETECTION_ENABLED = int(read_setting('LANE_DETECTION_ENABLED', 'Hardware.csv') or 1)
WHEELBASE = int(read_setting('WHEELBASE', 'Hardware.csv') or 0)
RADIUS = float(read_setting('RADIUS', 'Hardware.csv') or 0)
HWIP = read_setting('HWIP', 'Hardware.csv')
DEVICE_NUMBER = int(read_setting('DEVICE_NUMBER', 'Hardware.csv') or 2)
VELOCITY = int(read_setting('VELOCITY', 'Hardware.csv') or 0)
ACCELERATION = int(read_setting('ACCELERATION', 'Hardware.csv') or 0)
DECELERATION = int(read_setting('DECELERATION', 'Hardware.csv') or 0)
JOG_VEL = int(read_setting('JOG_VEL', 'Hardware.csv') or 0)
JOG_ACC = int(read_setting('JOG_ACC', 'Hardware.csv') or 0)
JOG_DCC = int(read_setting('JOG_DCC', 'Hardware.csv') or 0)
TURN_JOG_VEL = int(read_setting('TURN_JOG_VEL', 'Hardware.csv') or 60)
TURN_JOG_ACC = int(read_setting('TURN_JOG_ACC', 'Hardware.csv') or 3000)
OMNIRATIO = float(read_setting('OMNIRATIO', 'Hardware.csv') or 0)
PIXSTP = float(read_setting('PIXSTP', 'Hardware.csv') or 0)
TOLANG = float(read_setting('TOLANG', 'Hardware.csv') or 0)
LIDAR_MIN = float(read_setting('LIDAR_MIN', 'Hardware.csv') or 0)
LIDAR_MAX = float(read_setting('LIDAR_MAX', 'Hardware.csv') or 0)
LIDAR_DIS = float(read_setting('LIDAR_DIS', 'Hardware.csv') or 0.7)
WHEEL_BASE = float(read_setting('WHEEL_BASE', 'Hardware.csv') or 790)
KP = float(read_setting('KP', 'Hardware.csv') or 0.4)
KI = float(read_setting('KI', 'Hardware.csv') or 0.01)
KD = float(read_setting('KD', 'Hardware.csv') or 0.05)
DEADBAND = float(read_setting('DEADBAND', 'Hardware.csv') or 10)
MAX_CORRECT = float(read_setting('MAX_CORRECT', 'Hardware.csv') or 40)
VESTR = read_setting('VESTR', 'Hardware.csv') or "none"
FIDCH = int(read_setting('FIDCH', 'Hardware.csv') or 1)
VESTRBAND = int(read_setting('VESTRBAND', 'Hardware.csv') or 1)
VESTRINTR = int(read_setting('VESTRINTR', 'Hardware.csv') or 1)
MONOPXAREA = float(read_setting('MONOPXAREA', 'Hardware.csv') or 10)
CENOFFSET = float(read_setting('CENOFFSET', 'Hardware.csv') or 10)
TRACKYOFFSET = float(read_setting('TRACKYOFFSET', 'Hardware.csv') or 10)
GHOSTFID = int(read_setting('GHOSTFID', 'Hardware.csv') or 0)
ZONEYOFFSET = int(read_setting('ZONEYOFFSET', 'Hardware.csv') or 0)
ZONEAREA = int(read_setting('ZONEAREA', 'Hardware.csv') or 10)
NX = int(read_setting('NX', 'Hardware.csv') or 0)
NY = int(read_setting('NY', 'Hardware.csv') or 0)
EPCS = int(read_setting('EPCS', 'Hardware.csv') or 100)
NTRK = read_setting('NTRK', 'Hardware.csv')
LINEFOLLOW_X_OFFSET = int(read_setting('LINEFOLLOW_X_OFFSET', 'Hardware.csv') or 0)
CX_OFFSET = int(read_setting('CX', 'Hardware.csv') or 0)
CY_OFFSET = int(read_setting('CY', 'Hardware.csv') or 0)
# COLOR-STRIP ZONE BANDS (parsed HSV ranges, NOT ints)
#   SPEEDBND -> normal lane tracking
#   SLOWBND  -> hold steering (l_adj = 999)
#   STOPBND  -> jogStop (l_adj = 999 + cmd=jogStop)
# A band of 0 / none = ABSENCE trigger: fires when no other band is seen.
SPEEDBND = parse_band(read_setting('SPEEDBND', 'Hardware.csv'))
SLOWBND = parse_band(read_setting('SLOWBND', 'Hardware.csv'))
STOPBND = parse_band(read_setting('STOPBND', 'Hardware.csv'))
API_PORT = int(read_setting('API_PORT', 'Hardware.csv') or 8899)
# -------------------------
# RELOAD CSV FUNCTION
# -------------------------

def reloadCSV():

    global RIGHT_MOTOR, LEFT_MOTOR
    global RIGHT_TURN, LEFT_TURN
    global LIFT_MOTOR, DRAG_MOTOR
    global WHEEL_DIA, PPR
    global RIGHT_MOTOR_GEAR, LEFT_MOTOR_GEAR
    global RIGHT_TURN_GEAR, LEFT_TURN_GEAR
    global FRONT_CAM, BOTTOM_CAM, CAPTURE_WIDTH, CAPTURE_HEIGHT, FPS
    global LANE_DETECTION_ENABLED
    global VELOCITY, ACCELERATION, DECELERATION
    global JOG_VEL, JOG_ACC, JOG_DCC
    global TURN_JOG_VEL, TURN_JOG_ACC
    global TOLANG
    global LIDAR_MIN, LIDAR_MAX, LIDAR_DIS
    global WHEEL_BASE, CENOFFSET, TRACKYOFFSET, GHOSTFID, ZONEYOFFSET, ZONEAREA
    global HWIP, DEVICE_NUMBER, VESTR, FIDCH, VESTRBAND, VESTRINTR, MONOPXAREA
    global NX, NY, EPCS, NTRK, LINEFOLLOW_X_OFFSET, CX_OFFSET, CY_OFFSET
    global KP, KI, KD, DEADBAND, MAX_CORRECT
    global SPEEDBND, SLOWBND, STOPBND, API_PORT
    try:

        RIGHT_MOTOR = int(read_setting('RIGHT_MOTOR', 'Hardware.csv') or 0)
        LEFT_MOTOR = int(read_setting('LEFT_MOTOR', 'Hardware.csv') or 0)

        RIGHT_TURN = int(read_setting('RIGHT_TURN', 'Hardware.csv') or 0)
        LEFT_TURN = int(read_setting('LEFT_TURN', 'Hardware.csv') or 0)

        LIFT_MOTOR = int(read_setting('LIFT_MOTOR', 'Hardware.csv') or 0)
        DRAG_MOTOR = int(read_setting('DRAG_MOTOR', 'Hardware.csv') or 0)

        WHEEL_DIA = float(read_setting('WHEEL_DIA', 'Hardware.csv') or 0)

        PPR = int(read_setting('PPR', 'Hardware.csv') or 4000)

        RIGHT_MOTOR_GEAR = int(read_setting('RIGHT_GEAR', 'Hardware.csv') or 10)
        LEFT_MOTOR_GEAR = int(read_setting('LEFT_GEAR', 'Hardware.csv') or 10)

        RIGHT_TURN_GEAR = int(read_setting('RIGHT_TURN_GEAR', 'Hardware.csv') or 0)
        LEFT_TURN_GEAR = int(read_setting('LEFT_TURN_GEAR', 'Hardware.csv') or 0)

        FRONT_CAM = int(read_setting('FRONT_CAM', 'Hardware.csv') or 0)
        BOTTOM_CAM = int(read_setting('BOTTOM_CAM', 'Hardware.csv') or 0)
        CAPTURE_WIDTH = int(read_setting('CAPTURE_WIDTH', 'Hardware.csv') or 480)
        CAPTURE_HEIGHT = int(read_setting('CAPTURE_HEIGHT', 'Hardware.csv') or 360)
        FPS = int(read_setting('FPS', 'Hardware.csv') or 60)

        LANE_DETECTION_ENABLED = int(read_setting('LANE_DETECTION_ENABLED', 'Hardware.csv') or 1)

        VELOCITY = int(read_setting('VELOCITY', 'Hardware.csv') or 0)
        ACCELERATION = int(read_setting('ACCELERATION', 'Hardware.csv') or 0)
        DECELERATION = int(read_setting('DECELERATION', 'Hardware.csv') or 0)

        JOG_VEL = int(read_setting('JOG_VEL', 'Hardware.csv') or 0)
        JOG_ACC = int(read_setting('JOG_ACC', 'Hardware.csv') or 0)
        JOG_DCC = int(read_setting('JOG_DCC', 'Hardware.csv') or 0)

        TURN_JOG_VEL = int(read_setting('TURN_JOG_VEL', 'Hardware.csv') or 60)
        TURN_JOG_ACC = int(read_setting('TURN_JOG_ACC', 'Hardware.csv') or 3000)

        TOLANG = float(read_setting('TOLANG', 'Hardware.csv') or 0)

        LIDAR_MIN = float(read_setting('LIDAR_MIN', 'Hardware.csv') or 10)
        LIDAR_MAX = float(read_setting('LIDAR_MAX', 'Hardware.csv') or 170)
        LIDAR_DIS = float(read_setting('LIDAR_DIS', 'Hardware.csv') or 2)

        WHEEL_BASE = float(read_setting('WHEEL_BASE', 'Hardware.csv') or 790)

        KP = float(read_setting('KP', 'Hardware.csv') or 0.4)
        KI = float(read_setting('KI', 'Hardware.csv') or 0.01)
        KD = float(read_setting('KD', 'Hardware.csv') or 0.05)
        DEADBAND = float(read_setting('DEADBAND', 'Hardware.csv') or 10)
        MAX_CORRECT = float(read_setting('MAX_CORRECT', 'Hardware.csv') or 40)

        HWIP = read_setting('HWIP', 'Hardware.csv')
        DEVICE_NUMBER = int(read_setting('DEVICE_NUMBER', 'Hardware.csv') or 0)
        VESTR = read_setting('VESTR', 'Hardware.csv') or "none"
        FIDCH = int(read_setting('FIDCH', 'Hardware.csv') or 1)
        VESTRBAND = int(read_setting('VESTRBAND', 'Hardware.csv') or 1)
        VESTRINTR = int(read_setting('VESTRINTR', 'Hardware.csv') or 1)
        MONOPXAREA = float(read_setting('MONOPXAREA', 'Hardware.csv') or 10)
        CENOFFSET = float(read_setting('CENOFFSET', 'Hardware.csv') or 10)
        TRACKYOFFSET = float(read_setting('TRACKYOFFSET', 'Hardware.csv') or 10)
        GHOSTFID = int(read_setting('GHOSTFID', 'Hardware.csv') or 0)
        ZONEYOFFSET = int(read_setting('ZONEYOFFSET', 'Hardware.csv') or 0)
        ZONEAREA = int(read_setting('ZONEAREA', 'Hardware.csv') or 10)
        NX = int(read_setting('NX', 'Hardware.csv') or 0)
        NY = int(read_setting('NY', 'Hardware.csv') or 0)
        EPCS = int(read_setting('EPCS', 'Hardware.csv') or 100)
        NTRK = read_setting('NTRK', 'Hardware.csv')
        LINEFOLLOW_X_OFFSET = int(read_setting('LINEFOLLOW_X_OFFSET', 'Hardware.csv') or 0)
        CX_OFFSET = int(read_setting('CX', 'Hardware.csv') or 0)
        CY_OFFSET = int(read_setting('CY', 'Hardware.csv') or 0)

        SPEEDBND = parse_band(read_setting('SPEEDBND', 'Hardware.csv'))
        SLOWBND = parse_band(read_setting('SLOWBND', 'Hardware.csv'))
        STOPBND = parse_band(read_setting('STOPBND', 'Hardware.csv'))
        API_PORT = int(read_setting('API_PORT', 'Hardware.csv') or 8899)
    except Exception as e:
        print(f"Error reloading CSV: {e}")


# -------------------------
# UPDATE CSV FUNCTION
# -------------------------

def update_csv(setting_name, new_value, csv_file='Hardware.csv'):
    """Update a specific setting in the CSV file."""
    try:
        rows = []
        fieldnames = ['Setting', 'Value']
        found = False

        # Read existing data
        try:
            with open(csv_file, 'r', newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row.get('Setting') == setting_name:
                        row['Value'] = new_value
                        found = True
                    rows.append(row)
        except FileNotFoundError:
            pass

        # If setting doesn't exist, add it
        if not found:
            rows.append({'Setting': setting_name, 'Value': new_value})

        # Write back
        safe_write_csv(csv_file, fieldnames, rows)
        print(f"Updated {setting_name} to {new_value}")

    except Exception as e:
        print(f"Error updating CSV: {e}")