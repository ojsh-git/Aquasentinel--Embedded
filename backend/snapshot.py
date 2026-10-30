"""
Builds the compact "last N minutes" snapshot.

This is the ONLY thing the explainer / AI agent will ever see. The agent
never reads raw sensor streams and never decides the alert status: every
number and every status in here comes from deterministic backend code.
"""

from datetime import datetime, timedelta, timezone

# If no reading has arrived for this long, the node is treated as offline.
STALE_AFTER_S = 30

# Level change (percentage points per minute) below which we call it steady.
STEADY_BAND_PER_MIN = 0.5

# ML probability (0-100) at or above which the model is "calling" high risk.
ML_HIGH_THRESHOLD = 50.0

HIGH_LEVELS = ("HIGH", "CRITICAL")


def _parse(ts):
    return datetime.fromisoformat(ts)


def _agreement(risk_level, ml_probability):
    """Compare the rule engine with the ML model on the latest reading."""
    if ml_probability is None:
        return "UNKNOWN"
    rules_high = risk_level in HIGH_LEVELS
    ml_high = ml_probability >= ML_HIGH_THRESHOLD
    if rules_high and ml_high:
        return "CONFIRMED"        # both agree conditions are dangerous
    if ml_high:
        return "EARLY_WARNING"    # ML sees danger before the rules do
    if rules_high:
        return "RULES_ONLY"       # rules fired, ML does not agree
    return "CLEAR"


def _trend(rows):
    """rows: trusted readings, oldest first."""
    if not rows:
        return None
    levels = [r["water_level"] for r in rows]
    start, end = levels[0], levels[-1]
    elapsed_min = (
        _parse(rows[-1]["timestamp"]) - _parse(rows[0]["timestamp"])
    ).total_seconds() / 60

    per_minute = None
    direction = "INSUFFICIENT_DATA"
    if elapsed_min >= 0.5:
        per_minute = round((end - start) / elapsed_min, 2)
        if per_minute > STEADY_BAND_PER_MIN:
            direction = "RISING"
        elif per_minute < -STEADY_BAND_PER_MIN:
            direction = "FALLING"
        else:
            direction = "STEADY"

    return {
        "start_level": round(start, 1),
        "end_level": round(end, 1),
        "change": round(end - start, 1),
        "per_minute": per_minute,
        "direction": direction,
        "min_level": round(min(levels), 1),
        "max_level": round(max(levels), 1),
        "covered_minutes": round(elapsed_min, 1),
        "rain_fraction": round(sum(1 for r in rows if r["rain"]) / len(rows), 2),
    }


def build_snapshot(con, minutes=5, now=None):
    now = now or datetime.now(timezone.utc)

    latest = con.execute(
        "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if latest is None:
        return {
            "generated_at": now.isoformat(),
            "window_minutes": minutes,
            "alert": {"status": "NO_DATA", "agreement": "UNKNOWN"},
        }

    cutoff = (now - timedelta(minutes=minutes)).isoformat()
    window = con.execute(
        "SELECT * FROM readings WHERE timestamp >= ? ORDER BY id ASC",
        (cutoff,),
    ).fetchall()

    age_s = (now - _parse(latest["timestamp"])).total_seconds()
    online = age_s <= STALE_AFTER_S

    sources = {r["source"] for r in window} or {latest["source"]}
    if len(sources) > 1:
        data_source = "MIXED"
    else:
        data_source = sources.pop()

    trusted = [r for r in window if r["sensor_status"] != "FAULT"]
    faults = [r for r in window if r["sensor_status"] == "FAULT"]
    warnings = [r for r in window if r["sensor_status"] == "WARNING"]

    # Authoritative alert status. Order matters: a stale or faulty sensor
    # must never be reported as LOW / safe.
    if not online:
        status = "STALE"
    elif latest["sensor_status"] == "FAULT":
        status = "SENSOR_FAULT"
    else:
        status = latest["risk_level"]

    last_problem = next(
        (r for r in reversed(window) if r["sensor_status"] != "OK"), None
    )

    return {
        "generated_at": now.isoformat(),
        "window_minutes": minutes,
        "data_source": data_source,
        "device": {
            "online": online,
            "last_reading_at": latest["timestamp"],
            "last_reading_age_s": round(age_s, 1),
            "readings_in_window": len(window),
        },
        "current": {
            "water_level": latest["water_level"],
            "rise_rate": latest["rise_rate"],
            "rain": latest["rain"],
            "temperature": latest["temperature"],
            "humidity": latest["humidity"],
            "risk_score": latest["risk_score"],
            "risk_level": latest["risk_level"],
            "gate_status": latest["gate_status"],
        },
        "trend": _trend(trusted),
        "forecast": {
            "predicted_level_5min": latest["predicted_level"],
            "ml_high_risk_probability": latest["ml_high_risk_probability"],
        },
        "sensor_health": {
            "status": latest["sensor_status"],
            "faults_in_window": len(faults),
            "warnings_in_window": len(warnings),
            "last_issue": last_problem["fault_reason"] if last_problem else None,
        },
        "alert": {
            "status": status,
            "agreement": _agreement(
                latest["risk_level"], latest["ml_high_risk_probability"]
            ),
        },
    }
