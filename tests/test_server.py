import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from tracedrive.demo import sample_csv
from tracedrive.server import Server
from tracedrive.store import Store


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        web = root / "web"
        web.mkdir()
        (web / "index.html").write_text("<h1>TraceDrive</h1>")
        cls.server = Server(("127.0.0.1", 0), Store(root / "test.sqlite3"), web)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.tmp.cleanup()

    def request(self, method, path, payload=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = raw if raw is not None else json.dumps(payload) if payload is not None else None
        final_headers = {"Content-Type": "application/json"}
        final_headers.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=final_headers)
            response = connection.getresponse()
            data = response.read()
            result = json.loads(data) if response.getheader("Content-Type", "").startswith("application/json") else data
            return response.status, result
        finally:
            connection.close()

    def test_state_and_static_page(self):
        status, state = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertIn("runs", state)
        self.assertEqual(state["thresholds"]["battery_v"], 10.5)
        self.assertEqual(self.request("GET", "/")[0], 200)

    def test_import_and_read_and_compare(self):
        status, result = self.request("POST", "/api/runs", {"name": "HTTP run", "csv": sample_csv()})
        self.assertEqual(status, 201)
        run_id = result["run"]["id"]
        status, detail = self.request("GET", f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["run"]["name"], "HTTP run")
        self.assertEqual(len(detail["samples"]), 301)
        status, comparison = self.request("GET", f"/api/compare?left={run_id}&right={run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(comparison["deltas"]["mae_mps"], 0)

    def test_invalid_csv_returns_readable_json(self):
        status, result = self.request("POST", "/api/runs", {"name": "Bad", "csv": "wrong\n"})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "validation_error")
        self.assertIn("header", result["message"])

    def test_wrong_body_shapes_and_json(self):
        for payload in [[], {"name": "Oops"}, {"name": True, "csv": sample_csv()}, {"name": "Oops", "csv": 0}]:
            with self.subTest(payload=type(payload).__name__):
                self.assertEqual(self.request("POST", "/api/runs", payload)[0], 400)
        self.assertEqual(self.request("POST", "/api/runs", raw="{bad json")[0], 400)

    def test_media_type_and_body_limit(self):
        self.assertEqual(self.request("POST", "/api/runs", raw="{}", headers={"Content-Type": "text/plain"})[0], 415)
        status, error = self.request("POST", "/api/runs", raw="{}", headers={"Content-Length": str(2*1024*1024+1)})
        self.assertEqual(status, 413)
        self.assertEqual(error["error"], "body_too_large")

    def test_unknown_routes_and_missing_comparison(self):
        self.assertEqual(self.request("GET", "/api/runs/not-found")[0], 404)
        self.assertEqual(self.request("GET", "/api/compare?left=x")[0], 400)
        self.assertEqual(self.request("GET", "/api/unknown")[0], 404)
        self.assertEqual(self.request("DELETE", "/api/runs/x")[0], 405)

    def test_origin_and_host_are_local_only(self):
        self.assertEqual(self.request("POST", "/api/demo/seed", {}, headers={"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "example.com"})[0], 403)

    def test_sample_csv_download_is_valid(self):
        status, body = self.request("GET", "/api/sample.csv")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"time_s,target_velocity_mps"))


if __name__ == "__main__":
    unittest.main()
