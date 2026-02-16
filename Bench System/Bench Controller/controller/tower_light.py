"""
Tower light controller.

Maps system states to tower light patterns:
  GREEN steady  — System ready / idle
  YELLOW steady — Test in progress
  RED steady    — Fault / alarm active
  RED blink     — E-stop active
  GREEN blink   — Test passed
  RED+BUZZER    — Test failed

Supports blink patterns via a background timer thread.
"""

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class LightPattern(Enum):
    OFF = 'OFF'
    READY = 'READY'             # Green steady
    TESTING = 'TESTING'         # Yellow steady
    FAULT = 'FAULT'             # Red steady
    ESTOP = 'ESTOP'             # Red blink (fast)
    TEST_PASS = 'TEST_PASS'     # Green blink
    TEST_FAIL = 'TEST_FAIL'     # Red blink + buzzer
    STABILIZING = 'STABILIZING' # Yellow blink
    DRAINING = 'DRAINING'       # Yellow + green alternating


# Pattern definitions: (red, yellow, green, buzzer) tuples
# For blink patterns, two states alternate
PATTERN_MAP: dict[LightPattern, list[tuple[bool, bool, bool, bool]]] = {
    LightPattern.OFF:         [(False, False, False, False)],
    LightPattern.READY:       [(False, False, True, False)],
    LightPattern.TESTING:     [(False, True, False, False)],
    LightPattern.FAULT:       [(True, False, False, False)],
    LightPattern.ESTOP:       [
        (True, False, False, False),
        (False, False, False, False),
    ],
    LightPattern.TEST_PASS:   [
        (False, False, True, False),
        (False, False, False, False),
    ],
    LightPattern.TEST_FAIL:   [
        (True, False, False, True),
        (False, False, False, False),
    ],
    LightPattern.STABILIZING: [
        (False, True, False, False),
        (False, False, False, False),
    ],
    LightPattern.DRAINING:    [
        (False, True, False, False),
        (False, False, True, False),
    ],
}

# Blink rate in seconds
BLINK_INTERVAL = 0.5


class TowerLightController:
    """
    Tower light controller with blink patterns.

    Usage:
        tower = TowerLightController(backend='simulator')
        tower.init_backend()
        tower.set_pattern(LightPattern.READY)

        # During test:
        tower.set_pattern(LightPattern.TESTING)

        # After test:
        tower.set_pattern(LightPattern.TEST_PASS)
        time.sleep(5)
        tower.set_pattern(LightPattern.READY)

        tower.stop()
    """

    def __init__(self, backend: str = 'simulator'):
        self._backend = backend
        self._lock = threading.Lock()
        self._simulator = None
        self._serial_handler = None

        self._pattern = LightPattern.OFF
        self._blink_thread: threading.Thread | None = None
        self._blink_running = False
        self._blink_index = 0

    def init_backend(self):
        """Initialise the appropriate backend."""
        if self._backend == 'simulator':
            from controller.simulator import get_simulator
            self._simulator = get_simulator()
            logger.info("TowerLightController using SIMULATOR backend")
        else:
            logger.info("TowerLightController using REAL backend")

    def set_serial_handler(self, handler):
        """Set serial handler for real hardware mode."""
        self._serial_handler = handler

    # ------------------------------------------------------------------
    #  Pattern control
    # ------------------------------------------------------------------

    def set_pattern(self, pattern: LightPattern):
        """Set the tower light pattern."""
        with self._lock:
            if self._pattern == pattern:
                return
            self._pattern = pattern

        # Stop existing blink thread
        self._stop_blink()

        states = PATTERN_MAP.get(pattern, [(False, False, False, False)])

        if len(states) == 1:
            # Static pattern — apply immediately
            self._apply_state(*states[0])
        else:
            # Blink pattern — start blink thread
            self._start_blink(states)

        logger.debug("Tower light → %s", pattern.value)

    @property
    def pattern(self) -> LightPattern:
        """Current pattern."""
        with self._lock:
            return self._pattern

    # ------------------------------------------------------------------
    #  Blink thread
    # ------------------------------------------------------------------

    def _start_blink(self, states: list[tuple[bool, bool, bool, bool]]):
        """Start a blink pattern in background."""
        self._blink_running = True
        self._blink_index = 0
        self._blink_thread = threading.Thread(
            target=self._blink_loop,
            args=(states,),
            name='TowerBlink',
            daemon=True,
        )
        self._blink_thread.start()

    def _stop_blink(self):
        """Stop the blink thread if running."""
        self._blink_running = False
        if self._blink_thread:
            self._blink_thread.join(timeout=1.0)
            self._blink_thread = None

    def _blink_loop(self, states: list[tuple[bool, bool, bool, bool]]):
        """Alternates between blink states."""
        idx = 0
        while self._blink_running:
            self._apply_state(*states[idx % len(states)])
            idx += 1
            time.sleep(BLINK_INTERVAL)

    # ------------------------------------------------------------------
    #  Hardware interface
    # ------------------------------------------------------------------

    def _apply_state(self, red: bool, yellow: bool, green: bool, buzzer: bool):
        """Send tower light state to hardware."""
        if self._backend == 'simulator':
            if self._simulator:
                self._simulator.set_tower_light(red, yellow, green, buzzer)
        else:
            if self._serial_handler:
                try:
                    self._serial_handler.gpio_set('TOWER_RED', int(red))
                    self._serial_handler.gpio_set('TOWER_YELLOW', int(yellow))
                    self._serial_handler.gpio_set('TOWER_GREEN', int(green))
                    self._serial_handler.gpio_set('BUZZER', int(buzzer))
                except Exception:
                    logger.exception("Tower light GPIO write failed")

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def stop(self):
        """Stop the tower light controller and turn off all lights."""
        self._stop_blink()
        self._apply_state(False, False, False, False)
        self._pattern = LightPattern.OFF
        logger.info("Tower light stopped")

    def all_off(self):
        """Turn off all lights without changing pattern state."""
        self._apply_state(False, False, False, False)
