import math
import unittest

from tracedrive.analysis import FIELDS, ValidationError, analyze, parse_csv, validate_name


def csv_text(rows):
    return ",".join(FIELDS) + "\n" + "\n".join(",".join(str(v) for v in row) for row in rows) + "\n"


class AnalysisTests(unittest.TestCase):
    def test_irregular_sampling_uses_time_instead_of_sample_count(self):
        samples = parse_csv(csv_text([
            [0, 2, 2, 12, 1, 25],
            [1, 2, 0, 11.9, 2, 26],
            [10, 2, 0, 11.5, 3, 27],
        ]))
        result = analyze(samples)
        self.assertAlmostEqual(result["metrics"]["mae_mps"], 1.9)
        self.assertAlmostEqual(result["metrics"]["rmse_mps"], math.sqrt(3.8), places=6)
        self.assertEqual(result["duration_s"], 10)
        self.assertNotAlmostEqual(result["metrics"]["mae_mps"], 4/3)

    def test_constant_offset_does_not_change_duration_or_metrics(self):
        original = [[0, 1, .5, 12, 1, 25], [2, 1, .8, 11, 2, 26]]
        shifted = [[row[0]+500, *row[1:]] for row in original]
        a, b = (analyze(parse_csv(csv_text(rows))) for rows in (original, shifted))
        self.assertEqual(a["metrics"], b["metrics"])
        self.assertEqual(a["duration_s"], b["duration_s"])

    def test_consecutive_anomaly_samples_form_segments(self):
        rows = [[i, 1, v, battery, 1, 25] for i, v, battery in [
            (0, 1, 12), (1, .2, 10), (2, .1, 9.8), (3, 1, 12), (4, .4, 12),
        ]]
        result = analyze(parse_csv(csv_text(rows)))
        tracking = [event for event in result["anomalies"] if event["kind"] == "tracking_error"]
        battery = [event for event in result["anomalies"] if event["kind"] == "low_battery"]
        self.assertEqual([(e["start_s"], e["end_s"]) for e in tracking], [(1, 2), (4, 4)])
        self.assertEqual(tracking[0]["peak_value"], .9)
        self.assertEqual(battery[0]["peak_value"], 9.8)
        self.assertEqual(result["anomaly_count"], 3)

    def test_equal_threshold_does_not_trigger_sensor_anomalies(self):
        result = analyze(parse_csv(csv_text([[0, 1, 1, 10.5, 8, 60], [1, 1, 1, 10.5, 8, 60]])))
        self.assertEqual(result["anomalies"], [])

    def test_all_sensor_anomaly_kinds(self):
        result = analyze(parse_csv(csv_text([[0, 1, 0, 10, 9, 65], [1, 1, 0, 10, 9, 65]])))
        self.assertEqual({x["kind"] for x in result["anomalies"]}, {
            "tracking_error", "low_battery", "high_current", "high_temperature",
        })

    def test_nonfinite_values_rejected_with_row_and_column(self):
        for bad in ["nan", "NaN", "inf", "-inf", "1e999"]:
            with self.subTest(bad=bad), self.assertRaisesRegex(ValidationError, "Row 3, velocity_mps.*finite"):
                parse_csv(csv_text([[0, 1, 1, 12, 1, 25], [1, 1, bad, 12, 1, 25]]))

    def test_time_order_and_negative_time(self):
        for times in [[0, 0], [2, 1], [-1, 2]]:
            with self.subTest(times=times), self.assertRaises(ValidationError):
                parse_csv(csv_text([[t, 1, 1, 12, 1, 25] for t in times]))

    def test_missing_and_duplicate_headers(self):
        for header in [FIELDS[:-1], [*FIELDS[:-1], FIELDS[0]]]:
            with self.subTest(header=header), self.assertRaisesRegex(ValidationError, "header"):
                parse_csv(",".join(header) + "\n")

    def test_wrong_row_width_and_empty_numbers(self):
        for row in [[1, 1, 1], [1, 1, 1, 12, 1, 25, 9], [1, 1, "", 12, 1, 25]]:
            with self.subTest(row=row), self.assertRaisesRegex(ValidationError, "Row 3"):
                parse_csv(csv_text([[0, 1, 1, 12, 1, 25], row]))

    def test_empty_and_one_sample(self):
        for text in ["", csv_text([]), csv_text([[0, 1, 1, 12, 1, 25]])]:
            with self.subTest(text=text), self.assertRaises(ValidationError):
                parse_csv(text)

    def test_size_and_sample_limits(self):
        with self.assertRaisesRegex(ValidationError, "size limit"):
            parse_csv("a" * (2*1024*1024+1))
        with self.assertRaisesRegex(ValidationError, "maximum 20,000"):
            parse_csv(csv_text([[i, 1, 1, 12, 1, 25] for i in range(20_001)]))

    def test_utf8_bom_and_reordered_columns_accepted(self):
        normal = csv_text([[0, 1, 1, 12, 1, 25], [1, 1, .9, 12, 1, 25]])
        self.assertEqual(parse_csv(normal), parse_csv("\ufeff" + normal))
        lines = [",".join(reversed(line.split(","))) for line in normal.strip().splitlines()]
        self.assertEqual(parse_csv(normal), parse_csv("\n".join(lines)))

    def test_name_validation(self):
        self.assertEqual(validate_name("  Drivetrain A  "), "Drivetrain A")
        for name in [True, None, "", " ", "a"*81, "line\nbreak"]:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_name(name)

    def test_invalid_unicode_is_rejected_before_storage(self):
        with self.assertRaisesRegex(ValidationError, "UTF-8"):
            validate_name("bad\ud800name")
        with self.assertRaisesRegex(ValidationError, "UTF-8"):
            parse_csv("bad\ud800csv")


if __name__ == "__main__":
    unittest.main()
