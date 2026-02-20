import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import DeviceGroup, FieldDevice


def _require_config_permission(view_func):
    """Decorator: only admin/developer can access device configuration."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.can_configure_devices:
            messages.error(request, "Only admins and developers can configure devices.")
            return redirect('bench_ui:system_status')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@_require_config_permission
def device_config(request):
    """List all devices and groups for configuration."""
    groups = DeviceGroup.objects.prefetch_related('devices').all()
    devices = FieldDevice.objects.select_related('group').all()
    groups_json = json.dumps([
        {
            'id': g.pk, 'name': g.name, 'color': g.color,
            'description': g.description, 'display_order': g.display_order,
        }
        for g in groups
    ])
    devices_json = json.dumps([
        {
            'pk': d.pk, 'device_id': d.device_id, 'name': d.name,
            'category': d.category, 'group_id': d.group_id,
            'unit': d.unit, 'min_value': d.min_value, 'max_value': d.max_value,
            'display_order': d.display_order, 'is_active': d.is_active,
        }
        for d in devices
    ])
    categories_json = json.dumps(FieldDevice.CATEGORY_CHOICES)
    return render(request, 'controller/device_config.html', {
        'groups': groups,
        'devices': devices,
        'groups_json': groups_json,
        'devices_json': devices_json,
        'categories_json': categories_json,
    })


@_require_config_permission
@require_POST
def device_config_save(request):
    """Save device group assignments (bulk update)."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    assignments = body.get('assignments', [])
    for item in assignments:
        device_id = item.get('device_id')
        group_id = item.get('group_id')  # can be None
        try:
            device = FieldDevice.objects.get(device_id=device_id)
            if group_id:
                device.group_id = int(group_id)
            else:
                device.group = None
            device.save(update_fields=['group_id'])
        except FieldDevice.DoesNotExist:
            continue

    return JsonResponse({'ok': True})


@_require_config_permission
@require_POST
def group_save(request):
    """Create or update a device group."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    group_id = body.get('id')
    name = body.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required'}, status=400)

    if group_id:
        group = get_object_or_404(DeviceGroup, pk=group_id)
        group.name = name
        group.description = body.get('description', group.description)
        group.color = body.get('color', group.color)
        group.display_order = body.get('display_order', group.display_order)
        group.save()
    else:
        group = DeviceGroup.objects.create(
            name=name,
            description=body.get('description', ''),
            color=body.get('color', '#4CAF50'),
            display_order=body.get('display_order', 99),
        )

    return JsonResponse({
        'ok': True,
        'group': {
            'id': group.pk,
            'name': group.name,
            'color': group.color,
            'description': group.description,
            'display_order': group.display_order,
        },
    })


@_require_config_permission
@require_POST
def group_delete(request, group_id):
    """Delete a device group (devices become ungrouped)."""
    group = get_object_or_404(DeviceGroup, pk=group_id)
    group.delete()
    return JsonResponse({'ok': True})


@_require_config_permission
@require_POST
def device_save(request):
    """Create or update a field device."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    device_id = body.get('device_id', '').strip()
    if not device_id:
        return JsonResponse({'ok': False, 'error': 'device_id is required'}, status=400)

    name = body.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'name is required'}, status=400)

    category = body.get('category', '')
    valid_cats = [c[0] for c in FieldDevice.CATEGORY_CHOICES]
    if category not in valid_cats:
        return JsonResponse({'ok': False, 'error': f'Invalid category. Use: {valid_cats}'}, status=400)

    pk = body.get('pk')  # None for create, int for update
    group_id = body.get('group_id')
    unit = body.get('unit', '')
    min_value = body.get('min_value')
    max_value = body.get('max_value')
    display_order = body.get('display_order', 0)

    if pk:
        device = get_object_or_404(FieldDevice, pk=pk)
        device.device_id = device_id
        device.name = name
        device.category = category
        device.group_id = int(group_id) if group_id else None
        device.unit = unit
        device.min_value = float(min_value) if min_value not in (None, '') else None
        device.max_value = float(max_value) if max_value not in (None, '') else None
        device.display_order = int(display_order)
        device.save()
    else:
        if FieldDevice.objects.filter(device_id=device_id).exists():
            return JsonResponse({'ok': False, 'error': f'Device ID "{device_id}" already exists'}, status=400)
        device = FieldDevice.objects.create(
            device_id=device_id,
            name=name,
            category=category,
            group_id=int(group_id) if group_id else None,
            unit=unit,
            min_value=float(min_value) if min_value not in (None, '') else None,
            max_value=float(max_value) if max_value not in (None, '') else None,
            display_order=int(display_order),
        )

    return JsonResponse({
        'ok': True,
        'device': {
            'pk': device.pk,
            'device_id': device.device_id,
            'name': device.name,
            'category': device.category,
            'group_id': device.group_id,
            'unit': device.unit,
            'min_value': device.min_value,
            'max_value': device.max_value,
            'display_order': device.display_order,
        },
    })


@_require_config_permission
@require_POST
def device_delete(request, pk):
    """Delete a field device."""
    device = get_object_or_404(FieldDevice, pk=pk)
    device.delete()
    return JsonResponse({'ok': True})


@_require_config_permission
@require_POST
def device_toggle_active(request, pk):
    """Enable/disable a field device."""
    device = get_object_or_404(FieldDevice, pk=pk)
    device.is_active = not device.is_active
    device.save(update_fields=['is_active'])
    return JsonResponse({'ok': True, 'is_active': device.is_active})
