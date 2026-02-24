"""
Unit tests for ASP protocol encode/decode, crypto, and fragmentation.

Run: python manage.py test comms --settings=config.settings_bench
"""

import struct
import time

from django.test import TestCase, override_settings

from comms.crypto import encrypt, decrypt, sign, verify, _bytes_from_hex
from comms.protocol import (
    Fragment,
    FragmentReassembler,
    SequenceCounter,
    decode,
    encode,
    fragment,
    fragment_from_bytes,
    fragment_to_bytes,
    HEADER_SIZE,
    HMAC_SIZE,
)


# Test keys (64 hex chars = 32 bytes)
TEST_AES_KEY_HEX = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2'
TEST_HMAC_KEY_HEX = 'f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e0d1c2b3a4f5e6d7c8b9a0f1e2'
TEST_AES_KEY = _bytes_from_hex(TEST_AES_KEY_HEX)
TEST_HMAC_KEY = _bytes_from_hex(TEST_HMAC_KEY_HEX)
TEST_DEVICE_ID = 0x0002


class CryptoTests(TestCase):
    """Tests for comms/crypto.py"""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt returns original plaintext."""
        plaintext = b'Hello, IIIT-B test bench!'
        encrypted = encrypt(plaintext, TEST_AES_KEY)
        decrypted = decrypt(encrypted, TEST_AES_KEY)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_different_iv(self):
        """Two encryptions of same plaintext produce different ciphertext."""
        plaintext = b'Same message'
        enc1 = encrypt(plaintext, TEST_AES_KEY)
        enc2 = encrypt(plaintext, TEST_AES_KEY)
        self.assertNotEqual(enc1, enc2)

    def test_decrypt_wrong_key(self):
        """Decryption with wrong key raises ValueError."""
        plaintext = b'Secret data'
        encrypted = encrypt(plaintext, TEST_AES_KEY)
        wrong_key = b'\x00' * 32
        with self.assertRaises(ValueError):
            decrypt(encrypted, wrong_key)

    def test_decrypt_short_data(self):
        """Decryption of too-short data raises ValueError."""
        with self.assertRaises(ValueError):
            decrypt(b'short', TEST_AES_KEY)

    def test_encrypt_empty(self):
        """Encrypt/decrypt empty plaintext."""
        plaintext = b''
        encrypted = encrypt(plaintext, TEST_AES_KEY)
        decrypted = decrypt(encrypted, TEST_AES_KEY)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_large_payload(self):
        """Encrypt/decrypt large payload (>4KB)."""
        plaintext = b'X' * 5000
        encrypted = encrypt(plaintext, TEST_AES_KEY)
        decrypted = decrypt(encrypted, TEST_AES_KEY)
        self.assertEqual(decrypted, plaintext)

    def test_sign_verify(self):
        """HMAC sign and verify."""
        data = b'data to sign'
        tag = sign(data, TEST_HMAC_KEY)
        self.assertEqual(len(tag), 32)
        self.assertTrue(verify(data, tag, TEST_HMAC_KEY))

    def test_verify_wrong_key(self):
        """HMAC verify with wrong key returns False."""
        data = b'data'
        tag = sign(data, TEST_HMAC_KEY)
        wrong_key = b'\x00' * 32
        self.assertFalse(verify(data, tag, wrong_key))

    def test_verify_tampered_data(self):
        """HMAC verify with tampered data returns False."""
        data = b'original'
        tag = sign(data, TEST_HMAC_KEY)
        self.assertFalse(verify(b'tampered', tag, TEST_HMAC_KEY))

    def test_bytes_from_hex(self):
        """Hex string to bytes conversion."""
        result = _bytes_from_hex('aabbccdd')
        self.assertEqual(result, b'\xaa\xbb\xcc\xdd')


class ProtocolEncodeDecodeTests(TestCase):
    """Tests for ASP frame encode/decode roundtrip."""

    def test_roundtrip_simple(self):
        """Encode then decode returns original payload."""
        payload = {'command': 'HEARTBEAT', 'status': 'ok'}
        seq = 42
        ts = int(time.time())

        frame = encode(payload, TEST_DEVICE_ID, seq, TEST_AES_KEY, TEST_HMAC_KEY, ts)
        result = decode(frame, TEST_AES_KEY, TEST_HMAC_KEY)

        self.assertEqual(result.device_id, TEST_DEVICE_ID)
        self.assertEqual(result.seq, seq)
        self.assertEqual(result.timestamp, ts)
        self.assertEqual(result.payload, payload)

    def test_roundtrip_complex_payload(self):
        """Encode/decode with complex nested payload."""
        payload = {
            'command': 'TEST_RESULT',
            'test_id': 'TT001',
            'q_point': 'Q3',
            'target_flow_lph': 100.0,
            'actual_flow_lph': 99.5,
            'ref_volume_l': 10.050,
            'dut_volume_l': 10.120,
            'error_pct': 0.696,
            'mpe_pct': 2.0,
            'passed': True,
            'temperature_c': 22.1,
            'weight_kg': 10.032,
        }
        frame = encode(payload, TEST_DEVICE_ID, 100, TEST_AES_KEY, TEST_HMAC_KEY)
        result = decode(frame, TEST_AES_KEY, TEST_HMAC_KEY)
        self.assertEqual(result.payload, payload)

    def test_tampered_frame_rejected(self):
        """Modifying frame bytes causes HMAC failure."""
        payload = {'command': 'TEST_STATUS'}
        frame = encode(payload, TEST_DEVICE_ID, 1, TEST_AES_KEY, TEST_HMAC_KEY)

        tampered = bytearray(frame)
        tampered[HEADER_SIZE + 5] ^= 0xFF
        tampered = bytes(tampered)

        with self.assertRaises(ValueError):
            decode(tampered, TEST_AES_KEY, TEST_HMAC_KEY)

    def test_wrong_key_rejected(self):
        """Decoding with wrong key fails."""
        payload = {'command': 'HEARTBEAT'}
        frame = encode(payload, TEST_DEVICE_ID, 1, TEST_AES_KEY, TEST_HMAC_KEY)
        wrong_key = b'\x00' * 32

        with self.assertRaises(ValueError):
            decode(frame, wrong_key, TEST_HMAC_KEY)

    def test_short_frame_rejected(self):
        """Too-short frame raises ValueError."""
        with self.assertRaises(ValueError):
            decode(b'tooshort', TEST_AES_KEY, TEST_HMAC_KEY)

    def test_frame_structure(self):
        """Verify frame has correct structure."""
        payload = {'cmd': 'test'}
        frame = encode(payload, 0x0001, 0, TEST_AES_KEY, TEST_HMAC_KEY, timestamp=1000)

        self.assertGreaterEqual(len(frame), HEADER_SIZE + 32 + HMAC_SIZE)

        device_id, seq, ts = struct.unpack('!IHI', frame[:HEADER_SIZE])
        self.assertEqual(device_id, 0x0001)
        self.assertEqual(seq, 0)
        self.assertEqual(ts, 1000)


class SequenceCounterTests(TestCase):
    """Tests for sequence counter and replay protection."""

    def test_monotonic_increment(self):
        """Sequence counter increments monotonically."""
        counter = SequenceCounter()
        seqs = [counter.next() for _ in range(5)]
        self.assertEqual(seqs, [0, 1, 2, 3, 4])

    def test_wraparound(self):
        """Sequence counter wraps at 65535."""
        counter = SequenceCounter()
        counter._counter = 65535
        self.assertEqual(counter.next(), 65535)
        self.assertEqual(counter.next(), 0)
        self.assertEqual(counter.next(), 1)

    def test_replay_protection_accepts_valid(self):
        """Valid (higher) sequence accepted."""
        counter = SequenceCounter()
        now = int(time.time())
        self.assertTrue(counter.check_and_update(0x0001, 1, now))
        self.assertTrue(counter.check_and_update(0x0001, 2, now))
        self.assertTrue(counter.check_and_update(0x0001, 10, now))

    def test_replay_protection_rejects_duplicate(self):
        """Duplicate sequence rejected."""
        counter = SequenceCounter()
        now = int(time.time())
        self.assertTrue(counter.check_and_update(0x0001, 5, now))
        self.assertFalse(counter.check_and_update(0x0001, 5, now))

    def test_replay_protection_rejects_old(self):
        """Older sequence rejected."""
        counter = SequenceCounter()
        now = int(time.time())
        self.assertTrue(counter.check_and_update(0x0001, 10, now))
        self.assertFalse(counter.check_and_update(0x0001, 5, now))

    def test_replay_protection_rejects_stale_timestamp(self):
        """Stale timestamp (>5 min old) rejected."""
        counter = SequenceCounter()
        stale = int(time.time()) - 400
        self.assertFalse(counter.check_and_update(0x0001, 1, stale))

    def test_replay_protection_separate_devices(self):
        """Different devices have independent sequence tracking."""
        counter = SequenceCounter()
        now = int(time.time())
        self.assertTrue(counter.check_and_update(0x0001, 5, now))
        self.assertTrue(counter.check_and_update(0x0002, 5, now))


class FragmentationTests(TestCase):
    """Tests for LoRa fragmentation/reassembly."""

    def test_no_fragmentation_needed(self):
        """Small payload produces single fragment."""
        data = b'Hello' * 10
        frags = fragment(data, frag_id=1)
        self.assertEqual(len(frags), 1)
        self.assertEqual(frags[0].data, data)
        self.assertEqual(frags[0].total_fragments, 1)

    def test_fragmentation_splits(self):
        """Large payload is split into multiple fragments."""
        data = b'X' * 600
        frags = fragment(data, frag_id=42)
        self.assertGreater(len(frags), 1)
        for i, f in enumerate(frags):
            self.assertEqual(f.frag_id, 42)
            self.assertEqual(f.frag_index, i)
            self.assertEqual(f.total_fragments, len(frags))

    def test_fragment_serialization(self):
        """Fragment round-trip through bytes."""
        frag_obj = Fragment(frag_id=7, frag_index=2, total_fragments=5, data=b'testdata')
        raw = fragment_to_bytes(frag_obj)
        restored = fragment_from_bytes(raw)
        self.assertEqual(restored.frag_id, 7)
        self.assertEqual(restored.frag_index, 2)
        self.assertEqual(restored.total_fragments, 5)
        self.assertEqual(restored.data, b'testdata')

    def test_reassembly(self):
        """Fragment reassembly restores original data."""
        data = b'A' * 600
        frags = fragment(data, frag_id=1)

        reassembler = FragmentReassembler()
        result = None
        for f in frags:
            result = reassembler.add(f)

        self.assertIsNotNone(result)
        self.assertEqual(result, data)

    def test_reassembly_out_of_order(self):
        """Fragments received out of order are reassembled correctly."""
        data = b'B' * 600
        frags = fragment(data, frag_id=2)
        frags_reversed = list(reversed(frags))

        reassembler = FragmentReassembler()
        result = None
        for f in frags_reversed:
            result = reassembler.add(f)

        self.assertIsNotNone(result)
        self.assertEqual(result, data)

    def test_single_fragment_passthrough(self):
        """Single-fragment message returns data immediately."""
        frag_obj = Fragment(frag_id=0, frag_index=0, total_fragments=1, data=b'small')
        reassembler = FragmentReassembler()
        result = reassembler.add(frag_obj)
        self.assertEqual(result, b'small')

    def test_reassembly_incomplete(self):
        """Incomplete fragment set returns None."""
        data = b'C' * 600
        frags = fragment(data, frag_id=3)
        reassembler = FragmentReassembler()
        result = reassembler.add(frags[0])
        self.assertIsNone(result)


class FullRoundtripTest(TestCase):
    """End-to-end: encode -> fragment -> reassemble -> decode."""

    def test_full_roundtrip(self):
        """Complete encode -> fragment -> reassemble -> decode cycle."""
        payload = {
            'command': 'START_TEST',
            'meter_serial': 'ABC123',
            'meter_size': 'DN20',
            'meter_class': 'R160',
            'dut_mode': 'rs485',
            'q_points': [
                {'q_point': f'Q{i}', 'target_flow_lph': i * 100.0, 'target_volume_l': i * 5.0}
                for i in range(1, 9)
            ],
        }

        seq = 99
        frame = encode(payload, TEST_DEVICE_ID, seq, TEST_AES_KEY, TEST_HMAC_KEY)

        frags = fragment(frame, frag_id=7)

        raw_frags = [fragment_to_bytes(f) for f in frags]
        received_frags = [fragment_from_bytes(r) for r in raw_frags]

        reassembler = FragmentReassembler()
        reassembled = None
        for f in received_frags:
            reassembled = reassembler.add(f)

        self.assertIsNotNone(reassembled)

        result = decode(reassembled, TEST_AES_KEY, TEST_HMAC_KEY)
        self.assertEqual(result.device_id, TEST_DEVICE_ID)
        self.assertEqual(result.seq, seq)
        self.assertEqual(result.payload, payload)


# ===========================================================================
#  LoRa Handler tests (T-407)
# ===========================================================================

from unittest.mock import MagicMock, patch
from comms.lora_handler import MessageType, LoRaHandler, get_lora_handler
from comms.protocol import ASPFrame


class TestMessageTypeEnum(TestCase):

    def test_all_ten_values(self):
        """MessageType has exactly 10 entries."""
        self.assertEqual(len(MessageType), 10)
        self.assertEqual(MessageType.START_TEST.value, 'START_TEST')
        self.assertEqual(MessageType.HEARTBEAT.value, 'HEARTBEAT')


class TestLoRaHandlerSend(TestCase):
    """Test outgoing message construction (no serial/MQ needed)."""

    def setUp(self):
        self.handler = LoRaHandler.__new__(LoRaHandler)
        self.handler._mq = MagicMock()
        self.handler._serial = None
        self.handler._reassembler = FragmentReassembler()
        self.handler._frag_id_counter = 0
        self.handler._running = False
        self.handler._handlers = {}
        self.handler._link_online = False
        self.handler._device_id = 0x0002
        # Health tracking attrs
        self.handler._started_at = 0.0
        self.handler._last_heartbeat_sent = 0.0
        self.handler._last_message_received = 0.0
        self.handler._messages_sent = 0
        self.handler._messages_received = 0
        self.handler._messages_failed = 0
        self.handler._heartbeats_sent = 0
        # Message history attrs
        from collections import deque
        import threading
        self.handler._history = deque(maxlen=200)
        self.handler._history_counter = 0
        self.handler._history_lock = threading.Lock()

    def test_send_test_status(self):
        self.handler.send_test_status(42, 'Q3', 'FLOW_STABILIZE',
                                      flow_lph=150.0, pressure_bar=3.5, temp_c=22.1)
        self.handler._mq.send.assert_called_once()
        payload = self.handler._mq.send.call_args[0][0]
        self.assertEqual(payload['command'], 'TEST_STATUS')
        self.assertEqual(payload['test_id'], 42)
        self.assertEqual(payload['q_point'], 'Q3')
        self.assertAlmostEqual(payload['flow_rate_lph'], 150.0)

    def test_send_test_result(self):
        q_data = {'q_point': 'Q1', 'error_pct': 1.5, 'passed': True}
        self.handler.send_test_result(10, q_data)
        payload = self.handler._mq.send.call_args[0][0]
        self.assertEqual(payload['command'], 'TEST_RESULT')
        self.assertEqual(payload['test_id'], 10)
        self.assertTrue(payload['passed'])

    def test_send_test_complete(self):
        summary = {'test_id': 5, 'overall_pass': True, 'points': 8}
        self.handler.send_test_complete(summary)
        payload = self.handler._mq.send.call_args[0][0]
        self.assertEqual(payload['command'], 'TEST_COMPLETE')
        self.assertTrue(payload['overall_pass'])

    def test_send_heartbeat(self):
        self.handler.send_heartbeat()
        payload = self.handler._mq.send.call_args[0][0]
        self.assertEqual(payload['command'], 'HEARTBEAT')
        self.assertEqual(payload['device_id'], 0x0002)
        self.assertIn('uptime', payload)


class TestLoRaHandlerDispatch(TestCase):
    """Test incoming message dispatch."""

    def setUp(self):
        self.handler = LoRaHandler.__new__(LoRaHandler)
        self.handler._mq = MagicMock()
        self.handler._serial = None
        self.handler._reassembler = FragmentReassembler()
        self.handler._frag_id_counter = 0
        self.handler._running = False
        self.handler._handlers = {}
        self.handler._link_online = False
        self.handler._device_id = 0x0002
        # Health tracking attrs
        self.handler._started_at = 0.0
        self.handler._last_heartbeat_sent = 0.0
        self.handler._last_message_received = 0.0
        self.handler._messages_sent = 0
        self.handler._messages_received = 0
        self.handler._messages_failed = 0
        self.handler._heartbeats_sent = 0
        # Message history attrs
        from collections import deque
        import threading
        self.handler._history = deque(maxlen=200)
        self.handler._history_counter = 0
        self.handler._history_lock = threading.Lock()

    def _make_frame(self, payload):
        return ASPFrame(device_id=0x0001, seq=1, timestamp=int(time.time()),
                        payload=payload)

    def test_dispatch_start_test(self):
        called = []
        self.handler.on_start_test(lambda p: called.append(p))
        frame = self._make_frame({
            'command': 'START_TEST', 'test_id': 7,
            'meter_serial': 'X', 'meter_size': 'DN15',
        })
        self.handler._dispatch_incoming(frame)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0]['test_id'], 7)

    def test_dispatch_emergency_stop(self):
        called = []
        self.handler.on_emergency_stop(lambda p: called.append(p))
        frame = self._make_frame({'command': 'EMERGENCY_STOP', 'reason': 'fire'})
        self.handler._dispatch_incoming(frame)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0]['reason'], 'fire')

    def test_dispatch_unknown_command_no_error(self):
        frame = self._make_frame({'command': 'UNKNOWN_TYPE'})
        self.handler._dispatch_incoming(frame)  # should not raise

    def test_auto_ack_start_test(self):
        frame = self._make_frame({'command': 'START_TEST', 'test_id': 99})
        self.handler._dispatch_incoming(frame)
        self.handler._mq.send.assert_called()
        payload = self.handler._mq.send.call_args[0][0]
        self.assertEqual(payload['command'], 'START_TEST_ACK')
        self.assertEqual(payload['test_id'], 99)

    def test_auto_ack_emergency_stop(self):
        frame = self._make_frame({'command': 'EMERGENCY_STOP', 'reason': 'test'})
        self.handler._dispatch_incoming(frame)
        payload = self.handler._mq.send.call_args[0][0]
        self.assertEqual(payload['command'], 'EMERGENCY_ACK')


class TestLoRaHandlerSingleton(TestCase):

    def test_singleton_returns_same_instance(self):
        import comms.lora_handler as mod
        mod._lora_handler = None
        h1 = get_lora_handler()
        h2 = get_lora_handler()
        self.assertIs(h1, h2)
        mod._lora_handler = None


# ===========================================================================
#  ChannelManager tests
# ===========================================================================

from comms.serial_handler import SerialHandler, ChannelManager


class TestChannelManager(TestCase):

    @override_settings(BENCH_SERIAL_PORTS={
        'vfd': '/dev/ttyB2_VFD',
        'meter': '/dev/ttyB3_METER',
        'scale': '/dev/ttyB4_SCALE',
        'gpio': '/dev/ttyB5_GPIO',
        'tank': '/dev/ttyB6_TANK',
        'lora': '/dev/ttyB7_LORA',
    }, BENCH_SERIAL_BAUD=115200)
    def test_init_from_settings_creates_all_channels(self):
        """All 6 channels created from settings."""
        mgr = ChannelManager()
        mgr.init_from_settings()
        self.assertEqual(len(mgr.channels), 6)
        for name in ChannelManager.CHANNEL_NAMES:
            self.assertIn(name, mgr.channels)
            self.assertIsInstance(mgr.channels[name], SerialHandler)

    @override_settings(BENCH_SERIAL_PORTS={
        'vfd': '/dev/ttyB2_VFD',
    }, BENCH_SERIAL_BAUD=115200)
    def test_partial_settings_creates_subset(self):
        """Only configured channels are created."""
        mgr = ChannelManager()
        mgr.init_from_settings()
        self.assertEqual(len(mgr.channels), 1)
        self.assertIn('vfd', mgr.channels)
        self.assertIsNone(mgr.get('meter'))

    def test_get_returns_none_for_unknown(self):
        """get() returns None for missing channel."""
        mgr = ChannelManager()
        self.assertIsNone(mgr.get('unknown'))

    @override_settings(BENCH_SERIAL_PORTS={}, BENCH_SERIAL_BAUD=115200)
    def test_empty_settings_no_channels(self):
        """Empty settings creates no channels."""
        mgr = ChannelManager()
        mgr.init_from_settings()
        self.assertEqual(len(mgr.channels), 0)

    @override_settings(BENCH_SERIAL_PORTS={
        'vfd': '/dev/ttyB2_VFD',
    }, BENCH_SERIAL_BAUD=115200)
    def test_status_property(self):
        """status returns connection status dict."""
        mgr = ChannelManager()
        mgr.init_from_settings()
        status = mgr.status
        self.assertIn('vfd', status)
        self.assertFalse(status['vfd'])  # Not connected yet


# ===========================================================================
#  SerialHandler convenience method tests
# ===========================================================================

class TestSerialHandlerConvenienceMethods(TestCase):
    """Test that convenience methods build correct command dicts."""

    def setUp(self):
        """Create handler with mocked send_command."""
        self.handler = SerialHandler.__new__(SerialHandler)
        self.handler._port = '/dev/null'
        self.handler._baud = 115200
        self.handler._serial = None
        self.handler._is_connected = False
        self.handler._lock = __import__('threading').Lock()
        self.last_cmd = None

        def mock_send(cmd, timeout=2.0):
            self.last_cmd = cmd
            return {'ok': True}

        self.handler.send_command = mock_send

    def test_modbus_read_no_bus_param(self):
        """modbus_read sends MB_READ with addr/reg/count, no bus."""
        self.handler.modbus_read(1, 0x2100, 2)
        self.assertEqual(self.last_cmd['cmd'], 'MB_READ')
        self.assertEqual(self.last_cmd['addr'], 1)
        self.assertEqual(self.last_cmd['reg'], 0x2100)
        self.assertEqual(self.last_cmd['count'], 2)
        self.assertNotIn('bus', self.last_cmd)

    def test_modbus_write_no_bus_param(self):
        """modbus_write sends MB_WRITE with addr/reg/value, no bus."""
        self.handler.modbus_write(1, 0x2001, 500)
        self.assertEqual(self.last_cmd['cmd'], 'MB_WRITE')
        self.assertEqual(self.last_cmd['addr'], 1)
        self.assertEqual(self.last_cmd['reg'], 0x2001)
        self.assertEqual(self.last_cmd['value'], 500)
        self.assertNotIn('bus', self.last_cmd)

    def test_valve_control_hyphen_to_underscore(self):
        """valve_control translates BV-L1 → BV_L1 and uses 'name' field."""
        self.handler.valve_control('BV-L1', 'OPEN')
        self.assertEqual(self.last_cmd['cmd'], 'VALVE')
        self.assertEqual(self.last_cmd['name'], 'BV_L1')
        self.assertEqual(self.last_cmd['action'], 'OPEN')
        self.assertNotIn('valve', self.last_cmd)

    def test_valve_control_sv_drn(self):
        """valve_control translates SV-DRN → SV_DRN."""
        self.handler.valve_control('SV-DRN', 'CLOSE')
        self.assertEqual(self.last_cmd['name'], 'SV_DRN')

    def test_tower_set_command_format(self):
        """tower_set sends TOWER with r/g/buz fields."""
        self.handler.tower_set(1, 0, 1)
        self.assertEqual(self.last_cmd['cmd'], 'TOWER')
        self.assertEqual(self.last_cmd['r'], 1)
        self.assertEqual(self.last_cmd['g'], 0)
        self.assertEqual(self.last_cmd['buz'], 1)

    def test_scale_read_command(self):
        """scale_read sends SCALE_READ."""
        self.handler.scale_read()
        self.assertEqual(self.last_cmd['cmd'], 'SCALE_READ')

    def test_scale_tare_command(self):
        """scale_tare sends SCALE_TARE."""
        self.handler.scale_tare()
        self.assertEqual(self.last_cmd['cmd'], 'SCALE_TARE')

    def test_pressure_read_command(self):
        """pressure_read sends PRESSURE_READ."""
        self.handler.pressure_read()
        self.assertEqual(self.last_cmd['cmd'], 'PRESSURE_READ')

    def test_sensor_read_command(self):
        """sensor_read sends SENSOR_READ."""
        self.handler.sensor_read()
        self.assertEqual(self.last_cmd['cmd'], 'SENSOR_READ')

    def test_tank_read_command(self):
        """tank_read sends TANK_READ."""
        self.handler.tank_read()
        self.assertEqual(self.last_cmd['cmd'], 'TANK_READ')

    def test_get_status_command(self):
        """get_status sends STATUS."""
        self.handler.get_status()
        self.assertEqual(self.last_cmd['cmd'], 'STATUS')


# ---------------------------------------------------------------------------
#  LoRa Handler get_status() (US-306)
# ---------------------------------------------------------------------------

@override_settings(
    ASP_AES_KEY=TEST_AES_KEY_HEX,
    ASP_HMAC_KEY=TEST_HMAC_KEY_HEX,
)
class TestLoRaHandlerGetStatus(TestCase):
    """Tests for LoRaHandler.get_status() health reporting."""

    def _make_handler(self):
        from comms.lora_handler import LoRaHandler
        return LoRaHandler()

    def test_stopped_state(self):
        """Handler not started → state='stopped'."""
        h = self._make_handler()
        status = h.get_status()
        self.assertEqual(status['state'], 'stopped')
        self.assertFalse(status['running'])

    def test_online_state(self):
        """Running + link online + recent heartbeat → state='online'."""
        h = self._make_handler()
        h._running = True
        h._link_online = True
        h._started_at = time.time() - 10
        h._last_heartbeat_sent = time.time() - 5
        status = h.get_status()
        self.assertEqual(status['state'], 'online')
        self.assertTrue(status['running'])
        self.assertTrue(status['link_online'])

    def test_offline_state(self):
        """Running but link down → state='offline'."""
        h = self._make_handler()
        h._running = True
        h._link_online = False
        h._started_at = time.time() - 10
        status = h.get_status()
        self.assertEqual(status['state'], 'offline')

    def test_degraded_state(self):
        """Running, link online, but heartbeat stale → state='degraded'."""
        h = self._make_handler()
        h._running = True
        h._link_online = True
        h._started_at = time.time() - 300
        # Heartbeat older than 3x interval (3 * 30s = 90s)
        h._last_heartbeat_sent = time.time() - 100
        status = h.get_status()
        self.assertEqual(status['state'], 'degraded')

    def test_counters(self):
        """Counters reflect tracked values."""
        h = self._make_handler()
        h._running = True
        h._link_online = True
        h._started_at = time.time() - 60
        h._messages_sent = 15
        h._messages_received = 8
        h._messages_failed = 2
        h._heartbeats_sent = 4
        status = h.get_status()
        self.assertEqual(status['messages_sent'], 15)
        self.assertEqual(status['messages_received'], 8)
        self.assertEqual(status['messages_failed'], 2)
        self.assertEqual(status['heartbeats_sent'], 4)

    def test_queue_depth_without_mq(self):
        """Queue depth is 0 when no MessageQueue is attached."""
        h = self._make_handler()
        status = h.get_status()
        self.assertEqual(status['queue_depth'], 0)
        self.assertEqual(status['offline_queue_depth'], 0)

    def test_history_count_in_status(self):
        """get_status() includes history_count field."""
        h = self._make_handler()
        status = h.get_status()
        self.assertIn('history_count', status)
        self.assertEqual(status['history_count'], 0)


@override_settings(
    ASP_AES_KEY=TEST_AES_KEY_HEX,
    ASP_HMAC_KEY=TEST_HMAC_KEY_HEX,
)
class TestLoRaHandlerHistory(TestCase):
    """Tests for LoRaHandler message history circular buffer."""

    def _make_handler(self):
        from comms.lora_handler import LoRaHandler
        return LoRaHandler()

    def test_history_empty_initially(self):
        """New handler has empty history."""
        h = self._make_handler()
        self.assertEqual(h.get_history(), [])

    def test_send_records_tx(self):
        """Sending a message records TX entry in history."""
        from unittest.mock import MagicMock
        h = self._make_handler()
        h._mq = MagicMock()
        h.send_test_status(42, 'Q3', 'FLOW_STABILIZE', 150.0, 3.5, 22.1)
        history = h.get_history(include_heartbeats=True)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['direction'], 'TX')
        self.assertEqual(history[0]['msg_type'], 'TEST_STATUS')
        self.assertEqual(history[0]['status'], 'ok')
        self.assertIn('Q3', history[0]['summary'])

    def test_heartbeats_filtered_by_default(self):
        """get_history() excludes heartbeats by default."""
        from unittest.mock import MagicMock
        h = self._make_handler()
        h._mq = MagicMock()
        h.send_heartbeat()
        h.send_test_status(1, 'Q1', 'IDLE', 0, 0, 0)
        without_hb = h.get_history(include_heartbeats=False)
        with_hb = h.get_history(include_heartbeats=True)
        self.assertEqual(len(without_hb), 1)
        self.assertEqual(len(with_hb), 2)

    def test_history_limit(self):
        """get_history() respects limit parameter."""
        from unittest.mock import MagicMock
        h = self._make_handler()
        h._mq = MagicMock()
        for i in range(10):
            h.send_test_status(i, f'Q{i}', 'IDLE', 0, 0, 0)
        history = h.get_history(limit=3)
        self.assertEqual(len(history), 3)

    def test_history_newest_first(self):
        """get_history() returns newest entries first."""
        from unittest.mock import MagicMock
        h = self._make_handler()
        h._mq = MagicMock()
        h.send_test_status(1, 'Q1', 'IDLE', 0, 0, 0)
        h.send_test_status(2, 'Q2', 'IDLE', 0, 0, 0)
        history = h.get_history()
        self.assertGreater(history[0]['id'], history[1]['id'])

    def test_circular_buffer_evicts_old(self):
        """Buffer evicts oldest entries when full."""
        from collections import deque
        from unittest.mock import MagicMock
        h = self._make_handler()
        h._mq = MagicMock()
        h._history = deque(maxlen=5)
        for i in range(10):
            h.send_test_status(i, f'Q{i}', 'IDLE', 0, 0, 0)
        all_entries = h.get_history(limit=200, include_heartbeats=True)
        self.assertEqual(len(all_entries), 5)

    def test_receive_records_rx(self):
        """Receiving a message records RX entry in history."""
        from unittest.mock import MagicMock
        from comms.protocol import ASPFrame
        h = self._make_handler()
        h._mq = MagicMock()
        frame = ASPFrame(
            device_id=0x0001, seq=1, timestamp=int(time.time()),
            payload={'command': 'START_TEST', 'test_id': 7},
        )
        h._dispatch_incoming(frame)
        history = h.get_history()
        rx_entries = [e for e in history if e['direction'] == 'RX']
        self.assertTrue(len(rx_entries) >= 1)
        self.assertEqual(rx_entries[0]['msg_type'], 'START_TEST')
