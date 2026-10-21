import json
import os
import numpy as np

from model import normalize, sigmoid

def make_dataset(n=2500, seed=42):
    """
    Generates controlled synthetic examples for Phase 1.

    Positive label = conditions that represent high/critical flood risk.
    The labels are generated from transparent physical-style rules, then
    small noise is added so the neural network has to learn a boundary.

    This is NOT a claim that the synthetic dataset represents real-world
    flood physics. Real field data should replace it in a later phase.
    """
    rng = np.random.default_rng(seed)

    water = rng.uniform(0, 100, n)
    rise = rng.uniform(0, 10, n)
    rain = rng.integers(0, 2, n)
    temp = rng.uniform(15, 45, n)
    humidity = rng.uniform(20, 100, n)

    # Synthetic target rule:
    # high water + rapid rise + rain -> more likely high/critical
    score = (
        0.45 * water +
        4.0 * rise +
        18.0 * rain +
        0.12 * np.maximum(humidity - 70, 0)
    )

    # Add small noise so the model learns a general boundary.
    score += rng.normal(0, 5, n)

    y = (score >= 55).astype(float).reshape(-1, 1)

    X = np.column_stack([water, rise, rain, temp, humidity])
    return normalize(X), y

def train_and_save(path, epochs=3000, lr=0.08):
    X, y = make_dataset()

    rng = np.random.default_rng(7)
    W1 = rng.normal(0, 0.5, (5, 8))
    b1 = np.zeros((1, 8))
    W2 = rng.normal(0, 0.5, (8, 1))
    b2 = np.zeros((1, 1))

    for epoch in range(epochs):
        # Forward
        z1 = X @ W1 + b1
        h = np.tanh(z1)
        z2 = h @ W2 + b2
        pred = sigmoid(z2)

        # Binary cross entropy derivative for sigmoid output
        dz2 = pred - y
        dW2 = h.T @ dz2 / len(X)
        db2 = np.mean(dz2, axis=0, keepdims=True)

        dh = dz2 @ W2.T
        dz1 = dh * (1 - h * h)
        dW1 = X.T @ dz1 / len(X)
        db1 = np.mean(dz1, axis=0, keepdims=True)

        W1 -= lr * dW1
        b1 -= lr * db1
        W2 -= lr * dW2
        b2 -= lr * db2

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "W1": W1.tolist(),
            "b1": b1.tolist(),
            "W2": W2.tolist(),
            "b2": b2.tolist()
        }, f)

    print(f"Custom AquaSentinel model saved to: {path}")

if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    train_and_save(os.path.join(root, "ml", "model_weights.json"))
