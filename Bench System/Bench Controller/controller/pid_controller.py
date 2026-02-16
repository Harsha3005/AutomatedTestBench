"""
PID controller for flow rate regulation.

Adjusts VFD frequency to maintain a target flow rate measured by the
EM flow meter (FT-01). Runs at 200ms cycle time (5 Hz).

PID tuning defaults (from settings_bench.py):
  Kp = 0.5, Ki = 0.1, Kd = 0.05
  Output range: 5.0 – 50.0 Hz
  Sample rate: 200ms

Features:
  - Anti-windup via integral clamping
  - Derivative on measurement (not on error) to avoid setpoint kicks
  - Stability detection (consecutive readings within tolerance)
  - Manual output override capability
  - Thread-safe
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class PIDState:
    """Current state of the PID controller."""
    target_lph: float = 0.0
    measured_lph: float = 0.0
    output_hz: float = 0.0
    error: float = 0.0
    p_term: float = 0.0
    i_term: float = 0.0
    d_term: float = 0.0
    stable: bool = False
    enabled: bool = False
    last_update: float = 0.0


class PIDController:
    """
    PID controller for VFD frequency regulation.

    Usage:
        pid = PIDController()
        pid.set_target(500.0)  # 500 L/h
        pid.enable()

        # In polling loop (called every 200ms):
        output_hz = pid.compute(measured_flow_lph)
        vfd.set_frequency(output_hz)
    """

    def __init__(
        self,
        kp: float | None = None,
        ki: float | None = None,
        kd: float | None = None,
        output_min: float | None = None,
        output_max: float | None = None,
        sample_rate: float | None = None,
    ):
        self._kp = kp if kp is not None else getattr(settings, 'PID_KP', 0.5)
        self._ki = ki if ki is not None else getattr(settings, 'PID_KI', 0.1)
        self._kd = kd if kd is not None else getattr(settings, 'PID_KD', 0.05)
        self._output_min = output_min if output_min is not None else getattr(settings, 'PID_OUTPUT_MIN', 5.0)
        self._output_max = output_max if output_max is not None else getattr(settings, 'PID_OUTPUT_MAX', 50.0)
        self._sample_rate = sample_rate if sample_rate is not None else getattr(settings, 'PID_SAMPLE_RATE', 0.2)

        # Stability detection
        self._stability_tolerance = getattr(settings, 'SAFETY_FLOW_STABILITY', 2.0)
        self._stability_count = getattr(settings, 'SAFETY_STABILITY_COUNT', 5)

        self._lock = threading.Lock()
        self._target = 0.0
        self._enabled = False
        self._manual_output: float | None = None

        # Internal state
        self._integral = 0.0
        self._prev_measurement = 0.0
        self._prev_error = 0.0
        self._output = 0.0
        self._last_time = 0.0

        # Stability tracking
        self._error_history: deque[float] = deque(maxlen=self._stability_count)

    # ------------------------------------------------------------------
    #  Configuration
    # ------------------------------------------------------------------

    def set_target(self, target_lph: float):
        """Set the target flow rate in L/h."""
        with self._lock:
            self._target = max(0, target_lph)
            self._error_history.clear()
            logger.info("PID target set to %.1f L/h", self._target)

    def set_gains(self, kp: float, ki: float, kd: float):
        """Update PID gains on the fly."""
        with self._lock:
            self._kp = kp
            self._ki = ki
            self._kd = kd
            logger.info("PID gains updated: Kp=%.3f Ki=%.3f Kd=%.3f", kp, ki, kd)

    def enable(self):
        """Enable the PID controller."""
        with self._lock:
            self._enabled = True
            self._integral = 0.0
            self._prev_measurement = 0.0
            self._prev_error = 0.0
            self._last_time = time.time()
            self._error_history.clear()
            self._manual_output = None
            logger.info("PID enabled")

    def disable(self):
        """Disable the PID controller. Output goes to 0."""
        with self._lock:
            self._enabled = False
            self._output = 0.0
            self._integral = 0.0
            self._error_history.clear()
            logger.info("PID disabled")

    def reset(self):
        """Reset all internal state."""
        with self._lock:
            self._integral = 0.0
            self._prev_measurement = 0.0
            self._prev_error = 0.0
            self._output = 0.0
            self._last_time = time.time()
            self._error_history.clear()

    def set_manual_output(self, hz: float | None):
        """Override PID with manual frequency. Set None to return to auto."""
        with self._lock:
            self._manual_output = hz

    # ------------------------------------------------------------------
    #  Core computation
    # ------------------------------------------------------------------

    def compute(self, measured_lph: float) -> float:
        """
        Compute PID output given current flow measurement.

        Args:
            measured_lph: Current flow rate in L/h from EM meter.

        Returns:
            VFD frequency setpoint in Hz (clamped to output_min..output_max).
        """
        with self._lock:
            if not self._enabled:
                return 0.0

            # Manual override
            if self._manual_output is not None:
                self._output = max(self._output_min, min(self._output_max, self._manual_output))
                return self._output

            now = time.time()
            dt = now - self._last_time if self._last_time > 0 else self._sample_rate
            dt = max(dt, 0.001)  # Prevent division by zero
            self._last_time = now

            # Error
            error = self._target - measured_lph

            # P term
            p_term = self._kp * error

            # I term with anti-windup
            self._integral += error * dt
            i_term = self._ki * self._integral

            # Anti-windup: clamp integral so that output stays in range
            test_output = p_term + i_term
            if test_output > self._output_max:
                self._integral = (self._output_max - p_term) / self._ki if self._ki != 0 else 0
                i_term = self._ki * self._integral
            elif test_output < self._output_min and self._target > 0:
                self._integral = (self._output_min - p_term) / self._ki if self._ki != 0 else 0
                i_term = self._ki * self._integral

            # D term (derivative on measurement to avoid setpoint kicks)
            d_measurement = (measured_lph - self._prev_measurement) / dt
            d_term = -self._kd * d_measurement

            # Output
            output = p_term + i_term + d_term

            # Clamp to VFD range
            if self._target <= 0:
                output = 0.0
            else:
                output = max(self._output_min, min(self._output_max, output))

            self._output = output
            self._prev_measurement = measured_lph
            self._prev_error = error

            # Track stability
            if self._target > 0:
                error_pct = abs(error / self._target) * 100.0
                self._error_history.append(error_pct)

            return output

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    @property
    def state(self) -> PIDState:
        """Get current PID state."""
        with self._lock:
            return PIDState(
                target_lph=self._target,
                measured_lph=self._prev_measurement,
                output_hz=self._output,
                error=self._target - self._prev_measurement,
                p_term=self._kp * (self._target - self._prev_measurement),
                i_term=self._ki * self._integral,
                d_term=0.0,  # Can't reconstruct without d_measurement
                stable=self._is_stable(),
                enabled=self._enabled,
                last_update=self._last_time,
            )

    @property
    def is_stable(self) -> bool:
        """Check if flow is stable within tolerance."""
        with self._lock:
            return self._is_stable()

    def _is_stable(self) -> bool:
        """Internal stability check (caller must hold lock)."""
        if len(self._error_history) < self._stability_count:
            return False
        return all(e <= self._stability_tolerance for e in self._error_history)

    @property
    def output(self) -> float:
        """Current output frequency in Hz."""
        with self._lock:
            return self._output

    @property
    def target(self) -> float:
        """Current target flow in L/h."""
        with self._lock:
            return self._target

    @property
    def enabled(self) -> bool:
        """Whether PID is enabled."""
        with self._lock:
            return self._enabled
