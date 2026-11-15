# 🌊 AquaSentinel

**AquaSentinel** is an IoT flood-monitoring system. An ESP32 sensor node sends water level, rainfall, temperature and humidity readings to a Flask backend. The backend calculates a flood risk score, predicts the near-future water level with a small neural network, and shows everything on a live dashboard along with safety advice.

Until the hardware is connected, a built-in **simulator** replaces the ESP32, so the whole system can be tested end to end.

## Features

- Live monitoring of water level, rise rate, rainfall, temperature and humidity
- **Risk score (0–100)** with LOW / MODERATE / HIGH / CRITICAL levels
- **5-minute water-level prediction** from a small neural network trained on generated flood-like data
- **Advisor** that gives safety precautions for each risk level, with optional AI-written wording using Claude
- **Sensor health checks** to catch faulty or out-of-range readings
- SQLite storage of all historical readings
- REST API and live web dashboard
- Scenario-based simulator for testing without hardware
- ESP32-ready HTTP endpoint

## Architecture

```
ESP32 sensors (or simulator)
        │  HTTP POST (JSON)
        ▼
   Flask REST API ──► SQLite database
        │
        ├──► Risk engine (rule-based score)
        ├──► Neural-network model (5-minute prediction)
        ├──► Sensor health checks
        └──► Advisor (templates + optional Claude wording)
        │
        ▼
   Live dashboard
```

## Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Machine learning:** Small neural network built with NumPy
- **Frontend:** HTML, CSS, JavaScript
- **Hardware:** ESP32 with water level, rain, temperature and humidity sensors
- **AI advisor (optional):** Claude via the Anthropic API

## Project Structure

```
Aquasentinel--Embedded/
├── backend/
│   ├── app.py                    # Flask server and API routes
│   ├── calculations.py          # Risk score and rise-rate calculations
│   ├── advisor.py               # Advisor logic
│   ├── llm_advisor.py           # Optional AI-written advice
│   ├── precautions.py           # Precautions for each risk level
│   ├── sensor_health.py         # Sensor validation
│   ├── snapshot.py              # Recent-window snapshots
│   ├── simulator.py             # Simulated ESP32 sensor data
│   ├── esp32.ino                # ESP32 firmware sketch
│   └── esp32_payload_example.json
├── database/
│   └── aquasentinel.sql         # Database schema
├── ml/                          # Model training and prediction
├── frontend/                    # Live dashboard
├── tests/                       # Tests
├── LICENSE
└── requirements.txt
```

## Getting Started

Requires Python 3.9 or newer.

### 1. Clone and install

```bash
git clone https://github.com/ojsh-git/Aquasentinel--Embedded.git
cd Aquasentinel--Embedded
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
```

Windows:
```powershell
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start the server

```bash
python backend/app.py
```

Open http://127.0.0.1:5001

### 3. Run the simulator

In a second terminal:

```bash
source venv/bin/activate
python backend/simulator.py
```

The simulator sends changing readings to the same API the ESP32 will use, so the dashboard fills with live data.

### 4. Train the model (optional)

The server trains the model automatically if `ml/model_weights.json` does not exist. To retrain it manually:

```bash
python ml/train_model.py
```

### 5. Enable the AI advisor (optional)

The advisor always gives template-based safety advice. If you add an Anthropic API key, it also generates AI-written wording on top.

```bash
export ANTHROPIC_API_KEY="your_key_here"
python backend/app.py
```

Without a key the AI layer stays off and everything else works normally. You can also turn it off explicitly:

```bash
export AQUA_LLM=off
```

Never commit your API key to the repository.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/reading` | Submit a sensor reading |
| GET | `/api/latest` | Latest reading with risk score and level |
| GET | `/api/history?limit=50` | Recent historical readings |
| GET | `/api/snapshot?minutes=5` | Summary of the recent time window |
| GET | `/api/advisory` | Current safety advice |
| GET | `/api/predict` | 5-minute water-level prediction |
| GET | `/api/health` | Server health check |

Example request body for `POST /api/reading`:

```json
{
  "water_level": 62,
  "rise_rate": 3.2,
  "rain": 1,
  "temperature": 29.4,
  "humidity": 72
}
```

## Hardware Integration

The ESP32 sends the same JSON structure to:

`http://<server-ip>:5001/api/reading`

See `backend/esp32_payload_example.json` for an example. The backend and dashboard need no changes when the real hardware replaces the simulator.

<!-- Add a dashboard screenshot at screenshots/dashboard.png, then delete this line and the closing marker below, and remove nothing else:
## Screenshots

![Dashboard](screenshots/dashboard.png)
-->

## Security

**Measures in place**
- The Anthropic API key is read from an environment variable (`ANTHROPIC_API_KEY`) and never stored in the code or the repository.
- `.gitignore` excludes `.env` files, the runtime database, advisor logs, model weights and the virtual environment.
- The AI advisor is optional. Without a key, the system falls back to template-based advice.
- Incoming sensor readings go through health checks (`sensor_health.py`) to catch faulty or out-of-range values.
- The repository's commit history is kept intact as a record of authorship.

**Known limitations (development version)**
- The server uses Flask's development server and is meant for local and lab use only.
- `/api/reading` has no authentication, so any device on the same network can post readings.

**Before any real deployment**
- Turn off debug mode and run behind a production WSGI server (e.g. Gunicorn) with HTTPS.
- Add a device token that the ESP32 must send with every reading.
- Restrict network access to trusted devices.

## Future Improvements

- Connect the real ESP32 hardware
- Send SMS or app alerts when risk reaches HIGH or CRITICAL
- Train the model on real sensor data
- Deploy to a cloud server

## Team

AquaSentinel is a team project built by:

| Name | GitHub | Role |
|------|--------|------|
| Ojas Sharma | [@ojsh-git](https://github.com/ojsh-git) | [your role] |
| Toshi Singh | [@username](https://github.com/username) | [role] |
| R Kanish | [@username](https://github.com/username) | [role] |

## License and Copyright

Copyright © 2026 Ojas Sharma, Toshi Singh and R Kanish. All rights reserved.

This repository is public for viewing and portfolio purposes only. Copying, modifying, redistributing or presenting this work as your own is not permitted without written permission from the authors. See the [LICENSE](LICENSE) file.

Original development history, including commit authorship and timestamps, is preserved in this repository.
