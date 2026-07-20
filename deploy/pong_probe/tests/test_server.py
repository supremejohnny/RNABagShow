import unittest
import threading
import http.client
from deploy.pong_probe.server import PongHandler, _PONG_BODY
from http.server import HTTPServer


class TestPongHandlerDirect(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), PongHandler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def _response(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            resp.read()
            return resp
        finally:
            conn.close()

    def test_get_pong(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", "/probe/ping")
            resp = conn.getresponse()
            body = resp.read()
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.getheader("Content-Type"), "text/plain")
            self.assertEqual(resp.getheader("Cache-Control"), "no-store")
            self.assertEqual(body, _PONG_BODY)
        finally:
            conn.close()

    def test_head_pong(self):
        resp = self._response("HEAD", "/probe/ping")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "text/plain")
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")

    def test_get_unknown_path(self):
        resp = self._response("GET", "/api/v1/health/ready")
        self.assertEqual(resp.status, 404)

    def test_get_unknown_path_root(self):
        resp = self._response("GET", "/")
        self.assertEqual(resp.status, 404)

    def test_head_unknown_path(self):
        resp = self._response("HEAD", "/probe/pingx")
        self.assertEqual(resp.status, 404)

    def test_method_not_allowed(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("POST", "/probe/ping")
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 405)
        finally:
            conn.close()

    def test_method_not_allowed_put(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("PUT", "/probe/ping")
            resp = conn.getresponse()
            resp.read()
            self.assertEqual(resp.status, 405)
        finally:
            conn.close()

    def test_pong_body_exact(self):
        self.assertEqual(_PONG_BODY, b"pong\n")
