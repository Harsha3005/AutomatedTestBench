"""
LoRa communication handler for bench-lab ASP messaging.

Wraps comms/protocol.py, comms/message_queue.py, and comms/serial_handler.py
into a high-level bidirectional LoRa handler with domain-specific message types.

Usage:
    handler = get_lora_handler()
    handler.start()
    handler.send_test_status(test_id, q_point, state, flow, pressure, temp)
    handler.stop()
"""

import json
import logging
import threading
import time
from enum import Enum
from typing import Callable

from django.conf import settings

from comms.crypto import get_keys
from comms.message_queue import MessageQueue
from comms.protocol import FragmentReassembler, fragment, fragment_to_bytes, fragment_from_bytes
from comms.serial_handler import SerialHandler

logger = logging.getLogger(__name__)

# Defaults (overridable via Django settings)
HEARTBEAT_INTERVAL_S = 30.0


# ---------------------------------------------------------------------------
#  Message types (Doc8 Section 13)
# ---------------------------------------------------------------------------

class MessageType(Enum):
    """All LoRa message types for bench-lab communication."""
    START_TEST = 'START_TEST'
    START_TEST_ACK = 'START_TEST_ACK'
    TEST_STATUS = 'TEST_STATUS'
    TEST_RESULT = 'TEST_RESULT'
    TEST_COMPLETE = 'TEST_COMPLETE'
    RESULT_REQUEST = 'RESULT_REQUEST'
    EMERGENCY_STOP = 'EMERGENCY_STOP'
    EMERGENCY_ACK = 'EMERGENCY_ACK'
    APPROVAL_STATUS = 'APPROVAL_STATUS'
    HEARTBEAT = 'HEARTBEAT'


# ---------------------------------------------------------------------------
#  LoRa Handler
# ---------------------------------------------------------------------------

class LoRaHandler:
    """
    Bidirectional LoRa ASP handler for bench-lab communication.

    Outgoing (bench -> lab):
        send_test_status(), send_test_result(), send_test_complete(),
        send_start_test_ack(), send_emergency_ack(), send_heartbeat()

    Incoming (lab -> bench):
        Dispatches to registered handlers via on_start_test(),
        on_emergency_stop(), on_result_request(), on_approval_status()
    """

    def __init__(self):
        self._aes_key, self._hmac_key = get_keys()
        self._device_id = getattr(settings, 'ASP_DEVICE_ID', 0x0002)
        self._lora_port = getattr(settings, 'LORA_SERIAL_PORT', '/dev/ttyLORA')
        self._lora_baud = getattr(settings, 'LORA_SERIAL_BAUD', 115200)

        self._serial: SerialHandler | None = None
        self._mq: MessageQueue | None = None
        self._reassembler = FragmentReassembler(timeout=10.0)
        self._frag_id_counter = 0

        self._running = False
        self._heartbeat_thread: threading.Thread | None = None
        self._receive_thread: threading.Thread | None = None
        self._link_online = False

        # Incoming message callbacks: command → [callable]
        self._handlers: dict[str, list[Callable]] = {}

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Initialize serial port and start background threads."""
        if self._running:
            return

        self._serial = SerialHandler(self._lora_port, self._lora_baud)
        connected = self._serial.connect()
        self._link_online = connected

        self._mq = MessageQueue(
            device_id=self._device_id,
            aes_key=self._aes_key,
            hmac_key=self._hmac_key,
            send_func=self._transmit_frame,
            on_receive=self._dispatch_incoming,
        )
        self._mq.set_link_online(self._link_online)
        self._mq.start()

        self._running = True

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name='LoRa-Heartbeat', daemon=True,
        )
        self._heartbeat_thread.start()

        if connected:
            self._receive_thread = threading.Thread(
                target=self._receive_loop, name='LoRa-Receive', daemon=True,
            )
            self._receive_thread.start()

        logger.info("LoRaHandler started (link=%s)", 'online' if connected else 'offline')

    def stop(self):
        """Stop all threads and close serial."""
        self._running = False
        if self._mq:
            self._mq.stop()
        if self._serial:
            self._serial.disconnect()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=3.0)
        if self._receive_thread:
            self._receive_thread.join(timeout=3.0)
        logger.info("LoRaHandler stopped")

    @property
    def link_online(self) -> bool:
        return self._link_online

    # ------------------------------------------------------------------
    #  Outgoing: bench -> lab
    # ------------------------------------------------------------------

    def send_test_status(self, test_id: int, q_point: str, state: str,
                         flow_lph: float = 0, pressure_bar: float = 0,
                         temp_c: float = 0):
        """Send periodic test status (every ~5s during active test)."""
        self._send({
            'command': MessageType.TEST_STATUS.value,
            'test_id': test_id,
            'q_point': q_point,
            'state': state,
            'flow_rate_lph': round(flow_lph, 1),
            'pressure_up_bar': round(pressure_bar, 2),
            'temperature_c': round(temp_c, 1),
        })

    def send_test_result(self, test_id: int, q_point_data: dict):
        """Send individual Q-point result after CALCULATE."""
        payload = {
            'command': MessageType.TEST_RESULT.value,
            'test_id': test_id,
        }
        payload.update(q_point_data)
        self._send(payload)

    def send_test_complete(self, test_summary: dict):
        """Send test completion summary with overall verdict."""
        payload = {
            'command': MessageType.TEST_COMPLETE.value,
        }
        payload.update(test_summary)
        self._send(payload)

    def send_start_test_ack(self, test_id: int, status: str = 'acknowledged'):
        """ACK a START_TEST from lab."""
        self._send({
            'command': MessageType.START_TEST_ACK.value,
            'test_id': test_id,
            'status': status,
        })

    def send_emergency_ack(self, status: str = 'aborted', reason: str = ''):
        """ACK an EMERGENCY_STOP from lab."""
        self._send({
            'command': MessageType.EMERGENCY_ACK.value,
            'status': status,
            'reason': reason,
        })

    def send_heartbeat(self):
        """Send a heartbeat message."""
        self._send({
            'command': MessageType.HEARTBEAT.value,
            'device_id': self._device_id,
            'uptime': int(time.time()),
            'status': 'online',
        })

    def _send(self, payload: dict):
        """Queue a message for sending via MessageQueue."""
        if self._mq:
            self._mq.send(payload)

    # ------------------------------------------------------------------
    #  Incoming: lab -> bench
    # ------------------------------------------------------------------

    def on_start_test(self, callback: Callable):
        """Register handler for START_TEST from lab."""
        self._register_handler(MessageType.START_TEST.value, callback)

    def on_emergency_stop(self, callback: Callable):
        """Register handler for EMERGENCY_STOP from lab."""
        self._register_handler(MessageType.EMERGENCY_STOP.value, callback)

    def on_result_request(self, callback: Callable):
        """Register handler for RESULT_REQUEST from lab."""
        self._register_handler(MessageType.RESULT_REQUEST.value, callback)

    def on_approval_status(self, callback: Callable):
        """Register handler for APPROVAL_STATUS from lab."""
        self._register_handler(MessageType.APPROVAL_STATUS.value, callback)

    def _register_handler(self, command: str, callback: Callable):
        if command not in self._handlers:
            self._handlers[command] = []
        self._handlers[command].append(callback)

    def _dispatch_incoming(self, asp_frame):
        """Route incoming ASP frame to registered handlers."""
        command = asp_frame.payload.get('command', '')
        handlers = self._handlers.get(command, [])
        for handler in handlers:
            try:
                handler(asp_frame.payload)
            except Exception:
                logger.exception("Error in LoRa handler for %s", command)

        # Auto-respond to certain messages
        if command == MessageType.START_TEST.value:
            test_id = asp_frame.payload.get('test_id', 0)
            self.send_start_test_ack(test_id)

        elif command == MessageType.EMERGENCY_STOP.value:
            reason = asp_frame.payload.get('reason', '')
            self.send_emergency_ack(reason=reason)

    # ------------------------------------------------------------------
    #  Transport
    # ------------------------------------------------------------------

    def _transmit_frame(self, frame_bytes: bytes) -> bool:
        """Fragment and send a complete ASP frame via LoRa serial."""
        if not self._serial or not self._serial.is_connected:
            return False

        self._frag_id_counter = (self._frag_id_counter + 1) & 0xFF
        frags = fragment(frame_bytes, frag_id=self._frag_id_counter)

        try:
            for frag_obj in frags:
                raw = fragment_to_bytes(frag_obj)
                cmd = {'cmd': 'LORA_TX', 'data': raw.hex()}
                self._serial.send_command(cmd, timeout=2.0)
            return True
        except Exception:
            logger.debug("LoRa transmit failed", exc_info=True)
            return False

    def _receive_loop(self):
        """Background thread: read incoming LoRa fragments from serial."""
        while self._running:
            try:
                if not self._serial or not self._serial.is_connected:
                    time.sleep(1.0)
                    continue

                line = self._serial._recv_line(timeout=0.5)
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                if msg.get('cmd') == 'LORA_RX':
                    data_hex = msg.get('data', '')
                    raw = bytes.fromhex(data_hex)
                    frag_obj = fragment_from_bytes(raw)
                    frame = self._reassembler.add(frag_obj)
                    if frame is not None:
                        self._mq.receive_frame(frame)

                self._reassembler.cleanup_stale()
            except Exception:
                logger.debug("LoRa receive error", exc_info=True)
                time.sleep(0.5)

    def _heartbeat_loop(self):
        """Send heartbeat every HEARTBEAT_INTERVAL_S."""
        while self._running:
            try:
                self.send_heartbeat()
            except Exception:
                logger.debug("Heartbeat send failed", exc_info=True)
            # Sleep in small intervals for clean shutdown
            for _ in range(int(HEARTBEAT_INTERVAL_S / 0.5)):
                if not self._running:
                    break
                time.sleep(0.5)


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------

_lora_handler: LoRaHandler | None = None
_lora_lock = threading.Lock()


def get_lora_handler() -> LoRaHandler:
    """Get or create the global LoRaHandler singleton."""
    global _lora_handler
    if _lora_handler is None:
        with _lora_lock:
            if _lora_handler is None:
                _lora_handler = LoRaHandler()
    return _lora_handler
