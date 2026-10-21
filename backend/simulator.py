# import requests
# import time
# import math
# import random

# URL = "http://127.0.0.1:5001/api/reading"

# level = 15.0
# previous = level

# print("AquaSentinel simulator started.")
# print("Press Ctrl+C to stop.")

# try:
#     while True:
#         # Gradually create a flood-like scenario.
#         # This lets the complete online system be tested without hardware.
#         increase = random.uniform(0.5, 2.5)
#         level = min(98, level + increase)
#         rise_rate = level - previous
#         previous = level

#         rain = 1 if level > 30 or random.random() > 0.82 else 0
#         temperature = 28 + random.uniform(-1.5, 2.5)
#         humidity = min(98, 65 + level * 0.25 + random.uniform(-3, 3))

#         payload = {
#             "water_level": round(level, 2),
#             "rise_rate": round(rise_rate, 2),
#             "rain": rain,
#             "temperature": round(temperature, 1),
#             "humidity": round(humidity, 1)
#         }

#         try:
#             response = requests.post(URL, json=payload, timeout=3)
#             print(response.json())
#         except Exception as e:
#             print("Server error:", e)

#         if level >= 98:
#             print("Simulation reached critical water level. Restarting scenario.")
#             level = 10
#             previous = level

#         time.sleep(2)

# except KeyboardInterrupt:
#     print("\nSimulator stopped.")
import requests
import time
import random

URL = "http://127.0.0.1:5001/api/reading"

level = 15.0
previous = level

print("AquaSentinel simulator started.")
print("Press Ctrl+C to stop.")

try:
    while True:

        # Simulate increasing water level
        increase = random.uniform(0.5, 2.5)
        level = min(98, level + increase)

        # Calculate rate of rise
        rise_rate = level - previous
        previous = level

        # Simulate rain
        rain = 1 if level > 30 or random.random() > 0.82 else 0

        # Simulate environmental values
        temperature = 28 + random.uniform(-1.5, 2.5)
        humidity = min(
            98,
            65 + level * 0.25 + random.uniform(-3, 3)
        )

        payload = {
            "water_level": round(level, 2),
            "rise_rate": round(rise_rate, 2),
            "rain": rain,
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1)
        }

        try:
            response = requests.post(
                URL,
                json=payload,
                timeout=3
            )

            print("Status:", response.status_code)

            if response.status_code == 200:
                data = response.json()

                print(
                    f"Water: {data['water_level']}% | "
                    f"Risk: {data['risk_level']} "
                    f"({data['risk_score']}) | "
                    f"Prediction: {data['predicted_level']}% | "
                    f"ML: {data['ml_high_risk_probability']}% | "
                    f"Gate: {data['gate_status']}"
                )

            else:
                print("Server response:", response.text)

        except requests.exceptions.RequestException as e:
            print("Connection error:", e)

        if level >= 98:
            print("Simulation reached critical water level.")
            print("Restarting scenario...\n")

            level = 10
            previous = level

        time.sleep(2)

except KeyboardInterrupt:
    print("\nSimulator stopped.")