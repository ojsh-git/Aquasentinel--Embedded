"""
Scenario tests for the advisory agent.

Run:  python tests/test_advisor.py

Each scenario feeds readings into a fresh database through the real API,
then checks that the advisory:
  - reports exactly the snapshot's alert status
  - passes the consistency checker (no fallback needed)
  - never reassures during HIGH / CRITICAL / SENSOR_FAULT / STALE
  - labels simulated data
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import app as A                                     # noqa: E402
from advisor import check_advisory, generate_advisory  # noqa: E402


def fresh():
    A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
    A.init_db()
    return A.app.test_client()


def post(c, level, rise=0.5, rain=0, source="LIVE"):
    return c.post("/api/reading", json={
        "water_level": level, "rise_rate": rise, "rain": rain,
        "temperature": 25, "humidity": 60, "source": source}).get_json()


def spread(minutes):
    """Spread existing rows evenly over the last N minutes."""
    con = A.db()
    ids = [r[0] for r in con.execute("SELECT id FROM readings ORDER BY id")]
    now = datetime.now(timezone.utc)
    for k, i in enumerate(ids):
        ts = now - timedelta(seconds=minutes * 60 * (len(ids) - 1 - k) / max(1, len(ids) - 1))
        con.execute("UPDATE readings SET timestamp=? WHERE id=?", (ts.isoformat(), i))
    con.commit()
    con.close()


def age_last(seconds):
    con = A.db()
    ts = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    con.execute("UPDATE readings SET timestamp=? WHERE id=(SELECT MAX(id) FROM readings)", (ts,))
    con.commit()
    con.close()


SCENARIOS = {}


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


@scenario
def empty(c):
    return "NO_DATA"


@scenario
def calm_low(c):
    for lvl in [20, 20.2, 20.1, 20.3, 20.2]:
        post(c, lvl, rise=0)
    spread(4)
    return "LOW"


@scenario
def rising_fast_but_low(c):
    for lvl in [5, 8, 11, 14, 17, 20]:
        post(c, lvl, rise=3.5)
    spread(4)
    return None   # status from rules; we check prepare_early instead


@scenario
def moderate_rain(c):
    for lvl in [40, 41, 42, 43]:
        post(c, lvl, rise=1, rain=1)
    spread(3)
    return "MODERATE"


@scenario
def high(c):
    for lvl in [55, 58, 61, 64]:
        post(c, lvl, rise=3, rain=1)
    spread(3)
    return "HIGH"


@scenario
def critical(c):
    for lvl in [75, 80, 85, 90]:
        post(c, lvl, rise=6, rain=1)
    spread(3)
    return "CRITICAL"


@scenario
def sensor_spike(c):
    for lvl in [50, 50.5, 51]:
        post(c, lvl, rise=0.5)
    post(c, 2, rise=0.5)          # sudden jump -> FAULT
    return "SENSOR_FAULT"


@scenario
def offline(c):
    for lvl in [30, 30.5]:
        post(c, lvl)
    age_last(120)
    return "STALE"


@scenario
def simulated(c):
    for lvl in [30, 31, 32]:
        post(c, lvl, rise=1, source="SIMULATED")
    return None


def main():
    failures = 0
    for name, fn in SCENARIOS.items():
        c = fresh()
        expected = fn(c)
        adv = c.get("/api/advisory").get_json()
        snap = c.get("/api/snapshot").get_json()
        problems = []
        if expected and adv["status"] != expected:
            problems.append(f"expected {expected}, got {adv['status']}")
        if adv["status"] != snap["alert"]["status"]:
            problems.append("advisory status differs from snapshot")
        if not adv["check"]["passed"]:
            problems.append(f"checker failed: {adv['check']['problems']}")
        problems += check_advisory(adv, snap) if not adv["check"]["fallback_used"] else []
        if name == "rising_fast_but_low" and not adv["prepare_early"]:
            problems.append("fast rise did not trigger early preparation advice")
        if name == "simulated" and "SIMULATED" not in (adv["source_note"] or ""):
            problems.append("simulated data not labelled")

        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(f"[{status}] {name:22s} {adv['status']:13s} {adv['public']['headline']}")
        print(f"         public: {adv['public']['summary']}")
        print(f"         steps : {[s['id'] for s in adv['public']['steps']]}")
        for p in problems:
            print(f"         !! {p}")

    # The checker itself must catch bad messages.
    bad_snap = {"alert": {"status": "CRITICAL", "agreement": "CONFIRMED"}, "data_source": "LIVE"}
    bad = generate_advisory(bad_snap)
    bad["public"]["summary"] = "Conditions are stable, nothing to worry about."
    caught = check_advisory(bad, bad_snap)
    print(f"[{'PASS' if caught else 'FAIL'}] checker catches 'stable' during CRITICAL: {caught}")
    failures += not caught

    bad = generate_advisory({"alert": {"status": "HIGH"}, "data_source": "LIVE"})
    bad["pro"]["steps"].append({"id": "MADE_UP", "text": "Drink flood water", "source": "?"})
    caught = check_advisory(bad, {"alert": {"status": "HIGH"}, "data_source": "LIVE"})
    print(f"[{'PASS' if caught else 'FAIL'}] checker catches invented precaution: {caught}")
    failures += not caught

    print(f"\n{len(SCENARIOS) + 2 - failures}/{len(SCENARIOS) + 2} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
