/**
 * System Diagnostics — Alpine.js component
 * SCADA P&ID view with 2-second polling.
 */
function systemStatus() {
    return {
        groups: [],
        dev: {},            // flat device lookup: { 'BV1': {...}, 'PT-01': {...} }
        loraHealth: {},     // LoRa handler health from get_status()
        testActive: false,
        canActuate: false,
        pollTimer: null,
        _loaded: false,

        // Confirm dialog state
        confirmOpen: false,
        confirmMsg: '',
        pendingDeviceId: '',
        pendingAction: '',

        // LoRa message history
        loraHistoryOpen: false,
        loraHistoryShowHB: false,
        loraHistory: [],

        init() {
            this.canActuate = document.body.dataset.canActuate === 'true';
            this.fetchStatus();
            this.pollTimer = setInterval(() => this.fetchStatus(), 2000);
        },

        destroy() {
            if (this.pollTimer) clearInterval(this.pollTimer);
        },

        async fetchStatus() {
            try {
                const resp = await fetch('/bench/system/api/status/', {
                    credentials: 'same-origin',
                });
                if (!resp.ok) {
                    console.warn('[P&ID] API status:', resp.status, resp.statusText);
                    return;
                }
                const data = await resp.json();
                this.groups = data.groups;
                this.testActive = data.test_active;
                this.loraHealth = data.lora_health || {};

                // Build flat device lookup
                const map = {};
                let count = 0;
                data.groups.forEach(g => {
                    g.devices.forEach(d => { map[d.device_id] = d; count++; });
                });
                this.dev = map;

                // Debug: log once on first successful load
                if (!this._loaded) {
                    this._loaded = true;
                    console.log('[P&ID] Loaded', count, 'devices:', Object.keys(map).join(', '));
                }
            } catch (e) {
                console.warn('[P&ID] Poll failed:', e);
            }
        },

        // --- P&ID Helpers ---

        /** Shorthand device accessor */
        d(id) {
            return this.dev[id] || null;
        },

        /** Format a device's value with specified decimals */
        fv(id, decimals) {
            const device = this.dev[id];
            if (!device || device.value === null || device.value === undefined) return '--';
            return Number(device.value).toFixed(decimals !== undefined ? decimals : 1);
        },

        /** CSS class for valve state */
        valveClass(id) {
            const v = this.dev[id];
            if (!v) return '';
            return 'pid-valve--' + (v.state || 'closed');
        },

        /** Is the pump currently running? */
        pumpRunning() {
            const p = this.dev['P-01'];
            return p && p.state === 'running';
        },

        /**
         * Tank water Y position (group-local coords).
         * Tank rect: x=-45 y=0 w=90 h=135. Interior: y=2 to y=133, usable=131px.
         */
        tankWaterY() {
            const lvl = this.dev['RES-LVL'];
            const pct = lvl ? Math.max(0, Math.min(100, lvl.value)) / 100 : 0;
            return 2 + 131 * (1 - pct);
        },

        /** Tank water height (group-local) */
        tankWaterH() {
            const lvl = this.dev['RES-LVL'];
            const pct = lvl ? Math.max(0, Math.min(100, lvl.value)) / 100 : 0;
            return 131 * pct;
        },

        // --- Display Helpers ---

        formatValue(val) {
            if (val === null || val === undefined) return '--';
            return Number(val).toFixed(1);
        },

        barPercent(dev) {
            if (!dev || dev.min_value === null || dev.max_value === null) return 0;
            const range = dev.max_value - dev.min_value;
            if (range <= 0) return 0;
            return Math.max(0, Math.min(100, ((dev.value - dev.min_value) / range) * 100));
        },

        barColor(dev) {
            const pct = this.barPercent(dev);
            if (pct > 90 || pct < 10) return 'var(--bench-danger)';
            if (pct > 80 || pct < 20) return 'var(--bench-warning)';
            return 'var(--bench-accent)';
        },

        /** Format LoRa heartbeat age as human-readable text */
        loraHeartbeatText() {
            const s = this.loraHealth.last_heartbeat_ago_s;
            if (s === null || s === undefined) return '--';
            const secs = Math.round(s);
            if (secs < 60) return secs + 's ago';
            return Math.floor(secs / 60) + 'm ago';
        },

        /** LoRa comm LED state for P&ID sidebar */
        loraCommState() {
            const st = this.loraHealth.state;
            if (st === 'online') return 'online';
            if (st === 'degraded') return 'degraded';
            if (st === 'offline') return 'offline';
            return 'offline';
        },

        // --- LoRa History ---

        async fetchLoRaHistory() {
            try {
                const hb = this.loraHistoryShowHB ? '1' : '0';
                const resp = await fetch('/bench/system/api/lora-history/?limit=100&heartbeats=' + hb, {
                    credentials: 'same-origin',
                });
                if (!resp.ok) return;
                const data = await resp.json();
                this.loraHistory = data.messages || [];
            } catch (e) {
                console.warn('[LoRa History] Fetch failed:', e);
            }
        },

        formatMsgTime(ts) {
            if (!ts) return '--';
            var d = new Date(ts * 1000);
            return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        },

        // --- Command Helpers ---

        confirmCommand(deviceId, action, deviceName) {
            if (this.testActive || !this.canActuate) return;
            this.pendingDeviceId = deviceId;
            this.pendingAction = action;
            this.confirmMsg = `Toggle ${deviceName} (${deviceId})?`;
            this.confirmOpen = true;
        },

        async executeConfirmed() {
            this.confirmOpen = false;
            await this.sendCommand(this.pendingDeviceId, this.pendingAction);
        },

        async sendCommand(deviceId, action, extra = {}) {
            if (this.testActive) return;
            try {
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
                    || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

                const resp = await fetch('/bench/system/api/command/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                    },
                    body: JSON.stringify({ device_id: deviceId, action, ...extra }),
                });
                const data = await resp.json();
                if (!data.ok) {
                    console.error('Command failed:', data.error);
                    // Show interlock error to user
                    if (data.error) {
                        this.confirmMsg = data.error;
                        this.confirmOpen = true;
                        this.pendingDeviceId = '';
                        this.pendingAction = '';
                    }
                }
                // Immediately refresh state
                await this.fetchStatus();
            } catch (e) {
                console.error('Command error:', e);
            }
        },
    };
}
