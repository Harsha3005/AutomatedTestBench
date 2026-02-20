from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from accounts.permissions import role_required
from meters.models import TestMeter


@login_required
def meter_list(request):
    meters = TestMeter.objects.all()
    return render(request, 'meters/meter_list.html', {'meters': meters})


@login_required
def meter_detail(request, pk):
    meter = get_object_or_404(TestMeter, pk=pk)
    tests = meter.test_set.all()[:10]
    return render(request, 'meters/meter_detail.html', {
        'meter': meter,
        'tests': tests,
    })


@role_required('admin', 'manager', 'lab_tech', 'bench_tech')
def meter_create(request):
    if request.method == 'POST':
        serial_number = request.POST.get('serial_number', '').strip()
        if TestMeter.objects.filter(serial_number=serial_number).exists():
            messages.error(request, "A meter with this serial number already exists.")
            return redirect('meters:meter_create')

        meter = TestMeter.objects.create(
            serial_number=serial_number,
            meter_size=request.POST.get('meter_size', 'DN15'),
            meter_class=request.POST.get('meter_class', 'B'),
            manufacturer=request.POST.get('manufacturer', '').strip(),
            model_name=request.POST.get('model_name', '').strip(),
            meter_type=request.POST.get('meter_type', 'mechanical'),
            dut_mode=request.POST.get('dut_mode', 'manual'),
            modbus_address=int(request.POST.get('modbus_address', 20)),
            modbus_baud=int(request.POST.get('modbus_baud', 9600)),
            notes=request.POST.get('notes', '').strip(),
            registered_by=request.user,
        )
        messages.success(request, f"Meter '{meter.serial_number}' registered.")
        try:
            from audit.utils import log_audit
            log_audit(
                request.user, 'create', 'meter', meter.pk,
                f'Registered meter {meter.serial_number}',
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception:
            pass
        return redirect('meters:meter_detail', pk=meter.pk)

    return render(request, 'meters/meter_form.html', {
        'sizes': TestMeter.SIZE_CHOICES,
        'classes': TestMeter.CLASS_CHOICES,
        'types': TestMeter.TYPE_CHOICES,
        'dut_modes': TestMeter.DUT_MODE_CHOICES,
    })


@role_required('admin', 'manager', 'lab_tech', 'bench_tech')
def meter_edit(request, pk):
    meter = get_object_or_404(TestMeter, pk=pk)
    if request.method == 'POST':
        meter.meter_size = request.POST.get('meter_size', meter.meter_size)
        meter.meter_class = request.POST.get('meter_class', meter.meter_class)
        meter.manufacturer = request.POST.get('manufacturer', '').strip()
        meter.model_name = request.POST.get('model_name', '').strip()
        meter.meter_type = request.POST.get('meter_type', meter.meter_type)
        meter.dut_mode = request.POST.get('dut_mode', meter.dut_mode)
        meter.modbus_address = int(request.POST.get('modbus_address', 20))
        meter.modbus_baud = int(request.POST.get('modbus_baud', 9600))
        meter.notes = request.POST.get('notes', '').strip()
        meter.save()
        messages.success(request, f"Meter '{meter.serial_number}' updated.")
        try:
            from audit.utils import log_audit
            log_audit(
                request.user, 'update', 'meter', meter.pk,
                f'Updated meter {meter.serial_number}',
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        except Exception:
            pass
        return redirect('meters:meter_detail', pk=meter.pk)

    return render(request, 'meters/meter_form.html', {
        'meter': meter,
        'sizes': TestMeter.SIZE_CHOICES,
        'classes': TestMeter.CLASS_CHOICES,
        'types': TestMeter.TYPE_CHOICES,
        'dut_modes': TestMeter.DUT_MODE_CHOICES,
    })
