"""
AquaSentinel advisory agent, Phase 4: optional language-model wording.

The template advisor (advisor.py) always runs first and is always the
fallback. On top of it, a language model (Claude) may:
  - rewrite the resident headline and summary in more natural words
  - choose and order 2-4 precautions FROM THE ALREADY-ALLOWED LIST
  - add one short note for professionals

It may NOT:
  - change the alert status, numbers, or data-source label
  - invent precautions or change their text (we show our own text by ID)
  - use any number that is not in the facts we gave it
  - reassure during HIGH / CRITICAL / SENSOR_FAULT / STALE / NO_DATA

Every AI answer is checked. If the check fails, there is no API key,
no internet, a timeout, or bad JSON, the template advice is shown.

The AI call runs in a background thread, so /api/advisory always answers
instantly. The first request after a change gets template text; the AI
wording appears a few seconds later.

Configuration (environment variables):
  ANTHROPIC_API_KEY   your key; without it the AI layer is off
  AQUA_LLM            set to "off" to disable the AI layer
  AQUA_LLM_MODEL      default "claude-haiku-5-5"
"""

import copy
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

import requests

from advisor import Advisor, NOT_REASSURING_STATUSES, REASSURING, check_advisory

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"

TIMEOUT_S = 12
# Refresh AI wording at most this often while nothing important changes.
REFRESH_S = 45
# Water level is bucketed so small changes don't trigger new AI calls.
LEVEL_BUCKET = 5

MAX_HEADLINE = 80
MAX_SUMMARY = 420
MAX_NOTE = 240
MIN_STEPS, MAX_STEPS = 2, 4
NUMBER_TOLERANCE = 1.0

# Extra wording the model might use to downplay a serious status.
EXTRA_REASSURING = [r"\blow risk\b", r"\bno danger\b", r"\bno need\b", r"\bunder control\b",
                    r"\bfine\b", r"\bdon'?t worry\b"]
# A faulty or silent sensor gives no trustworthy trend.
TREND_WORDS = [r"\brising\b", r"\bfalling\b", r"\bgoing up\b", r"\bgoing down\b", r"\brises\b"]

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "advisor_log.jsonl")

SYSTEM_PROMPT = """You write short flood-safety messages for AquaSentinel, a student flood-monitoring prototype.

You receive FACTS (from sensors and deterministic code) and ALLOWED_PRECAUTIONS (id -> text).

Hard rules:
- The alert STATUS is decided by the system. Never contradict it, soften it, or add a different level.
- Use only numbers that appear in FACTS. Do not estimate, round to new values, or add times, distances or phone numbers.
- Never say or imply things are safe, normal, stable or fine when STATUS is HIGH, CRITICAL, SENSOR_FAULT, STALE or NO_DATA.
- When STATUS is LOW, stay calm: no words like emergency, evacuate, danger, act now, immediately.
- For SENSOR_FAULT or STALE, say the reading cannot be trusted; do not describe the water as rising or falling.
- Do not write precautions yourself. Choose 2 to 4 ids from ALLOWED_PRECAUTIONS, most urgent first.
- Plain, calm English for residents. Short sentences. No jargon (no "ML", "snapshot", "rule engine").

Reply with ONLY one JSON object, no other text:
{"headline": "<max 80 characters>", "summary": "<1-3 sentences, max 420 characters>", "step_ids": ["<id>", ...], "pro_note": "<one sentence for engineers, max 240 characters, may mention ML agreement>"}"""


# ----------------------------------------------------------------------
# Facts given to the model (and used to check its numbers)
# ----------------------------------------------------------------------

def build_facts(snap):
    alert = snap.get("alert") or {}
    cur = snap.get("current") or {}
    trend = snap.get("trend") or {}
    fc = snap.get("forecast") or {}
    health = snap.get("sensor_health") or {}
    dev = snap.get("device") or {}
    facts = {
        "status": alert.get("status", "NO_DATA"),
        "rules_vs_ml": alert.get("agreement", "UNKNOWN"),
        "data_source": snap.get("data_source"),
        "window_minutes": snap.get("window_minutes", 5),
    }
    if cur:
        facts.update({
            "water_level_percent_of_flood_mark": round(cur["water_level"], 1),
            "rise_rate_percent_per_minute": round(cur["rise_rate"], 2),
            "rain_detected": bool(cur["rain"]),
            "risk_score_out_of_100": round(cur["risk_score"], 1),
            "drain_gate": cur["gate_status"],
        })
    if trend and trend.get("per_minute") is not None:
        facts.update({
            "trend_direction": trend["direction"],
            "level_change_points": trend["change"],
            "trend_minutes": round(trend["covered_minutes"], 1),
            "level_at_start_of_window": trend["start_level"],
        })
    if fc.get("predicted_level_5min") is not None:
        facts["forecast_minutes"] = 5
        facts["forecast_level_percent"] = round(fc["predicted_level_5min"], 1)
    if fc.get("ml_high_risk_probability") is not None:
        facts["ml_high_risk_probability_percent"] = round(fc["ml_high_risk_probability"], 1)
    if health:
        facts["sensor_health"] = health.get("status")
    if dev:
        facts["seconds_since_last_reading"] = round(dev.get("last_reading_age_s", 0))
    return facts


def _fact_numbers(facts):
    nums = []
    for v in facts.values():
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            nums.append(float(v))
            nums.append(float(round(v)))
            nums.append(abs(float(v)))
    return nums


_NUM_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")


def numbers_in(text):
    return [float(m) for m in _NUM_RE.findall(text or "")]


# ----------------------------------------------------------------------
# Calling the model
# ----------------------------------------------------------------------

def call_claude(system, user, api_key, model, timeout=TIMEOUT_S):
    """One Messages API call. Returns the reply text. Raises on any error."""
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 400,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("stop_reason") not in ("end_turn", "stop_sequence"):
        raise RuntimeError(f"stop_reason {data.get('stop_reason')}")
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def parse_reply(text):
    """Extract the single JSON object from the reply."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    obj = json.loads(text[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("reply is not a JSON object")
    return obj


# ----------------------------------------------------------------------
# Checking and applying the model's answer
# ----------------------------------------------------------------------

def apply_reply(template, reply, facts):
    """
    Returns (advisory, problems). The advisory is a copy of the template
    with AI wording applied; problems is empty when it is safe to show.
    """
    problems = []
    headline = reply.get("headline")
    summary = reply.get("summary")
    note = reply.get("pro_note", "")
    step_ids = reply.get("step_ids")

    if not isinstance(headline, str) or not headline.strip():
        problems.append("missing headline")
    elif len(headline) > MAX_HEADLINE:
        problems.append("headline too long")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("missing summary")
    elif len(summary) > MAX_SUMMARY:
        problems.append("summary too long")
    if not isinstance(note, str):
        problems.append("pro_note is not text")
        note = ""
    elif len(note) > MAX_NOTE:
        problems.append("pro_note too long")

    allowed = {s["id"]: s for s in template["pro"]["steps"]}
    if not isinstance(step_ids, list) or not all(isinstance(i, str) for i in step_ids):
        problems.append("step_ids is not a list of ids")
        step_ids = []
    if len(set(step_ids)) != len(step_ids):
        problems.append("duplicate step ids")
    if not MIN_STEPS <= len(step_ids) <= MAX_STEPS:
        problems.append(f"needs {MIN_STEPS}-{MAX_STEPS} steps, got {len(step_ids)}")
    for i in step_ids:
        if i not in allowed:
            problems.append(f"step {i} is not in the allowed list")
    if problems:
        return None, problems

    # Every number the model wrote must come from the facts.
    known = _fact_numbers(facts)
    for n in numbers_in(headline + " " + summary + " " + note):
        if not any(abs(n - k) <= NUMBER_TOLERANCE for k in known):
            problems.append(f"number {n:g} is not in the facts")

    status = facts["status"]
    own = (headline + " " + summary + " " + note).lower()
    if status in NOT_REASSURING_STATUSES:
        for pat in REASSURING + EXTRA_REASSURING:
            if re.search(pat, own):
                problems.append(f"reassuring phrase '{pat}' not allowed for {status}")
    if status in ("SENSOR_FAULT", "STALE", "NO_DATA"):
        for pat in TREND_WORDS:
            if re.search(pat, own):
                problems.append(f"trend claim '{pat}' not allowed when the reading is not trusted")

    adv = copy.deepcopy(template)
    adv["public"]["headline"] = headline.strip()
    adv["public"]["summary"] = summary.strip()
    adv["public"]["steps"] = [allowed[i] for i in step_ids]   # our text, not the model's
    if note.strip():
        adv["pro"]["ai_note"] = note.strip()

    # Same consistency checker the template uses (status, alarm words for
    # LOW, precaution text unchanged, disclaimer, simulated label).
    problems += check_advisory(adv, {"alert": {"status": status},
                                     "data_source": facts.get("data_source")})
    return adv, problems


# ----------------------------------------------------------------------
# The advisor with optional AI wording
# ----------------------------------------------------------------------

class LLMAdvisor:
    def __init__(self, api_key=None, model=None, enabled=True, call=call_claude,
                 refresh_s=REFRESH_S, background=True, log_path=LOG_PATH):
        self.base = Advisor()
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.enabled = bool(enabled and api_key)
        self.reason_off = None if self.enabled else (
            "no ANTHROPIC_API_KEY set" if enabled else "AI wording turned off (AQUA_LLM=off)")
        self.call = call
        self.refresh_s = refresh_s
        self.background = background
        self.log_path = log_path
        self._lock = threading.Lock()
        self._cache = {}          # key -> {"adv", "at", "worded_at"}
        self._running = set()     # keys with a call in progress
        self._failed = {}         # key -> time of last failed attempt (backoff)
        self._last_error = None

    def _key(self, snap):
        cur = snap.get("current") or {}
        level = cur.get("water_level")
        bucket = None if level is None else int(level // LEVEL_BUCKET)
        return self.base.key_for(snap) + (bucket,)

    def get(self, snap):
        template = self.base.get(snap)
        if not self.enabled:
            template["wording"] = {"engine": "template", "state": "off", "reason": self.reason_off}
            return template

        key = self._key(snap)
        with self._lock:
            hit = self._cache.get(key)
            now = time.monotonic()
            fresh = hit and now - hit["at"] < self.refresh_s
            backing_off = now - self._failed.get(key, -1e9) < self.refresh_s
            start = not fresh and key not in self._running and not backing_off
            if start:
                self._running.add(key)
            last_error = self._last_error

        if start:
            if self.background:
                threading.Thread(target=self._generate, args=(key, snap, template),
                                 daemon=True).start()
            else:
                self._generate(key, snap, template)
                with self._lock:
                    hit = self._cache.get(key)

        if hit:
            adv = self._merge(template, hit["adv"])
            adv["wording"] = {"engine": self.model, "state": "ai", "worded_at": hit["worded_at"]}
            return adv
        template["wording"] = {
            "engine": "template",
            "state": "pending" if key in self._running else "fallback",
            "reason": last_error,
        }
        return template

    @staticmethod
    def _merge(template, ai):
        """Fresh numbers/details from the template, wording from the AI."""
        adv = copy.deepcopy(template)
        adv["public"] = copy.deepcopy(ai["public"])
        if ai["pro"].get("ai_note"):
            adv["pro"]["ai_note"] = ai["pro"]["ai_note"]
        return adv

    def _generate(self, key, snap, template):
        facts = build_facts(snap)
        allowed = {s["id"]: s["text"] for s in template["pro"]["steps"]}
        user = json.dumps({
            "FACTS": facts,
            "ALLOWED_PRECAUTIONS": allowed,
            "CURRENT_TEMPLATE_MESSAGE": {
                "headline": template["public"]["headline"],
                "summary": template["public"]["summary"],
            },
        }, indent=1)

        started = time.monotonic()
        entry = {"time": datetime.now(timezone.utc).isoformat(), "model": self.model,
                 "status": facts["status"], "data_source": facts.get("data_source")}
        try:
            text = self.call(SYSTEM_PROMPT, user, self.api_key, self.model)
            reply = parse_reply(text)
            adv, problems = apply_reply(template, reply, facts)
            entry.update(reply=reply, problems=problems, accepted=not problems)
            with self._lock:
                if problems:
                    self._last_error = "AI answer rejected: " + "; ".join(problems[:3])
                    self._failed[key] = time.monotonic()
                else:
                    self._cache[key] = {"adv": adv, "at": time.monotonic(),
                                        "worded_at": datetime.now(timezone.utc).isoformat()}
                    self._failed.pop(key, None)
                    self._last_error = None
                    while len(self._cache) > 50:            # keep memory bounded
                        self._cache.pop(next(iter(self._cache)))
        except Exception as e:  # network, timeout, bad JSON, API error
            entry.update(error=f"{type(e).__name__}: {e}"[:300], accepted=False)
            with self._lock:
                self._last_error = f"AI unavailable ({type(e).__name__})"
                self._failed[key] = time.monotonic()
        finally:
            entry["latency_s"] = round(time.monotonic() - started, 2)
            with self._lock:
                self._running.discard(key)
            self._log(entry)

    def _log(self, entry):
        """One line per AI attempt, for the Phase 5 evaluation."""
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass


def build_advisor_from_env():
    return LLMAdvisor(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None,
        model=os.environ.get("AQUA_LLM_MODEL", "").strip() or None,
        enabled=os.environ.get("AQUA_LLM", "on").strip().lower() != "off",
    )