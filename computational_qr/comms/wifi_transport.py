"""Pattern B – Wi-Fi LAN transport (HTTP POST + optional UDP discovery).

This module provides:

* :class:`WifiGatewayClient` – an HTTP client that POSTs capsules to a gateway
  endpoint on the local LAN (or any IP network).
* :class:`CapsuleHandler` – a minimal :mod:`http.server` handler that accepts
  incoming capsule POSTs and spools them to a directory (or an in-memory list
  for testing).
* :class:`CapsuleServer` – a thin wrapper that starts a
  :class:`CapsuleHandler`-based server in a background thread.
* :func:`udp_announce` / :func:`udp_listen` – optional UDP broadcast helpers
  for gateway discovery.  Both can be disabled or mocked for unit tests.

Pattern B overview
------------------

All devices share the same IP LAN (Wi-Fi, Ethernet, etc. – the underlying
link does not matter).  A *gateway node* runs a :class:`CapsuleServer`.
*Sender* devices call :meth:`WifiGatewayClient.send` to POST a capsule to the
gateway URL.  The gateway spools capsules for later retrieval.

Usage
-----

.. code-block:: python

    import threading
    from computational_qr.comms.capsule import Capsule
    from computational_qr.comms.wifi_transport import CapsuleServer, WifiGatewayClient

    # Start an in-process gateway (binds to 127.0.0.1 for the example)
    server = CapsuleServer(host="127.0.0.1", port=0)  # port=0 → OS picks free port
    server.start()

    # Client sends a capsule
    capsule = Capsule(payload=b"hello", content_type="text")
    client = WifiGatewayClient(f"http://127.0.0.1:{server.port}/capsule")
    client.send(capsule)

    # Retrieve spooled capsules
    received = server.get_capsules()
    server.stop()
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from computational_qr.comms.capsule import Capsule


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class WifiGatewayClient:
    """HTTP client that POSTs :class:`~computational_qr.comms.capsule.Capsule`
    objects to a gateway endpoint.

    Parameters
    ----------
    url:
        Full URL of the gateway capsule endpoint, e.g.
        ``"http://192.168.1.10:8765/capsule"``.
    timeout:
        Socket timeout in seconds for each HTTP request.
    """

    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout

    def send(self, capsule: Capsule) -> dict[str, Any]:
        """POST *capsule* to the gateway.

        Returns
        -------
        dict
            Parsed JSON response from the gateway.

        Raises
        ------
        urllib.error.URLError
            On connection failure.
        ValueError
            If the gateway returns a non-200 status.
        """
        body = capsule.to_json().encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            status = resp.status
            response_body = resp.read().decode()

        if status != 200:
            raise ValueError(
                f"Gateway returned HTTP {status}: {response_body!r}"
            )
        return json.loads(response_body)


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class CapsuleHandler(BaseHTTPRequestHandler):
    """Minimal HTTP request handler that accepts capsule POSTs.

    The server instance is expected to expose a ``spool`` attribute (a list)
    and an optional ``spool_dir`` attribute (a :class:`str` path).  Capsules
    are always appended to ``spool``; if ``spool_dir`` is set they are also
    written to ``<spool_dir>/<msg_id>.json``.
    """

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover
        """Suppress default access-log output."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            capsule = Capsule.from_bytes(body)
        except Exception as exc:
            self._respond(400, {"error": str(exc)})
            return

        self.server.spool.append(capsule)

        spool_dir = getattr(self.server, "spool_dir", None)
        if spool_dir:
            import os

            path = os.path.join(spool_dir, f"{capsule.msg_id}.json")
            with open(path, "w") as fh:
                fh.write(capsule.to_json())

        self._respond(200, {"status": "ok", "msg_id": capsule.msg_id})

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class CapsuleServer:
    """Lightweight in-process HTTP gateway server for capsule ingestion.

    Parameters
    ----------
    host:
        Bind address.  Use ``"127.0.0.1"`` for loopback-only (tests) or
        ``"0.0.0.0"`` to accept from any interface.
    port:
        TCP port to listen on.  Pass ``0`` to let the OS choose a free port
        (useful for tests); retrieve the actual port via :attr:`port`.
    spool_dir:
        If provided, received capsules are written as JSON files to this
        directory.  ``None`` (default) keeps everything in memory.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        spool_dir: str | None = None,
    ) -> None:
        self._host = host
        self._requested_port = port
        self.spool_dir = spool_dir
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the server in a daemon background thread."""
        self._server = HTTPServer((self._host, self._requested_port), CapsuleHandler)
        self._server.spool = []  # type: ignore[attr-defined]
        self._server.spool_dir = self.spool_dir  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="CapsuleServer",
        )
        self._thread.start()

    def stop(self) -> None:
        """Shutdown the server and wait for the background thread to finish."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def port(self) -> int:
        """Actual TCP port the server is listening on."""
        if self._server is None:
            raise RuntimeError("Server not started yet")
        return self._server.server_address[1]

    @property
    def host(self) -> str:
        """Bind address."""
        return self._host

    def get_capsules(self) -> list[Capsule]:
        """Return a snapshot of all spooled capsules (in arrival order)."""
        if self._server is None:
            return []
        return list(self._server.spool)  # type: ignore[attr-defined]

    def __enter__(self) -> "CapsuleServer":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# UDP discovery helpers
# ---------------------------------------------------------------------------

_DISCOVERY_PORT = 19876
_MULTICAST_GROUP = "239.255.42.42"
_ANNOUNCE_MAGIC = b"CQRC\x01"  # magic prefix: Computational-QR-Capsule v1


def udp_announce(
    service_port: int,
    *,
    multicast_group: str = _MULTICAST_GROUP,
    discovery_port: int = _DISCOVERY_PORT,
    ttl: int = 1,
) -> None:
    """Broadcast a UDP announcement so that devices on the LAN can discover
    the capsule gateway.

    The datagram payload is ``CQRC\\x01<port-as-2-byte-big-endian>``.

    Parameters
    ----------
    service_port:
        The TCP port the :class:`CapsuleServer` is listening on.
    multicast_group:
        IPv4 multicast group address.
    discovery_port:
        UDP port to send to.
    ttl:
        IP TTL for the multicast packet.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        payload = _ANNOUNCE_MAGIC + struct.pack(">H", service_port)
        sock.sendto(payload, (multicast_group, discovery_port))
    finally:
        sock.close()


def udp_listen(
    *,
    multicast_group: str = _MULTICAST_GROUP,
    discovery_port: int = _DISCOVERY_PORT,
    timeout: float = 2.0,
) -> int | None:
    """Listen for a UDP gateway announcement and return the service port.

    Returns ``None`` if no announcement is received within *timeout* seconds.

    Parameters
    ----------
    multicast_group:
        IPv4 multicast group to join.
    discovery_port:
        UDP port to bind to.
    timeout:
        How long to wait in seconds.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", discovery_port))
        group = socket.inet_aton(multicast_group)
        mreq = group + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(timeout)
        try:
            data, _ = sock.recvfrom(64)
        except socket.timeout:
            return None
        if data[: len(_ANNOUNCE_MAGIC)] != _ANNOUNCE_MAGIC:
            return None
        (port,) = struct.unpack(">H", data[len(_ANNOUNCE_MAGIC) : len(_ANNOUNCE_MAGIC) + 2])
        return port
    finally:
        sock.close()
