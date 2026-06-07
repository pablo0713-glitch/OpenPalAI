from __future__ import annotations

"""
Minimal Second Life protocol implementation.
Handles only what OpenPalAI needs: login, IM receive, IM send.

Uses only Python stdlib — no third-party SL libraries required.

Protocol references:
  https://wiki.secondlife.com/wiki/Login_API
  https://wiki.secondlife.com/wiki/SL_Packet_Format
  https://wiki.secondlife.com/wiki/ImprovedInstantMessage
"""

import asyncio
import hashlib
import logging
import struct
import time
import uuid
import xmlrpc.client
from dataclasses import dataclass, field
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

LOGIN_URI = "https://login.agni.lindenlab.com/cgi-bin/login.cgi"

# ------------------------------------------------------------------ Packet IDs
# SL uses three frequency tiers. Prefix bytes signal the tier:
#   High:   1 byte  (0x01..0xFE)
#   Medium: 2 bytes (0xFF, 0x01..0xFE)
#   Low:    4 bytes (0xFF, 0xFF, uint16 big-endian)

# Packet ID bytes (as sent on the wire, after the header)
PKT_USE_CIRCUIT_CODE        = b'\xff\xff\x00\x03'   # Low  3
PKT_COMPLETE_AGENT_MOVEMENT = b'\xff\xf9'           # Medium 249
PKT_AGENT_UPDATE            = b'\x04'               # High 4
PKT_IMPROVED_IM             = b'\xff\xfe'           # Medium 254
PKT_PACKET_ACK              = b'\xff\xff\xff\xfb'   # Fixed-ish (simplified)
PKT_AGENT_THROTTLE          = b'\xff\x96'           # Medium 150
PKT_REGION_HANDSHAKE        = b'\xff\xff\x00\x94'   # Low 148
PKT_REGION_HANDSHAKE_REPLY  = b'\xff\xff\x00\x95'   # Low 149
PKT_START_PING_CHECK        = b'\x01'               # High 1
PKT_COMPLETE_PING_CHECK     = b'\x02'               # High 2

# Header flags
FLAG_RELIABLE = 0x40
FLAG_ZERO_CODE = 0x80
FLAG_ACK = 0x10


# ------------------------------------------------------------------ Helpers

def _uuid_bytes(u: str) -> bytes:
    """Convert UUID string to 16 raw bytes."""
    return uuid.UUID(u).bytes


def _md5_password(password: str) -> str:
    """SL expects MD5 hashed password prefixed with '$1$'."""
    return "$1$" + hashlib.md5(password.encode()).hexdigest()


def _pack_header(sequence: int, flags: int = FLAG_RELIABLE) -> bytes:
    """Build a 6-byte packet header."""
    return struct.pack(">BIB", flags, sequence, 0)


def _unpack_header(data: bytes) -> tuple[int, int, int]:
    """Returns (flags, sequence, extra_offset)."""
    flags = data[0]
    seq = struct.unpack(">I", data[1:5])[0]
    offset = data[5]
    return flags, seq, offset


# ------------------------------------------------------------------ Login

@dataclass
class LoginResult:
    session_id: str
    agent_id: str
    circuit_code: int
    sim_ip: str
    sim_port: int
    seed_capability: str
    region_name: str = ""
    look_at: str = ""


def sl_login(firstname: str, lastname: str, password: str) -> LoginResult:
    """Synchronous XMLRPC login. Returns LoginResult or raises on failure."""
    params = {
        "first": firstname,
        "last": lastname,
        "passwd": _md5_password(password),
        "start": "last",
        "channel": "openpalai-bot",
        "version": "1.0.0",
        "platform": "lnx",
        "mac": "00:00:00:00:00:00",
        "id0": "00000000000000000000000000000000",
        "agree_to_tos": "true",
        "read_critical": "true",
    }

    transport = xmlrpc.client.SafeTransport()
    proxy = xmlrpc.client.ServerProxy(LOGIN_URI, transport=transport)

    try:
        result = proxy.login_to_simulator(params)
    except Exception as exc:
        raise ConnectionError(f"XMLRPC login failed: {exc}") from exc

    if str(result.get("login", "")).lower() != "true":
        reason = result.get("message", result.get("reason", "Unknown"))
        raise PermissionError(f"SL login rejected: {reason}")

    return LoginResult(
        session_id=result["session_id"],
        agent_id=result["agent_id"],
        circuit_code=int(result["circuit_code"]),
        sim_ip=result["sim_ip"],
        sim_port=int(result["sim_port"]),
        seed_capability=result.get("seed_capability", ""),
        region_name=result.get("region_name", ""),
    )


# ------------------------------------------------------------------ IM message

@dataclass
class IncomingIM:
    from_agent_id: str
    from_name: str
    message: str
    session_id: str = ""
    timestamp: int = 0


# ------------------------------------------------------------------ UDP Protocol

class SLProtocol(asyncio.DatagramProtocol):
    """
    Async UDP transport for the SL viewer protocol.
    Handles circuit setup, keepalive, IM receive/send, and ACKs.
    """

    def __init__(
        self,
        login: LoginResult,
        on_im: Callable[[IncomingIM], Awaitable[None]],
    ) -> None:
        self._login = login
        self._on_im = on_im
        self._transport: asyncio.DatagramTransport | None = None
        self._seq = 0
        self._pending_acks: list[int] = []
        self._connected = False

    # --------------------------------------------------------- asyncio hooks

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self._transport = transport
        logger.info("UDP socket open to %s:%s", self._login.sim_ip, self._login.sim_port)
        asyncio.get_event_loop().create_task(self._handshake())

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        try:
            self._handle_packet(data)
        except Exception:
            logger.exception("Error parsing SL packet")

    def error_received(self, exc: Exception) -> None:
        logger.error("SL UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("SL UDP connection lost: %s", exc)
        self._connected = False

    # --------------------------------------------------------- handshake

    async def _handshake(self) -> None:
        await asyncio.sleep(0.1)
        self._send_use_circuit_code()
        await asyncio.sleep(0.5)
        self._send_complete_agent_movement()
        await asyncio.sleep(0.5)
        self._connected = True
        logger.info("SL circuit established.")
        # Start keepalive loop
        asyncio.get_event_loop().create_task(self._keepalive_loop())

    async def _keepalive_loop(self) -> None:
        """Send AgentUpdate every 30 seconds to stay connected."""
        while self._connected:
            await asyncio.sleep(30)
            self._send_agent_update()
            self._flush_acks()

    # --------------------------------------------------------- packet builders

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _send(self, packet_id: bytes, body: bytes, reliable: bool = True) -> None:
        flags = FLAG_RELIABLE if reliable else 0
        header = _pack_header(self._next_seq(), flags)
        self._transport.sendto(header + packet_id + body)

    def _send_use_circuit_code(self) -> None:
        body = (
            struct.pack(">I", self._login.circuit_code)
            + _uuid_bytes(self._login.session_id)
            + _uuid_bytes(self._login.agent_id)
        )
        self._send(PKT_USE_CIRCUIT_CODE, body)
        logger.debug("Sent UseCircuitCode")

    def _send_complete_agent_movement(self) -> None:
        body = (
            _uuid_bytes(self._login.agent_id)
            + _uuid_bytes(self._login.session_id)
            + struct.pack(">I", self._login.circuit_code)
        )
        self._send(PKT_COMPLETE_AGENT_MOVEMENT, body)
        logger.debug("Sent CompleteAgentMovement")

    def _send_agent_update(self) -> None:
        # Minimal AgentUpdate — camera/body zeroed out
        body = (
            _uuid_bytes(self._login.agent_id)
            + _uuid_bytes(self._login.session_id)
            + b'\x00' * 48   # body rotation, head rotation, state, camera pos/axes
            + struct.pack(">f", 128.0)  # far
            + struct.pack(">I", 0)      # control flags
            + b'\x00'                    # flags
        )
        self._send(PKT_AGENT_UPDATE, body, reliable=False)

    def _send_region_handshake_reply(self) -> None:
        body = (
            _uuid_bytes(self._login.agent_id)
            + _uuid_bytes(self._login.session_id)
            + struct.pack(">I", 0)  # Flags
        )
        self._send(PKT_REGION_HANDSHAKE_REPLY, body)
        logger.debug("Sent RegionHandshakeReply")

    def _send_complete_ping_check(self, ping_id: int) -> None:
        body = struct.pack("B", ping_id)
        self._send(PKT_COMPLETE_PING_CHECK, body, reliable=False)

    def _flush_acks(self) -> None:
        if not self._pending_acks:
            return
        # PacketAck body: count (uint8) + list of uint32 sequence numbers
        acks = self._pending_acks[:255]
        self._pending_acks = self._pending_acks[255:]
        body = struct.pack("B", len(acks))
        for seq in acks:
            body += struct.pack(">I", seq)
        self._send(PKT_PACKET_ACK, body, reliable=False)

    # --------------------------------------------------------- send IM

    def send_instant_message(self, to_agent_id: str, message: str) -> None:
        """Send a private IM to another avatar."""
        timestamp = int(time.time())
        # IM dialog type 0 = plain IM
        msg_bytes = message.encode("utf-8") + b'\x00'

        body = (
            _uuid_bytes(self._login.agent_id)          # AgentID
            + _uuid_bytes(self._login.session_id)       # SessionID
            + b'\x00'                                    # FromGroup (bool)
            + _uuid_bytes(to_agent_id)                  # ToAgentID
            + struct.pack(">I", self._login.circuit_code)  # ParentEstateID (reuse CC)
            + _uuid_bytes("00000000-0000-0000-0000-000000000000")  # RegionID
            + struct.pack(">fff", 0.0, 0.0, 0.0)        # Position
            + b'\x00'                                    # Offline (0 = online)
            + b'\x00'                                    # Dialog (0 = plain IM)
            + _uuid_bytes("00000000-0000-0000-0000-000000000000")  # ID (session)
            + struct.pack(">I", timestamp)               # Timestamp
            + b'Agent Avatar\x00'                        # FromAgentName (null-term)
            + struct.pack(">H", len(msg_bytes))          # Message length
            + msg_bytes                                  # Message
            + struct.pack(">B", 0)                       # BinaryBucket length
        )
        self._send(PKT_IMPROVED_IM, body)

    # --------------------------------------------------------- packet parser

    def _handle_packet(self, data: bytes) -> None:
        if len(data) < 6:
            return

        flags, seq, offset = _unpack_header(data)
        body_start = 6 + offset
        body = data[body_start:]

        # Queue ACK for reliable packets
        if flags & FLAG_RELIABLE:
            self._pending_acks.append(seq)

        if not body:
            return

        # Detect packet type by prefix — check Low (4-byte) before Medium (2-byte) before High (1-byte)
        if body[:4] == PKT_USE_CIRCUIT_CODE:
            pass  # not incoming
        elif body[:4] == PKT_REGION_HANDSHAKE:
            self._send_region_handshake_reply()
        elif body[:4] == PKT_PACKET_ACK:
            pass  # our ACKs being ACKed
        elif body[:2] == PKT_IMPROVED_IM:
            self._parse_im(body[2:])
        elif body[:1] == PKT_START_PING_CHECK:
            ping_id = body[1] if len(body) > 1 else 0
            self._send_complete_ping_check(ping_id)
        # Silently ignore everything else

    def _parse_im(self, body: bytes) -> None:
        """Parse an ImprovedInstantMessage packet body and fire on_im."""
        try:
            pos = 0

            def read(n: int) -> bytes:
                nonlocal pos
                chunk = body[pos: pos + n]
                pos += n
                return chunk

            agent_id_bytes = read(16)
            session_id_bytes = read(16)
            from_group = read(1)[0]
            to_agent_id_bytes = read(16)
            parent_estate = struct.unpack(">I", read(4))[0]
            region_id = read(16)
            position = read(12)
            offline = read(1)[0]
            dialog = read(1)[0]
            im_session_id = read(16)
            timestamp = struct.unpack(">I", read(4))[0]

            # Null-terminated from name
            end = body.index(b'\x00', pos)
            from_name = body[pos:end].decode("utf-8", errors="replace")
            pos = end + 1

            msg_len = struct.unpack(">H", read(2))[0]
            msg_bytes = read(msg_len)
            message = msg_bytes.rstrip(b'\x00').decode("utf-8", errors="replace")

            from_agent_id = str(uuid.UUID(bytes=agent_id_bytes))

            # Skip messages from ourselves
            if from_agent_id == self._login.agent_id:
                return

            # Dialog 0 = plain IM (what we want)
            # Dialog 1 = group IM, 6 = from object, etc. — skip
            if dialog != 0:
                return

            incoming = IncomingIM(
                from_agent_id=from_agent_id,
                from_name=from_name,
                message=message,
                timestamp=timestamp,
            )

            asyncio.get_event_loop().create_task(self._on_im(incoming))

        except Exception:
            logger.exception("Failed to parse IM packet")
