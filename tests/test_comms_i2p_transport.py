"""Tests for computational_qr.comms.i2p_transport.

All tests use an in-process mock HTTP server – no real I2P network required.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from computational_qr.comms.capsule import Capsule
from computational_qr.comms.i2p_transport import I2PGatewayClient


# ---------------------------------------------------------------------------
# Mock I2P gateway server
# ---------------------------------------------------------------------------

class _MockI2PHandler(BaseHTTPRequestHandler):
    """Minimal I2P gateway mock that stores submitted capsules per topic."""

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover
        pass

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/i2p/submit":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                capsule = Capsule.from_bytes(body)
            except Exception as exc:
                self._respond(400, {"error": str(exc)})
                return
            topic = capsule.routing.get("topic", "_default")
            self.server.mailboxes.setdefault(topic, []).append(capsule)
            self._respond(200, {"status": "queued", "msg_id": capsule.msg_id})
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self) -> None:  # noqa: N802
        prefix = "/i2p/mailbox/"
        if self.path.startswith(prefix):
            topic = self.path[len(prefix):]
            capsules = self.server.mailboxes.get(topic, [])
            payload = [c.to_dict() for c in capsules]
            self._respond(200, {"topic": topic, "capsules": payload})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class _MockI2PGateway:
    def __init__(self):
        self._server = HTTPServer(("127.0.0.1", 0), _MockI2PHandler)
        self._server.mailboxes: dict[str, list[Capsule]] = {}
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="MockI2PGateway",
        )

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_capsule(text: str = "i2p message", **kwargs) -> Capsule:
    return Capsule(payload=text.encode(), content_type="text", **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestI2PGatewayClientSubmit:
    def setup_method(self):
        self.gateway = _MockI2PGateway()
        self.gateway.start()
        self.client = I2PGatewayClient(self.gateway.base_url)

    def teardown_method(self):
        self.gateway.stop()

    def test_submit_returns_queued(self):
        capsule = _make_capsule("hello i2p")
        result = self.client.submit(capsule)
        assert result["status"] == "queued"
        assert result["msg_id"] == capsule.msg_id

    def test_submit_stores_in_default_topic(self):
        capsule = _make_capsule("no topic")
        self.client.submit(capsule)
        assert "_default" in self.gateway._server.mailboxes
        stored = self.gateway._server.mailboxes["_default"]
        assert stored[0].msg_id == capsule.msg_id

    def test_submit_stores_in_named_topic(self):
        capsule = _make_capsule(
            "topical",
            routing={"topic": "news", "i2p_dest": "abc.b32.i2p"},
        )
        self.client.submit(capsule)
        assert "news" in self.gateway._server.mailboxes
        stored = self.gateway._server.mailboxes["news"]
        assert stored[0].payload == b"topical"

    def test_submit_multiple_capsules(self):
        for i in range(4):
            capsule = _make_capsule(f"msg {i}", routing={"topic": "batch"})
            self.client.submit(capsule)
        assert len(self.gateway._server.mailboxes["batch"]) == 4

    def test_submit_routing_preserved(self):
        routing = {"i2p_dest": "dest.b32.i2p", "topic": "secure"}
        capsule = Capsule(payload=b"encrypted", content_type="otp_ciphertext", routing=routing)
        self.client.submit(capsule)
        stored = self.gateway._server.mailboxes["secure"][0]
        assert stored.routing["i2p_dest"] == "dest.b32.i2p"

    def test_submit_binary_payload(self):
        payload = bytes(range(64))
        capsule = Capsule(payload=payload, content_type="bytes", routing={"topic": "bin"})
        self.client.submit(capsule)
        stored = self.gateway._server.mailboxes["bin"][0]
        assert stored.payload == payload


class TestI2PGatewayClientFetchMailbox:
    def setup_method(self):
        self.gateway = _MockI2PGateway()
        self.gateway.start()
        self.client = I2PGatewayClient(self.gateway.base_url)

    def teardown_method(self):
        self.gateway.stop()

    def test_fetch_empty_mailbox(self):
        result = self.client.fetch_mailbox("nonexistent")
        assert result == []

    def test_fetch_after_submit(self):
        capsule = _make_capsule("fetchable", routing={"topic": "inbox"})
        self.client.submit(capsule)
        received = self.client.fetch_mailbox("inbox")
        assert len(received) == 1
        assert received[0].payload == b"fetchable"

    def test_fetch_multiple_capsules(self):
        for i in range(3):
            capsule = _make_capsule(f"item {i}", routing={"topic": "multi"})
            self.client.submit(capsule)
        received = self.client.fetch_mailbox("multi")
        assert len(received) == 3
        payloads = {c.text_payload() for c in received}
        assert payloads == {"item 0", "item 1", "item 2"}

    def test_fetch_capsule_checksum_valid(self):
        capsule = _make_capsule("check", routing={"topic": "verify"})
        self.client.submit(capsule)
        received = self.client.fetch_mailbox("verify")
        assert received[0].verify() is True

    def test_fetch_different_topics_isolated(self):
        c1 = _make_capsule("topic-a", routing={"topic": "alpha"})
        c2 = _make_capsule("topic-b", routing={"topic": "beta"})
        self.client.submit(c1)
        self.client.submit(c2)
        alpha = self.client.fetch_mailbox("alpha")
        beta = self.client.fetch_mailbox("beta")
        assert len(alpha) == 1
        assert len(beta) == 1
        assert alpha[0].payload == b"topic-a"
        assert beta[0].payload == b"topic-b"


class TestI2PGatewayClientErrors:
    def setup_method(self):
        self.gateway = _MockI2PGateway()
        self.gateway.start()
        self.client = I2PGatewayClient(self.gateway.base_url)

    def teardown_method(self):
        self.gateway.stop()

    def test_submit_bad_checksum_returns_400(self):
        """Submitting corrupted JSON to the gateway yields a 400 response."""
        import urllib.request
        import urllib.error

        url = self.gateway.base_url + "/i2p/submit"
        req = urllib.request.Request(
            url,
            data=b'{"version":1,"bad":"json"}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 400

    def test_connection_error_raises(self):
        client = I2PGatewayClient("http://127.0.0.1:1")
        capsule = _make_capsule("unreachable")
        import urllib.error
        with pytest.raises((urllib.error.URLError, ConnectionRefusedError, OSError)):
            client.submit(capsule)

    def test_gateway_url_strips_trailing_slash(self):
        client = I2PGatewayClient("http://127.0.0.1:9999/")
        assert not client.gateway_url.endswith("/")


class TestI2PGatewayClientInit:
    def test_default_timeout(self):
        client = I2PGatewayClient("http://localhost:7070")
        assert client.timeout == 10.0

    def test_custom_timeout(self):
        client = I2PGatewayClient("http://localhost:7070", timeout=30.0)
        assert client.timeout == 30.0

    def test_gateway_url_stored(self):
        client = I2PGatewayClient("http://localhost:7070")
        assert "localhost" in client.gateway_url
