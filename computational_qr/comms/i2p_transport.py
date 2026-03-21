"""Pattern C – I2P gateway client.

This module wraps communication with an *I2P gateway* service.  The gateway
is a separate process (or remote host) that runs an I2P router and exposes a
small HTTP API for capsule injection.  The module itself does **not** implement
I2P internals; it simply provides a typed client for the gateway contract.

Gateway contract
----------------

``POST /i2p/submit``
    Submit a capsule for delivery.

    Request body: capsule JSON (``application/json``).

    Response (200 OK)::

        {"status": "queued", "msg_id": "<uuid>"}

``GET /i2p/mailbox/<topic>``
    Retrieve pending capsules for a mailbox/topic.

    Response (200 OK)::

        {"topic": "<topic>", "capsules": [<capsule-json>, ...]}

    Returns an empty list if no capsules are waiting.

Routing hints
-------------

Set ``capsule.routing["i2p_dest"]`` to the destination's I2P base64 address
and ``capsule.routing["topic"]`` to a mailbox label:

.. code-block:: python

    capsule = Capsule(
        payload=b"secret",
        content_type="otp_ciphertext",
        routing={"i2p_dest": "abcd...xyz.b32.i2p", "topic": "inbox_alice"},
    )

Usage
-----

.. code-block:: python

    from computational_qr.comms.capsule import Capsule
    from computational_qr.comms.i2p_transport import I2PGatewayClient

    client = I2PGatewayClient("http://localhost:7070")
    capsule = Capsule(
        payload=b"hello i2p",
        content_type="text",
        routing={"i2p_dest": "someaddr.b32.i2p", "topic": "greetings"},
    )
    result = client.submit(capsule)
    print(result)  # {'status': 'queued', 'msg_id': '...'}

    pending = client.fetch_mailbox("greetings")
    for c in pending:
        print(c.text_payload())
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from computational_qr.comms.capsule import Capsule


class I2PGatewayClient:
    """HTTP client for an I2P gateway service.

    Parameters
    ----------
    gateway_url:
        Base URL of the gateway, e.g. ``"http://localhost:7070"``.
        Must *not* have a trailing slash.
    timeout:
        Socket timeout in seconds.
    """

    _SUBMIT_PATH = "/i2p/submit"
    _MAILBOX_PATH = "/i2p/mailbox/{topic}"

    def __init__(self, gateway_url: str, timeout: float = 10.0) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, capsule: Capsule) -> dict[str, Any]:
        """Submit a :class:`~computational_qr.comms.capsule.Capsule` to the
        I2P gateway for delivery.

        The gateway queues the capsule and forwards it via I2P to the
        destination specified in ``capsule.routing["i2p_dest"]`` (if present).

        Returns
        -------
        dict
            Parsed JSON response, typically
            ``{"status": "queued", "msg_id": "<uuid>"}``.

        Raises
        ------
        urllib.error.URLError
            On connection failure.
        ValueError
            If the gateway returns a non-200 status.
        """
        url = self.gateway_url + self._SUBMIT_PATH
        body = capsule.to_json().encode()
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            status = resp.status
            response_body = resp.read().decode()

        if status != 200:
            raise ValueError(
                f"I2P gateway returned HTTP {status}: {response_body!r}"
            )
        return json.loads(response_body)

    def fetch_mailbox(self, topic: str) -> list[Capsule]:
        """Retrieve pending capsules for *topic* from the gateway mailbox.

        Parameters
        ----------
        topic:
            The mailbox/topic label (matches ``capsule.routing["topic"]``).

        Returns
        -------
        list[Capsule]
            Possibly-empty list of capsules waiting in the mailbox.

        Raises
        ------
        urllib.error.URLError
            On connection failure.
        ValueError
            If the gateway returns a non-200 status.
        """
        url = self.gateway_url + self._MAILBOX_PATH.format(topic=topic)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            status = resp.status
            response_body = resp.read().decode()

        if status != 200:
            raise ValueError(
                f"I2P gateway returned HTTP {status}: {response_body!r}"
            )

        data = json.loads(response_body)
        capsules = []
        for raw in data.get("capsules", []):
            if isinstance(raw, str):
                capsules.append(Capsule.from_json(raw))
            else:
                capsules.append(Capsule.from_dict(raw))
        return capsules
