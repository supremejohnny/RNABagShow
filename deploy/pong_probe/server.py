import os
from http.server import HTTPServer, BaseHTTPRequestHandler


_PONG_BODY = b"pong\n"


class PongHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/probe/ping":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(_PONG_BODY)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(_PONG_BODY)

    def do_HEAD(self):
        if self.path != "/probe/ping":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(_PONG_BODY)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self):
        self._send_405()

    def do_PUT(self):
        self._send_405()

    def do_PATCH(self):
        self._send_405()

    def do_DELETE(self):
        self._send_405()

    def do_OPTIONS(self):
        self._send_405()

    def do_TRACE(self):
        self._send_405()

    def do_CONNECT(self):
        self._send_405()

    def _send_405(self):
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.end_headers()

    def log_message(self, *args, **kwargs):
        pass


def main():
    host = os.environ.get("RNABAG_PONG_HOST", "0.0.0.0")
    port = int(os.environ.get("RNABAG_PONG_PORT", "8080"))
    server = HTTPServer((host, port), PongHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
