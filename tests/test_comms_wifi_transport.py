"""Tests for computational_qr.comms.wifi_transport.

All tests use loopback (127.0.0.1) – no real Wi-Fi hardware required.
The :class:`CapsuleServer` runs in a daemon background thread and binds to
port 0 so the OS picks a free port.
"""

import json
import os
import tempfile
import threading
import time

import pytest

from computational_qr.comms.capsule import Capsule
from computational_qr.comms.wifi_transport import (
    CapsuleServer,
    WifiGatewayClient,
    _ANNOUNCE_MAGIC,
    udp_announce,
    udp_listen,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_capsule(text: str = "hello wifi", **kwargs) -> Capsule:
    return Capsule(payload=text.encode(), content_type="text", **kwargs)


def _wait_for_capsules(server: CapsuleServer, count: int, timeout: float = 3.0) -> bool:
    """Poll until *count* capsules are spooled or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(server.get_capsules()) >= count:
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# Server lifecycle tests
# ---------------------------------------------------------------------------

class TestCapsuleServer:
    def test_start_stop(self):
        server = CapsuleServer(host="127.0.0.1", port=0)
        server.start()
        try:
            assert server.port > 0
        finally:
            server.stop()

    def test_context_manager(self):
        with CapsuleServer(host="127.0.0.1", port=0) as server:
            assert server.port > 0

    def test_get_capsules_empty_before_start(self):
        server = CapsuleServer(host="127.0.0.1", port=0)
        assert server.get_capsules() == []

    def test_port_raises_before_start(self):
        server = CapsuleServer(host="127.0.0.1", port=0)
        with pytest.raises(RuntimeError):
            _ = server.port


# ---------------------------------------------------------------------------
# Client / server integration tests
# ---------------------------------------------------------------------------

class TestClientServerIntegration:
    def setup_method(self):
        self.server = CapsuleServer(host="127.0.0.1", port=0)
        self.server.start()
        self.client = WifiGatewayClient(
            f"http://127.0.0.1:{self.server.port}/capsule"
        )

    def teardown_method(self):
        self.server.stop()

    def test_send_single_capsule(self):
        capsule = _make_capsule("single")
        result = self.client.send(capsule)
        assert result["status"] == "ok"
        assert result["msg_id"] == capsule.msg_id

    def test_receive_single_capsule(self):
        capsule = _make_capsule("receive me")
        self.client.send(capsule)
        assert _wait_for_capsules(self.server, 1)
        received = self.server.get_capsules()
        assert len(received) == 1
        assert received[0].payload == b"receive me"

    def test_send_multiple_capsules(self):
        for i in range(5):
            self.client.send(_make_capsule(f"msg {i}"))
        assert _wait_for_capsules(self.server, 5)
        assert len(self.server.get_capsules()) == 5

    def test_payload_preserved_roundtrip(self):
        payload = b"\x00\x01\x02\xfe\xff"
        capsule = Capsule(payload=payload, content_type="bytes")
        self.client.send(capsule)
        assert _wait_for_capsules(self.server, 1)
        received = self.server.get_capsules()[0]
        assert received.payload == payload

    def test_routing_preserved(self):
        capsule = Capsule(
            payload=b"routed",
            content_type="text",
            routing={"topic": "news", "i2p_dest": "test.b32.i2p"},
        )
        self.client.send(capsule)
        assert _wait_for_capsules(self.server, 1)
        received = self.server.get_capsules()[0]
        assert received.routing["topic"] == "news"
        assert received.routing["i2p_dest"] == "test.b32.i2p"

    def test_msg_id_preserved(self):
        capsule = _make_capsule("id-check")
        self.client.send(capsule)
        assert _wait_for_capsules(self.server, 1)
        received = self.server.get_capsules()[0]
        assert received.msg_id == capsule.msg_id

    def test_get_capsules_returns_snapshot(self):
        capsule = _make_capsule("snap")
        self.client.send(capsule)
        assert _wait_for_capsules(self.server, 1)
        snap1 = self.server.get_capsules()
        snap2 = self.server.get_capsules()
        assert snap1[0].msg_id == snap2[0].msg_id


class TestCapsuleServerSpoolDir:
    def test_spool_dir_writes_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = CapsuleServer(host="127.0.0.1", port=0, spool_dir=tmpdir)
            server.start()
            try:
                client = WifiGatewayClient(
                    f"http://127.0.0.1:{server.port}/capsule"
                )
                capsule = _make_capsule("spooled")
                client.send(capsule)
                assert _wait_for_capsules(server, 1)
                files = os.listdir(tmpdir)
                assert len(files) == 1
                assert files[0].endswith(".json")
                with open(os.path.join(tmpdir, files[0])) as fh:
                    data = json.load(fh)
                assert data["msg_id"] == capsule.msg_id
            finally:
                server.stop()


class TestCapsuleServerBadRequests:
    def setup_method(self):
        self.server = CapsuleServer(host="127.0.0.1", port=0)
        self.server.start()

    def teardown_method(self):
        self.server.stop()

    def test_invalid_json_returns_400(self):
        import urllib.request
        import urllib.error

        url = f"http://127.0.0.1:{self.server.port}/capsule"
        req = urllib.request.Request(
            url,
            data=b"not valid json {{",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 400


# ---------------------------------------------------------------------------
# UDP discovery helpers
# ---------------------------------------------------------------------------

class TestUDPDiscovery:
    """Test UDP announce/listen on localhost using the actual multicast group.

    If multicast is unavailable on the CI host, these tests are skipped.
    """

    _MCAST = "239.255.42.42"
    _PORT = 19877  # use a different port to avoid conflicts with the real default

    def _try_announce(self, service_port: int) -> bool:
        """Return True if udp_announce succeeds without raising."""
        try:
            udp_announce(
                service_port,
                multicast_group=self._MCAST,
                discovery_port=self._PORT,
                ttl=1,
            )
            return True
        except OSError:
            return False

    def test_announce_magic_bytes(self):
        """Verify the magic bytes constant is correct."""
        assert _ANNOUNCE_MAGIC == b"CQRC\x01"

    def test_announce_and_listen(self):
        """Full announce/listen cycle on loopback multicast."""
        received_port: list[int] = []
        errors: list[Exception] = []

        def listen_thread():
            try:
                port = udp_listen(
                    multicast_group=self._MCAST,
                    discovery_port=self._PORT,
                    timeout=2.0,
                )
                if port is not None:
                    received_port.append(port)
            except OSError as exc:
                errors.append(exc)

        t = threading.Thread(target=listen_thread, daemon=True)
        t.start()
        time.sleep(0.1)  # give listener time to bind

        ok = self._try_announce(
            service_port=9999,
        )
        t.join(timeout=3.0)

        if not ok or errors:
            pytest.skip("Multicast not available on this host")

        assert received_port == [9999]

    def test_listen_timeout_returns_none(self):
        """udp_listen should return None when no announcement arrives."""
        try:
            result = udp_listen(
                multicast_group=self._MCAST,
                discovery_port=self._PORT + 1,
                timeout=0.1,
            )
            assert result is None
        except OSError:
            pytest.skip("Multicast not available on this host")
