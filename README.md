# AquaSentinel — Online Phase 1

This is the software-first Phase 1 implementation of the AquaSentinel flood monitoring project.

## Architecture

ESP32 (later)
    -> HTTP POST
Flask API
    -> SQLite
    -> Risk Engine
    -> Custom ML model
    -> Dashboard

For now, `simulator.py` replaces the ESP32 so the entire online system can be tested before hardware integration.

## What is implemented

- Live water level, rise rate, rainfall, temperature and humidity
- 0–100 rule-based risk score
- LOW / MODERATE / HIGH / CRITICAL risk levels
- 5-minute water-level prediction
- Small neural-network model trained by this project on generated flood-like data
- SQLite historical data
- REST API
- Live dashboard
- Scenario simulator
- Ready-to-replace ESP32 HTTP endpoint

## 1. Install

Python 3.10+ recommended.

```bash
cd AquaSentinel_Online_Phase1
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
```

Windows:
```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Start server

```bash
python backend/app.py
```

Open:
http://127.0.0.1:5000

## 3. Run simulator

In another terminal:

```bash
source .venv/bin/activate
python backend/simulator.py
```

The simulator sends changing sensor readings to the same API that the future ESP32 will use.

## 4. Train the custom model

The server automatically trains the model if `ml/model_weights.json` does not exist.

You can retrain it manually:

```bash
python ml/train_model.py
```

## 5. API

POST `/api/reading`

Example:

```json
{
  "water_level": 62,
  "rise_rate": 3.2,
  "rain": 1,
  "temperature": 29.4,
  "humidity": 72
}
```

GET `/api/latest`

GET `/api/history?limit=50`

GET `/api/predict`

GET `/api/health`

## Hardware integration later

The ESP32 will POST the same JSON structure to:

`http://<computer-or-server-ip>:5000/api/reading`

The dashboard and backend do not need to change.
