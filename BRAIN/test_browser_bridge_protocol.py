import io
import json
import unittest
from browser_bridge_protocol import authorized, read_result, MAX_RESULT_BYTES


class ProtocolTests(unittest.TestCase):
    def test_auth(self):
        secret = "a" * 64
        self.assertTrue(authorized(secret, secret))
        for bad in (None, "", "a" * 63, "b" * 64, "a" * 64 + "\n", "é" * 64):
            self.assertFalse(authorized(secret, bad))
        self.assertFalse(authorized(None, secret))
        self.assertFalse(authorized("", ""))

    def decode(self, value):
        body = json.dumps(value).encode()
        return read_result({"Content-Type": "application/json", "Content-Length": str(len(body))}, io.BytesIO(body))

    def test_valid(self):
        self.assertEqual(self.decode({"id": "0123456789", "result": {"ok": True}}), ("0123456789", {"ok": True}))

    def test_envelope(self):
        for bad in ([], {}, {"id": "bad", "result": {"ok": True}}, {"id": "0123456789", "result": {"ok": 1}}, {"id": "0123456789", "result": []}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.decode(bad)

    def test_headers_and_size(self):
        for h in ({}, {"Content-Type": "application/json", "Content-Length": str(MAX_RESULT_BYTES + 1)}, {"Content-Type": "application/json", "Content-Length": "100"}, {"Content-Type": "application/json", "Content-Length": "2", "Transfer-Encoding": "chunked"}):
            with self.subTest(h=h), self.assertRaises(ValueError):
                read_result(h, io.BytesIO(b"{}"))


if __name__ == "__main__":
    unittest.main()
