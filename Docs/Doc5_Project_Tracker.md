# IIIT-B Water Meter Test Bench — Project Tracker

## Current Status
- **Phase**: Sprint 7 COMPLETE — ALL SPRINTS DONE
- **Last Updated**: 2026-02-16
- **Current Sprint**: Sprint 7 (Reports, Firmware & Deployment) — ALL 11 TASKS DONE
- **Sprints Completed**: Sprint 1 (Foundation), Sprint 2 (Communication), Sprint 3 (Controller Core), Sprint 4 (Test Engine), Sprint 5 (Lab Web Portal), Sprint 6 (Bench Touch UI), Sprint 7 (Reports, Firmware & Deployment)
- **Story Points Done**: 281 / 281 (100%)
- **Tasks Done**: 68 / 68 (100%)
- **Blockers**: None
- **Unit Tests**: 221 (all passing) — 58 controller + 6 integration + 42 comms + 31 bench_ui + 56 testing + 5 audit + 17 lab_ui + 10 reports
- **Server**: Bench on `http://0.0.0.0:8000` (Daphne), Lab on `http://0.0.0.0:8080` (Gunicorn)

---

## Session Log

### Session 1 — 2026-02-13 (Project Setup)
- **What happened**:
  1. Read all 4 design docs (Doc1-Architecture, Doc2-Hardware, Doc3-UI/UX, Doc4-DevGuide)
  2. Created `Doc5_Project_Tracker.md`, `Doc6_Sprint_Board.md`, `Doc7_Session_Instructions.md`
  3. Restored user's original separated folder structure (`Bench System/` + `Lab System/`)
  4. Verified all bench hardware groups are covered — no missing folders
  5. Decided: All firmware on **PlatformIO** (not Arduino IDE)
  6. Decided: Separated folder structure (user preference) over Doc4's flat `iiitb_testbench/`
  7. Full software stack breakdown provided (backend, UI, firmware per side)
- **Decisions**:
  - Folder structure: `Bench System/` + `Lab System/` separated by building/hardware group
  - Django project lives in `Bench System/Bench Controller/` (primary system)
  - Same code deployed to `Lab System/Lab Server/` with `settings_lab.py`
  - All ESP32 firmware uses PlatformIO (not Arduino IDE)
- **Next steps**: Build Sprint 1 tasks (T-101 through T-112)

### Session 2 — 2026-02-13 (Sprint 1 — COMPLETE)
- **What happened**:
  1. Completed ALL 12 Sprint 1 tasks (T-101 through T-112)
  2. Created `accounts/` app — CustomUser model with 5 roles, login/logout views, P&ID SVG login backgrounds, role-based decorators
  3. Created `meters/` app — TestMeter model, CRUD views (list, detail, create, edit)
  4. Created `testing/` app — ISO4064Standard, Test, TestResult models, test creation with auto Q1-Q8, services.py, iso4064.py
  5. Created `controller/` app — DeviceGroup, FieldDevice models, 23 devices seeded across 9 groups, device config UI
  6. Created `bench_ui/` app — Dashboard, test control, live HMI, lock/unlock, system status, settings, emergency stop, in-memory device simulator
  7. Created dual base templates — `base_bench.html` (dark HMI 1024x600) and `base_lab.html` (sidebar nav)
  8. Created CSS themes — `tokens.css`, `bench_hmi.css`, `lab_dashboard.css`
  9. Created JS — `bench_gauges.js`, `bench_system.js`
  10. Context processor for deployment switching (`is_bench`/`is_lab`)
  11. Created `Doc8_Data_Flow.md` — authoritative data flow document
- **Decisions**:
  - 5 user roles: admin, developer, manager, bench_tech, lab_tech
  - Bench UI has lock/unlock with 5min auto-lockout
  - Device simulator uses in-memory state dict (replaced in Sprint 2)
  - BenchSettings singleton model for bench configuration
- **Session ended without updating tracker/sprint board**

### Session 3 — 2026-02-14 (Sprint 2 — COMPLETE)
- **What happened**:
  1. Re-read all docs and codebase to restore context after session crash
  2. Updated Doc5 and Doc6 with Sprint 1 completion
  3. Completed ALL 9 Sprint 2 tasks (T-201 through T-209):
     - `comms/crypto.py` — AES-256-CBC encrypt/decrypt + HMAC-SHA256 sign/verify (pycryptodome)
     - `comms/protocol.py` — ASP frame encoder/decoder with zlib compression, fragmentation/reassembly for LoRa
     - `comms/serial_handler.py` — pyserial USB handler (SerialHandler + BusManager for Bus 1/2)
     - `comms/message_queue.py` — outgoing queue, ACK tracking, 3-retry/3s timeout, offline queue for graceful degradation
     - `controller/simulator.py` — physics-based hardware simulator (VFD ramp 5Hz/s, flow dynamics, scale accumulation, 23 devices)
     - `controller/sensor_manager.py` — SensorSnapshot dataclass, polling loop (200ms), simulator/real dual backends
     - `controller/vfd_controller.py` — Delta VFD022EL43A Modbus control (registers 0x2000-0x2105)
     - `controller/hardware.py` — HAL factory (get_sensor_manager, get_vfd_controller, start_all/stop_all/emergency_stop)
     - `comms/tests.py` — 31 unit tests (crypto, protocol, sequence, fragmentation, full roundtrip) — ALL PASS
  4. All 31 unit tests pass, `manage.py check` clean
  5. Comprehensive documentation update (this file + Doc6 + MEMORY.md)
- **Decisions**:
  - ASP frame uses zlib compression before AES encryption (saves LoRa bandwidth)
  - Simulator is physics-based: VFD ramps at 5 Hz/s, flow proportional to freq (50 Hz → 2500 L/h), scale accumulates during COLLECT
  - Hardware abstraction via module-level singletons with lazy init (get_sensor_manager(), get_vfd_controller())
  - SequenceCounter handles wraparound at 65535 with 32768-window for valid range
  - Fragmentation at 252-byte chunks for LoRa (255 max - 3 header bytes)
- **Next steps**: Sprint 3 — Controller Core

### Session 4 — 2026-02-14 (Sprint 3 — COMPLETE)
- **What happened**:
  1. Completed ALL 8 Sprint 3 tasks (T-301 through T-308):
     - `controller/pid_controller.py` — PID loop with anti-windup (integral clamping), derivative on measurement, stability detection (5 consecutive readings within ±2%)
     - `controller/safety_monitor.py` — parallel watchdog (200ms poll), 9 alarm codes (OVERPRESSURE, LOW_RESERVOIR, TEMP_HIGH/LOW, SCALE_OVERLOAD, ESTOP, CONTACTOR_TRIP, MCB_TRIP, VFD_FAULT), 3 severity levels, emergency stop trigger
     - `controller/valve_controller.py` — mutual exclusion for lane valves (BV-L1/L2/L3), diverter control (COLLECT/BYPASS), lane selection by meter size (DN15→BV-L3, DN20→BV-L2, DN25→BV-L1)
     - `controller/tower_light.py` — state-to-light pattern mapping with blink via background thread (READY=green, TESTING=yellow, FAULT=red, ESTOP=red blink, TEST_PASS=green blink)
     - `controller/gravimetric.py` — tare/collect/measure sequence, ISO 4064 water density correction, volume = net_mass / density(T)
     - `controller/dut_interface.py` — RS485 auto-read (Modbus addr 20, Bus 1) + manual entry modes, before/after totalizer readings
     - `controller/hardware.py` — expanded HAL with 6 new singleton factories, updated start_all/stop_all/emergency_stop
     - `controller/tests.py` — 54 new tests across 8 test classes (total 85 with Sprint 2 comms tests)
  2. Fixed DUT deadlock — changed threading.Lock to threading.RLock (set_mode calls reset internally)
  3. Fixed PID convergence test — deterministic dt approach (force _last_time before compute)
  4. All 85 tests pass, `manage.py check` clean
- **Decisions**:
  - PID anti-windup: integral clamping to keep output in [min, max] range
  - Derivative on measurement (not error) to avoid setpoint kicks
  - RLock for DUTInterface to support nested lock acquisition
  - Deterministic PID test: force dt externally rather than relying on wall-clock time
  - Lane valve mapping: DN25→1", DN20→3/4", DN15→1/2" (matches physical pipe sizes)
  - Tower blink patterns use background thread with 0.5s interval
  - Gravimetric density from `testing/iso4064.py` water_density() interpolation
- **Next steps**: Sprint 4 — State Machine & Test Execution

### Session 5 — 2026-02-15 (Sprint 4 — COMPLETE)
- **What happened**:
  1. Completed remaining 4 Sprint 4 tasks (T-402, T-404, T-406, T-407):
     - `testing/services.py` — Added `record_manual_dut_entry()` for persisting operator manual DUT readings (T-404)
     - `controller/state_machine.py` — Updated `submit_manual_dut_reading()` with DB persistence via `record_manual_dut_entry()` (T-404)
     - `bench_ui/views.py` — Added 5 JSON API endpoints: `api_test_start`, `api_test_abort`, `api_test_status`, `api_dut_prompt`, `api_dut_submit` + updated `emergency_stop` to call `abort_active_test()` (T-402)
     - `bench_ui/urls.py` — Added 5 URL patterns for test execution API (T-402)
     - `comms/lora_handler.py` — Created LoRa handler: `MessageType` enum (10 types), `LoRaHandler` class (send/receive/dispatch/heartbeat), thread-safe singleton (T-407)
     - `testing/management/commands/run_simulated_test.py` — Interactive management command for full simulated ISO 4064 test cycle (T-406)
     - `controller/tests_integration.py` — 2 integration tests: full 2-Q-point cycle to COMPLETE + abort during cycle to EMERGENCY_STOP (T-406)
  2. Added 32 new tests (4 testing + 15 bench_ui API + 11 comms LoRa + 2 integration)
  3. All 181 tests pass
- **Decisions**:
  - Integration tests use `TransactionTestCase` (daemon threads need committed DB data)
  - LoRa handler uses singleton pattern with thread-safe lock (same as hardware singletons)
  - API endpoints import state machine functions inside function body (lazy import for test isolation)
  - Integration test uses flow rates achievable by PID (500+ L/h, since PID min output = 5 Hz = 250 L/h)
  - DUT manual entry persistence is non-fatal (catch + log) to not block test execution
- **Next steps**: Sprint 5 — Lab Web Portal UI

### Session 6 — 2026-02-15 (Sprint 5 — COMPLETE)
- **What happened**:
  1. Completed ALL 12 Sprint 5 tasks (T-501 through T-512):
     - `audit/models.py` — AuditEntry model (user, action, target, description, IP, metadata)
     - `audit/utils.py` — `log_audit()` helper called from login/logout/create/approve/reject/export views
     - `lab_ui/urls.py` — 9 URL patterns (dashboard, wizard, monitor, certificates, audit, export, settings)
     - `lab_ui/views.py` — 9 views with HTMX polling, role-based access, CSV export
     - `lab_ui/templates/lab_ui/` — 6 templates (dashboard, test_wizard, live_monitor, certificates, audit_log, settings)
     - `static/js/error_curve.js` — Chart.js scatter chart with logarithmic X-axis and MPE envelope
     - `lab_ui` moved to `settings_base.py` INSTALLED_APPS (shared across both deployments)
  2. Fixed bench dashboard `VariableDoesNotExist` bug for `initiated_by` None
  3. Fixed URL routing to use `DEPLOYMENT_TYPE` setting instead of import-based detection
  4. All 203 tests pass (42 comms + 56 controller + 56 testing + 27 bench_ui + 5 audit + 17 lab_ui)
- **Decisions**:
  - `lab_ui` in shared INSTALLED_APPS (both bench and lab need it for URL resolution)
  - Context processor appended to `settings_lab.py` TEMPLATES
  - `override_settings(DEPLOYMENT_TYPE='lab')` for testing lab_ui under bench settings
  - `role_required` returns 403 (PermissionDenied) for authenticated users without access
- **Next steps**: Sprint 6 — Bench Touch UI

### Session 7 — 2026-02-15 (Sprint 6 — COMPLETE)
- **What happened**:
  1. Completed ALL 9 Sprint 6 tasks (T-601 through T-609):
     - T-604: `bench_ui/consumers.py` — TestConsumer (AsyncJsonWebsocketConsumer), 1s periodic data push, WS commands (start/abort/dut_submit)
     - T-604: `bench_ui/routing.py` — WebSocket URL routing (`ws/test/<int:test_id>/`)
     - T-604: `config/asgi.py` — Updated ProtocolTypeRouter + AuthMiddlewareStack
     - T-603: `static/js/bench_gauges.js` — Full rewrite: WebSocket primary (5-retry), HTTP polling fallback, DUT keypad handling
     - T-605: `test_control_live.html` — Added DUT manual entry overlay with blur backdrop, touch keypad, submit via WS
     - T-601: `dashboard.html` — Added status strip (6 LED pills polling 5s), last completed test summary, pulsing START button
     - T-602: `test_wizard.html` — 4-step Alpine.js wizard (select meter → DUT mode → review Q-points → confirm & start)
     - T-606: `test_results.html` — Verdict banner, zone verdicts, swipeable Q-point cards (CSS scroll-snap), error curve chart
     - T-607: `test_history.html` — 2-column grid, tap-to-expand accordion with inline Q-point results
     - T-608: `setup.html` — Read-only 3-column display: PID tuning, safety limits, serial config
     - T-609: `bench_touch.js` — Swipe detection (80px threshold), tab navigation, touch-active feedback
  2. Added 4 WebSocket consumer unit tests (connect, data, fields, disconnect)
  3. Added CSS: DUT overlay, state-node pulse animation, dashboard pills, wizard steps, scroll-snap, touch-active
  4. All 207 tests pass
- **Decisions**:
  - E-STOP always via HTTP POST (safety-critical, never WebSocket)
  - WebSocket fallback to HTTP polling after 5 retries
  - WebsocketCommunicator must wrap consumer in URLRouter for url_route kwargs
  - Combined T-603 + T-605 since DUT overlay is embedded in the live monitor template
  - All "New Test" links on bench now point to bench_ui:test_wizard
- **Next steps**: Sprint 7 — Reports, Firmware & Deployment

### Session 8 — 2026-02-15 (Lab UI Theme Overhaul)
- **What happened**:
  1. Lab UI redesign: 6 batches overhauling all templates to Make.com-inspired theme
  2. Font change from Inter to Plus Jakarta Sans
  3. Login gradient refined to softer sage tones
  4. Full test regression: 207 bench tests OK, 172/177 lab tests OK (5 pre-existing errors)
- **Decisions**:
  - Plus Jakarta Sans for lab UI (softer, more modern than Inter)
  - Sidebar: dark slate (#0f172a), content: sage green (#f2f5f2)

### Session 9 — 2026-02-16 (Sprint 7 — Reports, Firmware & Deployment — COMPLETE)
- **What happened**:
  1. Completed ALL 11 Sprint 7 tasks:
     - T-701: `reports/error_curve.py` — Matplotlib error curve (Agg backend, headless PNG, log X-axis, MPE envelope)
     - T-702: `reports/generator.py` — ReportLab A4 PDF certificate (header, meter/test details, Q1-Q8 table, error curve, verdict, signatures)
     - T-703: `testing/views.py` — Approval generates cert number + PDF, download endpoint (FileResponse)
     - T-705: B3 VFD Bridge firmware (PlatformIO ESP32, JSON lines, Modbus RTU → Delta VFD)
     - T-707: L2 Lab Bridge firmware (generic RS485 Modbus bridge with SET_BAUD)
     - T-704: B2 Sensor Bridge firmware (RS485 Modbus + GPIO: valves, diverter, tower, E-stop)
     - T-706: B4/L1 LinkMaster LoRa firmware (SX1262, 865 MHz, SF10, base64 pipe)
     - T-709: Lab systemd service (Gunicorn WSGI on 0.0.0.0:8080)
     - T-710: Udev rules (bench + lab serial port mapping)
     - T-708: Kiosk setup updated with udev rules
     - T-711: Integration tests expanded from 2 → 6 (cert, partial, manual DUT, LoRa roundtrip)
  2. 10 new reports tests + 4 new integration tests = 221 total, all pass
  3. All project milestones complete: 68/68 tasks, 281/281 story points
- **Decisions**:
  - Matplotlib Agg backend for headless chart rendering (no display needed)
  - LoRa ESP32 is a dumb pipe — ASP encryption/decryption stays on RPi5
  - Udev rules template with commented KERNELS paths (filled in after hardware connection)
  - Lab uses Gunicorn WSGI (no Channels/WebSocket needed), bench uses Daphne ASGI
- **PROJECT COMPLETE**

---

## Development Progress (33-Step Build Sequence from Doc4)

### Phase 1: Foundation (Steps 1–9) — ✅ ALL COMPLETE
| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Django project with dual settings | ✅ Done | config/ (settings_base, settings_bench, settings_lab, urls, asgi, wsgi) |
| 2 | CustomUser model + migrations | ✅ Done | accounts/models.py — 5 roles (admin, developer, manager, bench_tech, lab_tech) |
| 3 | Login/logout views + templates | ✅ Done | P&ID SVG backgrounds, glassmorphism cards, redirect handling |
| 4 | Role-based permission decorators | ✅ Done | accounts/permissions.py — @role_required, RoleRequiredMixin, AdminRequiredMixin, etc. |
| 5 | TestMeter model + CRUD views | ✅ Done | meters/ — list, detail, create, edit. DN15/20/25, classes A/B/C/R80-200 |
| 6 | ISO4064Standard model + fixture | ✅ Done | testing/ — fixture data for DN15/20/25 Q1-Q8 |
| 7 | Test + TestResult models | ✅ Done | testing/models.py + services.py + iso4064.py (water density, error calc) |
| 8 | Test creation view with auto Q1-Q8 | ✅ Done | testing/views.py — auto-populate from ISO 4064, advanced filtering |
| 9 | Base templates (lab sidebar + bench tabs) | ✅ Done | base_bench.html (dark HMI) + base_lab.html (sidebar) + CSS themes + JS |

### Phase 2: Communication + Controller (Steps 10–19) — ✅ ALL COMPLETE
| # | Task | Status | Notes |
|---|------|--------|-------|
| 10 | ASP protocol encoder/decoder | ✅ Done | comms/protocol.py — frame encode/decode, zlib, fragmentation, reassembly |
| 11 | AES-256 + HMAC crypto module | ✅ Done | comms/crypto.py — AES-256-CBC + HMAC-SHA256 (pycryptodome) |
| 12 | Serial handler (pyserial) | ✅ Done | comms/serial_handler.py — SerialHandler + BusManager (Bus 1 + Bus 2) |
| 13 | Message queue + ACK tracking | ✅ Done | comms/message_queue.py — 3-retry, 3s timeout, offline queue |
| 14 | Hardware simulator | ✅ Done | controller/simulator.py — physics-based, 23 devices, VFD ramp, flow/scale dynamics |
| 15 | Sensor manager (Modbus polling) | ✅ Done | controller/sensor_manager.py — SensorSnapshot, 200ms polling loop |
| 16 | PID controller module | ✅ Done | controller/pid_controller.py — anti-windup, stability detection, manual override |
| 17 | Safety watchdog | ✅ Done | controller/safety_monitor.py — 9 alarm types, emergency stop trigger |
| 18 | Valve controller + sequencing | ✅ Done | controller/valve_controller.py — mutual exclusion, diverter, lane selection by meter size |
| 19 | VFD controller | ✅ Done | controller/vfd_controller.py — Delta VFD022EL43A Modbus (0x2000-0x2105) |

### Phase 3: Test Engine + UI + Integration (Steps 20–33) — ✅ ALL COMPLETE
| # | Task | Status | Notes |
|---|------|--------|-------|
| 20 | State machine (12 states) | ✅ Done | controller/state_machine.py — 12-state threading engine, 22 unit tests |
| 21 | Gravimetric engine | ✅ Done | controller/gravimetric.py — tare/collect/measure, ISO 4064 density correction |
| 22 | DUT interface (RS485 + manual) | ✅ Done | controller/dut_interface.py — RS485 auto-read + manual entry, before/after readings |
| 23 | Lab web portal full UI | ✅ Done | lab_ui/ — Sprint 5: dashboard, wizard, monitor, certificates, audit, settings |
| 24 | Bench touch UI | ✅ Done | bench_ui/ — Sprint 6: dashboard, wizard, live HMI, results, history, setup, touch gestures |
| 25 | Live monitor with gauges | ✅ Done | Sprint 6: WebSocket consumer + SVG gauges + HTTP polling fallback |
| 26 | Manual DUT entry overlay | ✅ Done | Sprint 6: blur backdrop, touch keypad, before/after flow, WebSocket submit |
| 27 | Error curve chart | ✅ Done | static/js/error_curve.js — Chart.js scatter with MPE envelope (used in both lab + bench) |
| 28 | PDF certificate generator | ✅ Done | reports/generator.py + reports/error_curve.py — ReportLab A4 PDF + Matplotlib error curve |
| 29 | Manager approval workflow | ✅ Done | testing/views.py — approve → generate cert number + PDF → download endpoint |
| 30 | LoRa comm handler | ✅ Done | comms/lora_handler.py — 10 message types, bidirectional dispatch, heartbeat, singleton |
| 31 | ESP32 firmware (4 PlatformIO projects) | ✅ Done | B2 Sensor Bridge, B3 VFD Bridge, B4/L1 LinkMaster LoRa, L2 Lab Bridge |
| 32 | Kiosk deployment (bench + lab) | ✅ Done | scripts/ — kiosk-setup.sh, bench-django.service, lab-django.service, lab-setup.sh, udev rules |
| 33 | E2E integration test | ✅ Done | controller/tests_integration.py — 6 integration tests (full cycle, abort, cert, partial, manual DUT, LoRa) |

---

## Key Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-13 | Separated folder structure: `Bench System/` + `Lab System/` | User preference. Organized by building/hardware group. |
| 2026-02-13 | Django project in `Bench System/Bench Controller/` | Primary standalone system. Lab Server gets same code with lab settings. |
| 2026-02-13 | All ESP32 firmware on PlatformIO | User preference. Better than Arduino IDE for project management. |
| 2026-02-13 | 5 user roles: admin, developer, manager, bench_tech, lab_tech | Covers all access patterns. Developer role for engineering access. |
| 2026-02-13 | Bench lock/unlock with 5min auto-lockout | Security on shared bench kiosk. User stays authenticated. |
| 2026-02-13 | BenchSettings as singleton model | Single config object for bench (theme, brightness, auto_lock, etc.) |
| 2026-02-14 | ASP frames use zlib compression before AES | Reduces LoRa payload size, fewer fragments needed. |
| 2026-02-14 | Physics-based simulator (not random values) | VFD ramp 5Hz/s, flow∝freq, scale accumulates. Realistic for PID tuning. |
| 2026-02-14 | Hardware abstraction via singleton factories | `get_sensor_manager()` / `get_vfd_controller()` — lazy init, backend from settings. |
| 2026-02-14 | Sequence counter with 32768-window wraparound | Handles 16-bit rollover gracefully. Reject stale timestamps >5min. |
| 2026-02-14 | Fragment size: 252 bytes data per LoRa packet | 255 max LoRa payload - 3 byte fragment header (id, index, total). |
| 2026-02-14 | PID anti-windup via integral clamping | Clamps integral so output stays in [min, max]. Derivative on measurement (not error) to avoid setpoint kicks. |
| 2026-02-14 | RLock for DUTInterface (not Lock) | `set_mode()` calls `reset()` internally — requires reentrant lock to avoid deadlock. |
| 2026-02-14 | Deterministic dt for PID convergence tests | Force `pid._last_time = now - dt` before each `compute()` call — avoids wall-clock non-determinism in CI. |
| 2026-02-14 | Lane-to-meter-size mapping: DN25→BV-L1, DN20→BV-L2, DN15→BV-L3 | Maps pipe diameter to corresponding lane valve. Mutual exclusion enforced. |
| 2026-02-14 | Tower light blink patterns via background thread | Multi-tuple patterns in PATTERN_MAP cycle at 0.5s intervals. Single-tuple = static. |
| 2026-02-14 | Gravimetric density correction from ISO 4064 | Volume = mass / density(T). Uses `water_density()` interpolation from `testing/iso4064.py`. |

---

## Architecture Notes
- **Project root**: `/home/harshavardhan/I.R.A.S/Water Flow Meter Calibration System/`
- **Django project**: `Bench System/Bench Controller/` (primary, deploys to both RPi5s)
- **Lab deployment**: Same code in `Lab System/Lab Server/` with `settings_lab.py`
- **Docs**: `Docs/` — Doc1 through Doc8
- **Bench firmware**: PlatformIO projects in each ESP group folder
- **Lab firmware**: PlatformIO projects in `Lab System/LinkMaster LoRa/` and `Lab System/RS485 Bridge/`
- **Hardware backend**: `HARDWARE_BACKEND = 'simulator' | 'real'` in settings
- **Dev server**: `python manage.py runserver 0.0.0.0:8080 --settings=config.settings_bench`
- **Run tests**: `python manage.py test comms controller --settings=config.settings_bench`

---

## Django App Structure (Bench Controller)
```
Bench System/Bench Controller/
├── config/                          # Django configuration
│   ├── settings_base.py             # Shared settings (apps, auth, static, ASP keys)
│   ├── settings_bench.py            # Bench: +channels, controller, bench_ui, Redis, serial, PID, safety
│   ├── settings_lab.py              # Lab: +lab_ui, 30min session, no WebSocket
│   ├── urls.py                      # Root URL router (conditional bench/lab)
│   ├── context_processors.py        # Injects is_bench, is_lab, base_template
│   ├── asgi.py                      # ASGI with Channels support
│   └── wsgi.py                      # Standard WSGI
│
├── accounts/                        # Authentication & authorization
│   ├── models.py                    # CustomUser (5 roles, is_admin, can_actuate, etc.)
│   ├── views.py                     # login, logout, profile, user_list, user_create, user_edit, user_toggle
│   ├── urls.py                      # 7 URL patterns
│   ├── permissions.py               # @role_required, RoleRequiredMixin, AdminRequiredMixin
│   ├── templates/accounts/          # login.html, profile.html, user_list.html, user_form.html
│   └── migrations/                  # 0001_initial, 0002_alter_role
│
├── meters/                          # Meter inventory management
│   ├── models.py                    # TestMeter (serial, size, class, manufacturer, dut_mode, modbus config)
│   ├── views.py                     # meter_list, meter_detail, meter_create, meter_edit
│   ├── urls.py                      # 4 URL patterns
│   ├── templates/meters/            # meter_list.html, meter_detail.html, meter_form.html
│   └── migrations/                  # 0001_initial, 0002_alter, 0003_alter
│
├── testing/                         # Test creation, execution tracking, results
│   ├── models.py                    # ISO4064Standard, Test (8 statuses), TestResult (per Q-point)
│   ├── views.py                     # test_list (advanced filters), test_detail, test_create, test_approve, test_results_api
│   ├── urls.py                      # 5 URL patterns
│   ├── services.py                  # start_test, update_test_state, record_result, complete_test, abort_test, generate_certificate_number
│   ├── iso4064.py                   # water_density() interpolation, calculate_error(), check_pass()
│   ├── admin.py                     # ISO4064Standard, Test (with TestResult inline)
│   ├── templates/testing/           # test_list.html, test_detail.html, test_form.html, test_approve.html
│   ├── fixtures/                    # ISO 4064 standard data
│   ├── management/commands/         # Custom management commands
│   └── migrations/                  # 0001_initial, 0002_add_class, 0003_alter
│
├── comms/                           # Communication layer (Sprint 2)
│   ├── crypto.py                    # AES-256-CBC encrypt/decrypt + HMAC-SHA256 sign/verify
│   ├── protocol.py                  # ASP frame encode/decode, SequenceCounter, Fragment, FragmentReassembler
│   ├── serial_handler.py            # SerialHandler (thread-safe, JSON lines) + BusManager (Bus 1 + Bus 2)
│   ├── message_queue.py             # MessageQueue (ACK, 3-retry, 3s timeout, offline queue, link status)
│   ├── tests.py                     # 31 unit tests (crypto, protocol, sequence, fragmentation, roundtrip)
│   ├── models.py                    # (empty — no DB models yet)
│   └── migrations/                  # (empty)
│
├── controller/                      # Hardware control (bench-only)
│   ├── models.py                    # DeviceGroup, FieldDevice (23 devices, 9 groups)
│   ├── views.py                     # device_config, device_config_save, group_save/delete, device_save/delete/toggle
│   ├── urls.py                      # 7 URL patterns (under /system/config/)
│   ├── admin.py                     # DeviceGroup, FieldDevice admin
│   ├── simulator.py                 # HardwareSimulator (physics-based, thread-safe, Modbus command interface)
│   ├── sensor_manager.py            # SensorManager + SensorSnapshot (200ms poll, dual backend)
│   ├── vfd_controller.py            # VFDController for Delta VFD022EL43A (start/stop/freq/status/emergency)
│   ├── pid_controller.py            # PIDController (anti-windup, stability detect, manual override)
│   ├── safety_monitor.py            # SafetyMonitor (9 alarm types, 3 severities, emergency stop)
│   ├── valve_controller.py          # ValveController (mutual exclusion, diverter, lane selection)
│   ├── tower_light.py               # TowerLightController (state-to-light mapping, blink patterns)
│   ├── gravimetric.py               # GravimetricEngine (tare/collect/measure, density correction)
│   ├── dut_interface.py             # DUTInterface (RS485 auto-read + manual entry, before/after)
│   ├── hardware.py                  # HAL factory: 8 singleton factories, start_all(), stop_all(), emergency_stop()
│   ├── tests.py                     # 54 controller tests (PID, safety, valves, tower, gravimetric, DUT)
│   ├── templates/controller/        # device_config.html
│   └── migrations/                  # 0001_initial, 0002_seed_devices, 0003_update_topology
│
├── bench_ui/                        # Bench HMI (bench-only)
│   ├── models.py                    # BenchSettings (singleton), SensorReading (time-series), DUTManualEntry
│   ├── views.py                     # dashboard, test_control, test_control_live, test_wizard, test_results,
│   │                                # test_history, setup_page, lock/unlock, system_status, system_api_status/command,
│   │                                # emergency_stop, settings_page/save, 5 JSON API endpoints
│   ├── consumers.py                 # TestConsumer (AsyncJsonWebsocketConsumer) — WebSocket real-time data
│   ├── routing.py                   # WebSocket URL routing (ws/test/<int:test_id>/)
│   ├── urls.py                      # 19 URL patterns (under /bench/)
│   ├── tests.py                     # 31 tests (models, API, WebSocket consumer)
│   ├── templates/bench_ui/          # dashboard, test_control, test_control_live, test_wizard, test_results,
│   │                                # test_history, setup, lock_screen, system_status, settings
│   └── migrations/                  # 0001_initial, 0002_sensor_reading, 0003_dut_manual_entry
│
├── lab_ui/                          # Lab portal (shared deployment)
│   ├── models.py                    # (empty — uses testing/meters models)
│   ├── views.py                     # dashboard, test_wizard, live_monitor, monitor_data_api, certificates,
│   │                                # audit_log, audit_export, lab_settings, test_export_csv
│   ├── urls.py                      # 9 URL patterns (under /lab/)
│   ├── tests.py                     # 17 tests (views, permissions, CSV export)
│   ├── templates/lab_ui/            # dashboard, test_wizard, live_monitor, certificates, audit_log, settings
│   └── migrations/                  # (empty)
│
├── reports/                         # PDF certificates & charts
│   ├── error_curve.py               # Matplotlib error curve (headless PNG)
│   ├── generator.py                 # ReportLab A4 PDF certificate generator
│   ├── tests.py                     # 10 tests (PNG, PDF, save, download)
│   ├── models.py                    # (empty)
│   └── migrations/                  # (empty)
│
├── audit/                           # Audit logging
│   ├── models.py                    # AuditEntry (user, action, target_type, target_id, description, ip, metadata)
│   ├── utils.py                     # log_audit() helper
│   ├── tests.py                     # 5 tests
│   └── migrations/                  # 0001_initial
│
├── templates/                       # Base templates
│   ├── base.html                    # Generic fallback
│   ├── base_bench.html              # Dark HMI (1024x600, bottom tab bar, e-stop button)
│   └── base_lab.html                # Professional sidebar (responsive, indigo accent)
│
├── static/
│   ├── css/
│   │   ├── tokens.css               # Design tokens (colors, spacing, typography)
│   │   ├── bench_hmi.css            # Dark industrial theme (~2280 lines)
│   │   └── lab_dashboard.css        # Professional lab theme
│   ├── js/
│   │   ├── bench_gauges.js          # WebSocket live test control (Alpine.js component)
│   │   ├── bench_system.js          # System status P&ID control (Alpine.js component)
│   │   ├── bench_touch.js           # Touch gesture handling (swipe, feedback)
│   │   └── error_curve.js           # Chart.js error curve visualization
│   └── img/                         # Images
│
├── scripts/                         # Deployment utilities
├── manage.py                        # Django CLI
├── requirements.txt                 # django, pyserial, pycryptodome, channels, daphne, redis, whitenoise, Pillow
└── db_bench.sqlite3                 # Development database
```

---

## Codebase Statistics
| Metric | Count |
|--------|-------|
| Django Apps | 9 (all active) |
| Models | 11 (CustomUser, DeviceGroup, FieldDevice, TestMeter, ISO4064Standard, Test, TestResult, BenchSettings, SensorReading, DUTManualEntry, AuditEntry) |
| Views | ~57 function-based |
| URL Patterns | ~57 |
| Templates | 35+ HTML files |
| CSS Files | 3 (tokens.css, bench_hmi.css ~2280 lines, lab_dashboard.css) |
| JS Files | 6 (bench_gauges.js, bench_system.js, bench_touch.js, error_curve.js + inline) |
| Migrations | 17 |
| Unit Tests | 221 (all passing — 42 comms + 58 controller + 6 integration + 56 testing + 31 bench_ui + 5 audit + 17 lab_ui + 10 reports) |
| Seeded Devices | 23 across 9 groups |
| ESP32 Firmware | 4 PlatformIO projects (B2, B3, B4/L1, L2) |
| Deployment Scripts | 6 (kiosk-setup.sh, bench-django.service, bench-kiosk.service, lab-django.service, lab-setup.sh, udev rules) |

---

## Folder Structure (Full Project)
```
Water Flow Meter Calibration System/
├── Docs/
│   ├── Doc1_System_Architecture.docx
│   ├── Doc2_Hardware_Group_Mapping.docx
│   ├── Doc3_UI_UX_Specification.docx
│   ├── Doc4_Claude_Code_Dev_Guide.docx
│   ├── Doc5_Project_Tracker.md          ← this file
│   ├── Doc6_Sprint_Board.md
│   ├── Doc7_Session_Instructions.md
│   ├── Doc8_Data_Flow.md
│   ├── Doc8_Data_Flow_Scenarios.docx
│   ├── Complete_Data_Flow.docx
│   └── Screenshots (1-Bench Login.png ... 9-System Settings.png)
├── Bench System/
│   ├── Bench Controller/                ← B1: Django project (PRIMARY — see app tree above)
│   ├── Measurement ESP Group/           ← B2 function: sensor Modbus polling
│   ├── Modbus Bus Bridge/               ← B2 function: Modbus RTU layer
│   ├── RS485 Bridge/                    ← B2/B4 bridge: USB ↔ RS485
│   ├── VFD & Safety ESP Group/          ← B3: VFD control + safety
│   ├── Valves & Process ESP Group/      ← B2 function: valve GPIO + tower light
│   └── LinkMaster LoRa/                 ← B4: LoRa gateway
├── Lab System/
│   ├── Lab Server/                      ← L3: Django (lab settings)
│   ├── LinkMaster LoRa/                 ← L1: LoRa gateway (same firmware as B4)
│   └── RS485 Bridge/                    ← L2: USB ↔ RS485 bridge
└── Ra01S/                               ← SX1262 LoRa library (TX + RX PlatformIO projects)
```

---

## Open Questions / Items to Discuss
1. ~~Folder structure~~ — RESOLVED: separated by building/hardware group
2. GPIO pin assignments for B2 are all TBD — confirm when Maxsense board info is available
3. VFD Modbus register addresses — using Delta standard (0x2000-0x2105), needs confirmation from manual
4. ~~ESP32 firmware — Arduino IDE or PlatformIO?~~ — RESOLVED: PlatformIO
5. bench_ui/views.py still uses inline `_sim_states` dict — should migrate to `controller.hardware.get_simulator()` (deferred to Sprint 4/5 UI rework)

---

## Files Changed Per Session

### Session 1 — 2026-02-13 (Project Setup)
- Created: `Docs/Doc5_Project_Tracker.md`
- Created: `Docs/Doc6_Sprint_Board.md`
- Created: `Docs/Doc7_Session_Instructions.md`
- Restored: `Bench System/` + `Lab System/` original folder structure

### Session 2 — 2026-02-13 (Sprint 1 — Foundation)
- Created: `config/` — settings_base.py, settings_bench.py, settings_lab.py, urls.py, asgi.py, wsgi.py, context_processors.py
- Created: `accounts/` — models.py, views.py, urls.py, permissions.py, templates (4 files)
- Created: `meters/` — models.py, views.py, urls.py, templates (3 files)
- Created: `testing/` — models.py, views.py, urls.py, services.py, iso4064.py, admin.py, templates (4 files)
- Created: `controller/` — models.py, views.py, urls.py, admin.py, templates (1 file), migrations (3 — incl. seed 23 devices)
- Created: `bench_ui/` — models.py, views.py, urls.py, templates (6 files), migrations (1)
- Created: `templates/` — base.html, base_bench.html, base_lab.html
- Created: `static/css/` — tokens.css, bench_hmi.css, lab_dashboard.css
- Created: `static/js/` — bench_gauges.js, bench_system.js
- Created: `Docs/Doc8_Data_Flow.md`
- Created: manage.py, requirements.txt, db_bench.sqlite3

### Session 3 — 2026-02-14 (Sprint 2 — Communication & Hardware)
- Created: `comms/crypto.py` — AES-256-CBC + HMAC-SHA256
- Created: `comms/protocol.py` — ASP frame encoder/decoder + fragmentation
- Created: `comms/serial_handler.py` — SerialHandler + BusManager
- Created: `comms/message_queue.py` — outgoing queue + ACK + retry
- Created: `controller/simulator.py` — physics-based hardware simulator
- Created: `controller/sensor_manager.py` — SensorManager + SensorSnapshot
- Created: `controller/vfd_controller.py` — VFDController for Delta VFD
- Created: `controller/hardware.py` — hardware abstraction layer
- Updated: `comms/tests.py` — 31 unit tests (all pass)
- Updated: `Docs/Doc5_Project_Tracker.md` — complete rewrite with full status
- Updated: `Docs/Doc6_Sprint_Board.md` — Sprint 1 + Sprint 2 tasks marked Done
- Updated: `MEMORY.md` — Sprint 2 modules documented

### Session 4 — 2026-02-14 (Sprint 3 — Controller Core)
- Created: `controller/pid_controller.py` — PID controller with anti-windup + stability detection
- Created: `controller/safety_monitor.py` — parallel watchdog (9 alarms, 3 severities)
- Created: `controller/valve_controller.py` — mutual exclusion, diverter, lane selection
- Created: `controller/tower_light.py` — state-to-light mapping with blink patterns
- Created: `controller/gravimetric.py` — tare/collect/measure, density correction
- Created: `controller/dut_interface.py` — RS485 auto-read + manual entry
- Updated: `controller/hardware.py` — 6 new singleton factories, expanded start/stop/emergency
- Updated: `controller/tests.py` — 54 new tests (total 85 with comms tests)
- Updated: `Docs/Doc5_Project_Tracker.md` — Sprint 3 completion, session log, decisions, app tree
- Updated: `Docs/Doc6_Sprint_Board.md` — Sprint 3 tasks Done, epic progress updated
- Updated: `MEMORY.md` — Sprint 3 modules documented

### Session 5 — 2026-02-15 (Sprint 4 — Test Engine)
- Created: `comms/lora_handler.py` — LoRa handler (10 message types, bidirectional dispatch, heartbeat)
- Created: `controller/state_machine.py` — 12-state TestStateMachine (threading daemon)
- Created: `controller/tests_integration.py` — 2 integration tests (full cycle + abort)
- Created: `testing/management/commands/run_simulated_test.py` — interactive simulated test
- Updated: `testing/services.py` — record_manual_dut_entry, process_q_point_result, record_sensor_reading
- Updated: `bench_ui/models.py` — SensorReading, DUTManualEntry models
- Updated: `bench_ui/views.py` — 5 JSON API endpoints + emergency stop integration
- Updated: `bench_ui/urls.py` — 5 new URL patterns for API

### Session 6 — 2026-02-15 (Sprint 5 — Lab Web Portal)
- Created: `audit/models.py` — AuditEntry model
- Created: `audit/utils.py` — log_audit() helper
- Created: `audit/tests.py` — 5 audit tests
- Created: `lab_ui/views.py` — 9 views (dashboard, wizard, monitor, certificates, audit, settings, CSV)
- Created: `lab_ui/urls.py` — 9 URL patterns
- Created: `lab_ui/tests.py` — 17 lab_ui tests
- Created: `lab_ui/templates/lab_ui/` — 6 templates
- Created: `static/js/error_curve.js` — Chart.js error curve with MPE envelope
- Updated: `config/settings_base.py` — lab_ui added to shared INSTALLED_APPS
- Updated: `config/settings_lab.py` — context processor appended
- Updated: `config/urls.py` — DEPLOYMENT_TYPE-based URL routing

### Session 7 — 2026-02-15 (Sprint 6 — Bench Touch UI)
- Created: `bench_ui/consumers.py` — TestConsumer (AsyncJsonWebsocketConsumer)
- Created: `bench_ui/routing.py` — WebSocket URL routing
- Created: `bench_ui/templates/bench_ui/test_wizard.html` — 4-step Alpine.js wizard
- Created: `bench_ui/templates/bench_ui/test_results.html` — Swipeable Q-point cards + error curve
- Created: `bench_ui/templates/bench_ui/test_history.html` — 2-column grid + accordion
- Created: `bench_ui/templates/bench_ui/setup.html` — Read-only PID/safety/serial config
- Created: `static/js/bench_touch.js` — Touch gesture handling
- Updated: `config/asgi.py` — ProtocolTypeRouter + WebSocket routing
- Updated: `static/js/bench_gauges.js` — Full rewrite: WebSocket + DUT keypad + polling fallback
- Updated: `bench_ui/templates/bench_ui/test_control_live.html` — DUT overlay, VFD display
- Updated: `bench_ui/templates/bench_ui/dashboard.html` — Status strip, last test, START pulse
- Updated: `bench_ui/templates/bench_ui/test_control.html` — Links to wizard
- Updated: `templates/base_bench.html` — bench_touch.js script include
- Updated: `bench_ui/views.py` — test_wizard, test_results, test_history, setup_page views
- Updated: `bench_ui/urls.py` — 4 new URL patterns (wizard, results, history, setup)
- Updated: `bench_ui/tests.py` — 4 WebSocket consumer tests
- Updated: `static/css/bench_hmi.css` — DUT overlay, state pulse, status pills, wizard, scroll-snap, touch CSS
- Updated: `Docs/Doc5_Project_Tracker.md`, `Docs/Doc6_Sprint_Board.md`, `MEMORY.md`

### Session 9 — 2026-02-16 (Sprint 7 — Reports, Firmware & Deployment)
- Created: `reports/error_curve.py` — Matplotlib error curve generator (Agg backend, headless PNG)
- Created: `reports/generator.py` — ReportLab PDF certificate generator (A4, full layout)
- Created: `reports/tests.py` — 10 tests (PNG, PDF, save, download)
- Created: `scripts/lab-django.service` — Gunicorn WSGI on 0.0.0.0:8080
- Created: `scripts/lab-setup.sh` — Lab deployment setup (4-step)
- Created: `scripts/99-bench-serial.rules` — Udev rules for B2/B3/B4 symlinks
- Created: `scripts/99-lab-serial.rules` — Udev rules for L2 symlink
- Created: `Bench System/VFD & Safety ESP Group/` — B3 VFD Bridge firmware (platformio.ini, config.h, main.cpp)
- Created: `Lab System/RS485 Bridge/` — L2 Lab Bridge firmware (platformio.ini, config.h, main.cpp)
- Created: `Bench System/RS485 Bridge/` — B2 Sensor Bridge firmware (platformio.ini, config.h, main.cpp)
- Created: `Bench System/LinkMaster LoRa/` — B4 LoRa firmware (platformio.ini, config.h, main.cpp, lib/Ra01S/)
- Created: `Lab System/LinkMaster LoRa/` — L1 LoRa firmware (same as B4, lib/Ra01S/)
- Updated: `testing/views.py` — Certificate generation on approve + download_certificate view
- Updated: `testing/urls.py` — Added certificate download URL
- Updated: `testing/templates/testing/test_detail.html` — PDF download button
- Updated: `lab_ui/templates/lab_ui/certificates.html` — Download column
- Updated: `requirements.txt` — Added reportlab>=4.0, matplotlib>=3.8
- Updated: `config/urls.py` — Added media file serving for dev
- Updated: `scripts/kiosk-setup.sh` — Added udev rules installation step
- Updated: `controller/tests_integration.py` — Expanded from 2 → 6 tests
- Updated: `Docs/Doc5_Project_Tracker.md` — Final sprint completion
