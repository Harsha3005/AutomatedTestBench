"""
Valve controller for the test bench.

Manages solenoid valves, ball valves, and the 3-way diverter.
Enforces mutual exclusion for lane-select valves (only one open at a time).

Valves:
  SV1      — Main solenoid (normally closed, opens to start flow)
  BV-L1    — Lane 1 ball valve (1")
  BV-L2    — Lane 2 ball valve (3/4")
  BV-L3    — Lane 3 ball valve (1/2")
  SV-DRN   — Drain solenoid (collection tank → reservoir)
  BV-BP    — Bypass ball valve (recirculate to reservoir)
  Diverter — 3-way: COLLECT (to tank) or BYPASS (recirculate)
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Lane valve IDs (mutual exclusion group)
LANE_VALVES = ('BV-L1', 'BV-L2', 'BV-L3')

# All controllable valves
ALL_VALVES = ('SV1', 'BV-L1', 'BV-L2', 'BV-L3', 'SV-DRN', 'BV-BP')

# Lane ID to valve mapping
LANE_MAP = {
    '1': 'BV-L1',
    '1_inch': 'BV-L1',
    '3/4': 'BV-L2',
    '3/4_inch': 'BV-L2',
    '1/2': 'BV-L3',
    '1/2_inch': 'BV-L3',
}

# Meter size to lane
SIZE_TO_LANE = {
    'DN25': 'BV-L1',   # 1"
    'DN20': 'BV-L2',   # 3/4"
    'DN15': 'BV-L3',   # 1/2"
}


@dataclass
class ValveStates:
    """Snapshot of all valve states."""
    valves: dict[str, bool] = field(default_factory=lambda: {v: False for v in ALL_VALVES})
    diverter: str = 'BYPASS'
    active_lane: str | None = None
    timestamp: float = field(default_factory=time.time)


class ValveController:
    """
    High-level valve controller with mutual exclusion.

    Usage:
        vc = ValveController(backend='simulator')
        vc.init_backend()
        vc.select_lane('DN20')     # Opens BV-L2, closes BV-L1/L3
        vc.open_valve('SV1')       # Open main solenoid
        vc.set_diverter('COLLECT') # Divert to collection tank
        vc.close_all()             # Close everything
    """

    def __init__(self, backend: str = 'simulator'):
        self._backend = backend
        self._lock = threading.Lock()
        self._simulator = None
        self._serial_handler = None  # Bus 1 handler for real mode

        # Track valve states locally
        self._valve_states: dict[str, bool] = {v: False for v in ALL_VALVES}
        self._diverter: str = 'BYPASS'
        self._active_lane: str | None = None
        self._valve_timeout = getattr(settings, 'SAFETY_VALVE_TIMEOUT', 5.0)

    def init_backend(self):
        """Initialise the appropriate backend."""
        if self._backend == 'simulator':
            from controller.simulator import get_simulator
            self._simulator = get_simulator()
            logger.info("ValveController using SIMULATOR backend")
        else:
            logger.info("ValveController using REAL backend")

    def set_serial_handler(self, handler):
        """Set the serial handler for real hardware mode."""
        self._serial_handler = handler

    # ------------------------------------------------------------------
    #  Valve operations
    # ------------------------------------------------------------------

    def open_valve(self, valve_id: str) -> bool:
        """
        Open a valve.

        For lane valves (BV-L1/L2/L3), enforces mutual exclusion:
        opening one closes the others.

        Returns True on success.
        """
        if valve_id not in ALL_VALVES:
            logger.error("Unknown valve: %s", valve_id)
            return False

        with self._lock:
            # Mutual exclusion for lane valves
            if valve_id in LANE_VALVES:
                for lv in LANE_VALVES:
                    if lv != valve_id and self._valve_states.get(lv, False):
                        if not self._actuate_valve(lv, False):
                            logger.error("Failed to close %s for mutual exclusion", lv)
                            return False
                self._active_lane = valve_id

            return self._actuate_valve(valve_id, True)

    def close_valve(self, valve_id: str) -> bool:
        """Close a valve. Returns True on success."""
        if valve_id not in ALL_VALVES:
            logger.error("Unknown valve: %s", valve_id)
            return False

        with self._lock:
            if valve_id in LANE_VALVES and self._active_lane == valve_id:
                self._active_lane = None
            return self._actuate_valve(valve_id, False)

    def close_all(self) -> bool:
        """Close all valves and set diverter to BYPASS. Returns True if all succeeded."""
        with self._lock:
            success = True
            for valve_id in ALL_VALVES:
                if not self._actuate_valve(valve_id, False):
                    success = False
            self._set_diverter_internal('BYPASS')
            self._active_lane = None
            return success

    def select_lane(self, meter_size_or_lane: str) -> bool:
        """
        Select the correct lane valve based on meter size or lane ID.

        Args:
            meter_size_or_lane: 'DN15', 'DN20', 'DN25', or 'BV-L1/L2/L3'

        Returns True on success.
        """
        # Resolve to valve ID
        valve_id = SIZE_TO_LANE.get(meter_size_or_lane)
        if valve_id is None:
            valve_id = LANE_MAP.get(meter_size_or_lane)
        if valve_id is None and meter_size_or_lane in LANE_VALVES:
            valve_id = meter_size_or_lane
        if valve_id is None:
            logger.error("Cannot resolve lane for: %s", meter_size_or_lane)
            return False

        return self.open_valve(valve_id)

    def set_diverter(self, position: str) -> bool:
        """
        Set 3-way diverter position.

        Args:
            position: 'COLLECT' or 'BYPASS'
        """
        if position not in ('COLLECT', 'BYPASS'):
            logger.error("Invalid diverter position: %s", position)
            return False

        with self._lock:
            return self._set_diverter_internal(position)

    # ------------------------------------------------------------------
    #  Internal actuator commands
    # ------------------------------------------------------------------

    def _actuate_valve(self, valve_id: str, open_state: bool) -> bool:
        """Actuate a single valve. Caller must hold lock."""
        action = 'OPEN' if open_state else 'CLOSE'

        if self._backend == 'simulator':
            try:
                self._simulator.set_valve(valve_id, open_state)
                self._valve_states[valve_id] = open_state
                logger.debug("Valve %s → %s (simulator)", valve_id, action)
                return True
            except Exception:
                logger.exception("Simulator valve %s %s failed", valve_id, action)
                return False
        else:
            # Real hardware via serial
            if not self._serial_handler:
                logger.error("No serial handler for valve control")
                return False
            try:
                result = self._serial_handler.valve_control(valve_id, action)
                ok = result.get('ok', False)
                if ok:
                    self._valve_states[valve_id] = open_state
                    logger.debug("Valve %s → %s (real)", valve_id, action)
                else:
                    logger.error("Valve %s %s failed: %s", valve_id, action, result)
                return ok
            except Exception:
                logger.exception("Valve %s %s command error", valve_id, action)
                return False

    def _set_diverter_internal(self, position: str) -> bool:
        """Set diverter. Caller must hold lock."""
        if self._backend == 'simulator':
            try:
                self._simulator.set_diverter(position)
                self._diverter = position
                logger.debug("Diverter → %s (simulator)", position)
                return True
            except Exception:
                logger.exception("Simulator diverter %s failed", position)
                return False
        else:
            if not self._serial_handler:
                logger.error("No serial handler for diverter control")
                return False
            try:
                result = self._serial_handler.diverter_control(position)
                ok = result.get('ok', False)
                if ok:
                    self._diverter = position
                    logger.debug("Diverter → %s (real)", position)
                else:
                    logger.error("Diverter %s failed: %s", position, result)
                return ok
            except Exception:
                logger.exception("Diverter %s command error", position)
                return False

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    @property
    def states(self) -> ValveStates:
        """Get current valve states."""
        with self._lock:
            return ValveStates(
                valves=dict(self._valve_states),
                diverter=self._diverter,
                active_lane=self._active_lane,
            )

    def get_valve_state(self, valve_id: str) -> bool | None:
        """Get state of a single valve. Returns None if unknown."""
        with self._lock:
            return self._valve_states.get(valve_id)

    @property
    def diverter_position(self) -> str:
        """Current diverter position."""
        with self._lock:
            return self._diverter

    @property
    def active_lane(self) -> str | None:
        """Currently active lane valve, or None."""
        with self._lock:
            return self._active_lane

    def is_valve_open(self, valve_id: str) -> bool:
        """Check if a specific valve is open."""
        with self._lock:
            return self._valve_states.get(valve_id, False)
