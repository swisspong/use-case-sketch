"""Synthetic loopback OpenAI-compatible provider only; never real credentials/documents."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from types import SimpleNamespace

import pytest


def completion(content, *, finish_reason="stop"):
    return json.dumps({
        "model": "untrusted-model-assertion",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {
            "role": "assistant", "content": content,
        }}],
    }).encode("utf-8")


@pytest.fixture
def ocr_provider(request, tmp_path):
    """Replies with state.replies in order (bytes); the last reply repeats."""
    state = SimpleNamespace(
        requests=[], status=200, block=None,
        replies=[completion(json.dumps({"outcome": "text", "text": "ข้อความจากภาพ"}))],
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state.requests.append((self.path, dict(self.headers), json.loads(body)))
            if state.block is not None:
                state.block.wait(timeout=5)
            payload = state.replies[min(len(state.requests), len(state.replies)) - 1]
            try:
                self.send_response(state.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    scheme = "http"
    if getattr(request, "param", "http") == "https":
        import shutil
        import ssl
        import subprocess
        if shutil.which("openssl") is None:
            server.server_close()
            pytest.skip("openssl unavailable for isolated TLS certificate fixture")
        certificate = tmp_path / "synthetic-cert.pem"
        key = tmp_path / "synthetic-key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=localhost",
            "-addext", "subjectAltName=IP:127.0.0.1",
        ], check=True, capture_output=True, timeout=15)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    state.endpoint = f"{scheme}://127.0.0.1:{server.server_port}/litellm"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        if state.block is not None:
            state.block.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
