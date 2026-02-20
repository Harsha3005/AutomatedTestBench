"""
Gravimetric measurement engine for the test bench.

Performs water volume measurement using the gravimetric (weighing) method
per ISO 4064. Sequence: tare scale → divert to collection tank →
collect water → divert to bypass → settle → read weight →
density-correct to volume.

Volume = net_mass / density(T)

Where density(T) is the temperature-dependent water density from
the ISO 4064 lookup table (testing/iso4064.py).
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from testing.iso4064 import water_density

logger = logging.getLogger(__name__)


class MeasureState(Enum):
    IDLE = 'IDLE'
    TARING = 'TARING'
    COLLECTING = 'COLLECTING'
    SETTLING = 'SETTLING'
    READING = 'READING'
    COMPLETE = 'COMPLETE'
    ERROR = 'ERROR'


@dataclass
class GravimetricResult:
    """Result of a gravimetric volume measurement."""
    success: bool = False
    net_weight_kg: float = 0.0
    tare_weight_kg: float = 0.0
    gross_weight_kg: float = 0.0
    temperature_c: float = 20.0
    density_kg_l: float = 0.99820
    volume_l: float = 0.0
    collect_time_s: float = 0.0
    avg_flow_lph: float = 0.0
    error_message: str = ''
    timestamp: float = field(default_factory=time.time)


# Default timing parameters
SETTLE_TIME_S = 2.0       # Wait after diverter closes before reading
TARE_TOLERANCE_KG = 0.020  # Scale must be within ±20g of zero after tare
TARE_TIMEOUT_S = 5.0       # Max wait for scale to settle during tare
DRAIN_TIMEOUT_S = 60.0     # Max wait for drain to complete
DRAIN_THRESHOLD_KG = 0.1   # Weight at which tank is considered empty


class GravimetricEngine:
    """
    Gravimetric measurement engine.

    Usage:
        engine = GravimetricEngine(sensor_manager, valve_controller)

        # Tare before each Q-point
        tare_ok = engine.tare()

        # Collect
        engine.start_collection()
        # ... wait for desired volume / time ...
        result = engine.stop_collection_and_measure()

        # Drain tank
        engine.drain_tank()
    """

    def __init__(self, sensor_manager=None, valve_controller=None):
        """
        Args:
            sensor_manager: SensorManager for reading scale and temperature.
            valve_controller: ValveController for diverter and drain valve.
        """
        self._sensor_manager = sensor_manager
        self._valve_controller = valve_controller
        self._state = MeasureState.IDLE

        # Measurement tracking
        self._tare_weight = 0.0
        self._collect_start_time = 0.0
        self._em_totalizer_start = 0.0

    @property
    def state(self) -> MeasureState:
        return self._state

    # ------------------------------------------------------------------
    #  Tare
    # ------------------------------------------------------------------

    def tare(self, timeout_s: float = TARE_TIMEOUT_S) -> bool:
        """
        Tare the weighing scale.

        Ensures diverter is in BYPASS and waits for scale to settle
        within TARE_TOLERANCE_KG of zero.

        Returns True if tare succeeded.
        """
        self._state = MeasureState.TARING
        logger.info("Gravimetric: taring scale...")

        # Ensure diverter is on bypass
        if self._valve_controller:
            self._valve_controller.set_diverter('BYPASS')

        # Read initial weight
        snap = self._sensor_manager.latest if self._sensor_manager else None
        if snap is None:
            self._state = MeasureState.ERROR
            return False

        # For simulator, command the tare
        from controller.hardware import _get_backend
        if _get_backend() == 'simulator':
            from controller.simulator import get_simulator
            sim = get_simulator()
            sim.tare_scale()

        # Wait for scale to settle near zero
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            snap = self._sensor_manager.latest
            weight = snap.weight_kg
            if abs(weight) <= TARE_TOLERANCE_KG:
                self._tare_weight = snap.weight_raw_kg
                self._state = MeasureState.IDLE
                logger.info("Tare complete: offset=%.3f kg, reading=%.3f kg",
                            self._tare_weight, weight)
                return True
            time.sleep(0.1)

        logger.error("Tare timeout: scale reading %.3f kg not within tolerance",
                      snap.weight_kg if snap else 0)
        self._state = MeasureState.ERROR
        return False

    # ------------------------------------------------------------------
    #  Collection
    # ------------------------------------------------------------------

    def start_collection(self):
        """
        Start collecting water into the tank.
        Switches diverter to COLLECT position.
        """
        if self._valve_controller:
            self._valve_controller.set_diverter('COLLECT')

        self._collect_start_time = time.time()

        # Record EM totalizer start for reference
        snap = self._sensor_manager.latest if self._sensor_manager else None
        self._em_totalizer_start = snap.em_totalizer_l if snap else 0.0

        self._state = MeasureState.COLLECTING
        logger.info("Gravimetric: collection started")

    def stop_collection_and_measure(
        self,
        settle_time_s: float = SETTLE_TIME_S,
    ) -> GravimetricResult:
        """
        Stop collection and perform the gravimetric measurement.

        1. Switch diverter to BYPASS
        2. Wait for settle_time_s
        3. Read weight and temperature
        4. Calculate volume using density correction

        Returns GravimetricResult with volume in litres.
        """
        # Switch diverter to bypass
        self._state = MeasureState.SETTLING
        if self._valve_controller:
            self._valve_controller.set_diverter('BYPASS')

        collect_time = time.time() - self._collect_start_time
        logger.info("Collection stopped after %.1f s, settling...", collect_time)

        # Wait for water to settle
        time.sleep(settle_time_s)

        # Read final values
        self._state = MeasureState.READING
        snap = self._sensor_manager.latest if self._sensor_manager else None
        if snap is None:
            self._state = MeasureState.ERROR
            return GravimetricResult(
                success=False,
                error_message="No sensor data available",
            )

        net_weight = snap.weight_kg
        gross_weight = snap.weight_raw_kg
        temperature = snap.water_temp_c
        em_totalizer_end = snap.em_totalizer_l

        # Density correction
        density = water_density(temperature)
        volume = net_weight / density if density > 0 else 0.0

        # Average flow rate
        avg_flow = 0.0
        if collect_time > 0:
            avg_flow = (volume / collect_time) * 3600  # L/h

        result = GravimetricResult(
            success=True,
            net_weight_kg=net_weight,
            tare_weight_kg=self._tare_weight,
            gross_weight_kg=gross_weight,
            temperature_c=temperature,
            density_kg_l=density,
            volume_l=volume,
            collect_time_s=collect_time,
            avg_flow_lph=avg_flow,
        )

        self._state = MeasureState.COMPLETE
        logger.info(
            "Gravimetric result: weight=%.3f kg, temp=%.1f C, "
            "density=%.5f kg/L, volume=%.4f L",
            net_weight, temperature, density, volume,
        )
        return result

    # ------------------------------------------------------------------
    #  Convenience: single-shot measurement
    # ------------------------------------------------------------------

    def measure_volume(
        self,
        settle_time_s: float = SETTLE_TIME_S,
    ) -> GravimetricResult:
        """
        Perform a complete measurement cycle.

        Assumes collection is already happening (diverter in COLLECT).
        Stops collection, settles, reads weight, and calculates volume.

        For the full cycle (tare → collect → measure), use
        tare() + start_collection() + stop_collection_and_measure().
        """
        return self.stop_collection_and_measure(settle_time_s)

    @staticmethod
    def calculate_volume(net_weight_kg: float, temperature_c: float) -> tuple[float, float]:
        """
        Static utility: calculate volume from weight and temperature.

        Returns (volume_l, density_kg_l).
        """
        density = water_density(temperature_c)
        volume = net_weight_kg / density if density > 0 else 0.0
        return volume, density

    # ------------------------------------------------------------------
    #  Drain
    # ------------------------------------------------------------------

    def drain_tank(
        self,
        timeout_s: float = DRAIN_TIMEOUT_S,
        threshold_kg: float = DRAIN_THRESHOLD_KG,
    ) -> bool:
        """
        Drain the collection tank back to reservoir.

        Opens SV-DRN, waits until weight drops below threshold,
        then closes SV-DRN.

        Returns True when tank is empty (or near-empty).
        """
        logger.info("Draining collection tank...")

        if not self._valve_controller:
            return False

        # Open drain valve
        self._valve_controller.open_valve('SV-DRN')

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            snap = self._sensor_manager.latest if self._sensor_manager else None
            if snap and snap.weight_kg <= threshold_kg:
                self._valve_controller.close_valve('SV-DRN')
                logger.info("Tank drained (weight=%.3f kg)", snap.weight_kg)
                return True
            time.sleep(0.5)

        # Timeout — close drain anyway
        self._valve_controller.close_valve('SV-DRN')
        snap = self._sensor_manager.latest if self._sensor_manager else None
        weight = snap.weight_kg if snap else 0
        logger.warning("Drain timeout (weight=%.3f kg still > threshold)", weight)
        return False

    def reset(self):
        """Reset engine state to IDLE."""
        self._state = MeasureState.IDLE
        self._tare_weight = 0.0
        self._collect_start_time = 0.0
        self._em_totalizer_start = 0.0
