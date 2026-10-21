import json
import os
import numpy as np

FEATURE_MIN = np.array([0, 0, 0, 15, 20], dtype=float)
FEATURE_MAX = np.array([100, 10, 1, 45, 100], dtype=float)

def normalize(x):
    x = np.asarray(x, dtype=float)
    return (x - FEATURE_MIN) / (FEATURE_MAX - FEATURE_MIN + 1e-9)

def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -50, 50)))

class FloodModel:
    """
    Small neural network created for AquaSentinel.

    Architecture:
        5 sensor inputs
          -> 8 hidden neurons (tanh)
          -> 1 sigmoid output

    It is trained from generated flood-like examples by train_model.py.
    No pretrained flood model or external model is used.
    """

    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            # Allow the app to create a model automatically.
            from train_model import train_and_save
            train_and_save(path)
        with open(path, "r") as f:
            p = json.load(f)
        self.W1 = np.array(p["W1"], dtype=float)
        self.b1 = np.array(p["b1"], dtype=float)
        self.W2 = np.array(p["W2"], dtype=float)
        self.b2 = np.array(p["b2"], dtype=float)

    def predict(self, features):
        x = normalize(features).reshape(1, -1)
        h = np.tanh(x @ self.W1 + self.b1)
        y = sigmoid(h @ self.W2 + self.b2)
        return float(y[0, 0])
