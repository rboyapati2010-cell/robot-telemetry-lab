"""Deterministic illustrative data. These are not real robot measurements."""

import csv
import io
import math

from .analysis import FIELDS


def sample_csv(*, tuned: bool = False) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FIELDS)
    for index in range(301):
        t = index / 10
        target = 0.0 if t < 2 or t >= 27 else (1.4 if t < 12 else 2.0 if t < 22 else 0.8)
        # An explicit simulation equation, not an inferred model of a real robot.
        disturbance = 0.48 if 14 <= t <= 18 else 0.0
        tracking = (0.04 if tuned else 0.16) + (0.025 if tuned else 0.13) * math.sin(t * 2.1)
        velocity = max(0, target - tracking - disturbance * (0.22 if tuned else 1))
        battery = 12.5 - 0.035 * t - (0.4 if tuned else 1.65) * (14 <= t <= 18)
        current = 1.2 + target * 1.7 + (1.4 if tuned else 5.2) * (14 <= t <= 18)
        temperature = 29 + t * (0.50 if tuned else 1.15)
        writer.writerow([f"{v:.4f}" for v in (t, target, velocity, battery, current, temperature)])
    return output.getvalue()
