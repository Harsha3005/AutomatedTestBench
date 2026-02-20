"""
Message queue with ACK tracking and retry logic for ASP protocol.

Handles outgoing message queue, ACK wait, 3-retry with 3s timeout,
and graceful degradation when LoRa link is down (queues for later).

Thread-safe — runs its own dispatch thread.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from comms.protocol import SequenceCounter, encode, decode, ASPFrame

logger = logging.getLogger(__name__)

# Defaults
ACK_TIMEOUT = 3.0       # seconds
MAX_RETRIES = 3
HEARTBEAT_INTERVAL = 30  # seconds


class MessageStatus(Enum):
    PENDING = 'pending'
    SENT = 'sent'
    ACKED = 'acked'
    FAILED = 'failed'
    QUEUED = 'queued'   # Queued for resend when link recovers


@dataclass
class OutgoingMessage:
    """A message waiting to be sent or awaiting ACK."""
    msg_id: int
    payload: dict[str, Any]
    status: MessageStatus = MessageStatus.PENDING
    seq: int = 0
    retries: int = 0
    sent_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    ack_received: threading.Event = field(default_factory=threading.Event)


class MessageQueue:
    """
    Outgoing message queue with ACK tracking.

    Usage:
        mq = MessageQueue(
            device_id=0x0002,
            aes_key=aes_key,
            hmac_key=hmac_key,
            send_func=my_send_func,  # callable(frame_bytes) -> bool
        )
        mq.start()
        mq.send({'command': 'TEST_STATUS', ...})
        mq.stop()
    """

    def __init__(
        self,
        device_id: int,
        aes_key: bytes,
        hmac_key: bytes,
        send_func: Callable[[bytes], bool] | None = None,
        on_receive: Callable[[ASPFrame], None] | None = None,
    ):
        """
        Args:
            device_id: This device's ASP ID (e.g. 0x0002 for bench)
            aes_key: 32-byte AES key
            hmac_key: 32-byte HMAC key
            send_func: Callback to transmit frame bytes (returns True on success)
            on_receive: Callback for incoming decoded messages
        """
        self._device_id = device_id
        self._aes_key = aes_key
        self._hmac_key = hmac_key
        self._send_func = send_func
        self._on_receive = on_receive

        self._seq = SequenceCounter()
        self._lock = threading.Lock()
        self._queue: deque[OutgoingMessage] = deque()
        self._pending_acks: dict[int, OutgoingMessage] = {}  # seq → message
        self._offline_queue: deque[OutgoingMessage] = deque()  # queued for resend
        self._msg_counter = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._link_online = True
        self._last_heartbeat = 0.0

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the dispatch thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._dispatch_loop,
            name='MessageQueue',
            daemon=True,
        )
        self._thread.start()
        logger.info("MessageQueue started (device_id=0x%04X)", self._device_id)

    def stop(self):
        """Stop the dispatch thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("MessageQueue stopped")

    # ------------------------------------------------------------------
    #  Send API
    # ------------------------------------------------------------------

    def send(
        self,
        payload: dict[str, Any],
        require_ack: bool = True,
    ) -> OutgoingMessage:
        """
        Queue a message for sending.

        Args:
            payload: JSON dict to send
            require_ack: If True, waits for ACK (with retry)

        Returns:
            OutgoingMessage tracking object.
        """
        with self._lock:
            self._msg_counter += 1
            msg = OutgoingMessage(
                msg_id=self._msg_counter,
                payload=payload,
            )
            self._queue.append(msg)
            logger.debug("Queued message #%d: %s", msg.msg_id, payload.get('command', '?'))
        return msg

    def send_and_wait(
        self,
        payload: dict[str, Any],
        timeout: float = ACK_TIMEOUT * MAX_RETRIES + 1,
    ) -> bool:
        """Send a message and block until ACK or failure."""
        msg = self.send(payload, require_ack=True)
        msg.ack_received.wait(timeout=timeout)
        return msg.status == MessageStatus.ACKED

    # ------------------------------------------------------------------
    #  Receive API
    # ------------------------------------------------------------------

    def receive_frame(self, frame_bytes: bytes):
        """
        Process an incoming ASP frame (received from LoRa/serial).

        Decodes the frame, checks for ACK responses, and dispatches
        to the on_receive callback.
        """
        try:
            asp_frame = decode(frame_bytes, self._aes_key, self._hmac_key)
        except ValueError as e:
            logger.warning("Failed to decode incoming frame: %s", e)
            return

        # Replay protection
        if not self._seq.check_and_update(
            asp_frame.device_id, asp_frame.seq, asp_frame.timestamp
        ):
            logger.warning(
                "Replay rejected: device=0x%04X seq=%d",
                asp_frame.device_id, asp_frame.seq,
            )
            return

        # Check if this is an ACK for a pending message
        command = asp_frame.payload.get('command', '')
        if command.endswith('_ACK') or asp_frame.payload.get('ack'):
            ack_seq = asp_frame.payload.get('ack_seq')
            if ack_seq is not None:
                self._handle_ack(ack_seq)
                return

        # Dispatch to handler
        if self._on_receive:
            try:
                self._on_receive(asp_frame)
            except Exception:
                logger.exception("Error in message receive handler")

    def _handle_ack(self, ack_seq: int):
        """Mark a pending message as ACKed."""
        with self._lock:
            msg = self._pending_acks.pop(ack_seq, None)
            if msg:
                msg.status = MessageStatus.ACKED
                msg.ack_received.set()
                logger.debug("ACK received for seq=%d (msg #%d)", ack_seq, msg.msg_id)

    # ------------------------------------------------------------------
    #  Link status
    # ------------------------------------------------------------------

    def set_link_online(self, online: bool):
        """Update LoRa link status."""
        was_online = self._link_online
        self._link_online = online
        if online and not was_online:
            logger.info("Link online — flushing offline queue (%d messages)", len(self._offline_queue))
            with self._lock:
                while self._offline_queue:
                    msg = self._offline_queue.popleft()
                    msg.status = MessageStatus.PENDING
                    msg.retries = 0
                    self._queue.append(msg)

    @property
    def link_online(self) -> bool:
        return self._link_online

    @property
    def queue_depth(self) -> int:
        """Total messages pending (active + offline)."""
        with self._lock:
            return len(self._queue) + len(self._offline_queue)

    @property
    def offline_queue_depth(self) -> int:
        with self._lock:
            return len(self._offline_queue)

    # ------------------------------------------------------------------
    #  Dispatch loop
    # ------------------------------------------------------------------

    def _dispatch_loop(self):
        """Main dispatch loop — sends messages, checks ACK timeouts."""
        while self._running:
            # Send next queued message
            msg = None
            with self._lock:
                if self._queue:
                    msg = self._queue.popleft()

            if msg:
                self._dispatch_message(msg)

            # Check ACK timeouts
            self._check_timeouts()

            time.sleep(0.1)

    def _dispatch_message(self, msg: OutgoingMessage):
        """Encode and send a single message."""
        if not self._link_online:
            msg.status = MessageStatus.QUEUED
            with self._lock:
                self._offline_queue.append(msg)
            logger.debug("Link offline — queued msg #%d for later", msg.msg_id)
            return

        if not self._send_func:
            msg.status = MessageStatus.FAILED
            msg.ack_received.set()
            return

        # Encode
        seq = self._seq.next()
        msg.seq = seq
        frame = encode(
            payload=msg.payload,
            device_id=self._device_id,
            seq=seq,
            aes_key=self._aes_key,
            hmac_key=self._hmac_key,
        )

        # Send
        try:
            success = self._send_func(frame)
        except Exception:
            logger.exception("Send failed for msg #%d", msg.msg_id)
            success = False

        if success:
            msg.status = MessageStatus.SENT
            msg.sent_at = time.time()
            with self._lock:
                self._pending_acks[seq] = msg
            logger.debug("Sent msg #%d (seq=%d)", msg.msg_id, seq)
        else:
            # Retry or fail
            msg.retries += 1
            if msg.retries < MAX_RETRIES:
                with self._lock:
                    self._queue.appendleft(msg)
                logger.debug("Send failed, retry %d/%d for msg #%d",
                             msg.retries, MAX_RETRIES, msg.msg_id)
            else:
                msg.status = MessageStatus.FAILED
                msg.ack_received.set()
                logger.warning("Message #%d FAILED after %d retries", msg.msg_id, MAX_RETRIES)

    def _check_timeouts(self):
        """Check for ACK timeouts and trigger retries."""
        now = time.time()
        timed_out = []

        with self._lock:
            for seq, msg in list(self._pending_acks.items()):
                if now - msg.sent_at > ACK_TIMEOUT:
                    timed_out.append((seq, msg))

        for seq, msg in timed_out:
            with self._lock:
                self._pending_acks.pop(seq, None)

            msg.retries += 1
            if msg.retries < MAX_RETRIES:
                logger.debug(
                    "ACK timeout for msg #%d (seq=%d), retry %d/%d",
                    msg.msg_id, seq, msg.retries, MAX_RETRIES,
                )
                with self._lock:
                    self._queue.appendleft(msg)
            else:
                msg.status = MessageStatus.FAILED
                msg.ack_received.set()
                logger.warning(
                    "Message #%d FAILED — no ACK after %d retries",
                    msg.msg_id, MAX_RETRIES,
                )
