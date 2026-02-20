import os

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from accounts.permissions import role_required
from meters.models import TestMeter
from testing.models import Test, TestResult, ISO4064Standard


@login_required
def test_list(request):
    tests = Test.objects.select_related('meter', 'initiated_by').all()

    # Collect active filters
    filters = {}

    # Search (meter serial, test ID, notes)
    search = request.GET.get('q', '').strip()
    if search:
        from django.db.models import Q
        q = Q(meter__serial_number__icontains=search) | Q(notes__icontains=search)
        if search.isdigit():
            q |= Q(pk=int(search))
        tests = tests.filter(q)
        filters['q'] = search

    # Status
    status_filter = request.GET.get('status')
    if status_filter:
        tests = tests.filter(status=status_filter)
        filters['status'] = status_filter

    # Result (pass / fail)
    result_filter = request.GET.get('result')
    if result_filter == 'pass':
        tests = tests.filter(overall_pass=True)
        filters['result'] = 'pass'
    elif result_filter == 'fail':
        tests = tests.filter(overall_pass=False)
        filters['result'] = 'fail'

    # Approval status
    approval_filter = request.GET.get('approval')
    if approval_filter:
        tests = tests.filter(approval_status=approval_filter)
        filters['approval'] = approval_filter

    # Source
    source_filter = request.GET.get('source')
    if source_filter:
        tests = tests.filter(source=source_filter)
        filters['source'] = source_filter

    # Meter
    meter_filter = request.GET.get('meter')
    if meter_filter:
        tests = tests.filter(meter_id=meter_filter)
        filters['meter'] = meter_filter

    # Initiated by
    user_filter = request.GET.get('user')
    if user_filter:
        tests = tests.filter(initiated_by_id=user_filter)
        filters['user'] = user_filter

    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        tests = tests.filter(created_at__date__gte=date_from)
        filters['date_from'] = date_from
    if date_to:
        tests = tests.filter(created_at__date__lte=date_to)
        filters['date_to'] = date_to

    from accounts.models import CustomUser
    from meters.models import TestMeter
    from django.conf import settings as django_settings

    context = {
        'tests': tests,
        'status_choices': Test.STATUS_CHOICES,
        'approval_choices': Test.APPROVAL_CHOICES,
        'source_choices': Test.SOURCE_CHOICES,
        'current_filter': status_filter,
        'filters': filters,
        'filter_count': len(filters),
        'all_meters': TestMeter.objects.all().order_by('serial_number'),
        'all_users': CustomUser.objects.filter(is_active=True).order_by('username'),
    }

    # Lab: paginate results
    if getattr(django_settings, 'DEPLOYMENT_TYPE', '') == 'lab':
        from django.core.paginator import Paginator
        paginator = Paginator(tests, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context['page_obj'] = page_obj
        context['tests'] = page_obj

    return render(request, 'testing/test_list.html', context)


@login_required
def test_detail(request, pk):
    test = get_object_or_404(
        Test.objects.select_related('meter', 'initiated_by', 'approved_by'),
        pk=pk,
    )
    results = test.results.all()
    return render(request, 'testing/test_detail.html', {
        'test': test,
        'results': results,
    })


@role_required('admin', 'manager', 'lab_tech', 'bench_tech')
def test_create(request):
    from testing.models import TEST_CLASS_CHOICES

    if request.method == 'POST':
        meter_id = request.POST.get('meter_id')
        meter = get_object_or_404(TestMeter, pk=meter_id)
        test_class = request.POST.get('test_class', meter.meter_class)

        test = Test.objects.create(
            meter=meter,
            test_class=test_class,
            initiated_by=request.user,
            source='bench',
        )

        # Auto-populate Q-point result placeholders from ISO 4064
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

        messages.success(request, f"Test #{test.pk} created for {meter.serial_number} ({test_class}).")
        try:
            from audit.utils import log_audit
            log_audit(
                request.user, 'create', 'test', test.pk,
                f'Created test #{test.pk} for {meter.serial_number}',
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception:
            pass
        return redirect('testing:test_detail', pk=test.pk)

    meters = TestMeter.objects.all()
    return render(request, 'testing/test_form.html', {
        'meters': meters,
        'class_choices': TEST_CLASS_CHOICES,
    })


@role_required('admin', 'manager')
def test_approve(request, pk):
    test = get_object_or_404(Test, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '').strip()

        if action == 'approve':
            test.approval_status = 'approved'
            test.approved_by = request.user
            test.approval_comment = comment
            test.save()

            # Generate certificate number and PDF
            try:
                from testing.services import generate_certificate_number
                from reports.generator import save_certificate
                generate_certificate_number(test)
                save_certificate(test)
                messages.success(
                    request,
                    f"Test #{test.pk} approved. Certificate {test.certificate_number} generated."
                )
            except Exception as e:
                messages.success(request, f"Test #{test.pk} approved.")
                messages.warning(request, f"Certificate generation failed: {e}")
        elif action == 'reject':
            test.approval_status = 'rejected'
            test.approved_by = request.user
            test.approval_comment = comment
            test.save()
            messages.warning(request, f"Test #{test.pk} rejected.")

        if action in ('approve', 'reject'):
            try:
                from audit.utils import log_audit
                log_audit(
                    request.user, action, 'test', test.pk,
                    f'Test #{test.pk} {action}d' + (f': {comment}' if comment else ''),
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
            except Exception:
                pass

        return redirect('testing:test_detail', pk=test.pk)

    return render(request, 'testing/test_approve.html', {'test': test})


@login_required
def test_results_api(request, pk):
    """JSON endpoint for HTMX polling of test status."""
    from django.http import JsonResponse

    test = get_object_or_404(Test, pk=pk)
    results = list(test.results.values(
        'q_point', 'error_pct', 'mpe_pct', 'passed', 'zone',
    ))
    return JsonResponse({
        'status': test.status,
        'current_q_point': test.current_q_point,
        'current_state': test.current_state,
        'overall_pass': test.overall_pass,
        'results': results,
    })


@login_required
def download_certificate(request, pk):
    """Download a test certificate PDF."""
    test = get_object_or_404(Test, pk=pk)
    if not test.certificate_pdf:
        raise Http404("No certificate available for this test.")

    filepath = os.path.join(django_settings.MEDIA_ROOT, test.certificate_pdf)
    if not os.path.isfile(filepath):
        raise Http404("Certificate file not found.")

    filename = f'{test.certificate_number or f"test_{test.pk}"}.pdf'
    return FileResponse(
        open(filepath, 'rb'),
        content_type='application/pdf',
        as_attachment=True,
        filename=filename,
    )
