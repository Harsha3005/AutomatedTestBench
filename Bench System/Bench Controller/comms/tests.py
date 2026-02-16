"""
Unit tests for ASP protocol encode/decode, crypto, and fragmentation.

Run: python manage.py test comms --settings=config.settings_bench
"""

import struct
import time

from django.test import TestCase

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
