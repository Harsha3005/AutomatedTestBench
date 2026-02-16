/**
 * Bench HMI - Test Control Alpine.js Component
 * Real-time test monitoring via WebSocket with HTTP polling fallback.
 */
function testControl(testId) {
    return {
        testId: testId,

        // Gauge values
        flowRate: 0,
        pressure: 0,
        temperature: 0,
        weight: 0,
        vfdFreq: 0,

        // Test state
        testStatus: 'pending',
        currentState: '',
        currentQPoint: '',
        overallPass: null,

        // Q-point results (keyed by q_point name)
        qResults: {},

        // State machine states
        states: ['PRE_CHECK', 'LINE_SELECT', 'PUMP_START', 'STABILIZE', 'TARE', 'MEASURE', 'CALCULATE', 'DRAIN', 'COMPLETE'],
        completedStates: [],

        // WebSocket
        ws: null,
        wsRetries: 0,
        wsMaxRetries: 5,

        // Polling fallback
        pollInterval: null,
        usePolling: false,

        // DUT manual entry
        dutPrompt: { pending: false, reading_type: '', q_point: '' },
        dutValue: '',

        /**
         * Calculate SVG gauge arc offset.
         * 270-degree arc, circumference = 2 * PI * 52 ~ 326.7
         * We use 245 (3/4 of circumference) for 270-degree range.
         */
        gaugeArc(value, max) {
            const pct = Math.min(Math.max(value / max, 0), 1);
            return 245 * (1 - pct);
        },

        /**
         * Initialize — try WebSocket first, fall back to polling.
         */
        startPolling() {
            this.initWebSocket();
        },

        /**
         * Connect via WebSocket.
         */
        initWebSocket() {
            if (this.usePolling) return;
            try {
                const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
                this.ws = new WebSocket(
                    `${wsProto}://${location.host}/ws/test/${this.testId}/`
                );

                this.ws.onopen = () => {
                    this.wsRetries = 0;
                    console.log('[WS] Connected to test', this.testId);
                };

                this.ws.onmessage = (e) => {
                    try {
                        this.handleMessage(JSON.parse(e.data));
                    } catch (err) {
                        console.warn('[WS] Parse error:', err);
                    }
                };

                this.ws.onclose = (e) => {
                    console.log('[WS] Disconnected:', e.code);
                    this.ws = null;

                    // Don't reconnect if test is finished
                    if (['completed', 'failed', 'aborted'].includes(this.testStatus)) {
                        return;
                    }

                    this.wsRetries++;
                    if (this.wsRetries <= this.wsMaxRetries) {
                        setTimeout(() => this.initWebSocket(), 2000);
                    } else {
                        console.warn('[WS] Max retries reached, falling back to polling');
                        this.usePolling = true;
                        this._startPollingFallback();
                    }
                };

                this.ws.onerror = (e) => {
                    console.warn('[WS] Error:', e);
                };
            } catch (err) {
                console.warn('[WS] Failed to create WebSocket:', err);
                this.usePolling = true;
                this._startPollingFallback();
            }
        },

        /**
         * Handle incoming WebSocket message.
         */
        handleMessage(data) {
            if (data.type === 'error') {
                console.error('[WS] Server error:', data.message);
                return;
            }

            if (data.type === 'command_result') {
                if (!data.ok) {
                    console.error('[WS] Command failed:', data.error);
                }
                return;
            }

            // Update gauge values
            this.flowRate = data.flow_rate ?? this.flowRate;
            this.pressure = data.pressure ?? this.pressure;
            this.temperature = data.temperature ?? this.temperature;
            this.weight = data.weight ?? this.weight;
            this.vfdFreq = data.vfd_freq ?? this.vfdFreq;

            // Update test state
            this.testStatus = data.status || this.testStatus;
            this.currentQPoint = data.current_q_point || '';
            this.overallPass = data.overall_pass;

            // Update state machine position
            if (data.current_state) {
                this.currentState = data.current_state;
                this._updateCompletedStates(data.current_state);
            }

            // Update Q-point results
            if (data.results) {
                data.results.forEach(r => {
                    this.qResults[r.q_point] = {
                        ref_volume: r.ref_volume,
                        dut_volume: r.dut_volume,
                        error_pct: r.error_pct,
                        passed: r.passed,
                    };
                });
            }

            // DUT manual entry prompt
            if (data.dut_prompt) {
                this.dutPrompt = data.dut_prompt;
                if (data.dut_prompt.pending) {
                    this.dutValue = '';
                }
            }

            // Test complete — close WebSocket
            if (data.type === 'test_complete') {
                if (this.ws) {
                    this.ws.close();
                    this.ws = null;
                }
            }
        },

        /**
         * Track which states have been completed.
         */
        _updateCompletedStates(currentState) {
            const idx = this.states.indexOf(currentState);
            if (idx > 0) {
                this.completedStates = this.states.slice(0, idx);
            }
        },

        // --- HTTP Polling Fallback ---

        _startPollingFallback() {
            this.fetchData();
            this.pollInterval = setInterval(() => this.fetchData(), 2000);
        },

        async fetchData() {
            try {
                const resp = await fetch(`/tests/${this.testId}/status/`);
                if (!resp.ok) return;
                const data = await resp.json();

                this.testStatus = data.status || this.testStatus;
                this.currentQPoint = data.current_q_point || '';
                this.currentState = data.current_state || '';
                this.overallPass = data.overall_pass;

                if (data.results) {
                    data.results.forEach(r => {
                        this.qResults[r.q_point] = {
                            ref_volume: r.ref_volume_l,
                            dut_volume: r.dut_volume_l,
                            error_pct: r.error_pct,
                            passed: r.passed,
                        };
                    });
                }

                if (['completed', 'failed', 'aborted'].includes(this.testStatus)) {
                    clearInterval(this.pollInterval);
                }
            } catch (e) {
                console.warn('[Poll] Failed:', e);
            }
        },

        // --- CSRF Token ---

        getCsrf() {
            const match = document.cookie.match(/csrftoken=([^;]+)/);
            return match ? match[1] : '';
        },

        // --- Commands ---

        /**
         * Emergency stop — always via HTTP POST (safety-critical).
         */
        async estop() {
            if (!confirm('EMERGENCY STOP — This will abort the running test and stop all pumps. Continue?')) return;
            const form = document.getElementById('estop-form');
            if (form) {
                form.submit();
            } else {
                const resp = await fetch('/bench/emergency-stop/', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': this.getCsrf() },
                });
                if (resp.ok) window.location.href = '/bench/';
            }
        },

        /**
         * Start test via WebSocket or HTTP.
         */
        async startTest() {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ command: 'start' }));
            } else {
                const resp = await fetch(`/bench/api/test/start/${this.testId}/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': this.getCsrf() },
                });
                const data = await resp.json();
                if (!data.ok) {
                    alert(data.error || 'Failed to start test');
                }
            }
        },

        /**
         * Abort test via WebSocket or HTTP.
         */
        async abortTest() {
            if (!confirm('Abort this test? This cannot be undone.')) return;
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({
                    command: 'abort',
                    reason: 'Operator abort via bench UI',
                }));
            } else {
                const resp = await fetch('/bench/api/test/abort/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrf(),
                    },
                    body: JSON.stringify({ reason: 'Operator abort via bench UI' }),
                });
                const data = await resp.json();
                if (!data.ok) {
                    alert(data.error || 'Failed to abort test');
                }
            }
        },

        // --- DUT Manual Entry ---

        dutKeyPress(key) {
            if (key === '\u232B') {
                // Backspace
                this.dutValue = this.dutValue.slice(0, -1);
            } else if (key === '.') {
                // Only one decimal point
                if (!this.dutValue.includes('.')) {
                    this.dutValue += '.';
                }
            } else {
                // Limit to 10 digits
                if (this.dutValue.replace('.', '').length < 10) {
                    this.dutValue += key;
                }
            }
        },

        dutSubmit() {
            const value = parseFloat(this.dutValue);
            if (isNaN(value)) return;

            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({
                    command: 'dut_submit',
                    reading_type: this.dutPrompt.reading_type,
                    value: value,
                }));
            } else {
                fetch('/bench/api/test/dut-submit/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrf(),
                    },
                    body: JSON.stringify({
                        reading_type: this.dutPrompt.reading_type,
                        value: value,
                    }),
                });
            }

            this.dutValue = '';
            this.dutPrompt = { pending: false, reading_type: '', q_point: '' };
        },
    };
}
