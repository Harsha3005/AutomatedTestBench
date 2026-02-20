"""
Hardware abstraction layer.

Provides factory functions that return the appropriate backend
(simulator or real) based on HARDWARE_BACKEND setting.

Sprint 3 additions: valve_controller, pid_controller, safety_monitor,
tower_light, gravimetric_engine, dut_interface.

Usage:
    from controller.hardware import get_sensor_manager, get_vfd_controller

    sensor_mgr = get_sensor_manager()
    sensor_mgr.start()

    vfd = get_vfd_controller()
    vfd.start(frequency=30.0)
"""

import logging
import threading

from django.conf import settings

from controller.sensor_manager import SensorManager
from controller.vfd_controller import VFDController
from controller.valve_controller import ValveController
from controller.pid_controller import PIDController
from controller.tower_light import TowerLightController
from controller.gravimetric import GravimetricEngine
from controller.dut_interface import DUTInterface, DUTMode

logger = logging.getLogger(__name__)

# Module-level singletons
_sensor_manager: SensorManager | None = None
_vfd_controller: VFDController | None = None
_valve_controller: ValveController | None = None
_pid_controller: PIDController | None = None
_safety_monitor = None  # Type hint deferred to avoid circular import
_tower_light: TowerLightController | None = None
_gravimetric: GravimetricEngine | None = None
_dut_interface: DUTInterface | None = None
_init_lock = threading.Lock()


def _get_backend() -> str:
    """Get the configured hardware backend."""
    return getattr(settings, 'HARDWARE_BACKEND', 'simulator')


def get_sensor_manager() -> SensorManager:
    """Get or create the global SensorManager instance."""
    global _sensor_manager
    if _sensor_manager is None:
        with _init_lock:
            if _sensor_manager is None:
                backend = _get_backend()
                _sensor_manager = SensorManager(backend=backend)
                logger.info("SensorManager created (backend=%s)", backend)
    return _sensor_manager


def get_vfd_controller() -> VFDController:
    """Get or create the global VFDController instance."""
    global _vfd_controller
    if _vfd_controller is None:
        with _init_lock:
            if _vfd_controller is None:
                backend = _get_backend()
                _vfd_controller = VFDController(backend=backend)
                _vfd_controller.init_backend()
                logger.info("VFDController created (backend=%s)", backend)
    return _vfd_controller


def get_valve_controller() -> ValveController:
    """Get or create the global ValveController instance."""
    global _valve_controller
    if _valve_controller is None:
        with _init_lock:
            if _valve_controller is None:
                backend = _get_backend()
                _valve_controller = ValveController(backend=backend)
                _valve_controller.init_backend()
                logger.info("ValveController created (backend=%s)", backend)
    return _valve_controller


def get_pid_controller() -> PIDController:
    """Get or create the global PIDController instance."""
    global _pid_controller
    if _pid_controller is None:
        with _init_lock:
            if _pid_controller is None:
                _pid_controller = PIDController()
                logger.info("PIDController created")
    return _pid_controller


def get_safety_monitor():
    """Get or create the global SafetyMonitor instance."""
    global _safety_monitor
    if _safety_monitor is None:
        with _init_lock:
            if _safety_monitor is None:
                from controller.safety_monitor import SafetyMonitor
                import controller.hardware as hw
                _safety_monitor = SafetyMonitor(
                    sensor_manager=get_sensor_manager(),
                    hardware=hw,
                )
                logger.info("SafetyMonitor created")
    return _safety_monitor


def get_tower_light() -> TowerLightController:
    """Get or create the global TowerLightController instance."""
    global _tower_light
    if _tower_light is None:
        with _init_lock:
            if _tower_light is None:
                backend = _get_backend()
                _tower_light = TowerLightController(backend=backend)
                _tower_light.init_backend()
                logger.info("TowerLightController created (backend=%s)", backend)
    return _tower_light


def get_gravimetric_engine() -> GravimetricEngine:
    """Get or create the global GravimetricEngine instance."""
    global _gravimetric
    if _gravimetric is None:
        with _init_lock:
            if _gravimetric is None:
                _gravimetric = GravimetricEngine(
                    sensor_manager=get_sensor_manager(),
                    valve_controller=get_valve_controller(),
                )
                logger.info("GravimetricEngine created")
    return _gravimetric


def get_dut_interface(mode: DUTMode = DUTMode.RS485) -> DUTInterface:
    """Get or create the global DUTInterface instance."""
    global _dut_interface
    if _dut_interface is None:
        with _init_lock:
            if _dut_interface is None:
                backend = _get_backend()
                _dut_interface = DUTInterface(backend=backend, mode=mode)
                _dut_interface.init_backend()
                logger.info("DUTInterface created (backend=%s, mode=%s)", backend, mode.value)
    return _dut_interface


def get_simulator():
    """Get the simulator instance (only valid in simulator mode)."""
    backend = _get_backend()
    if backend != 'simulator':
        raise RuntimeError("Simulator not available in real hardware mode")
    from controller.simulator import get_simulator as _get_sim
    return _get_sim()


def start_all():
    """Start all hardware subsystems."""
    sm = get_sensor_manager()
    poll_rate = getattr(settings, 'PID_SAMPLE_RATE', 0.2)
    sm.start(poll_interval=poll_rate)

    # Start safety monitor
    monitor = get_safety_monitor()
    monitor.start(poll_interval=poll_rate)

    # Set tower to READY
    tower = get_tower_light()
    from controller.tower_light import LightPattern
    tower.set_pattern(LightPattern.READY)

    logger.info("All hardware subsystems started")


def stop_all():
    """Stop all hardware subsystems."""
    global _sensor_manager, _vfd_controller, _valve_controller
    global _pid_controller, _safety_monitor, _tower_light
    global _gravimetric, _dut_interface

    if _pid_controller:
        _pid_controller.disable()
    if _safety_monitor:
        _safety_monitor.stop()
    if _tower_light:
        _tower_light.stop()
    if _sensor_manager:
        _sensor_manager.stop()
    if _vfd_controller:
        _vfd_controller.emergency_stop()
    if _valve_controller:
        _valve_controller.close_all()

    _sensor_manager = None
    _vfd_controller = None
    _valve_controller = None
    _pid_controller = None
    _safety_monitor = None
    _tower_light = None
    _gravimetric = None
    _dut_interface = None
    logger.info("All hardware subsystems stopped")


def emergency_stop():
    """Emergency stop — stop VFD, close all valves, disable PID."""
    if _pid_controller:
        _pid_controller.disable()
    if _vfd_controller:
        _vfd_controller.emergency_stop()
    if _valve_controller:
        _valve_controller.close_all()
    if _tower_light:
        from controller.tower_light import LightPattern
        _tower_light.set_pattern(LightPattern.ESTOP)

    backend = _get_backend()
    if backend == 'simulator':
        from controller.simulator import get_simulator as _get_sim
        sim = _get_sim()
        sim.trigger_estop()
    logger.warning("HARDWARE EMERGENCY STOP executed")
