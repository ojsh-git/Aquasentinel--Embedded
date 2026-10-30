from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "aquasentinel.db")
FRONTEND = os.path.join(ROOT, "frontend")

sys.path.insert(0, os.path.join(ROOT, "ml"))
from model import FloodModel

app = Flask(__name__, static_folder=FRONTEND, static_url_path="")

MODEL = FloodModel(os.path.join(ROOT, "ml", "model_weights.json"))

@app.after_request
def allow_dashboard(resp):
       resp.headers["Access-Control-Allow-Origin"] = "*"
       resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
       resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
       return resp

def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            water_level REAL NOT NULL,
            rise_rate REAL NOT NULL,
            rain INTEGER NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            risk_score REAL NOT NULL,
            risk_level TEXT NOT NULL,
            predicted_level REAL NOT NULL,
            gate_status TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def calculate_risk(water_level, rise_rate, rain, temperature, humidity):
    # Phase-1 transparent rule engine.
    # 40 points: current water level
    # 30 points: rate of rise
    # 20 points: rain
    # 10 points: environmental condition
    level_points = clamp(water_level / 100 * 40)

    # 0 cm/min -> 0, 5 cm/min or more -> 30
    rise_points = clamp(rise_rate / 5 * 30)

    if rain >= 0.75:
        rain_points = 20
    elif rain >= 0.30:
        rain_points = 12
    else:
        rain_points = 0

    # Environmental contribution is deliberately small.
    # It is a supporting signal, not a claim that temperature itself causes flooding.
    env_points = 0
    if humidity >= 85:
        env_points += 5
    if temperature >= 35:
        env_points += 5

    score = round(clamp(level_points + rise_points + rain_points + env_points), 1)

    if score < 25:
        level = "LOW"
    elif score < 50:
        level = "MODERATE"
    elif score < 75:
        level = "HIGH"
    else:
        level = "CRITICAL"

    return score, level

def predict_next_level(water_level, rise_rate, minutes=5):
    return round(clamp(water_level + rise_rate * minutes), 1)

def gate_for(level):
    if level in ("HIGH", "CRITICAL"):
        return "OPEN"
    return "CLOSED"

def model_probability(water_level, rise_rate, rain, temperature, humidity):
    # Our custom model predicts probability of HIGH/CRITICAL conditions.
    return MODEL.predict([water_level, rise_rate, rain, temperature, humidity])

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")

@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND, path)

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "AquaSentinel API"})

@app.post("/api/reading")
def add_reading():
    payload = request.get_json(silent=True) or {}
    required = ["water_level", "rise_rate", "rain", "temperature", "humidity"]
    missing = [k for k in required if k not in payload]
    if missing:
        return jsonify({"error": "Missing fields", "fields": missing}), 400

    try:
        water_level = float(payload["water_level"])
        rise_rate = float(payload["rise_rate"])
        rain = float(payload["rain"])
        temperature = float(payload["temperature"])
        humidity = float(payload["humidity"])
    except (TypeError, ValueError):
        return jsonify({"error": "All sensor fields must be numeric"}), 400

    water_level = clamp(water_level)
    rise_rate = max(0, rise_rate)
    rain = clamp(rain, 0, 1)
    humidity = clamp(humidity)
    risk_score, risk_level = calculate_risk(
        water_level, rise_rate, rain, temperature, humidity
    )

    predicted_level = predict_next_level(water_level, rise_rate, 5)
    ml_probability = round(model_probability(
        water_level, rise_rate, rain, temperature, humidity
    ) * 100, 1)

    # Final display decision: transparent risk engine remains authoritative.
    # ML is an additional predictive signal in Phase 1.
    gate_status = gate_for(risk_level)
    timestamp = datetime.now(timezone.utc).isoformat()

    con = db()
    con.execute("""
        INSERT INTO readings
        (timestamp, water_level, rise_rate, rain, temperature, humidity,
         risk_score, risk_level, predicted_level, gate_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp, water_level, rise_rate, int(rain >= 0.5),
        temperature, humidity, risk_score, risk_level,
        predicted_level, gate_status
    ))
    con.commit()
    con.close()

    return jsonify({
        "timestamp": timestamp,
        "water_level": water_level,
        "rise_rate": rise_rate,
        "rain": int(rain >= 0.5),
        "temperature": temperature,
        "humidity": humidity,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "predicted_level": predicted_level,
        "prediction_minutes": 5,
        "ml_high_risk_probability": ml_probability,
        "gate_status": gate_status
    })

@app.get("/api/latest")
def latest():
    con = db()
    row = con.execute(
        "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()

    if not row:
        return jsonify({"message": "No readings yet"}), 404

    return jsonify(dict(row))

@app.get("/api/history")
def history():
    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 500))
    con = db()
    rows = con.execute(
        "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()

    return jsonify([dict(r) for r in reversed(rows)])

@app.get("/api/predict")
def predict():
    con = db()
    row = con.execute(
        "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()

    if not row:
        return jsonify({"message": "No readings yet"}), 404

    return jsonify({
        "current_level": row["water_level"],
        "rise_rate": row["rise_rate"],
        "prediction_minutes": 5,
        "predicted_level": row["predicted_level"],
        "ml_high_risk_probability": MODEL.predict([
            row["water_level"], row["rise_rate"], row["rain"],
            row["temperature"], row["humidity"]
        ])
    })

if __name__ == "__main__":
    init_db()
    print("AquaSentinel API running at http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
else:
    init_db()
