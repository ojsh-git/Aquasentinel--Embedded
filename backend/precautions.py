"""
Approved precaution list for the AquaSentinel advisory agent.

The agent may ONLY show precautions from this file. It never writes new
safety advice. Every item is a short paraphrase of official Indian flood
guidance, with its source:

  NDMA - National Disaster Management Authority, "Flood: Do's and Don'ts"
         https://sphereindia.org.in/sites/default/files/2022-07/Flood%20Do%27s%20and%20Don%27ts%20%28210%20%C3%97%20297%20mm%29.pdf
  IMD  - India Meteorological Department, "Floods: Do's and Don'ts"
         https://www.imdnagpur.gov.in/docs_general/Floods_Dos_and_Donts.pdf

The team should review this list before any public demo. To change advice,
edit this file only.
"""

PRECAUTIONS = {
    # --- Stay informed / get ready (LOW, MODERATE) ---
    "INFO_UPDATES":   {"text": "Follow official weather and flood updates on radio, TV or SMS.", "source": "NDMA, IMD"},
    "INFO_RUMOURS":   {"text": "Ignore rumours. Stay calm and rely on official information.", "source": "IMD"},
    "PREP_PHONE":     {"text": "Keep your mobile phone charged for emergency calls and SMS.", "source": "IMD"},
    "PREP_KIT":       {"text": "Keep an emergency kit ready: drinking water, ready-to-eat food, torch, first-aid box and medicines.", "source": "IMD"},
    "PREP_DOCS":      {"text": "Put important documents and valuables in waterproof bags.", "source": "IMD"},
    "PREP_ROUTE":     {"text": "Know the safe route to the nearest shelter or raised pucca building.", "source": "IMD"},
    "PREP_DRAINS":    {"text": "Be aware of nearby drains, canals and streams. They can flood suddenly.", "source": "NDMA, IMD"},
    "PREP_FAMILY":    {"text": "Agree on a family communication plan in case you get separated.", "source": "IMD"},

    # --- Act now (HIGH) ---
    "ACT_ELEVATE":    {"text": "Move essential items, furniture and appliances to a higher place.", "source": "NDMA, IMD"},
    "ACT_POWER":      {"text": "If instructed, switch off electricity and gas at the main switch and unplug appliances.", "source": "NDMA, IMD"},
    "ACT_AVOID_WATER":{"text": "Do not walk or drive through flood water. Two feet of moving water can sweep away a car.", "source": "NDMA, IMD"},
    "ACT_AVOID_DRAINS":{"text": "Stay away from drains, gutters, culverts and open manholes.", "source": "IMD"},
    "ACT_AVOID_POLES":{"text": "Stay away from electric poles and fallen power lines.", "source": "IMD"},
    "ACT_EVACUATE_READY": {"text": "Be ready to leave. Evacuate immediately if officials tell you to.", "source": "IMD"},

    # --- Emergency (CRITICAL) ---
    "EMG_HIGHER":     {"text": "Move to higher ground or a safe shelter now, if you can do so safely.", "source": "NDMA, IMD"},
    "EMG_TAKE_KIT":   {"text": "Take your emergency kit, medicines and documents with you.", "source": "IMD"},
    "EMG_CAR":        {"text": "If water rises around your car, leave it and move to higher ground if you can do so safely.", "source": "NDMA"},
    "EMG_WET_ELEC":   {"text": "Do not touch electrical equipment if you are wet or standing in water.", "source": "NDMA"},
    "EMG_STICK":      {"text": "If you must walk in water, walk where it is not moving and use a stick to check the ground ahead.", "source": "NDMA, IMD"},

    # --- Sensor problem / no data (SENSOR_FAULT, STALE, NO_DATA) ---
    "FAULT_NO_RELY":  {"text": "This reading may be wrong. Do not use it to decide that conditions are fine.", "source": "AquaSentinel"},
    "FAULT_LOOK":     {"text": "Check the water level by other means, such as looking at the drain or asking local officials.", "source": "AquaSentinel"},
    "FAULT_CHECK_NODE":{"text": "Check the sensor node: power, Wi-Fi and whether something is blocking the sensor.", "source": "AquaSentinel"},
}

# Which precautions belong to each alert status, in display order.
# The agent may pick a subset from this list, never anything outside it.
STATUS_PRECAUTIONS = {
    "LOW":          ["INFO_UPDATES", "PREP_PHONE", "PREP_KIT", "PREP_DRAINS"],
    "MODERATE":     ["INFO_UPDATES", "PREP_PHONE", "PREP_DOCS", "PREP_ROUTE", "PREP_DRAINS", "INFO_RUMOURS"],
    "HIGH":         ["ACT_ELEVATE", "ACT_AVOID_WATER", "ACT_AVOID_DRAINS", "ACT_POWER", "ACT_AVOID_POLES",
                     "ACT_EVACUATE_READY", "PREP_DOCS"],
    "CRITICAL":     ["EMG_HIGHER", "ACT_AVOID_WATER", "EMG_WET_ELEC", "EMG_TAKE_KIT", "EMG_CAR", "EMG_STICK",
                     "ACT_AVOID_POLES"],
    "SENSOR_FAULT": ["FAULT_NO_RELY", "FAULT_LOOK", "FAULT_CHECK_NODE", "INFO_UPDATES"],
    "STALE":        ["FAULT_NO_RELY", "FAULT_CHECK_NODE", "FAULT_LOOK", "INFO_UPDATES"],
    "NO_DATA":      ["FAULT_CHECK_NODE", "INFO_UPDATES"],
}

# Extra "get ready" items allowed when the level is LOW/MODERATE but rising
# fast or forecast to become high. Status stays the same; advice gets earlier.
RISING_EXTRA = ["PREP_KIT", "PREP_DOCS", "ACT_ELEVATE", "PREP_ROUTE"]

DISCLAIMER = (
    "AquaSentinel is a student prototype, not an official flood warning. "
    "Always follow instructions from local authorities. In an emergency call 112."
)
