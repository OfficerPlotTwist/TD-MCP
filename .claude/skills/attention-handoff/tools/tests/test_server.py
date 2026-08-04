import base64
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as srv_mod

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        with open(os.path.join(cls.dir, "video.mp4"), "wb") as f:
            f.write(bytes(range(256)) * 40)  # 10240-byte fake video
        srv_mod.SESSION = srv_mod.Session(cls.dir)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv_mod.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(method, path, body, headers or {})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def test_1_capture_roundtrip(self):
        img = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 12.5, "type": "param", "bbox": [1, 2, 3, 4],
             "pairId": None, "role": None, "image": img}))
        self.assertEqual(resp.status, 200)
        rec = json.loads(data)
        self.assertEqual(rec["id"], "c001")
        self.assertEqual(rec["file"], "crops/c001.png")
        self.assertTrue(os.path.exists(
            os.path.join(self.dir, "crops", "c001.png")))
        resp, data = self.req("GET", "/captures")
        self.assertEqual(len(json.loads(data)), 1)

    def test_2_delete_removes_record_and_crop(self):
        img = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 1.0, "type": "network", "bbox": [0, 0, 5, 5],
             "pairId": None, "role": None, "image": img}))
        cid = json.loads(data)["id"]
        self.req("POST", "/delete", json.dumps({"id": cid}))
        resp, data = self.req("GET", "/captures")
        self.assertNotIn(cid, [c["id"] for c in json.loads(data)])
        self.assertFalse(os.path.exists(
            os.path.join(self.dir, "crops", cid + ".png")))

    def test_2b_ids_not_reused_after_delete(self):
        img = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 2.0, "type": "param", "bbox": [0, 0, 1, 1],
             "pairId": None, "role": None, "image": img}))
        id1 = json.loads(data)["id"]
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 3.0, "type": "param", "bbox": [0, 0, 1, 1],
             "pairId": None, "role": None, "image": img}))
        id2 = json.loads(data)["id"]
        self.req("POST", "/delete", json.dumps({"id": id2}))
        resp, data = self.req("POST", "/capture", json.dumps(
            {"t": 4.0, "type": "param", "bbox": [0, 0, 1, 1],
             "pairId": None, "role": None, "image": img}))
        id3 = json.loads(data)["id"]
        self.assertGreater(int(id3[1:]), int(id2[1:]))

    def test_3_status_flow(self):
        resp, data = self.req("GET", "/status")
        self.assertEqual(json.loads(data)["state"], "capturing")
        self.req("POST", "/done", "{}")
        resp, data = self.req("GET", "/status")
        self.assertEqual(json.loads(data)["state"], "captured")
        self.req("POST", "/approved", json.dumps({"ops": [], "wires": []}))
        resp, data = self.req("GET", "/status")
        self.assertEqual(json.loads(data)["state"], "approved")
        with open(os.path.join(self.dir, "approved.json")) as f:
            self.assertEqual(json.load(f)["ops"], [])

    def test_4_readings_endpoint(self):
        resp, data = self.req("GET", "/readings")
        self.assertEqual(json.loads(data), {})
        with open(os.path.join(self.dir, "readings.json"), "w") as f:
            json.dump({"c001": {"kind": "param", "opName": "noise1",
                                "opType": "noiseTOP",
                                "params": {"period": "4"},
                                "boxes": {"period": [10, 20, 200, 18]}}}, f)
        resp, data = self.req("GET", "/readings")
        self.assertEqual(json.loads(data)["c001"]["opName"], "noise1")

    def test_5_video_full(self):
        resp, data = self.req("GET", "/video")
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(data), 10240)
        self.assertEqual(resp.getheader("Accept-Ranges"), "bytes")

    def test_6_video_range(self):
        resp, data = self.req("GET", "/video",
                              headers={"Range": "bytes=100-199"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(len(data), 100)
        self.assertEqual(resp.getheader("Content-Range"),
                         "bytes 100-199/10240")
        self.assertEqual(data[0], 100)

    def test_7_video_open_ended_range(self):
        resp, data = self.req("GET", "/video",
                              headers={"Range": "bytes=10200-"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(len(data), 40)

    def test_8_video_range_beyond_eof(self):
        resp, data = self.req("GET", "/video",
                              headers={"Range": "bytes=20000-"})
        self.assertEqual(resp.status, 416)
        self.assertEqual(resp.getheader("Content-Range"), "bytes */10240")
        self.assertEqual(len(data), 0)


if __name__ == "__main__":
    unittest.main()
