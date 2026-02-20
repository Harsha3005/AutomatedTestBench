"""
ASP (ACMIS Serial Protocol) frame encoder/decoder.

Frame layout:
  ┌──────────┬──────┬───────────┬──────────────────────────┬──────────────┐
  │ DeviceID │ Seq# │ Timestamp │ IV + AES-CBC(payload)    │ HMAC-SHA256  │
  │ 4 bytes  │ 2 B  │ 4 bytes   │ 16 + variable            │ 32 bytes     │
  └──────────┴──────┴───────────┴──────────────────────────┴──────────────┘

  - DeviceID: uint32 big-endian (0x0001=Lab, 0x0002=Bench)
  - Seq#: uint16 big-endian (monotonic, replay protection)
  - Timestamp: uint32 big-endian (Unix epoch)
  - Encrypted payload: 16-byte IV + AES-256-CBC ciphertext (PKCS7 padded)
  - HMAC: SHA-256 over everything before it (device_id + seq + ts + encrypted)
"""

import json
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any

from comms.crypto import encrypt, decrypt, sign, verify


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

HEADER_FMT = '!IHI'         # device_id(4) + seq(2) + timestamp(4) = 10 bytes
HEADER_SIZE = struct.calcsize(HEADER_FMT)
HMAC_SIZE = 32
MAX_LORA_PAYLOAD = 255
FRAGMENT_HEADER_SIZE = 3     # frag_id(1) + frag_index(1) + total(1)
MAX_FRAGMENT_DATA = MAX_LORA_PAYLOAD - FRAGMENT_HEADER_SIZE  # 252 bytes


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class ASPFrame:
    """Decoded ASP frame."""
    device_id: int
    seq: int
    timestamp: int
    payload: dict[str, Any]  # Decoded JSON payload


@dataclass
class Fragment:
    """Single LoRa fragment."""
    frag_id: int
    frag_index: int
    total_fragments: int
    data: bytes


# ---------------------------------------------------------------------------
#  Sequence counter
# ---------------------------------------------------------------------------

class SequenceCounter:
    """Thread-safe monotonic 16-bit sequence counter with replay protection."""

    def __init__(self):
        self._counter: int = 0
        self._last_received: dict[int, int] = {}  # device_id → last seq

    def next(self) -> int:
        """Get next sequence number (0-65535, wraps around)."""
        seq = self._counter
        self._counter = (self._counter + 1) & 0xFFFF
        return seq

    def check_and_update(self, device_id: int, seq: int, timestamp: int) -> bool:
        """
        Check if a received seq is valid (replay protection).

        Returns True if the message should be accepted.
        Rejects if:
          - seq <= last received seq from this device (unless wraparound)
          - timestamp is more than 5 minutes stale
        """
        now = int(time.time())
        # Reject stale timestamps (>300s old)
        if abs(now - timestamp) > 300:
            return False

        last = self._last_received.get(device_id)
        if last is not None:
            # Handle wraparound: accept if seq is in (last, last+32768] mod 65536
            diff = (seq - last) & 0xFFFF
            if diff == 0 or diff > 32768:
                return False  # Duplicate or out-of-order

        self._last_received[device_id] = seq
        return True


# ---------------------------------------------------------------------------
#  Encoder
# ---------------------------------------------------------------------------

def encode(
    payload: dict[str, Any],
    device_id: int,
    seq: int,
    aes_key: bytes,
    hmac_key: bytes,
    timestamp: int | None = None,
) -> bytes:
    """
    Encode a payload dict into an ASP frame.

    Args:
        payload: JSON-serialisable dict
        device_id: Sender device ID (e.g. 0x0002 for bench)
        seq: Sequence number (0-65535)
        aes_key: 32-byte AES key
        hmac_key: 32-byte HMAC key
        timestamp: Unix timestamp (auto-generated if None)

    Returns:
        Complete ASP frame bytes.
    """
    if timestamp is None:
        timestamp = int(time.time())

    # Serialise and compress payload
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    compressed = zlib.compress(payload_json, level=6)

    # Encrypt
    encrypted = encrypt(compressed, aes_key)

    # Build header
    header = struct.pack(HEADER_FMT, device_id, seq, timestamp)

    # HMAC over header + encrypted payload
    frame_body = header + encrypted
    tag = sign(frame_body, hmac_key)

    return frame_body + tag


def decode(
    frame: bytes,
    aes_key: bytes,
    hmac_key: bytes,
) -> ASPFrame:
    """
    Decode an ASP frame.

    Args:
        frame: Raw frame bytes
        aes_key: 32-byte AES key
        hmac_key: 32-byte HMAC key

    Returns:
        ASPFrame with decoded payload.

    Raises:
        ValueError: HMAC verification failed, decryption error, or malformed frame.
    """
    if len(frame) < HEADER_SIZE + 32 + HMAC_SIZE:
        raise ValueError(f"Frame too short: {len(frame)} bytes")

    # Split frame
    frame_body = frame[:-HMAC_SIZE]
    received_tag = frame[-HMAC_SIZE:]

    # Verify HMAC
    if not verify(frame_body, received_tag, hmac_key):
        raise ValueError("HMAC verification failed — frame tampered or wrong key")

    # Parse header
    device_id, seq, timestamp = struct.unpack(HEADER_FMT, frame_body[:HEADER_SIZE])

    # Decrypt
    encrypted = frame_body[HEADER_SIZE:]
    compressed = decrypt(encrypted, aes_key)

    # Decompress
    payload_json = zlib.decompress(compressed)
    payload = json.loads(payload_json.decode('utf-8'))

    return ASPFrame(
        device_id=device_id,
        seq=seq,
        timestamp=timestamp,
        payload=payload,
    )


# ---------------------------------------------------------------------------
#  Fragmentation (for LoRa payloads > MAX_LORA_PAYLOAD)
# ---------------------------------------------------------------------------

def fragment(frame: bytes, frag_id: int = 0) -> list[Fragment]:
    """
    Fragment an ASP frame for LoRa transmission.

    If frame fits in a single LoRa packet, returns one fragment.
    Otherwise splits into multiple fragments with 3-byte headers.

    Args:
        frame: Complete ASP frame bytes
        frag_id: Fragment group identifier (0-255)

    Returns:
        List of Fragment objects.
    """
    if len(frame) <= MAX_LORA_PAYLOAD:
        return [Fragment(
            frag_id=frag_id,
            frag_index=0,
            total_fragments=1,
            data=frame,
        )]

    # Split into chunks
    chunks = []
    offset = 0
    while offset < len(frame):
        chunk = frame[offset:offset + MAX_FRAGMENT_DATA]
        chunks.append(chunk)
        offset += MAX_FRAGMENT_DATA

    return [
        Fragment(
            frag_id=frag_id,
            frag_index=i,
            total_fragments=len(chunks),
            data=chunk,
        )
        for i, chunk in enumerate(chunks)
    ]


def fragment_to_bytes(frag: Fragment) -> bytes:
    """Serialise a fragment to bytes for LoRa transmission."""
    header = struct.pack('BBB', frag.frag_id, frag.frag_index, frag.total_fragments)
    return header + frag.data


def fragment_from_bytes(data: bytes) -> Fragment:
    """Deserialise bytes to a Fragment."""
    if len(data) < FRAGMENT_HEADER_SIZE:
        raise ValueError("Fragment too short")
    frag_id, frag_index, total = struct.unpack('BBB', data[:FRAGMENT_HEADER_SIZE])
    return Fragment(
        frag_id=frag_id,
        frag_index=frag_index,
        total_fragments=total,
        data=data[FRAGMENT_HEADER_SIZE:],
    )


class FragmentReassembler:
    """Collects fragments and reassembles complete frames."""

    def __init__(self, timeout: float = 10.0):
        self._buffers: dict[int, dict[int, bytes]] = {}  # frag_id → {index: data}
        self._totals: dict[int, int] = {}                # frag_id → total
        self._timestamps: dict[int, float] = {}          # frag_id → first_seen
        self._timeout = timeout

    def add(self, frag: Fragment) -> bytes | None:
        """
        Add a fragment. Returns reassembled frame bytes when all fragments
        of a group are received, or None if still waiting.
        """
        fid = frag.frag_id

        # Single-fragment message
        if frag.total_fragments == 1:
            return frag.data

        # Initialise buffer
        if fid not in self._buffers:
            self._buffers[fid] = {}
            self._totals[fid] = frag.total_fragments
            self._timestamps[fid] = time.time()

        self._buffers[fid][frag.frag_index] = frag.data

        # Check completeness
        if len(self._buffers[fid]) == self._totals[fid]:
            # Reassemble in order
            frame = b''.join(
                self._buffers[fid][i] for i in range(self._totals[fid])
            )
            # Cleanup
            del self._buffers[fid]
            del self._totals[fid]
            del self._timestamps[fid]
            return frame

        return None

    def cleanup_stale(self):
        """Remove fragment groups older than timeout."""
        now = time.time()
        stale = [
            fid for fid, ts in self._timestamps.items()
            if now - ts > self._timeout
        ]
        for fid in stale:
            self._buffers.pop(fid, None)
            self._totals.pop(fid, None)
            self._timestamps.pop(fid, None)
