"""
WebSocket consumer for real-time bench test data.

Pushes gauge readings, state machine status, Q-point results,
and DUT manual entry prompts to the live monitor UI at ~1Hz.
Accepts commands: start, abort, dut_submit.
"""

import asyncio
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class TestConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for a single test's live data feed."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_id = None
        self.send_task = None

    async def connect(self):
        self.test_id = self.scope['url_route']['kwargs']['test_id']
        self.group_name = f'test_{self.test_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        # Start periodic data push
        self.send_task = asyncio.ensure_future(self._periodic_send())

    async def disconnect(self, close_code):
        if self.send_task:
            self.send_task.cancel()
            self.send_task = None
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name,
            )

    async def receive_json(self, content, **kwargs):
        """Handle commands from the client."""
        command = content.get('command')

        if command == 'start':
            result = await self._start_test()
            await self.send_json(result)

        elif command == 'abort':
            result = await self._abort_test(content.get('reason', ''))
            await self.send_json(result)

        elif command == 'dut_submit':
            result = await self._submit_dut_reading(
                reading_type=content.get('reading_type', ''),
                value=content.get('value'),
            )
            await self.send_json(result)

    # ------------------------------------------------------------------
    #  Periodic data push
    # ------------------------------------------------------------------

    async def _periodic_send(self):
        """Push test data every 1 second."""
        try:
            while True:
                data = await self._get_test_data()
                await self.send_json(data)
                # Stop if test is finished
                if data.get('status') in ('completed', 'failed', 'aborted'):
                    await asyncio.sleep(1)
                    # Send one final update then stop
                    data = await self._get_test_data()
                    await self.send_json({**data, 'type': 'test_complete'})
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception('Error in periodic send for test %s', self.test_id)

    @database_sync_to_async
    def _get_test_data(self):
        """Build the JSON payload for the client."""
        from testing.models import Test
        from bench_ui.models import SensorReading

        try:
            test = Test.objects.select_related('meter').get(pk=self.test_id)
        except Test.DoesNotExist:
            return {'type': 'error', 'message': 'Test not found'}

        # Latest sensor reading
        sensor = SensorReading.objects.filter(
            test_id=self.test_id,
        ).order_by('-timestamp').first()

        # Q-point results
        results = []
        for r in test.results.all().order_by('q_point'):
            results.append({
                'q_point': r.q_point,
                'target_flow_lph': r.target_flow_lph,
                'ref_volume': r.ref_volume_l,
                'dut_volume': r.dut_volume_l,
                'error_pct': r.error_pct,
                'mpe_pct': r.mpe_pct,
                'passed': r.passed,
            })

        # State machine info
        sm_state = test.current_state or ''
        sm_q_point = test.current_q_point or ''

        # Check for active state machine (more accurate than DB fields)
        try:
            from controller.state_machine import get_active_machine
            sm = get_active_machine()
            if sm and sm.test_id == self.test_id:
                sm_state = sm.state.value
                sm_q_point = sm.current_q_point or sm_q_point
        except Exception:
            pass

        # DUT manual entry prompt
        dut_prompt = {'pending': False}
        try:
            from controller.state_machine import get_active_machine
            from controller.dut_interface import DUTState, DUTMode
            sm = get_active_machine()
            if sm and sm.test_id == self.test_id:
                if hasattr(sm, '_dut') and sm._dut is not None:
                    if sm._dut.mode == DUTMode.MANUAL and sm._dut.state in (
                        DUTState.WAITING_BEFORE, DUTState.WAITING_AFTER,
                    ):
                        dut_prompt = {
                            'pending': True,
                            'q_point': sm_q_point,
                            'reading_type': (
                                'before' if sm._dut.state == DUTState.WAITING_BEFORE
                                else 'after'
                            ),
                        }
        except Exception:
            pass

        data = {
            'type': 'test_data',
            'test_id': self.test_id,
            'status': test.status,
            'overall_pass': test.overall_pass,
            'current_state': sm_state,
            'current_q_point': sm_q_point,
            # Sensor values
            'flow_rate': sensor.flow_rate_lph if sensor else 0,
            'pressure': sensor.pressure_upstream_bar if sensor else 0,
            'temperature': sensor.water_temp_c if sensor else 0,
            'weight': sensor.weight_kg if sensor else 0,
            'vfd_freq': sensor.vfd_freq_hz if sensor else 0,
            # Results
            'results': results,
            # DUT prompt
            'dut_prompt': dut_prompt,
        }
        return data

    # ------------------------------------------------------------------
    #  Command handlers
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _start_test(self):
        """Start the test via state machine."""
        from controller.state_machine import start_test_machine, get_active_machine
        from testing.models import Test

        active = get_active_machine()
        if active is not None:
            return {
                'type': 'command_result',
                'command': 'start',
                'ok': False,
                'error': f'Test #{active.test_id} is already running',
            }

        try:
            test = Test.objects.get(pk=self.test_id)
        except Test.DoesNotExist:
            return {
                'type': 'command_result',
                'command': 'start',
                'ok': False,
                'error': 'Test not found',
            }

        if test.status not in ('pending', 'queued', 'acknowledged'):
            return {
                'type': 'command_result',
                'command': 'start',
                'ok': False,
                'error': f'Test cannot be started (status={test.status})',
            }

        try:
            sm = start_test_machine(self.test_id)
            return {
                'type': 'command_result',
                'command': 'start',
                'ok': True,
                'state': sm.state.value,
            }
        except RuntimeError as e:
            return {
                'type': 'command_result',
                'command': 'start',
                'ok': False,
                'error': str(e),
            }

    @database_sync_to_async
    def _abort_test(self, reason):
        """Abort the active test."""
        from controller.state_machine import abort_active_test
        aborted = abort_active_test(reason or 'Aborted via WebSocket')
        return {
            'type': 'command_result',
            'command': 'abort',
            'ok': aborted,
            'error': '' if aborted else 'No active test to abort',
        }

    @database_sync_to_async
    def _submit_dut_reading(self, reading_type, value):
        """Submit a manual DUT reading."""
        from controller.state_machine import get_active_machine

        sm = get_active_machine()
        if sm is None or sm.test_id != self.test_id:
            return {
                'type': 'command_result',
                'command': 'dut_submit',
                'ok': False,
                'error': 'No active test',
            }

        if reading_type not in ('before', 'after'):
            return {
                'type': 'command_result',
                'command': 'dut_submit',
                'ok': False,
                'error': 'reading_type must be before or after',
            }

        if value is None or not isinstance(value, (int, float)):
            return {
                'type': 'command_result',
                'command': 'dut_submit',
                'ok': False,
                'error': 'value must be a number',
            }

        # Get user from scope if available
        user = self.scope.get('user')
        ok = sm.submit_manual_dut_reading(
            reading_type=reading_type,
            value=float(value),
            entered_by=user if user and user.is_authenticated else None,
        )
        return {
            'type': 'command_result',
            'command': 'dut_submit',
            'ok': ok,
            'error': '' if ok else 'Reading rejected',
        }
