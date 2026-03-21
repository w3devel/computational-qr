"""``computational_qr.comms`` – modular communications subsystem.

Three transport patterns are provided:

* **Pattern A** (:mod:`~computational_qr.comms.qr_transport`) – multi-frame
  QR / video-QR framing.  Splits a :class:`Capsule` into fixed-size chunks
  that each fit in a QR symbol, reassembles in any order.

* **Pattern B** (:mod:`~computational_qr.comms.wifi_transport`) – Wi-Fi LAN
  transport via HTTP POST.  Includes an in-process HTTP server for testing and
  optional UDP multicast discovery.

* **Pattern C** (:mod:`~computational_qr.comms.i2p_transport`) – I2P gateway
  client.  POSTs capsules to a gateway that forwards them over I2P; supports
  mailbox/topic retrieval.

All patterns share the same :class:`Capsule` envelope (versioned, signed with
a SHA-256 checksum, base64url payload).
"""

from computational_qr.comms.capsule import Capsule
from computational_qr.comms.i2p_transport import I2PGatewayClient
from computational_qr.comms.qr_transport import QRFrame, QRFramer
from computational_qr.comms.wifi_transport import (
    CapsuleHandler,
    CapsuleServer,
    WifiGatewayClient,
    udp_announce,
    udp_listen,
)

__all__ = [
    "Capsule",
    "QRFrame",
    "QRFramer",
    "WifiGatewayClient",
    "CapsuleHandler",
    "CapsuleServer",
    "udp_announce",
    "udp_listen",
    "I2PGatewayClient",
]
