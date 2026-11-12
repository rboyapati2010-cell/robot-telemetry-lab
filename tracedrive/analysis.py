"""CSV validation and deterministic, time-weighted telemetry analysis.

Only standard-library dependencies are used. Thresholds are illustrative and
must not be interpreted as limits for a particular robot or battery.
"""

from __future__ import annotations

import csv
import io
import math
from typing import Any

FIELDS = (
    "time_s", "target_velocity_mps", "velocity_mps", "battery_v",
    "motor_current_a", "temperature_c",
)
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_SAMPLES = 20_000
THRESHOLDS = {
    "tracking_error_mps": 0.35,
    "battery_v": 10.5,
    "current_a": 8.0,
    "temperature_c": 60.0,
}
BOUNDS = {
    "time_s": (0.0, 86_400.0),
    "target_velocity_mps": (-50.0, 50.0),
    "velocity_mps": (-50.0, 50.0),
    "battery_v": (0.0, 100.0),
    "motor_current_a": (-200.0, 200.0),
    "temperature_c": (-50.0, 200.0),
}


class ValidationError(ValueError):
    """A readable input validation failure; safe to return to the client."""


def parse_csv(text: str) -> list[dict[str, float]]:
    """Validate and parse CSV. Reject the whole run if any record is invalid."""
    if not isinstance(text, str):
        raise ValidationError("csv must be a UTF-8 CSV string.")
    try:
        encoded_size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValidationError("CSV must contain valid UTF-8 text.") from None
    if encoded_size > MAX_CSV_BYTES:
        raise ValidationError("CSV exceeds the 2 MiB size limit.")
    if "\x00" in text:
        raise ValidationError("CSV contains a NUL character.")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    try:
        header = reader.fieldnames
        if not header:
            raise ValidationError("CSV is empty; include the six required column headers.")
        if len(set(header)) != len(header):
            raise ValidationError("CSV header contains duplicate column names.")
        missing = sorted(set(FIELDS) - set(header))
        extra = sorted(set(header) - set(FIELDS))
        if missing or extra:
            problems = []
            if missing:
                problems.append("missing " + ", ".join(missing))
            if extra:
                problems.append("unexpected " + ", ".join(extra))
            raise ValidationError("CSV header: " + "; ".join(problems) + ".")

        samples = []
        for row in reader:
            line = reader.line_num
            if len(samples) >= MAX_SAMPLES:
                raise ValidationError(f"Row {line}: maximum {MAX_SAMPLES:,} samples per run.")
            if None in row or any(row[field] is None for field in FIELDS):
                raise ValidationError(f"Row {line}: expected exactly six values.")
            sample = {}
            for field in FIELDS:
                raw = row[field]
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    raise ValidationError(f"Row {line}, {field}: expected a number.") from None
                if not math.isfinite(value):
                    raise ValidationError(f"Row {line}, {field}: value must be finite.")
                low, high = BOUNDS[field]
                if not low <= value <= high:
                    raise ValidationError(f"Row {line}, {field}: must be between {low:g} and {high:g}.")
                sample[field] = value
            if samples and sample["time_s"] <= samples[-1]["time_s"]:
                raise ValidationError(f"Row {line}, time_s: timestamps must strictly increase.")
            samples.append(sample)
    except csv.Error as exc:
        raise ValidationError(f"Row {reader.line_num}: malformed CSV ({exc}).") from None
    if len(samples) < 2:
        raise ValidationError("At least two samples are required to measure a run.")
    return samples


def _segments(samples: list[dict[str, float]], *, kind: str, field: str,
              threshold: float, below: bool, units: str) -> list[dict[str, Any]]:
    events = []
    active: list[tuple[dict[str, float], float]] = []

    def finish() -> None:
        if not active:
            return
        peak = (min if below else max)(value for _, value in active)
        comparison = "below" if below else "above"
        labels = {
            "tracking_error": "Absolute velocity error", "low_battery": "Battery voltage",
            "high_current": "Motor current", "high_temperature": "Temperature",
        }
        events.append({
            "kind": kind,
            "start_s": active[0][0]["time_s"],
            "end_s": active[-1][0]["time_s"],
            "peak_value": round(peak, 6),
            "threshold": threshold,
            "detail": f"{labels[kind]} {comparison} the illustrative {threshold:g} {units} threshold in {len(active)} consecutive sample(s).",
        })
        active.clear()

    for sample in samples:
        value = (abs(sample["velocity_mps"] - sample["target_velocity_mps"])
                 if field == "error" else sample[field])
        is_active = value < threshold if below else value > threshold
        if is_active:
            active.append((sample, value))
        else:
            finish()
    finish()
    return events


def analyze(samples: list[dict[str, float]]) -> dict[str, Any]:
    """Analyze validated samples with trapezoidal integration over time."""
    if len(samples) < 2:
        raise ValidationError("At least two samples are required.")
    duration = samples[-1]["time_s"] - samples[0]["time_s"]
    if duration <= 0:
        raise ValidationError("Run duration must be positive.")
    errors = [abs(sample["velocity_mps"] - sample["target_velocity_mps"]) for sample in samples]
    integrated_abs = 0.0
    integrated_sq = 0.0
    for index in range(1, len(samples)):
        dt = samples[index]["time_s"] - samples[index-1]["time_s"]
        if dt <= 0:
            raise ValidationError("Timestamps must strictly increase.")
        a, b = errors[index-1], errors[index]
        integrated_abs += dt * (a + b) / 2
        integrated_sq += dt * (a*a + b*b) / 2
    metrics = {
        "mae_mps": integrated_abs / duration,
        "rmse_mps": math.sqrt(integrated_sq / duration),
        "peak_error_mps": max(errors),
        "min_battery_v": min(sample["battery_v"] for sample in samples),
        "peak_current_a": max(sample["motor_current_a"] for sample in samples),
        "peak_temperature_c": max(sample["temperature_c"] for sample in samples),
    }
    specs = [
        ("tracking_error", "error", THRESHOLDS["tracking_error_mps"], False, "m/s"),
        ("low_battery", "battery_v", THRESHOLDS["battery_v"], True, "V"),
        ("high_current", "motor_current_a", THRESHOLDS["current_a"], False, "A"),
        ("high_temperature", "temperature_c", THRESHOLDS["temperature_c"], False, "C"),
    ]
    anomalies = [event for kind, field, threshold, below, units in specs
                 for event in _segments(samples, kind=kind, field=field,
                                        threshold=threshold, below=below, units=units)]
    anomalies.sort(key=lambda event: (event["start_s"], event["kind"]))
    return {
        "sample_count": len(samples), "duration_s": round(duration, 6),
        "metrics": {name: round(value, 6) for name, value in metrics.items()},
        "anomaly_count": len(anomalies), "anomalies": anomalies,
    }


def validate_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name must be a non-empty string.")
    name = name.strip()
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        raise ValidationError("name must contain valid UTF-8 text.") from None
    if len(name) > 80:
        raise ValidationError("name must contain at most 80 characters.")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValidationError("name must not contain control characters.")
    return name
