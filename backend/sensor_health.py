"""
Deterministic sensor-health checks for AquaSentinel.

These run on EVERY incoming reading, before the risk engine, so a broken
or blocked sensor cannot silently produce a "safe" reading.

Status values:
    OK       - reading looks physically plausible
    WARNING  - reading is usable but suspicious (e.g. stuck value)
    FAULT    - reading is not trusted; the last good water level is held
"""

# Physical plausibility limits for the raw payload.
LEVEL_RANGE = (0.0, 100.0)        # water level is a percentage of tank height
TEMP_RANGE = (-10.0, 60.0)        # degrees C
HUMIDITY_RANGE = (0.0, 100.0)     # percent

# A real tank cannot jump this many percentage points between two readings
# taken a few seconds apart. Ultrasonic echoes off the tank wall or a hand
# over the sensor typically cause this.
MAX_JUMP_POINTS = 30.0
MAX_JUMP_WINDOW_S = 15.0

# A big jump that repeats this many readings in a row (within the tolerance)
# is treated as a real level change, not a spike.
CONFIRM_SHIFT_READINGS = 3
SHIFT_TOLERANCE = 5.0

# If this many consecutive readings have exactly the same level, the sensor
# may be frozen. Real ultrasonic readings always have a little noise.
STUCK_COUNT = 30


def _outside(value, bounds):
    return value < bounds[0] or value > bounds[1]


def check_reading(raw, previous_rows, seconds_since_previous):
    """
    raw: dict with float water_level, temperature, humidity (before clamping)
    previous_rows: most recent stored rows, newest first (sqlite3.Row/dicts)
    seconds_since_previous: seconds since the newest stored row, or None

    Returns (status, reason, last_good_level)
    """
    faults = []
    warnings = []

    if _outside(raw["water_level"], LEVEL_RANGE):
        faults.append(f"water level {raw['water_level']:.1f}% out of range")
    if _outside(raw["temperature"], TEMP_RANGE):
        faults.append(f"temperature {raw['temperature']:.1f}C out of range")
    if _outside(raw["humidity"], HUMIDITY_RANGE):
        faults.append(f"humidity {raw['humidity']:.1f}% out of range")

    last_good_level = None
    for row in previous_rows:
        if row["sensor_status"] != "FAULT":
            last_good_level = row["water_level"]
            break

    if (
        last_good_level is not None
        and seconds_since_previous is not None
        and seconds_since_previous <= MAX_JUMP_WINDOW_S
        and abs(raw["water_level"] - last_good_level) > MAX_JUMP_POINTS
    ):
        # A one-off spike is a fault. But if the previous readings were
        # also rejected and all agree with this one, the level really did
        # change (tank drained, sensor re-seated): accept it, with a warning,
        # so the system cannot get stuck in FAULT forever.
        recent = previous_rows[: CONFIRM_SHIFT_READINGS - 1]
        shift_confirmed = (
            len(recent) == CONFIRM_SHIFT_READINGS - 1
            and all(
                r["sensor_status"] == "FAULT"
                and r["raw_water_level"] is not None
                and abs(r["raw_water_level"] - raw["water_level"]) <= SHIFT_TOLERANCE
                for r in recent
            )
        )
        if shift_confirmed:
            warnings.append(
                f"level shift to {raw['water_level']:.1f}% accepted after "
                f"{CONFIRM_SHIFT_READINGS} consistent readings"
            )
        else:
            faults.append(
                f"water level jumped {last_good_level:.1f}% -> "
                f"{raw['water_level']:.1f}% in {seconds_since_previous:.0f}s"
            )

    recent_levels = [r["raw_water_level"] for r in previous_rows[: STUCK_COUNT - 1]]
    if (
        len(recent_levels) == STUCK_COUNT - 1
        and all(lvl == raw["water_level"] for lvl in recent_levels)
    ):
        warnings.append(f"water level unchanged for {STUCK_COUNT} readings")

    if faults:
        return "FAULT", "; ".join(faults), last_good_level
    if warnings:
        return "WARNING", "; ".join(warnings), last_good_level
    return "OK", "", last_good_level
