"""SQLite persistence, with one short-lived connection per operation."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .analysis import analyze, parse_csv, validate_name
from .demo import sample_csv


class RunNotFound(LookupError):
    pass


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                samples_json TEXT NOT NULL,
                anomalies_json TEXT NOT NULL
            )""")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _prepare(name: str, text: str, source: str) -> tuple[dict, list, list]:
        name = validate_name(name)
        samples = parse_csv(text)
        analysis = analyze(samples)
        anomalies = analysis.pop("anomalies")
        metadata = {
            "id": "run_" + uuid4().hex[:16], "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source, **analysis,
        }
        return metadata, samples, anomalies

    @staticmethod
    def _insert(conn: sqlite3.Connection, prepared: tuple[dict, list, list]) -> dict:
        metadata, samples, anomalies = prepared
        conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)", (
            metadata["id"], metadata["created_at"], json.dumps(metadata, allow_nan=False),
            json.dumps(samples, allow_nan=False), json.dumps(anomalies, allow_nan=False),
        ))
        return metadata

    def add(self, name: str, text: str) -> dict:
        prepared = self._prepare(name, text, "uploaded_csv")
        with self.connect() as conn:
            return self._insert(conn, prepared)

    def list_runs(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT metadata_json FROM runs ORDER BY rowid DESC").fetchall()
        return [json.loads(row["metadata_json"]) for row in rows]

    def get(self, run_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound("Run not found.")
        return {
            "run": json.loads(row["metadata_json"]),
            "samples": json.loads(row["samples_json"]),
            "anomalies": json.loads(row["anomalies_json"]),
        }

    def compare(self, left: str, right: str) -> dict:
        left_run, right_run = self.get(left)["run"], self.get(right)["run"]
        deltas = {key: round(right_run["metrics"][key] - value, 6)
                  for key, value in left_run["metrics"].items()}
        deltas["duration_s"] = round(right_run["duration_s"] - left_run["duration_s"], 6)
        return {"left": left_run, "right": right_run, "deltas": deltas}

    def seed(self) -> dict:
        baseline = self._prepare("Baseline / synthetic", sample_csv(), "synthetic_demo")
        tuned = self._prepare("Tuned / synthetic", sample_csv(tuned=True), "synthetic_demo")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM runs LIMIT 1").fetchone():
                rows = conn.execute("SELECT metadata_json FROM runs ORDER BY rowid DESC").fetchall()
                return {"seeded": False, "runs": [json.loads(row["metadata_json"]) for row in rows]}
            runs = [self._insert(conn, baseline), self._insert(conn, tuned)]
            return {"seeded": True, "runs": runs}
