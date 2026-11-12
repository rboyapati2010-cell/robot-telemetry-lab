import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tracedrive.analysis import ValidationError
from tracedrive.demo import sample_csv
from tracedrive.store import RunNotFound, Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runs.sqlite3"
        self.store = Store(self.path)

    def test_import_survives_reopening_database(self):
        run = self.store.add("Morning run", sample_csv())
        reloaded = Store(self.path).get(run["id"])
        self.assertEqual(reloaded["run"], run)
        self.assertEqual(len(reloaded["samples"]), 301)
        self.assertEqual(run["source"], "uploaded_csv")

    def test_invalid_import_never_creates_partial_run(self):
        with self.assertRaises(ValidationError):
            self.store.add("Broken", "time_s\n0\n")
        self.assertEqual(self.store.list_runs(), [])

    def test_demo_seed_is_atomic_and_non_destructive(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: self.store.seed(), range(6)))
        self.assertEqual(sum(r["seeded"] for r in responses), 1)
        self.assertEqual(len(self.store.list_runs()), 2)
        self.assertTrue(all(run["source"] == "synthetic_demo" for run in self.store.list_runs()))

    def test_demo_seed_preserves_existing_imports(self):
        run = self.store.add("My run", sample_csv())
        result = self.store.seed()
        self.assertFalse(result["seeded"])
        self.assertEqual([x["id"] for x in result["runs"]], [run["id"]])

    def test_comparison_is_right_minus_left(self):
        baseline, tuned = self.store.seed()["runs"]
        comparison = self.store.compare(baseline["id"], tuned["id"])
        self.assertEqual(comparison["left"]["id"], baseline["id"])
        self.assertLess(comparison["deltas"]["mae_mps"], 0)
        self.assertGreater(comparison["deltas"]["min_battery_v"], 0)
        self.assertEqual(comparison["deltas"]["duration_s"], 0)
        reverse = self.store.compare(tuned["id"], baseline["id"])
        self.assertEqual(reverse["deltas"]["mae_mps"], -comparison["deltas"]["mae_mps"])

    def test_same_run_comparison_has_zero_deltas(self):
        run = self.store.add("Run", sample_csv())
        comparison = self.store.compare(run["id"], run["id"])
        self.assertTrue(all(value == 0 for value in comparison["deltas"].values()))

    def test_missing_run_is_explicit(self):
        with self.assertRaises(RunNotFound):
            self.store.get("missing")


if __name__ == "__main__":
    unittest.main()
