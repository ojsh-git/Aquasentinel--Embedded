MAX_LEVEL_CM = 11


def calculate_prediction(level_cm, rise_rate):

    predicted_cm = level_cm + (rise_rate * 5)

    if predicted_cm > MAX_LEVEL_CM:
        predicted_cm = MAX_LEVEL_CM

    predicted_percentage = (
        predicted_cm / MAX_LEVEL_CM
    ) * 100

    return predicted_percentage


def get_risk_level(score):

    if score < 25:
        return "LOW"

    elif score < 50:
        return "MODERATE"

    elif score < 75:
        return "HIGH"

    else:
        return "CRITICAL"


def get_recommendation(level):

    if level == "LOW":
        return "Continue monitoring"

    elif level == "MODERATE":
        return "Monitor water rise"

    elif level == "HIGH":
        return "Issue local warning"

    elif level == "CRITICAL":
        return "Emergency warning / open drainage"

    return "Waiting for data"