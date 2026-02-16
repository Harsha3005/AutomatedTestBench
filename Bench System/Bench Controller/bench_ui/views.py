import json
import random
import time

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST
from testing.models import Test
from meters.models import TestMeter
from controller.models import DeviceGroup, FieldDevice
from accounts.models import CustomUser
from accounts.permissions import role_required


@login_required
def dashboard(request):
    """Bench dashboard: system status, current test, quick actions."""
    active_test = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged']
    ).select_related('meter').first()
    recent_tests = Test.objects.select_related(
        'meter', 'initiated_by',
    ).order_by('-created_at')[:8]
    last_test = Test.objects.filter(
        status='completed',
    ).select_related('meter').order_by('-completed_at').first()
    stats = {
        'total_tests': Test.objects.count(),
        'registered_meters': TestMeter.objects.count(),
        'passed': Test.objects.filter(overall_pass=True).count(),
        'failed': Test.objects.filter(overall_pass=False).count(),
    }
    return render(request, 'bench_ui/dashboard.html', {
        'active_test': active_test,
        'recent_tests': recent_tests,
        'last_test': last_test,
        'stats': stats,
    })


@login_required
def test_control(request):
    """Test control page: select/start a test or view running test."""
    active_test = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged']
    ).select_related('meter').first()
    pending_tests = Test.objects.filter(
        status='pending'
    ).select_related('meter')
    return render(request, 'bench_ui/test_control.html', {
        'active_test': active_test,
        'pending_tests': pending_tests,
    })


@login_required
def test_control_live(request, test_id):
    """Live HMI view for an active test."""
    test = get_object_or_404(Test.objects.select_related('meter'), pk=test_id)
    results = test.results.all()
    return render(request, 'bench_ui/test_control_live.html', {
        'test': test,
        'results': results,
    })


@login_required
def lock_screen(request):
    """Display the lock screen. User stays authenticated but must re-enter password."""
    return render(request, 'bench_ui/lock_screen.html')


@login_required
def unlock(request):
    """Verify password to unlock the bench."""
    if request.method == 'POST':
        password = request.POST.get('password', '')
        user = authenticate(
            request,
            username=request.user.username,
            password=password,
        )
        if user is not None:
            # Re-login to refresh session
            login(request, user)
            next_url = request.POST.get('next', '/')
            return redirect(next_url)
        else:
            messages.error(request, "Incorrect password.")
            return redirect('bench_ui:lock_screen')
    return redirect('bench_ui:lock_screen')


# ---------------------------------------------------------------------------
#  System Tab — Diagnostics & Commissioning
# ---------------------------------------------------------------------------

# In-memory simulated device states (until real hardware connected)
_sim_states = {}


def _get_simulated_state(device):
    """Generate realistic simulated values for each device category."""
    did = device.device_id
    if did not in _sim_states:
        # Initialise on first call
        if device.category == 'valve':
            # BV-L2 (3/4" lane) starts open; all others start closed
            if did == 'BV-L2':
                _sim_states[did] = {'state': 'open'}
            else:
                _sim_states[did] = {'state': 'closed'}
        elif device.category == 'pump':
            _sim_states[did] = {'state': 'stopped', 'frequency': 0.0}
        elif device.category == 'indicator':
            _sim_states[did] = {'red': False, 'green': True, 'buzzer': False}
        elif device.category == 'meter':
            _sim_states[did] = {'state': 'disconnected'}
        elif device.category == 'communication':
            _sim_states[did] = {'state': 'online', 'last_seen': time.time()}
        else:
            # Sensors — start at midpoint, except reservoir level (start at 85%)
            if did == 'RES-LVL':
                _sim_states[did] = {'value': 85.0}
            else:
                mn = device.min_value or 0
                mx = device.max_value or 100
                _sim_states[did] = {'value': round((mn + mx) / 2, 2)}

    state = _sim_states[did]

    # Add sensor noise on every read
    if device.category.startswith('sensor_'):
        mn = device.min_value or 0
        mx = device.max_value or 100
        rng = mx - mn
        state['value'] = round(
            max(mn, min(mx, state['value'] + random.uniform(-rng * 0.005, rng * 0.005))), 2
        )
    if device.category == 'communication':
        state['last_seen'] = time.time()

    return dict(state)


@login_required
def system_status(request):
    """Render the System diagnostics tab page."""
    groups = DeviceGroup.objects.prefetch_related('devices').all()
    test_active = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged']
    ).exists()
    return render(request, 'bench_ui/system_status.html', {
        'groups': groups,
        'test_active': test_active,
    })


@login_required
def system_api_status(request):
    """GET: Return all device states as JSON, grouped."""
    groups = DeviceGroup.objects.prefetch_related('devices').all()
    test_active = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged']
    ).exists()

    data = {
        'test_active': test_active,
        'groups': [],
    }
    for group in groups:
        g = {
            'name': group.name,
            'color': group.color,
            'devices': [],
        }
        for dev in group.devices.filter(is_active=True):
            state = _get_simulated_state(dev)
            g['devices'].append({
                'device_id': dev.device_id,
                'name': dev.name,
                'category': dev.category,
                'unit': dev.unit,
                'min_value': dev.min_value,
                'max_value': dev.max_value,
                **state,
            })
        data['groups'].append(g)

    return JsonResponse(data)


@login_required
@require_POST
def system_api_command(request):
    """POST: Send a manual command to a device."""
    # Safety: no manual actuation during active tests
    test_active = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged']
    ).exists()
    if test_active:
        return JsonResponse(
            {'ok': False, 'error': 'Manual controls locked — test in progress'},
            status=403,
        )

    # Role check
    if not request.user.can_actuate:
        return JsonResponse(
            {'ok': False, 'error': 'Insufficient permissions'},
            status=403,
        )

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    device_id = body.get('device_id')
    action = body.get('action')
    if not device_id or not action:
        return JsonResponse(
            {'ok': False, 'error': 'device_id and action required'}, status=400
        )

    try:
        device = FieldDevice.objects.get(device_id=device_id, is_active=True)
    except FieldDevice.DoesNotExist:
        return JsonResponse(
            {'ok': False, 'error': f'Device {device_id} not found'}, status=404
        )

    # Process command based on device category
    state = _get_simulated_state(device)

    if device.category == 'valve':
        if action == 'toggle':
            new_state = 'open' if state['state'] == 'closed' else 'closed'
        elif action in ('open', 'close'):
            new_state = action + ('d' if action == 'close' else '')
        else:
            new_state = state['state']

        # Safety interlocks for SV1
        if device_id == 'SV1' and new_state == 'open':
            # 1. DUT/MUT must be present on the line
            dut_state = _sim_states.get('DUT', {}).get('state', 'disconnected')
            if dut_state != 'connected':
                return JsonResponse(
                    {'ok': False, 'error': 'Cannot open SV1: no meter installed. Confirm MUT presence first.'},
                    status=400,
                )
            # 2. At least one test lane must be open
            lanes_open = any(
                _sim_states.get(lane, {}).get('state') == 'open'
                for lane in ('BV-L1', 'BV-L2', 'BV-L3')
            )
            if not lanes_open:
                return JsonResponse(
                    {'ok': False, 'error': 'Cannot open SV1: no test lane open. Open at least one lane valve (BV-L1/L2/L3) first.'},
                    status=400,
                )

        state['state'] = new_state
        _sim_states[device_id] = state

        # Safety interlock: auto-stop pump if no flow path remains
        if device_id in ('SV1', 'BV-BP') and state['state'] == 'closed':
            sv1 = _sim_states.get('SV1', {})
            bvbp = _sim_states.get('BV-BP', {})
            pump = _sim_states.get('P-01', {})
            if pump.get('state') == 'running':
                if sv1.get('state') != 'open' and bvbp.get('state') != 'open':
                    _sim_states['P-01']['state'] = 'stopped'
                    _sim_states['P-01']['frequency'] = 0.0

    elif device.category == 'pump':
        # Safety interlock: pump can only start if at least one flow path is open
        # Either main line (SV1) or bypass (BV-BP) must be open
        def _has_open_flow_path():
            sv1 = _sim_states.get('SV1', {})
            bvbp = _sim_states.get('BV-BP', {})
            return sv1.get('state') == 'open' or bvbp.get('state') == 'open'

        # Safety interlock: reservoir must have at least 70% water level
        def _tank_level_ok():
            res = _sim_states.get('RES-LVL', {})
            return res.get('value', 0) >= 70

        if action == 'toggle':
            if state['state'] == 'stopped':
                if not _tank_level_ok():
                    return JsonResponse(
                        {'ok': False, 'error': 'Cannot start pump: reservoir level below 70%. Minimum 70% required.'},
                        status=400,
                    )
                if not _has_open_flow_path():
                    return JsonResponse(
                        {'ok': False, 'error': 'Cannot start pump: no flow path open. Open SV1 (main line) or BV-BP (bypass) first.'},
                        status=400,
                    )
                state['state'] = 'running'
                state['frequency'] = 30.0
            else:
                state['state'] = 'stopped'
                state['frequency'] = 0.0
        elif action == 'start':
            if not _tank_level_ok():
                return JsonResponse(
                    {'ok': False, 'error': 'Cannot start pump: reservoir level below 70%. Minimum 70% required.'},
                    status=400,
                )
            if not _has_open_flow_path():
                return JsonResponse(
                    {'ok': False, 'error': 'Cannot start pump: no flow path open. Open SV1 (main line) or BV-BP (bypass) first.'},
                    status=400,
                )
            state['state'] = 'running'
            state['frequency'] = body.get('frequency', 30.0)
        elif action == 'stop':
            state['state'] = 'stopped'
            state['frequency'] = 0.0
        _sim_states[device_id] = state

    elif device.category == 'meter':
        if action == 'toggle':
            state['state'] = 'connected' if state['state'] == 'disconnected' else 'disconnected'
        elif action == 'connect':
            state['state'] = 'connected'
        elif action == 'disconnect':
            state['state'] = 'disconnected'
        # Safety: if DUT is disconnected while SV1 is open, close SV1 and stop pump
        if state['state'] == 'disconnected':
            sv1 = _sim_states.get('SV1', {})
            if sv1.get('state') == 'open':
                _sim_states['SV1']['state'] = 'closed'
                pump = _sim_states.get('P-01', {})
                if pump.get('state') == 'running':
                    bvbp = _sim_states.get('BV-BP', {})
                    if bvbp.get('state') != 'open':
                        _sim_states['P-01']['state'] = 'stopped'
                        _sim_states['P-01']['frequency'] = 0.0
        _sim_states[device_id] = state

    elif device.category == 'indicator':
        if action == 'set':
            for key in ('red', 'green', 'buzzer'):
                if key in body:
                    state[key] = bool(body[key])
            _sim_states[device_id] = state
        elif action in ('red', 'green', 'buzzer'):
            state[action] = not state.get(action, False)
            _sim_states[device_id] = state

    else:
        return JsonResponse(
            {'ok': False, 'error': f'Device {device_id} does not support commands'},
            status=400,
        )

    return JsonResponse({'ok': True, 'device_id': device_id, 'state': state})


# ---------------------------------------------------------------------------
#  Emergency Stop
# ---------------------------------------------------------------------------

@login_required
@require_POST
def emergency_stop(request):
    """Emergency stop: abort all active tests and stop pumps."""
    from testing.services import abort_test
    from controller.state_machine import abort_active_test

    # Abort via state machine (if running)
    abort_active_test(reason=f'Emergency stop by {request.user.username}')

    # Also abort any DB-level active tests not caught by state machine
    active_tests = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged']
    )
    count = 0
    for test in active_tests:
        abort_test(test, reason=f'Emergency stop by {request.user.username}')
        count += 1

    # Stop all pumps via simulator
    for did, state in _sim_states.items():
        if 'frequency' in state:
            state['state'] = 'stopped'
            state['frequency'] = 0.0

    if count:
        messages.warning(request, f'EMERGENCY STOP — {count} test(s) aborted.')
    else:
        messages.info(request, 'Emergency stop — no active tests found.')
    return redirect('bench_ui:dashboard')


# ---------------------------------------------------------------------------
#  Test Execution API (T-402)
# ---------------------------------------------------------------------------

@login_required
@role_required('admin', 'developer', 'bench_tech')
@require_POST
def api_test_start(request, test_id):
    """POST: Start a pending test through the state machine."""
    from controller.state_machine import start_test_machine, get_active_machine

    active = get_active_machine()
    if active is not None:
        return JsonResponse({
            'ok': False,
            'error': f'Test #{active.test_id} is already running',
        }, status=409)

    try:
        test = Test.objects.get(pk=test_id)
    except Test.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Test not found'}, status=404)

    if test.status not in ('pending', 'queued', 'acknowledged'):
        return JsonResponse({
            'ok': False,
            'error': f'Test cannot be started (status={test.status})',
        }, status=400)

    try:
        sm = start_test_machine(test_id)
        return JsonResponse({
            'ok': True,
            'test_id': test_id,
            'state': sm.state.value,
        })
    except RuntimeError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=409)


@login_required
@require_POST
def api_test_abort(request):
    """POST: Abort the currently running test."""
    from controller.state_machine import abort_active_test as _abort

    body = {}
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        pass

    reason = body.get('reason', f'Aborted by {request.user.username}')
    aborted = _abort(reason)

    if aborted:
        return JsonResponse({'ok': True, 'message': 'Abort requested'})
    return JsonResponse({'ok': False, 'error': 'No active test to abort'}, status=404)


@login_required
def api_test_status(request):
    """GET: Return current test state machine status."""
    from controller.state_machine import get_active_machine

    sm = get_active_machine()
    if sm is None:
        return JsonResponse({
            'active': False,
            'state': 'IDLE',
            'test_id': None,
            'q_point': '',
        })

    return JsonResponse({
        'active': True,
        'state': sm.state.value,
        'test_id': sm.test_id,
        'q_point': sm.current_q_point,
    })


@login_required
def api_dut_prompt(request):
    """GET: Check if there's a pending manual DUT reading request."""
    from controller.state_machine import get_active_machine

    sm = get_active_machine()
    if sm is None:
        return JsonResponse({'pending': False})

    if hasattr(sm, '_dut') and sm._dut is not None:
        from controller.dut_interface import DUTState, DUTMode
        if sm._dut.mode == DUTMode.MANUAL and sm._dut.state in (
            DUTState.WAITING_BEFORE, DUTState.WAITING_AFTER,
        ):
            reading_type = 'before' if sm._dut.state == DUTState.WAITING_BEFORE else 'after'
            return JsonResponse({
                'pending': True,
                'test_id': sm.test_id,
                'q_point': sm.current_q_point,
                'reading_type': reading_type,
            })

    return JsonResponse({'pending': False})


@login_required
@role_required('admin', 'developer', 'bench_tech')
@require_POST
def api_dut_submit(request):
    """POST: Submit a manual DUT reading."""
    from controller.state_machine import get_active_machine

    sm = get_active_machine()
    if sm is None:
        return JsonResponse({'ok': False, 'error': 'No active test'}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    reading_type = body.get('reading_type')
    value = body.get('value')

    if reading_type not in ('before', 'after'):
        return JsonResponse({
            'ok': False, 'error': 'reading_type must be before or after',
        }, status=400)
    if value is None or not isinstance(value, (int, float)):
        return JsonResponse({
            'ok': False, 'error': 'value must be a number',
        }, status=400)

    ok = sm.submit_manual_dut_reading(
        reading_type=reading_type,
        value=float(value),
        entered_by=request.user,
    )

    if ok:
        return JsonResponse({'ok': True})
    return JsonResponse({
        'ok': False, 'error': 'Reading rejected',
    }, status=400)


# ---------------------------------------------------------------------------
#  Settings Page
# ---------------------------------------------------------------------------

@login_required
def settings_page(request):
    """Main settings page with User Management and General Settings tabs."""
    import sys
    from bench_ui.models import BenchSettings
    bench_settings = BenchSettings.load()
    users = CustomUser.objects.all().order_by('username')
    is_admin = request.user.role == 'admin'
    return render(request, 'bench_ui/settings.html', {
        'bench_settings': bench_settings,
        'users': users,
        'is_admin': is_admin,
        'roles': CustomUser.ROLE_CHOICES,
        'python_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
    })


@role_required('admin')
def settings_general_save(request):
    """POST: Save general settings (admin only)."""
    if request.method != 'POST':
        return redirect('bench_ui:settings')

    from bench_ui.models import BenchSettings
    s = BenchSettings.load()

    s.theme = request.POST.get('theme', 'dark')

    timeout_val = request.POST.get('auto_lock_timeout', '300')
    try:
        s.auto_lock_timeout = max(0, int(timeout_val))
    except (ValueError, TypeError):
        s.auto_lock_timeout = 300

    s.buzzer_enabled = request.POST.get('buzzer_enabled') == 'on'
    s.datetime_format = request.POST.get('datetime_format', '24h')

    brightness_val = request.POST.get('display_brightness', '100')
    try:
        s.display_brightness = max(0, min(100, int(brightness_val)))
    except (ValueError, TypeError):
        s.display_brightness = 100

    s.bench_id = request.POST.get('bench_id', s.bench_id).strip()

    s.save()
    messages.success(request, 'Settings saved.')
    return redirect('bench_ui:settings')


# ---------------------------------------------------------------------------
#  Bench Test Wizard (T-602)
# ---------------------------------------------------------------------------

@login_required
@role_required('admin', 'developer', 'bench_tech')
def test_wizard(request):
    """4-step bench test wizard: select meter → DUT mode → review Q-points → confirm & start."""
    from testing.models import ISO4064Standard, TestResult

    if request.method == 'POST':
        meter_id = request.POST.get('meter_id')
        dut_mode = request.POST.get('dut_mode', 'manual')
        notes = request.POST.get('notes', '').strip()

        if not meter_id:
            messages.error(request, 'Please select a meter.')
            return redirect('bench_ui:test_wizard')

        try:
            meter = TestMeter.objects.get(pk=meter_id)
        except TestMeter.DoesNotExist:
            messages.error(request, 'Meter not found.')
            return redirect('bench_ui:test_wizard')

        # Update meter DUT mode
        if dut_mode in ('rs485', 'manual'):
            meter.dut_mode = dut_mode
            meter.save(update_fields=['dut_mode'])

        # Create test
        test = Test.objects.create(
            meter=meter,
            test_class=meter.meter_class,
            source='bench',
            status='pending',
            initiated_by=request.user,
            notes=notes,
        )

        # Auto-populate TestResults from ISO 4064 standards
        standards = ISO4064Standard.objects.filter(
            meter_size=meter.meter_size,
            meter_class=meter.meter_class,
        ).order_by('q_point')

        for std in standards:
            TestResult.objects.create(
                test=test,
                q_point=std.q_point,
                target_flow_lph=std.flow_rate_lph,
                mpe_pct=std.mpe_pct,
                zone=std.zone,
            )

        return redirect('bench_ui:test_control_live', test_id=test.pk)

    # GET: render wizard
    meters = TestMeter.objects.all().order_by('serial_number')

    # Build ISO standards lookup as JSON for Alpine.js
    standards_qs = ISO4064Standard.objects.all().order_by('q_point')
    standards_map = {}
    for std in standards_qs:
        key = f'{std.meter_size}_{std.meter_class}'
        if key not in standards_map:
            standards_map[key] = []
        standards_map[key].append({
            'q_point': std.q_point,
            'flow_rate_lph': std.flow_rate_lph,
            'test_volume_l': std.test_volume_l,
            'duration_s': std.duration_s,
            'mpe_pct': std.mpe_pct,
            'zone': std.zone,
        })

    return render(request, 'bench_ui/test_wizard.html', {
        'meters': meters,
        'standards_json': json.dumps(standards_map),
    })


# ---------------------------------------------------------------------------
#  Bench Results Tab (T-606)
# ---------------------------------------------------------------------------

@login_required
def test_results(request, test_id):
    """Bench results view: swipeable Q-point cards, error curve."""
    from testing.services import get_test_summary

    test = get_object_or_404(Test.objects.select_related('meter'), pk=test_id)
    summary = get_test_summary(test)

    # Build Q-point and MPE data for error curve chart
    qpoint_chart_data = []
    mpe_chart_data = []
    for qp in summary.q_points:
        qpoint_chart_data.append({
            'q_point': qp.q_point.replace('Q', ''),
            'flow_rate': qp.target_flow_lph,
            'error_pct': qp.error_pct,
            'passed': qp.passed,
        })
        mpe_chart_data.append({
            'flow_rate': qp.target_flow_lph,
            'mpe': qp.mpe_pct,
        })

    return render(request, 'bench_ui/test_results.html', {
        'test': test,
        'summary': summary,
        'qpoint_chart_json': json.dumps(qpoint_chart_data),
        'mpe_chart_json': json.dumps(mpe_chart_data),
    })


# ---------------------------------------------------------------------------
#  Bench History Tab (T-607)
# ---------------------------------------------------------------------------

@login_required
def test_history(request):
    """Bench history view: scrollable list of past tests."""
    tests = Test.objects.select_related(
        'meter', 'initiated_by',
    ).order_by('-created_at')[:50]

    return render(request, 'bench_ui/test_history.html', {
        'tests': tests,
    })


# ---------------------------------------------------------------------------
#  Bench Setup Tab (T-608)
# ---------------------------------------------------------------------------

@login_required
@role_required('admin')
def setup_page(request):
    """Read-only display of PID, safety, and serial configuration."""
    from django.conf import settings as django_settings
    from bench_ui.models import BenchSettings
    import sys

    bench_settings = BenchSettings.load()

    pid_config = {
        'Kp': getattr(django_settings, 'PID_KP', '—'),
        'Ki': getattr(django_settings, 'PID_KI', '—'),
        'Kd': getattr(django_settings, 'PID_KD', '—'),
        'Output Min (Hz)': getattr(django_settings, 'PID_OUTPUT_MIN', '—'),
        'Output Max (Hz)': getattr(django_settings, 'PID_OUTPUT_MAX', '—'),
        'Sample Rate (s)': getattr(django_settings, 'PID_SAMPLE_RATE', '—'),
    }

    safety_config = {
        'Pressure Max (bar)': getattr(django_settings, 'SAFETY_PRESSURE_MAX', '—'),
        'Reservoir Min (%)': getattr(django_settings, 'SAFETY_RESERVOIR_MIN', '—'),
        'Scale Max (kg)': getattr(django_settings, 'SAFETY_SCALE_MAX', '—'),
        'Temp Min (\u00b0C)': getattr(django_settings, 'SAFETY_TEMP_MIN', '—'),
        'Temp Max (\u00b0C)': getattr(django_settings, 'SAFETY_TEMP_MAX', '—'),
        'Valve Timeout (s)': getattr(django_settings, 'SAFETY_VALVE_TIMEOUT', '—'),
        'Flow Stability (%)': getattr(django_settings, 'SAFETY_FLOW_STABILITY', '—'),
        'Stability Count': getattr(django_settings, 'SAFETY_STABILITY_COUNT', '—'),
    }

    serial_config = {
        'Bus 1 Port': getattr(django_settings, 'BENCH_SERIAL_PORT_BUS1', '—'),
        'Bus 2 Port': getattr(django_settings, 'BENCH_SERIAL_PORT_BUS2', '—'),
        'Serial Baud': getattr(django_settings, 'BENCH_SERIAL_BAUD', '—'),
        'Modbus Baud': getattr(django_settings, 'MODBUS_BAUD', '—'),
        'ASP Device ID': hex(getattr(django_settings, 'ASP_DEVICE_ID', 0)),
    }

    return render(request, 'bench_ui/setup.html', {
        'bench_settings': bench_settings,
        'pid_config': pid_config,
        'safety_config': safety_config,
        'serial_config': serial_config,
        'python_version': f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
        'deployment_type': getattr(django_settings, 'DEPLOYMENT_TYPE', '—'),
    })
