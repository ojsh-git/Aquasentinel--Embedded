"""
AquaSentinel advisory agent (Phase 2, template engine).

Input : the 5-minute snapshot from snapshot.py (built from the readings log).
Output: plain-language advice for two audiences.
    public - short, calm, action-first
    pro    - numbers, trend, rules-vs-ML agreement, sensor health

Safety rules this module follows:
  1. It never decides the alert status. It copies snapshot["alert"]["status"].
  2. It only shows precautions from precautions.py.
  3. Every message goes through check_advisory(). If a message breaks a rule,
     a fixed fallback message for that status is returned instead.
  4. It works fully offline. A language-model rewrite can be added later
     behind the same checker (and that version will be cached, because
     it is slow and costs money; this template version is instant).
"""

import re
from datetime import datetime, timezone

from precautions import (
    DISCLAIMER, PRECAUTIONS, RISING_EXTRA, STATUS_PRECAUTIONS,
)

ENGINE = "template-v1"

# Level % per minute above which we call the rise "fast".
FAST_RISE_PER_MIN = 2.0
# Forecast level (%) at which a rising LOW/MODERATE gets "get ready" advice.
FORECAST_PREPARE_AT = 75.0
# How many precautions to show the public at once.
MAX_PUBLIC_STEPS = 4

HEADLINES = {
    "LOW":          "Water level is normal",
    "MODERATE":     "Water level needs watching",
    "HIGH":         "Flood risk is high: get ready to act",
    "CRITICAL":     "Flood danger: act now",
    "SENSOR_FAULT": "Sensor problem: reading not trusted",
    "STALE":        "No recent readings from the sensor",
    "NO_DATA":      "Waiting for the first reading",
}

TONE = {
    "LOW": "calm", "MODERATE": "watch", "HIGH": "warning", "CRITICAL": "danger",
    "SENSOR_FAULT": "fault", "STALE": "fault", "NO_DATA": "fault",
}

# Phrases that would wrongly reassure people. Never allowed in these statuses.
REASSURING = [
    r"\bis safe\b", r"\bare safe\b", r"\bsafe limits?\b", r"\bstable\b",
    r"\bno risk\b", r"\bno action\b", r"\bnothing to worry\b", r"\ball clear\b",
    r"\bnormal\b",
]
NOT_REASSURING_STATUSES = {"HIGH", "CRITICAL", "SENSOR_FAULT", "STALE", "NO_DATA"}

# Phrases that would cause panic. Not allowed when the status is LOW.
ALARMING = [r"\bevacuate\b", r"\bemergency\b", r"\bact now\b", r"\bdanger\b", r"\bimmediately\b"]


# ----------------------------------------------------------------------
# Building the messages
# ----------------------------------------------------------------------

def _pct(x):
    return f"{x:.0f}%"


def _is_rising_fast(trend):
    return bool(trend and trend.get("per_minute") is not None
                and trend["per_minute"] >= FAST_RISE_PER_MIN)


def _pick_precautions(status, trend, forecast):
    ids = list(STATUS_PRECAUTIONS.get(status, STATUS_PRECAUTIONS["NO_DATA"]))
    prepare_early = False
    if status in ("LOW", "MODERATE"):
        predicted = (forecast or {}).get("predicted_level_5min") or 0
        if _is_rising_fast(trend) or predicted >= FORECAST_PREPARE_AT:
            prepare_early = True
            # Put the "get ready" items first, without duplicates.
            ids = RISING_EXTRA + [i for i in ids if i not in RISING_EXTRA]
    return ids, prepare_early


def _public_summary(snap, status, prepare_early):
    cur = snap.get("current") or {}
    trend = snap.get("trend")
    forecast = snap.get("forecast") or {}
    parts = []

    if status == "NO_DATA":
        return "The system has not received any readings yet."
    if status == "STALE":
        age = round((snap.get("device") or {}).get("last_reading_age_s", 0))
        return (f"The sensor has not sent a reading for {age} seconds. "
                "The last values shown may be out of date.")
    if status == "SENSOR_FAULT":
        return ("The latest sensor reading failed a safety check, so the system "
                "is holding the last trusted level. Treat the numbers with caution.")

    level = cur.get("water_level")
    if level is not None:
        parts.append(f"Water is at {_pct(level)} of the flood mark")

    if trend and trend.get("direction") == "RISING":
        speed = "fast" if _is_rising_fast(trend) else "slowly"
        parts[-1:] = [parts[-1] + f" and rising {speed}"] if parts else [f"Water is rising {speed}"]
        mins = max(1, round(trend["covered_minutes"]))
        parts.append(f"It went up {trend['change']:.0f} points in the last "
                     f"{mins} minute{'s' if mins != 1 else ''}")
    elif trend and trend.get("direction") == "FALLING":
        parts[-1:] = [parts[-1] + " and going down"] if parts else ["Water is going down"]
    elif trend and trend.get("direction") == "STEADY":
        parts[-1:] = [parts[-1] + " and not changing much"] if parts else []

    predicted = forecast.get("predicted_level_5min")
    if predicted is not None and level is not None and predicted - level >= 5:
        parts.append(f"At this pace it could reach {_pct(predicted)} in about 5 minutes")

    if cur.get("rain"):
        parts.append("Rain is being detected")

    if prepare_early:
        parts.append("Get ready now, before it becomes serious")
    elif status == "LOW":
        parts.append("Keep an eye on updates")

    return ". ".join(parts) + "." if parts else ""


def _pro_details(snap, status):
    cur = snap.get("current") or {}
    trend = snap.get("trend")
    fc = snap.get("forecast") or {}
    health = snap.get("sensor_health") or {}
    dev = snap.get("device") or {}
    alert = snap.get("alert") or {}
    lines = []

    if cur:
        lines.append(f"Level {cur['water_level']:.1f}% · rise {cur['rise_rate']:.2f} %/min · "
                     f"rain {'yes' if cur['rain'] else 'no'} · risk score {cur['risk_score']:.1f} "
                     f"({cur['risk_level']}) · gate {cur['gate_status']}")
    if trend and trend.get("per_minute") is not None:
        lines.append(f"5-min trend {trend['direction']}: {trend['start_level']}% → {trend['end_level']}% "
                     f"({trend['change']:+.1f} pts, {trend['per_minute']:+.2f} %/min, "
                     f"min {trend['min_level']}%, max {trend['max_level']}%, "
                     f"rain in {trend['rain_fraction'] * 100:.0f}% of readings)")
    elif cur:
        lines.append("5-min trend: not enough readings yet")
    if fc.get("predicted_level_5min") is not None:
        ml = fc.get("ml_high_risk_probability")
        lines.append(f"Forecast +5 min: {fc['predicted_level_5min']:.1f}% (linear) · "
                     f"ML high-risk probability: {'n/a' if ml is None else f'{ml:.1f}%'}")
    agreement = alert.get("agreement", "UNKNOWN")
    meaning = {
        "CONFIRMED": "rules and ML both flag high risk",
        "EARLY_WARNING": "ML flags high risk before the rules do; treat as an early warning",
        "RULES_ONLY": "rules flag high risk but ML does not; rules stay authoritative",
        "CLEAR": "neither rules nor ML flag high risk",
        "UNKNOWN": "no ML result",
    }.get(agreement, agreement)
    lines.append(f"Rules vs ML: {agreement} ({meaning})")
    if health:
        hl = f"Sensor health {health.get('status')}: {health.get('faults_in_window', 0)} faults, " \
             f"{health.get('warnings_in_window', 0)} warnings in window"
        if health.get("last_issue"):
            hl += f"; last issue: {health['last_issue']}"
        lines.append(hl)
    if dev:
        lines.append(f"Node {'online' if dev.get('online') else 'OFFLINE'} · last reading "
                     f"{dev.get('last_reading_age_s', 0):.0f}s ago · "
                     f"{dev.get('readings_in_window', 0)} readings in {snap.get('window_minutes', 5)} min")
    return lines


def _pro_actions(status, agreement, prepare_early):
    actions = {
        "LOW": "Routine monitoring.",
        "MODERATE": "Increase monitoring; confirm the rain and level trend.",
        "HIGH": "Issue a local warning; drainage gate opens at HIGH; prepare response teams.",
        "CRITICAL": "Emergency warning; coordinate with local authorities on evacuation.",
        "SENSOR_FAULT": "Inspect the sensor; verify the level manually before relying on it.",
        "STALE": "Restore the node (power / Wi-Fi); verify the level manually meanwhile.",
        "NO_DATA": "Start the node or simulator and confirm readings arrive.",
    }[status]
    if prepare_early:
        actions += " Fast rise or high forecast: prepare ahead of the status change."
    if agreement == "EARLY_WARNING":
        actions += " ML early warning: watch closely for escalation."
    return actions


def generate_advisory(snap):
    """Build the advisory from a snapshot. Pure function, no I/O."""
    alert = snap.get("alert") or {}
    status = alert.get("status", "NO_DATA")
    if status not in HEADLINES:
        status = "NO_DATA"
    trend = snap.get("trend")
    forecast = snap.get("forecast")

    ids, prepare_early = _pick_precautions(status, trend, forecast)
    steps = [{"id": i, **PRECAUTIONS[i]} for i in ids]

    source = snap.get("data_source")
    source_note = None
    if source in ("SIMULATED", "MIXED"):
        source_note = ("This is SIMULATED test data, not a real flood reading."
                       if source == "SIMULATED" else
                       "Some of this data is SIMULATED test data, not real readings.")

    adv = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE,
        "status": status,
        "tone": TONE[status],
        "data_source": source,
        "source_note": source_note,
        "public": {
            "headline": HEADLINES[status],
            "summary": _public_summary(snap, status, prepare_early),
            "steps": steps[:MAX_PUBLIC_STEPS],
        },
        "pro": {
            "headline": f"{status} · agreement {alert.get('agreement', 'UNKNOWN')}",
            "details": _pro_details(snap, status),
            "action": _pro_actions(status, alert.get("agreement"), prepare_early),
            "steps": steps,
        },
        "disclaimer": DISCLAIMER,
        "prepare_early": prepare_early,
    }
    problems = check_advisory(adv, snap)
    if problems:
        adv = fallback_advisory(status, source_note)
        adv["check"] = {"passed": False, "problems": problems, "fallback_used": True}
    else:
        adv["check"] = {"passed": True, "problems": [], "fallback_used": False}
    return adv


# ----------------------------------------------------------------------
# Consistency checker: the advisory may never contradict the status
# ----------------------------------------------------------------------

def _all_text(adv):
    p = adv["public"]
    parts = [p["headline"], p["summary"], adv["pro"]["action"]]
    parts += [s["text"] for s in adv["pro"]["steps"]]
    return " ".join(parts).lower()


def check_advisory(adv, snap):
    problems = []
    true_status = (snap.get("alert") or {}).get("status", "NO_DATA")
    if adv["status"] != true_status and true_status in HEADLINES:
        problems.append(f"status mismatch: advisory {adv['status']} vs snapshot {true_status}")

    allowed = set(STATUS_PRECAUTIONS.get(adv["status"], []))
    if adv["status"] in ("LOW", "MODERATE"):
        allowed |= set(RISING_EXTRA)
    for step in adv["pro"]["steps"]:
        if step["id"] not in PRECAUTIONS:
            problems.append(f"unknown precaution {step['id']}")
        elif step["id"] not in allowed:
            problems.append(f"precaution {step['id']} not allowed for {adv['status']}")
        elif step["text"] != PRECAUTIONS[step["id"]]["text"]:
            problems.append(f"precaution {step['id']} text was altered")

    # Reassurance is checked everywhere, including the precaution texts.
    text = _all_text(adv)
    if adv["status"] in NOT_REASSURING_STATUSES:
        for pat in REASSURING:
            if re.search(pat, text):
                problems.append(f"reassuring phrase '{pat}' not allowed for {adv['status']}")
    # Alarm words are checked only in the agent's own sentences. Reviewed
    # precautions like "keep an emergency kit ready" are fine when LOW.
    own_text = " ".join([adv["public"]["headline"], adv["public"]["summary"],
                         adv["pro"]["action"]]).lower()
    if adv["status"] == "LOW":
        for pat in ALARMING:
            if re.search(pat, own_text):
                problems.append(f"alarming phrase '{pat}' not allowed for LOW")

    if not adv.get("disclaimer"):
        problems.append("missing disclaimer")
    if snap.get("data_source") in ("SIMULATED", "MIXED") and not adv.get("source_note"):
        problems.append("simulated data not labelled")
    return problems


def fallback_advisory(status, source_note=None):
    """Fixed, pre-checked message used if a generated one fails the checker."""
    ids = STATUS_PRECAUTIONS.get(status, STATUS_PRECAUTIONS["NO_DATA"])
    steps = [{"id": i, **PRECAUTIONS[i]} for i in ids]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE + "-fallback",
        "status": status,
        "tone": TONE.get(status, "fault"),
        "data_source": None,
        "source_note": source_note,
        "public": {"headline": HEADLINES.get(status, HEADLINES["NO_DATA"]),
                   "summary": "", "steps": steps[:MAX_PUBLIC_STEPS]},
        "pro": {"headline": status, "details": [], "action": "", "steps": steps},
        "disclaimer": DISCLAIMER,
        "prepare_early": False,
    }


# ----------------------------------------------------------------------
# Advisor: regenerates on every request (templates are instant) and records
# when the advice last changed in a meaningful way, so the dashboard can
# say "advice updated at ..." and a future LLM engine can cache on the key.
# ----------------------------------------------------------------------

class Advisor:
    def __init__(self):
        self._key = None
        self._changed_at = None

    @staticmethod
    def key_for(snap):
        alert = snap.get("alert") or {}
        trend = snap.get("trend") or {}
        health = snap.get("sensor_health") or {}
        fc = snap.get("forecast") or {}
        return (
            alert.get("status"), alert.get("agreement"), trend.get("direction"),
            _is_rising_fast(trend),
            (fc.get("predicted_level_5min") or 0) >= FORECAST_PREPARE_AT,
            health.get("status"), snap.get("data_source"),
        )

    def get(self, snap):
        adv = generate_advisory(snap)
        key = self.key_for(snap)
        if key != self._key:
            self._key = key
            self._changed_at = adv["generated_at"]
        adv["advice_changed_at"] = self._changed_at
        return adv
