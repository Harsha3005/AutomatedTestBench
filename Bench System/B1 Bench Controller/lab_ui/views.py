import csv
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard


# ---------------------------------------------------------------------------
#  T-502: Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    """Lab dashboard: stats, active test, comms status, recent tests."""
    today = timezone.now().date()

    active_test = Test.objects.filter(
        status__in=['running', 'queued', 'acknowledged'],
    ).select_related('meter').first()

    today_tests = Test.objects.filter(created_at__date=today)
    pending_approvals = Test.objects.filter(
        status='completed', approval_status='pending',
    ).count()

    total_tests = Test.objects.count()
    total_meters = TestMeter.objects.count()
    passed = Test.objects.filter(overall_pass=True).count()
    pass_rate = round(passed / total_tests * 100, 1) if total_tests else 0

    recent_tests = Test.objects.select_related(
        'meter', 'initiated_by',
    ).order_by('-created_at')[:10]

    # LoRa link status (best-effort)
    lora_status = {'state': 'unknown'}
    try:
        from comms.lora_handler import get_lora_handler
        handler = get_lora_handler()
        lora_status = handler.get_status()
    except Exception:
        pass
    link_status = lora_status.get('state', 'unknown')

    # Week test count
    from datetime import timedelta
    week_start = today - timedelta(days=today.weekday())
    week_tests = Test.objects.filter(created_at__date__gte=week_start).count()

    return render(request, 'lab_ui/dashboard.html', {
        'active_test': active_test,
        'today_completed': today_tests.filter(status='completed').count(),
        'today_total': today_tests.count(),
        'pending_approvals': pending_approvals,
        'total_tests': total_tests,
        'total_meters': total_meters,
        'pass_rate': pass_rate,
        'week_tests': week_tests,
        'recent_tests': recent_tests,
        'link_status': link_status,
        'lora_status': lora_status,
    })


# ---------------------------------------------------------------------------
#  LoRa Status API (US-306)
# ---------------------------------------------------------------------------

@login_required
def lora_status_api(request):
    """JSON endpoint for LoRa connection health (polled by dashboard)."""
    try:
        from comms.lora_handler import get_lora_handler
        handler = get_lora_handler()
        return JsonResponse(handler.get_status())
    except Exception:
        return JsonResponse({'state': 'unknown'})


@login_required
def lora_history_api(request):
    """JSON endpoint for LoRa message history."""
    try:
        from comms.lora_handler import get_lora_handler
        handler = get_lora_handler()
        limit = int(request.GET.get('limit', 50))
        include_hb = request.GET.get('heartbeats', '0') == '1'
        history = handler.get_history(
            limit=min(limit, 200), include_heartbeats=include_hb,
        )
        return JsonResponse({'messages': history})
    except Exception:
        return JsonResponse({'messages': []})


# ---------------------------------------------------------------------------
#  T-503: Test Wizard (3-step)
# ---------------------------------------------------------------------------

@role_required('admin', 'manager', 'lab_tech')
def test_wizard(request):
    """3-step test creation wizard for lab."""
    if request.method == 'POST':
        meter_id = request.POST.get('meter_id')
        meter = get_object_or_404(TestMeter, pk=meter_id)
        test_class = request.POST.get('test_class', meter.meter_class)
        notes = request.POST.get('notes', '').strip()

        test = Test.objects.create(
            meter=meter,
            test_class=test_class,
            initiated_by=request.user,
            source='lab',
            notes=notes,
        )

        # Auto-populate Q-point result placeholders
        q_points = ISO4064Standard.objects.filter(
            meter_size=meter.meter_size,
            meter_class=test_class,
        )
        for qp in q_points:
            TestResult.objects.create(
                test=test,
                q_point=qp.q_point,
                target_flow_lph=qp.flow_rate_lph,
                mpe_pct=qp.mpe_pct,
                zone=qp.zone,
            )

        # Try sending START_TEST via LoRa (non-fatal)
        try:
            from comms.lora_handler import get_lora_handler
            handler = get_lora_handler()
            if handler.link_online:
                handler.send_start_test_ack(test.pk, status='submitted')
        except Exception:
            pass

        # Audit log
        try:
            from audit.utils import log_audit
            log_audit(
                request.user, 'create', 'test', test.pk,
                f'Created test #{test.pk} for {meter.serial_number} via lab wizard',
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception:
            pass

        from django.contrib import messages
        messages.success(request, f"Test #{test.pk} submitted for {meter.serial_number}.")
        return redirect('testing:test_detail', pk=test.pk)

    meters = TestMeter.objects.all().order_by('serial_number')

    # Build ISO data as JSON for JavaScript step 2 preview
    iso_data = {}
    for std in ISO4064Standard.objects.all().order_by('q_point'):
        key = f"{std.meter_size}_{std.meter_class}"
        if key not in iso_data:
            iso_data[key] = []
        iso_data[key].append({
            'q_point': std.q_point,
            'flow_rate_lph': std.flow_rate_lph,
            'test_volume_l': std.test_volume_l,
            'mpe_pct': std.mpe_pct,
            'zone': std.zone,
        })

    from testing.models import TEST_CLASS_CHOICES

    return render(request, 'lab_ui/test_wizard.html', {
        'meters': meters,
        'class_choices': TEST_CLASS_CHOICES,
        'iso_data_json': json.dumps(iso_data),
    })


# ---------------------------------------------------------------------------
#  T-504: Live Monitor
# ---------------------------------------------------------------------------

@login_required
def live_monitor(request, test_id):
    """Lab live monitor page with HTMX polling."""
    if test_id == 0:
        # Find active test or show empty
        active = Test.objects.filter(
            status__in=['running', 'queued', 'acknowledged'],
        ).select_related('meter').first()
        if active:
            return redirect('lab_ui:live_monitor', test_id=active.pk)
        return render(request, 'lab_ui/live_monitor.html', {
            'test': None,
            'results': [],
        })

    test = get_object_or_404(Test.objects.select_related('meter'), pk=test_id)
    results = test.results.all().order_by('q_point')
    return render(request, 'lab_ui/live_monitor.html', {
        'test': test,
        'results': results,
    })


@login_required
def monitor_data_api(request, test_id):
    """JSON endpoint for HTMX live monitor polling."""
    test = get_object_or_404(Test, pk=test_id)
    results = list(test.results.values(
        'q_point', 'target_flow_lph', 'error_pct', 'mpe_pct',
        'passed', 'zone', 'ref_volume_l', 'dut_volume_l',
    ))

    data = {
        'test_id': test.pk,
        'status': test.status,
        'current_q_point': test.current_q_point,
        'current_state': test.current_state,
        'overall_pass': test.overall_pass,
        'results': results,
    }

    # Try to get live sensor data from bench_ui SensorReading
    try:
        from bench_ui.models import SensorReading
        latest = SensorReading.objects.filter(test=test).order_by('-timestamp').first()
        if latest:
            data['sensors'] = {
                'flow_rate_lph': latest.flow_rate_lph,
                'pressure_bar': latest.pressure_upstream_bar,
                'weight_kg': latest.weight_kg,
                'temperature_c': latest.water_temp_c,
                'vfd_freq_hz': latest.vfd_freq_hz,
            }
    except Exception:
        pass

    return JsonResponse(data)


# ---------------------------------------------------------------------------
#  T-508: Certificates
# ---------------------------------------------------------------------------

@login_required
def certificates(request):
    """Certificates listing page."""
    certs = Test.objects.filter(
        certificate_number__gt='',
    ).select_related('meter', 'initiated_by', 'approved_by').order_by('-completed_at')

    search_q = request.GET.get('q', '').strip()
    if search_q:
        from django.db.models import Q
        certs = certs.filter(
            Q(certificate_number__icontains=search_q) |
            Q(meter__serial_number__icontains=search_q)
        )

    return render(request, 'lab_ui/certificates.html', {
        'certs': certs,
        'search_q': search_q,
    })


# ---------------------------------------------------------------------------
#  T-510: Audit Log
# ---------------------------------------------------------------------------

@role_required('admin', 'manager')
def audit_log(request):
    """Audit log page with filters."""
    try:
        from audit.models import AuditEntry
    except ImportError:
        return render(request, 'lab_ui/audit_log.html', {'entries': [], 'page_obj': None})

    entries = AuditEntry.objects.select_related('user').order_by('-timestamp')

    # Filters
    action_filter = request.GET.get('action', '')
    if action_filter:
        entries = entries.filter(action=action_filter)

    user_filter = request.GET.get('user', '')
    if user_filter:
        entries = entries.filter(user_id=user_filter)

    target_filter = request.GET.get('target_type', '')
    if target_filter:
        entries = entries.filter(target_type=target_filter)

    date_from = request.GET.get('date_from', '')
    if date_from:
        entries = entries.filter(timestamp__date__gte=date_from)

    date_to = request.GET.get('date_to', '')
    if date_to:
        entries = entries.filter(timestamp__date__lte=date_to)

    # Paginate
    from django.core.paginator import Paginator
    paginator = Paginator(entries, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    from accounts.models import CustomUser
    action_choices = [
        'login', 'logout', 'create', 'update', 'delete',
        'approve', 'reject', 'abort', 'export',
    ]

    return render(request, 'lab_ui/audit_log.html', {
        'page_obj': page_obj,
        'action_choices': action_choices,
        'all_users': CustomUser.objects.filter(is_active=True).order_by('username'),
        'filters': {
            'action': action_filter,
            'user': user_filter,
            'target_type': target_filter,
            'date_from': date_from,
            'date_to': date_to,
        },
    })


@role_required('admin', 'manager')
def audit_export(request):
    """CSV export of audit log entries."""
    try:
        from audit.models import AuditEntry
    except ImportError:
        return StreamingHttpResponse('', content_type='text/csv')

    entries = AuditEntry.objects.select_related('user').order_by('-timestamp')

    # Apply same filters as audit_log
    action_filter = request.GET.get('action', '')
    if action_filter:
        entries = entries.filter(action=action_filter)
    user_filter = request.GET.get('user', '')
    if user_filter:
        entries = entries.filter(user_id=user_filter)

    def generate():
        yield 'Timestamp,User,Action,Target Type,Target ID,Description\n'
        for e in entries.iterator():
            user_str = e.user.username if e.user else 'system'
            ts = e.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            desc = e.description.replace('"', '""')
            yield f'{ts},{user_str},{e.action},{e.target_type},{e.target_id or ""},"{desc}"\n'

    response = StreamingHttpResponse(generate(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
    return response


# ---------------------------------------------------------------------------
#  T-511: Settings
# ---------------------------------------------------------------------------

@role_required('admin')
def lab_settings(request):
    """Lab settings page (read-only for now)."""
    import sys
    import django
    from django.conf import settings

    info = {
        'django_version': django.get_version(),
        'python_version': sys.version.split()[0],
        'deployment_type': getattr(settings, 'DEPLOYMENT_TYPE', 'unknown'),
        'database': settings.DATABASES['default']['NAME'],
        'serial_port': getattr(settings, 'LAB_SERIAL_PORT', 'N/A'),
        'serial_baud': getattr(settings, 'LAB_SERIAL_BAUD', 'N/A'),
        'asp_device_id': hex(getattr(settings, 'ASP_DEVICE_ID', 0)),
        'debug': settings.DEBUG,
        'session_timeout': getattr(settings, 'SESSION_COOKIE_AGE', 0),
    }

    # Crypto key status
    try:
        from comms.crypto import get_keys
        aes_key, hmac_key = get_keys()
        info['crypto_status'] = 'Keys loaded'
        info['aes_key_len'] = len(aes_key) * 8
        info['hmac_key_len'] = len(hmac_key) * 8
    except Exception:
        info['crypto_status'] = 'Keys not available'

    return render(request, 'lab_ui/settings.html', {'info': info})


# ---------------------------------------------------------------------------
#  T-506: CSV Export for test history
# ---------------------------------------------------------------------------

@login_required
def test_export_csv(request):
    """Export filtered test list as CSV."""
    tests = Test.objects.select_related('meter', 'initiated_by').order_by('-created_at')

    # Apply same filters as test_list
    search = request.GET.get('q', '').strip()
    if search:
        from django.db.models import Q
        q = Q(meter__serial_number__icontains=search) | Q(notes__icontains=search)
        if search.isdigit():
            q |= Q(pk=int(search))
        tests = tests.filter(q)

    status_filter = request.GET.get('status')
    if status_filter:
        tests = tests.filter(status=status_filter)

    result_filter = request.GET.get('result')
    if result_filter == 'pass':
        tests = tests.filter(overall_pass=True)
    elif result_filter == 'fail':
        tests = tests.filter(overall_pass=False)

    def generate():
        yield 'Test #,Meter,Size,Class,Status,Result,Source,Initiated By,Created,Completed,Approval,Certificate\n'
        for t in tests.iterator():
            result = 'PASS' if t.overall_pass is True else ('FAIL' if t.overall_pass is False else '')
            user = t.initiated_by.username if t.initiated_by else ''
            created = t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else ''
            completed = t.completed_at.strftime('%Y-%m-%d %H:%M') if t.completed_at else ''
            yield (
                f'{t.pk},{t.meter.serial_number},{t.meter.meter_size},{t.test_class},'
                f'{t.get_status_display()},{result},{t.get_source_display()},'
                f'{user},{created},{completed},'
                f'{t.get_approval_status_display()},{t.certificate_number}\n'
            )

    response = StreamingHttpResponse(generate(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="test_history.csv"'

    # Audit log
    try:
        from audit.utils import log_audit
        log_audit(
            request.user, 'export', 'test', description='Exported test history CSV',
            ip_address=request.META.get('REMOTE_ADDR'),
        )
    except Exception:
        pass

    return response
