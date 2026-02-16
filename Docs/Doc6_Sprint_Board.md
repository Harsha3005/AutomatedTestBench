# IIIT-B Water Meter Test Bench — Sprint Board & Project Management

---

## EPICS

| Epic ID | Epic Name | Description |
|---------|-----------|-------------|
| EP-1 | Foundation & Auth | Django project setup, user management, role-based access |
| EP-2 | Meter & Test Data | Meter registry, ISO 4064 standards, test/result models |
| EP-3 | Communication Layer | ACMIS protocol, encryption, serial handling, LoRa |
| EP-4 | Hardware Controller | Sensor polling, PID, VFD, valves, safety, simulator |
| EP-5 | Test Engine | State machine, gravimetric engine, DUT interface |
| EP-6 | Lab Web Portal | Full 11-page desktop web UI with HTMX |
| EP-7 | Bench Touch UI | 7-inch kiosk UI with WebSocket gauges |
| EP-8 | Reports & Certificates | PDF generation, error curves, approval workflow |
| EP-9 | ESP32 Firmware | All 4 firmware variants (B2, B3, L1/B4, L2) |
| EP-10 | Deployment & Integration | Kiosk setup, systemd, udev, E2E testing |

---

## USER STORIES

### EP-1: Foundation & Auth
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-101 | As a **developer**, I want the Django project to run with separate lab and bench settings, so that one codebase serves both sides. | P0-Critical | 3 |
| US-102 | As an **admin**, I want to create user accounts with roles (Admin/Manager/Lab Tech/Bench Tech), so that access is controlled. | P0-Critical | 5 |
| US-103 | As a **user**, I want to log in with username and password, so that I can access the system securely. | P0-Critical | 3 |
| US-104 | As a **user**, I want to be redirected based on my role after login, so that I see relevant content. | P1-High | 2 |
| US-105 | As an **admin**, I want to activate/deactivate users, so that I can manage access without deleting accounts. | P1-High | 2 |
| US-106 | As a **system**, I want role-based decorators that restrict views by role, so that unauthorized access is prevented. | P0-Critical | 3 |

### EP-2: Meter & Test Data
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-201 | As a **lab tech**, I want to register a new water meter (serial, size, class, manufacturer, type), so that it can be tested. | P0-Critical | 5 |
| US-202 | As a **lab tech**, I want to view all registered meters in a searchable list, so that I can find meters quickly. | P1-High | 3 |
| US-203 | As a **lab tech**, I want to edit meter details, so that I can correct mistakes. | P2-Medium | 2 |
| US-204 | As a **system**, I want ISO 4064 Q1-Q8 parameters auto-loaded as fixtures for DN15/DN20/DN25, so that test points are standards-compliant. | P0-Critical | 3 |
| US-205 | As a **lab tech**, I want to create a new test by selecting a meter, so that Q1-Q8 test points are auto-populated based on meter size and class. | P0-Critical | 5 |
| US-206 | As a **user**, I want to view test results with pass/fail per Q-point and overall verdict, so that I can assess meter accuracy. | P0-Critical | 5 |
| US-207 | As a **user**, I want to browse test history with filters (date, meter, status, technician), so that I can find past tests. | P1-High | 3 |

### EP-3: Communication Layer
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-301 | As a **system**, I want to encode/decode ASP protocol frames (STX, version, device ID, AES payload, HMAC, ETX), so that lab and bench can communicate securely. | P1-High | 8 |
| US-302 | As a **system**, I want AES-256-CBC encryption with random IV and HMAC-SHA256 signing, so that communication is tamper-proof. | P1-High | 5 |
| US-303 | As a **system**, I want a serial handler using pyserial for USB communication with ESP32 bridges, so that the RPi5 can talk to hardware. | P0-Critical | 5 |
| US-304 | As a **system**, I want a message queue with ACK tracking and 3-retry logic, so that no messages are silently lost. | P1-High | 5 |
| US-305 | As a **system**, I want replay protection via monotonic sequence counters, so that old messages cannot be replayed. | P1-High | 3 |
| US-306 | As a **lab tech**, I want to see LoRa connection status (connected/offline/last heartbeat), so that I know if bench communication is working. | P1-High | 3 |

### EP-4: Hardware Controller
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-401 | As a **developer**, I want a hardware simulator that mimics all sensors/actuators, so that I can develop without physical hardware. | P0-Critical | 8 |
| US-402 | As a **system**, I want a sensor manager that polls EM meter, scale, pressure, temperature, and DUT via Modbus through B2, so that live readings are available. | P0-Critical | 8 |
| US-403 | As a **system**, I want a PID controller that adjusts VFD frequency to maintain target flow rate (200ms cycle, ±2% stability), so that flow is precisely controlled. | P0-Critical | 8 |
| US-404 | As a **system**, I want a safety watchdog checking interlocks every 200ms (pressure, reservoir, temperature, E-stop), so that unsafe conditions trigger immediate shutdown. | P0-Critical | 5 |
| US-405 | As a **system**, I want valve sequencing with mutual exclusion (only one line-select valve open at a time), so that hydraulic conflicts are prevented. | P0-Critical | 5 |
| US-406 | As a **system**, I want VFD control (set frequency, start, stop, read status/faults) via B3 bridge, so that the pump is software-controlled. | P0-Critical | 5 |
| US-407 | As a **system**, I want tower light states mapped to system states (green=ready, yellow=testing, red=E-stop), so that operators have visual feedback. | P2-Medium | 2 |
| US-408 | As a **developer**, I want hardware abstraction (`HARDWARE_BACKEND = 'simulator' | 'real'`), so that switching to real hardware requires only a config change. | P0-Critical | 3 |

### EP-5: Test Engine
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-501 | As a **system**, I want a 12-state machine (IDLE → PRE_CHECK → LINE_SELECT → PUMP_START → [Q-point loop] → COMPLETE), so that tests execute in the correct sequence. | P0-Critical | 13 |
| US-502 | As a **system**, I want gravimetric measurement (tare scale, collect water, read mass, density-correct to volume), so that reference volume is accurate. | P0-Critical | 8 |
| US-503 | As a **bench tech**, I want to enter DUT readings manually via a touch keypad when the meter doesn't have RS485, so that non-digital meters can be tested. | P0-Critical | 5 |
| US-504 | As a **system**, I want DUT RS485 auto-read (totalizer before/after), so that digital meters are tested hands-free. | P1-High | 5 |
| US-505 | As a **system**, I want error% calculated as (DUT - REF) / REF × 100 and compared against MPE per Q-point, so that pass/fail is standards-compliant. | P0-Critical | 3 |
| US-506 | As a **system**, I want per-Q-point results sent to lab via LoRa as they complete, so that lab staff see real-time progress. | P1-High | 5 |
| US-507 | As a **bench tech**, I want to abort a running test with confirmation, so that I can stop safely if something is wrong. | P0-Critical | 3 |

### EP-6: Lab Web Portal
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-601 | As a **user**, I want a dashboard showing comm health, active test status, and today's summary, so that I get a quick overview. | P1-High | 5 |
| US-602 | As a **lab tech**, I want a 3-step test creation wizard (select meter → review Q-points → confirm & submit), so that test creation is guided. | P0-Critical | 8 |
| US-603 | As a **user**, I want a live monitor page with gauges (flow, pressure, weight) and Q-point progress, so that I can watch tests remotely. | P1-High | 8 |
| US-604 | As a **user**, I want a test results page with Q1-Q8 table and error curve chart, so that I can analyze accuracy. | P0-Critical | 5 |
| US-605 | As a **manager**, I want to approve/reject test results with comments, so that quality is verified before certification. | P0-Critical | 5 |
| US-606 | As a **user**, I want a test history page with filters and CSV export, so that I can review and report on past tests. | P1-High | 5 |
| US-607 | As a **lab tech**, I want a meter registry with card/table views, so that I can manage the meter inventory. | P1-High | 3 |
| US-608 | As a **manager**, I want a certificates page to view and download PDFs, so that I can provide official documents. | P1-High | 3 |
| US-609 | As an **admin**, I want a user management page, so that I can add/edit/deactivate accounts. | P1-High | 3 |
| US-610 | As an **admin/manager**, I want an audit log page, so that I can review all system actions. | P2-Medium | 3 |
| US-611 | As an **admin**, I want a settings page (serial ports, security keys, backup), so that I can configure the system. | P2-Medium | 3 |

### EP-7: Bench Touch UI
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-701 | As a **bench tech**, I want a home screen showing system health (LoRa, power, buses, reservoir), so that I know the bench is ready. | P0-Critical | 5 |
| US-702 | As a **bench tech**, I want a 4-step test wizard on touch screen (select meter → DUT mode → review points → confirm), so that I can start tests locally. | P0-Critical | 8 |
| US-703 | As a **bench tech**, I want a full-screen live monitor with 3 large circular gauges (flow, pressure, weight), so that I can watch the test at the bench. | P0-Critical | 8 |
| US-704 | As a **bench tech**, I want a manual DUT entry overlay with large touch keypad, so that I can enter meter readings accurately. | P0-Critical | 5 |
| US-705 | As a **bench tech**, I want swipeable Q-point result cards, so that I can review results on the small screen. | P1-High | 5 |
| US-706 | As a **bench tech**, I want a scrollable test history, so that I can review past tests on-site. | P1-High | 3 |
| US-707 | As an **admin**, I want a setup page with PID tuning, serial config, and safety limits, so that the bench can be calibrated. | P1-High | 5 |
| US-708 | As a **system**, I want the bench to boot into kiosk mode (no desktop, no cursor, Chromium fullscreen), so that operators only see the test app. | P1-High | 3 |

### EP-8: Reports & Certificates
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-801 | As a **manager**, I want a PDF certificate with header, meter details, Q1-Q8 results, error curve, and verdict, so that official calibration documents are generated. | P0-Critical | 8 |
| US-802 | As a **user**, I want an error curve chart (flow rate vs error%) with MPE envelope, so that accuracy is visualized. | P1-High | 5 |
| US-803 | As a **manager**, I want each certificate to have a unique ID and be downloadable, so that records are traceable. | P1-High | 3 |

### EP-9: ESP32 Firmware
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-901 | As a **system**, I want B2 firmware that bridges USB↔RS485 Modbus + controls GPIOs for valves/tower light/E-stop, so that RPi5 can interact with sensors and actuators. | P0-Critical | 13 |
| US-902 | As a **system**, I want B3 firmware that bridges USB↔RS485 for VFD Delta Modbus on isolated Bus 2, so that pump control is electrically isolated. | P0-Critical | 5 |
| US-903 | As a **system**, I want L1/B4 LinkMaster firmware that bridges USB↔LoRa 865MHz (SX1262), so that buildings can communicate wirelessly. | P1-High | 8 |
| US-904 | As a **system**, I want L2 firmware that bridges USB↔RS485 transparently, so that RPi5 can reach the LoRa LinkMaster. | P1-High | 3 |

### EP-10: Deployment & Integration
| Story ID | User Story | Priority | Story Points |
|----------|-----------|----------|--------------|
| US-1001 | As a **developer**, I want systemd services for Django, Redis, and Channels on both RPi5s, so that everything auto-starts on boot. | P1-High | 3 |
| US-1002 | As a **developer**, I want udev rules mapping USB-serial devices to fixed names (/dev/ttyBENCH_BUS, /dev/ttyVFD_BUS), so that ports don't shuffle. | P1-High | 2 |
| US-1003 | As a **developer**, I want an end-to-end integration test (create test → run all Q-points → results → cert), so that the full flow is validated. | P0-Critical | 8 |
| US-1004 | As a **developer**, I want Chromium kiosk auto-start (openbox + unclutter + Chromium --kiosk), so that the bench boots into the app. | P1-High | 3 |

---

## USER FLOWS

### UF-1: Lab Tech Creates & Submits a Test
```
Login (lab portal)
  → Dashboard
  → Click "New Test"
  → Step 1: Search/select meter from registry (or register new)
  → Step 2: Review auto-populated Q1-Q8 table (ISO 4064)
  → Step 3: Add notes → Click "Submit to Bench"
  → System: ASP message sent via LoRa to bench
  → Toast: "Test submitted, waiting for bench acknowledgment..."
  → Redirect to Live Monitor (auto-polls for updates)
```

### UF-2: Bench Tech Runs a Test Locally
```
Touch LCD Home screen
  → Tap "START NEW TEST"
  → Step 1: Select meter from list (or register new)
  → Step 2: Choose DUT mode (RS485 Auto / Manual Entry)
  → Step 3: Review Q1-Q8 test points
  → Step 4: Confirm → Tap "START TEST"
  → System: PRE_CHECK state (verify sensors, valves, reservoir)
  → System: LINE_SELECT (open correct valve for meter size)
  → System: PUMP_START (VFD ramps up)
  → FOR EACH Q-POINT (Q1 to Q8):
      → FLOW_STABILIZE (PID adjusts VFD, wait 5 readings within ±2%)
      → TARE_SCALE (zero scale, confirm ±0.020 kg)
      → If manual DUT: show keypad overlay → enter BEFORE reading
      → Record EM start totalizer
      → OPEN DIVERTER to collection tank → start timing
      → COLLECT VOLUME (monitor weight, PID maintains flow)
      → CLOSE DIVERTER to bypass → 2s settling
      → Record final weight
      → If manual DUT: show keypad overlay → enter AFTER reading
      → Record EM end totalizer
      → CALCULATE: ref_vol = mass/density(T), error% = (DUT-REF)/REF×100
      → Show result on screen (pass/fail badge)
      → Send result to lab via LoRa
      → DRAIN tank → wait weight ≈ 0
      → Advance to next Q-point
  → All Q-points done → COMPLETE state
  → Show overall verdict (PASS/FAIL)
  → Tower light: green blink (pass) or red blink (fail)
```

### UF-3: Manager Approves Results & Generates Certificate
```
Login (lab portal)
  → Dashboard → see "Pending Approvals" badge
  → Click → Test Results page
  → Review Q1-Q8 table (error%, pass/fail per point)
  → Review error curve chart (MPE envelope)
  → Enter comment
  → Click "Approve" (or "Reject")
  → If approved: "Generate Certificate" button appears
  → Click → PDF generated with all data + error curve + verdict
  → Certificate listed in Certificates page
  → Download PDF
```

### UF-4: Emergency Stop
```
HARDWARE PATH (primary, no software):
  Operator presses E-Stop mushroom button
  → NC contact opens → contactor coil de-energized
  → VFD loses power → pump stops
  → 24V rail drops → all valves close (spring return)
  → RPi5 + ESP32s stay powered (5V separate rail)

SOFTWARE DETECTION:
  B2 monitors contactor aux contact via GPIO (200ms poll)
  → GPIO goes LOW → B2 sends EVENT ESTOP 1 to RPi5
  → Safety monitor triggers EMERGENCY_STOP state
  → UI: red blinking status bar "EMERGENCY STOP ACTIVE"
  → Tower light: red steady
  → Test aborted, partial data saved
  → To resume: physically reset E-stop → contactor re-energizes → operator must restart test
```

### UF-5: Admin Manages Users
```
Login (lab portal, admin role)
  → Sidebar → Users
  → See user table (username, name, role badge, status, last login)
  → Click "Add User" → modal: username, password, full name, email, role dropdown
  → Submit → user created
  → To deactivate: toggle active/inactive switch on user row
  → Cannot deactivate self, cannot change own role
```

### UF-6: Bench Tech Manual DUT Entry
```
During MEASURE state, DUT mode = "Manual":
  Full-screen overlay appears (blur background)
  → Prompt: "Read meter display and enter BEFORE value"
  → Large numeric display + touch keypad (0-9, decimal, backspace, clear)
  → Enter value → tap CONFIRM
  → System records before_reading
  → ... measurement runs ...
  → Overlay appears again: "Enter AFTER value"
  → Enter value (must be > before) → tap CONFIRM
  → System records after_reading
  → DUT volume = after - before
```

### UF-7: Remote Test Monitoring (Lab)
```
Login (lab portal)
  → Navigate to Live Monitor
  → Top: Q1-Q8 progress stepper (green ✓ / blue pulse / gray ○ / red ✗)
  → Center: 3 circular gauges (flow, pressure, weight) — HTMX polls every 2s
  → Below: key metrics (temp, VFD Hz, error%, state name)
  → Bottom: status bar + ABORT button (requires typing "ABORT" to confirm)
  → On completion: redirect to results page
```

### UF-8: Certificate Download
```
Lab portal → Certificates page
  → Search by cert number or meter serial
  → Table: cert number, meter serial, date, tested by, approved by
  → Click download icon → PDF downloads
  → PDF contains: header/logo, lab info, meter details, Q1-Q8 table, error curve, verdict, cert ID
```

---

## SPRINTS

### Sprint 1 — Project Bootstrap & Data Models
**Goal**: Django project running on both settings, all models migrated, authentication working.
**Duration**: Days 1–4

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-101 | Create Django project skeleton with `config/` (settings_base, settings_lab, settings_bench, urls, wsgi, asgi) | US-101 | P0 | ✅ Done | 4h | — |
| T-102 | Create `requirements.txt` and install dependencies | US-101 | P0 | ✅ Done | 1h | T-101 |
| T-103 | Create `CustomUser` model with role field + migrations | US-102 | P0 | ✅ Done | 2h | T-101 |
| T-104 | Create login/logout views and login template | US-103 | P0 | ✅ Done | 3h | T-103 |
| T-105 | Create role-based permission decorators/mixins (`@role_required`) | US-106 | P0 | ✅ Done | 2h | T-103 |
| T-106 | Create `TestMeter` model + CRUD views + templates | US-201 | P0 | ✅ Done | 4h | T-103 |
| T-107 | Create `ISO4064Standard` model + fixture data (DN15/20/25 R160) | US-204 | P0 | ✅ Done | 3h | T-101 |
| T-108 | Create `Test` + `TestResult` models + migrations | US-205 | P0 | ✅ Done | 3h | T-106, T-107 |
| T-109 | Create test creation view with auto Q1-Q8 population | US-205 | P0 | ✅ Done | 4h | T-108 |
| T-110 | Create `base_lab.html` (sidebar layout) + `base_bench.html` (bottom tabs) | US-601, US-701 | P0 | ✅ Done | 4h | T-101 |
| T-111 | Setup static files: CSS tokens, Bootstrap 5.3, HTMX, Alpine.js, Lucide, Inter font | — | P0 | ✅ Done | 2h | T-110 |
| T-112 | Create superuser + seed data management command | US-102 | P1 | ✅ Done | 1h | T-103 |

**Sprint 1 Total**: ~33h | **Story Points**: 31

---

### Sprint 2 — Communication & Hardware Abstraction
**Goal**: ASP protocol working, serial handler connected, hardware simulator providing fake sensor data.
**Duration**: Days 5–8

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-201 | Create `comms/protocol.py` — ASP frame encoder/decoder (STX/ETX, header, payload) | US-301 | P1 | ✅ Done | 6h | T-101 |
| T-202 | Create `comms/crypto.py` — AES-256-CBC encrypt/decrypt + HMAC-SHA256 sign/verify | US-302 | P1 | ✅ Done | 4h | T-201 |
| T-203 | Create `comms/serial_handler.py` — pyserial USB handler with frame detection (STX/ETX) | US-303 | P0 | ✅ Done | 4h | T-101 |
| T-204 | Create `comms/message_queue.py` — outgoing queue, ACK tracking, 3-retry, sequence counter | US-304 | P1 | ✅ Done | 4h | T-201, T-203 |
| T-205 | Create `controller/simulator.py` — full hardware simulator (all sensors + actuators) | US-401 | P0 | ✅ Done | 8h | T-101 |
| T-206 | Create `controller/sensor_manager.py` — Modbus polling via B2 (with simulator backend) | US-402 | P0 | ✅ Done | 6h | T-205 |
| T-207 | Create `controller/vfd_controller.py` — VFD commands via B3 (with simulator backend) | US-406 | P0 | ✅ Done | 4h | T-205 |
| T-208 | Create hardware abstraction layer (`HARDWARE_BACKEND` config switch) | US-408 | P0 | ✅ Done | 2h | T-205, T-206 |
| T-209 | Write unit tests for protocol encode/decode roundtrip | US-301 | P1 | ✅ Done | 2h | T-201, T-202 |

**Sprint 2 Total**: ~40h | **Story Points**: 42

---

### Sprint 3 — Controller Core (PID, Safety, Valves)
**Goal**: PID controller converging, safety watchdog running, valve sequencing working, all on simulator.
**Duration**: Days 9–12

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-301 | Create `controller/pid_controller.py` — PID loop (200ms cycle, EM feedback → VFD freq) | US-403 | P0 | ✅ Done | 6h | T-206, T-207 |
| T-302 | Create `controller/safety_monitor.py` — parallel watchdog (pressure, reservoir, temp, E-stop) | US-404 | P0 | ✅ Done | 4h | T-206 |
| T-303 | Create `controller/valve_controller.py` — valve commands, mutual exclusion, timing, position feedback | US-405 | P0 | ✅ Done | 4h | T-205 |
| T-304 | Create `controller/tower_light.py` — state-to-light mapping | US-407 | P2 | ✅ Done | 2h | T-303 |
| T-305 | Create `controller/gravimetric.py` — tare, measure, density correction, volume calc | US-502 | P0 | ✅ Done | 6h | T-206 |
| T-306 | Create `controller/dut_interface.py` — RS485 auto-read + manual entry handler | US-503, US-504 | P0 | ✅ Done | 4h | T-206 |
| T-307 | Test PID convergence on simulator (target flow → stable within ±2%) | US-403 | P0 | ✅ Done | 3h | T-301 |
| T-308 | Test safety watchdog triggers (simulate overpressure, low reservoir) | US-404 | P0 | ✅ Done | 2h | T-302 |

**Sprint 3 Total**: ~31h | **Story Points**: 35

---

### Sprint 4 — State Machine & Test Execution
**Goal**: Full Q1-Q8 test cycle running on simulator, results stored in DB, pass/fail calculated.
**Duration**: Days 13–15

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-401 | Create `controller/state_machine.py` — 12-state threading engine | US-501 | P0 | ✅ Done | 10h | T-301, T-302, T-303, T-305, T-306 |
| T-402 | Integrate state machine with bench_ui API endpoints (start/abort/status/DUT) | US-501 | P0 | ✅ Done | 6h | T-401 |
| T-403 | Create error calculation service (`testing/services.py` — error%, MPE comparison, pass/fail) | US-505 | P0 | ✅ Done | 3h | T-108 |
| T-404 | Store per-Q-point results + DUTManualEntry persistence during test execution | US-206 | P0 | ✅ Done | 3h | T-401, T-403 |
| T-405 | Create bench-only models (`SensorReading`, `DUTManualEntry`) + migrations | US-503 | P1 | ✅ Done | 2h | T-108 |
| T-406 | Run full simulated Q1-Q8 test cycle, verify all results correct | US-501 | P0 | ✅ Done | 4h | T-402, T-404 |
| T-407 | Create `comms/lora_handler.py` — ASP message handling for lab communication | US-506 | P1 | ✅ Done | 4h | T-201, T-204 |

**Sprint 4 Total**: ~32h | **Story Points**: 36

---

### Sprint 5 — Lab Web Portal UI
**Goal**: All 11 lab pages functional with HTMX partial updates, role-based access enforced.
**Duration**: Days 16–18

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-501 | Create lab login page (centered card, logo, error animation) | US-103 | P0 | **Done** | 2h | T-104, T-110 |
| T-502 | Create lab dashboard (comm health, active test, today summary, recent tests, quick actions) | US-601 | P1 | **Done** | 5h | T-110 |
| T-503 | Create lab new test wizard (3-step: select meter → review Q-points → confirm & submit) | US-602 | P0 | **Done** | 6h | T-109, T-110 |
| T-504 | Create lab live monitor (Q-point stepper, 3 gauges, metrics row, HTMX polling 2s) | US-603 | P1 | **Done** | 6h | T-110 |
| T-505 | Create lab test results page (Q1-Q8 table + error curve chart + approval section) | US-604, US-605 | P0 | **Done** | 6h | T-110, T-403 |
| T-506 | Create lab test history page (filterable table, pagination, CSV export) | US-606 | P1 | **Done** | 4h | T-110 |
| T-507 | Create lab meter registry page (card grid + table toggle, add modal, detail page) | US-607 | P1 | **Done** | 4h | T-106, T-110 |
| T-508 | Create lab certificates page (table, search, download PDF) | US-608 | P1 | **Done** | 3h | T-110 |
| T-509 | Create lab user management page (admin only — table, add/edit modal, active toggle) | US-609 | P1 | **Done** | 3h | T-105, T-110 |
| T-510 | Create lab audit log page (chronological table, filters, CSV export) | US-610 | P2 | **Done** | 3h | T-110 |
| T-511 | Create lab settings page (serial ports, security, backup) | US-611 | P2 | **Done** | 3h | T-110 |
| T-512 | Create audit logging middleware (`audit/middleware.py` — auto-log all actions) | US-610 | P2 | **Done** | 3h | T-110 |

**Sprint 5 Total**: ~48h | **Story Points**: 44

---

### Sprint 6 — Bench Touch UI
**Goal**: All bench pages functional for 1024x600, WebSocket gauges live, manual DUT overlay working.
**Duration**: Days 18–20

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-601 | Create bench home screen (status pills, START TEST button, last test summary, status strip) | US-701 | P0 | ✅ Done | 4h | T-110 |
| T-602 | Create bench test wizard (4-step touch: select meter → DUT mode → review → confirm) | US-702 | P0 | ✅ Done | 6h | T-109, T-110 |
| T-603 | Create bench live monitor (full-screen, 3 large SVG gauges, Q-point stepper, WebSocket) | US-703 | P0 | ✅ Done | 8h | T-110, T-401 |
| T-604 | Setup Django Channels + WebSocket consumer for real-time gauge data from Redis | US-703 | P0 | ✅ Done | 4h | T-603 |
| T-605 | Create manual DUT entry overlay (blur bg, large keypad, validation) | US-704 | P0 | ✅ Done | 5h | T-306 |
| T-606 | Create bench results tab (swipeable Q-point cards, verdict banner, error curve modal) | US-705 | P1 | ✅ Done | 5h | T-110 |
| T-607 | Create bench history tab (scrollable list, tap expand, pull-down refresh) | US-706 | P1 | ✅ Done | 3h | T-110 |
| T-608 | Create bench setup tab (PID tuning, serial config, safety limits, system info) | US-707 | P1 | ✅ Done | 4h | T-110 |
| T-609 | Touch gesture handling (swipe nav, long-press, pull-refresh) + touch CSS (48px targets) | US-703 | P1 | ✅ Done | 3h | T-603 |

**Sprint 6 Total**: ~42h | **Story Points**: 42

---

### Sprint 7 — Reports, Firmware & Deployment
**Goal**: PDF certs generated, ESP32 firmware flashed, kiosk boot working, E2E test passing.
**Duration**: Days 20–23

| Task ID | Task | Story | Priority | Status | Estimate | Dependencies |
|---------|------|-------|----------|--------|----------|--------------|
| T-701 | Create `reports/error_curve.py` — Matplotlib error curve (log scale, MPE envelope, Q-point dots) | US-802 | P1 | ✅ Done | 4h | T-403 |
| T-702 | Create `reports/generator.py` — ReportLab PDF cert (header, meter info, Q1-Q8 table, chart, verdict, cert ID) | US-801 | P0 | ✅ Done | 6h | T-701 |
| T-703 | Create approval → certificate generation flow in `testing/views.py` | US-605 | P0 | ✅ Done | 3h | T-702, T-505 |
| T-704 | Create B2 sensor bridge firmware (USB↔RS485 Modbus + GPIO command protocol) | US-901 | P0 | ✅ Done | 10h | — |
| T-705 | Create B3 VFD bridge firmware (USB↔RS485 Modbus pass-through) | US-902 | P0 | ✅ Done | 4h | — |
| T-706 | Create L1/B4 LinkMaster firmware (USB↔LoRa SX1262 865MHz bridge) | US-903 | P1 | ✅ Done | 6h | — |
| T-707 | Create L2 lab bridge firmware (USB↔RS485 transparent) | US-904 | P1 | ✅ Done | 2h | — |
| T-708 | Create kiosk boot scripts (openbox + Chromium --kiosk + unclutter + systemd) | US-708, US-1004 | P1 | ✅ Done | 3h | — |
| T-709 | Create systemd service files (Django, Redis, Channels) | US-1001 | P1 | ✅ Done | 2h | — |
| T-710 | Create udev rules for USB-serial port mapping | US-1002 | P1 | ✅ Done | 1h | — |
| T-711 | Run full E2E integration test on simulator | US-1003 | P0 | ✅ Done | 6h | ALL |

**Sprint 7 Total**: ~47h | **Story Points**: 51

---

## EPIC PROGRESS

| Epic | Name | Stories Done | Stories Total | Status |
|------|------|:-----------:|:------------:|--------|
| EP-1 | Foundation & Auth | 6 | 6 | ✅ Complete |
| EP-2 | Meter & Test Data | 7 | 7 | ✅ Complete |
| EP-3 | Communication Layer | 5 | 6 | 🔶 83% (US-306 LoRa status UI remaining) |
| EP-4 | Hardware Controller | 8 | 8 | ✅ Complete |
| EP-5 | Test Engine | 7 | 7 | ✅ Complete |
| EP-6 | Lab Web Portal | 11 | 11 | ✅ Complete |
| EP-7 | Bench Touch UI | 8 | 8 | ✅ Complete (incl. US-708 kiosk boot) |
| EP-8 | Reports & Certificates | 3 | 3 | ✅ Complete |
| EP-9 | ESP32 Firmware | 4 | 4 | ✅ Complete |
| EP-10 | Deployment & Integration | 4 | 4 | ✅ Complete |
| **TOTAL** | | **63** | **64** | **98% complete** (US-306 LoRa status UI deferred) |

### User Stories Completed (by Epic)

**EP-1**: US-101 ✅ US-102 ✅ US-103 ✅ US-104 ✅ US-105 ✅ US-106 ✅
**EP-2**: US-201 ✅ US-202 ✅ US-203 ✅ US-204 ✅ US-205 ✅ US-206 ✅ US-207 ✅
**EP-3**: US-301 ✅ US-302 ✅ US-303 ✅ US-304 ✅ US-305 ✅ | US-306 ○
**EP-4**: US-401 ✅ US-402 ✅ US-403 ✅ US-404 ✅ US-405 ✅ US-406 ✅ US-407 ✅ US-408 ✅
**EP-5**: US-501 ✅ US-502 ✅ US-503 ✅ US-504 ✅ US-505 ✅ US-506 ✅ US-507 ✅
**EP-6**: US-601 ✅ US-602 ✅ US-603 ✅ US-604 ✅ US-605 ✅ US-606 ✅ US-607 ✅ US-608 ✅ US-609 ✅ US-610 ✅ US-611 ✅
**EP-7**: US-701 ✅ US-702 ✅ US-703 ✅ US-704 ✅ US-705 ✅ US-706 ✅ US-707 ✅ US-708 ✅
**EP-8**: US-801 ✅ US-802 ✅ US-803 ✅
**EP-9**: US-901 ✅ US-902 ✅ US-903 ✅ US-904 ✅
**EP-10**: US-1001 ✅ US-1002 ✅ US-1003 ✅ US-1004 ✅

---

## SPRINT SUMMARY

| Sprint | Name | Days | Story Points | Tasks | Status | Key Deliverable |
|--------|------|------|:-----------:|:-----:|--------|-----------------|
| 1 | Project Bootstrap & Data Models | 1–4 | 31 | 12/12 | ✅ Complete | Django running, models migrated, auth working |
| 2 | Communication & Hardware Abstraction | 5–8 | 42 | 9/9 | ✅ Complete | ASP protocol, serial handler, simulator providing data |
| 3 | Controller Core | 9–12 | 35 | 8/8 | ✅ Complete | PID converging, safety active, valves sequencing |
| 4 | State Machine & Test Execution | 13–15 | 36 | 7/7 | ✅ Complete | Full Q1-Q8 cycle on simulator, LoRa handler, API endpoints |
| 5 | Lab Web Portal UI | 16–18 | 44 | 12/12 | ✅ Complete | All 11 lab pages, audit logging, CSV export |
| 6 | Bench Touch UI | 18–20 | 42 | 9/9 | ✅ Complete | WebSocket gauges, DUT keypad, wizard, results, touch gestures |
| 7 | Reports, Firmware & Deployment | 20–23 | 51 | 11/11 | ✅ Complete | PDF certs, 4 firmware variants, udev, systemd, 6 E2E tests |
| **TOTAL** | | **23 days** | **281 pts** | **68/68** | **✅ 100% done** | 221 tests passing |

---

## DEFINITION OF DONE (per task)
- [ ] Code written and functional
- [ ] No errors on `python manage.py check`
- [ ] Tested manually (described test in task passes)
- [ ] No regressions on existing features
- [ ] Doc5_Project_Tracker.md updated with status

---

## LABELS / TAGS REFERENCE
- **Priority**: P0-Critical, P1-High, P2-Medium, P3-Low
- **Type**: Feature, Bug, Chore, Spike
- **Side**: Lab, Bench, Both, Firmware
- **Epic**: EP-1 through EP-10
