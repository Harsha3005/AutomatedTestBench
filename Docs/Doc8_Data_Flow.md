# Doc8: Complete Data Flow — Lab & Bench System

> Authoritative reference for all data flow, hardware interaction, state machine execution,
> and inter-building communication. Aligned with Doc8_Data_Flow_Scenarios.docx.

---

## 1. System Overview

The IIIT Bangalore Water Meter Test Bench is a **two-building system** designed for
ISO 4064 compliant calibration of DN15/DN20/DN25 water meters using the gravimetric method.

| Aspect | Bench System (Test Bench Building) | Lab System (Lab Building) |
|--------|-------------------------------------|---------------------------|
| Role | **Standalone primary** — controls all hardware, runs tests, operates independently | **Convenience/monitoring layer** — initiates tests remotely, receives results, manages certificates |
| Hardware Control | Full (VFD, valves, sensors, PID, safety) | **NONE** — never directly controls hardware |
| Connectivity Required | None (standalone) | LoRa link to Bench (graceful degradation if down) |
| Django Settings | `config.settings_bench` | `config.settings_lab` |
| RPi5 Unit | B1 | L3 |
| Database | `db_bench.sqlite3` (primary) | `db_lab.sqlite3` (mirror) |
| Real-time | WebSocket via Django Channels (200ms) | HTMX polling (2s) |
| Communication | Via B4 LinkMaster (LoRa 865MHz ASP) | Via L1 LinkMaster (LoRa 865MHz ASP) |

---

## 2. Physical Architecture

```
╔═══════════════════════════════════════════════════════════════════════╗
║                           LAB BUILDING                               ║
║                                                                       ║
║  ┌────────────────────────────────────────────────────────┐          ║
║  │              L3: RPi5 — Lab Server                      │          ║
║  │  ┌──────────────────┐   ┌─────────────┐                │          ║
║  │  │   Django App      │   │  SQLite DB   │                │          ║
║  │  │  (Lab Portal)     │   │ db_lab.sqlite│                │          ║
║  │  │  settings_lab.py  │   └─────────────┘                │          ║
║  │  └────────┬─────────┘                                   │          ║
║  │           │ Ethernet LAN ──→ Lab staff browsers         │          ║
║  │           │ USB Serial                                   │          ║
║  │  ┌────────┴─────────┐                                   │          ║
║  │  │  L2: ESP32 Bridge │  Indoor. USB↔RS485 transparent.  │          ║
║  │  └────────┬─────────┘                                   │          ║
║  │           │ RS485                                        │          ║
║  │  ┌────────┴─────────┐                                   │          ║
║  │  │  L1: ESP32+RA01SH │  Rooftop. LoRa↔RS485 gateway.   │          ║
║  │  │   Lab LinkMaster   │  SX1262, 865MHz IN865 band.     │          ║
║  │  └────────┬─────────┘                                   │          ║
║  └───────────┼─────────────────────────────────────────────┘          ║
║              │                                                        ║
╚══════════════╪════════════════════════════════════════════════════════╝
               │  LoRa 865 MHz — ASP Encrypted (AES-256-CBC + HMAC-SHA256)
       ~~~~~~~~│~~~~~~~~ Air Gap (200m+) ~~~~~~~~~~~~~~~~~~~~~~~~
               │
╔══════════════╪════════════════════════════════════════════════════════╗
║              │          TEST BENCH BUILDING                           ║
║  ┌───────────┼─────────────────────────────────────────────┐         ║
║  │  ┌────────┴──────────┐   B1: RPi5 — Bench Controller    │         ║
║  │  │  B4: ESP32+RA01SH  │  ┌────────────────────────────┐ │         ║
║  │  │  Bench LinkMaster   │  │  Django App (Bench)         │ │         ║
║  │  │  Rooftop. SX1262.  │  │  settings_bench.py          │ │         ║
║  │  └────────┬──────────┘  │  Test Engine + PID + Safety   │ │         ║
║  │           │ RS485→USB    │  db_bench.sqlite3             │ │         ║
║  │           └──────────→  │  7-inch HDMI Touch LCD (kiosk)│ │         ║
║  │                          └──────┬────────┬──────────────┘ │         ║
║  │                                 │        │                 │         ║
║  │                            USB-1│        │USB-2            │         ║
║  │                                 │        │                 │         ║
║  │  ┌──────────────────────────────┴┐  ┌───┴────────────────┐│         ║
║  │  │  B2: ESP32 — Sensor Bridge    │  │  B3: ESP32 — VFD   ││         ║
║  │  │  RS485 Bus 1 + GPIOs          │  │  Bridge             ││         ║
║  │  │  (EM, Scale, 4-20mA, DUT)     │  │  RS485 Bus 2       ││         ║
║  │  │  (5 valves, tower, E-stop)     │  │  (VFD only)        ││         ║
║  │  └──────────┬────────────────────┘  └───┬────────────────┘│         ║
║  └─────────────┼───────────────────────────┼─────────────────┘         ║
║                │                           │                           ║
║         RS485 Bus 1                  RS485 Bus 2                      ║
║         (9600 baud)                  (9600 baud, isolated)            ║
║                │                           │                           ║
║    ┌───────────┼───────────┐               │                           ║
║    │     │     │     │     │               │                           ║
║   F1    F2    F3   F4×2   DUT            F5                           ║
║   EM   Scale 4-20mA Press  Meter         VFD Delta                    ║
║  addr=1 addr=2 addr=3      addr=20       addr=1                       ║
║                             (or manual)                                ║
║                                                                        ║
║  B2 GPIOs:                     Hardwired (NO software):               ║
║  ├─ BV1: Ball Valve DN25       ├─ E-Stop Button (NC → Contactor)      ║
║  ├─ BV2: Ball Valve DN20       ├─ Contactor (415V + 24V rail)         ║
║  ├─ BV3: Ball Valve DN15       └─ Exhaust Fan (direct MCB)            ║
║  ├─ DV1: 3-Way Diverter                                               ║
║  ├─ DRN: Drain Valve           F6: Pump Kirloskar 3HP                 ║
║  ├─ Tower Light (R/Y/G)          (3-phase via VFD, no software)       ║
║  └─ E-Stop Monitor (input)                                            ║
║                                                                        ║
╚════════════════════════════════════════════════════════════════════════╝
```

---

## 3. Unit Reference

| ID | Unit | Location | Role |
|----|------|----------|------|
| L1 | Lab LinkMaster | Lab rooftop | ESP32+RA01SH (SX1262, 865MHz). LoRa↔RS485 gateway. |
| L2 | Lab RS485 Bridge | Lab indoor | ESP32. USB↔RS485 transparent bridge to L1. |
| L3 | Lab RPi5 | Lab indoor | Django web portal. Accessed via LAN by lab staff. |
| B1 | Bench RPi5 + Touch LCD | Bench indoor | Main controller. Django + test engine + 7-inch HDMI kiosk. 2× USB to B2, B3. |
| B2 | Sensor Bridge ESP32 | Bench | RS485 Bus 1 (EM, scale, 4-20mA, DUT) + GPIO (5 valves, tower light, E-stop monitor). |
| B3 | VFD Bridge ESP32 | Bench | RS485 Bus 2 (VFD Delta only). Electrically isolated bus. |
| B4 | Bench LinkMaster | Bench rooftop | ESP32+RA01SH (SX1262, 865MHz). LoRa↔RS485 gateway. |

---

## 4. Field Devices

| ID | Device | Interface | Connected To | Bus / Notes |
|----|--------|-----------|-------------|-------------|
| F1 | EM Flow Meter DN25 (±0.5%) | RS485 Modbus | B2 | Bus 1, addr=1 |
| F2 | Weighing Scale 200 kg | RS485 | B2 | Bus 1, addr=2 |
| F3 | 4-20mA Modbus Module | RS485 Modbus | B2 | Bus 1, addr=3. Reads 2× pressure + temp. |
| F4 | Pressure Transmitter ×2 | 4-20mA analog | F3 inputs | Upstream (Ch1) + Downstream (Ch2) |
| F5 | VFD Delta VFD022EL43A | RS485 Modbus | B3 | Bus 2, addr=1. Isolated. |
| F6 | Pump Kirloskar 3HP | 3-phase via VFD | F5 | No software interface. |
| BV1 | Ball Valve DN25 | Relay | B2 GPIO | Line select — DN25 meters |
| BV2 | Ball Valve DN20 | Relay | B2 GPIO | Line select — DN20 meters |
| BV3 | Ball Valve DN15 | Relay | B2 GPIO | Line select — DN15 meters |
| DV1 | 3-Way Diverter Valve | Relay pair | B2 GPIO | +/- polarity: collection vs bypass |
| DRN | Drain Valve | Relay | B2 GPIO | Collection tank drain |
| — | Tower Light (R/Y/G) | Digital out | B2 GPIO | 3 outputs for Red/Yellow/Green |
| — | E-Stop Button | Hardwired NC | Contactor coil | **NO software in the loop** |
| — | Contactor | Hardwired | 415V + 24V rail | E-stop breaks coil → all power cut |
| — | Exhaust Fan | Direct MCB | Contactor/MCB | No software control |
| DUT | Device Under Test | RS485 or Manual | B2 Bus 1 / Touch UI | addr=20 (configurable), or manual entry |

---

## 5. Scenario 1 — Lab Initiates Test Remotely

| # | Actor / Component | Action |
|---|-------------------|--------|
| 1 | Lab Technician | Logs into Lab Portal (`http://<L3-ip>:8080`) via browser on LAN. |
| 2 | Lab Portal (L3) | Technician registers meter (serial, DN15/20/25, class, type, DUT mode) → saved to Lab SQLite DB. |
| 3 | Lab Portal (L3) | Technician creates new test for the meter. System auto-populates Q1–Q8 from ISO 4064 fixture. Test record created: `status='pending'`, `source='lab'`. |
| 4 | Lab Django | Packages test request as ASP message: `{command: START_TEST, meter_serial, meter_size, meter_class, dut_mode, q_points: [Q1..Q8 params]}`. Encrypts with AES-256-CBC, signs with HMAC-SHA256, adds sequence number + timestamp. |
| 5 | L3 → L2 → L1 | ASP frame sent via USB Serial to L2 bridge, forwarded via RS485 to L1 LinkMaster. |
| 6 | L1 → LoRa → B4 | L1 transmits via LoRa 865MHz. If payload > ~200 bytes after encryption, ASP fragments into multiple LoRa packets (max 255 bytes each). |
| 7 | B4 → Bridge → B1 | B4 receives LoRa, forwards via RS485/USB to Bench Django on B1. |
| 8 | Bench Django (B1) | Verifies HMAC signature. Decrypts AES payload. Checks sequence number (replay protection). Creates/mirrors Test record in Bench DB: `source='lab'`, `status='pending'`. |
| 9 | Bench Django (B1) | Sends ACK back: B1 → B4 → LoRa → L1 → L2 → L3. |
| 10 | Lab Portal (L3) | Receives ACK. Updates test `status='acknowledged'`. Shows "Test sent to bench" in UI. |
| 11 | Bench | Test enters the execution queue. If bench is IDLE, begins test execution (Scenario 3). If busy, queues with `status='queued'`. |

### ASP Message Frame Structure

```
┌─────────────┬───────────┬────────────┬──────────────────────────┬───────────────┐
│ Device ID   │ Seq #     │ Timestamp  │ AES-256-CBC Encrypted    │ HMAC-SHA256   │
│ (4 bytes)   │ (2 bytes) │ (4 bytes)  │ Payload (variable)       │ (32 bytes)    │
│ 0x0001=Lab  │ Big-endian│ Unix epoch │ IV prepended (16 bytes)  │ Over entire   │
│ 0x0002=Bench│           │            │ + compressed JSON        │ frame         │
└─────────────┴───────────┴────────────┴──────────────────────────┴───────────────┘
```

### Fragmentation (payloads > 200 bytes)

```
Fragment Header (3 bytes): [Fragment ID (1)] [Fragment Index (1)] [Total Fragments (1)]
Each LoRa packet: [Fragment Header (3)] + [Fragment Data (up to 252 bytes)]
Receiver reassembles fragments by Fragment ID, validates completeness, then processes.
Retry: If ACK not received within 3 seconds, retransmit. Max 3 retries.
```

---

## 6. Scenario 2 — Bench Runs Test Locally

| # | Actor / Component | Action |
|---|-------------------|--------|
| 1 | Bench Technician | Interacts with 7-inch touch LCD (Chromium kiosk on B1). Auto-logged in as system user (session timeout = 1 year). |
| 2 | Bench Touch UI | Technician registers meter or selects existing one. Saved to Bench SQLite DB. |
| 3 | Bench Touch UI | Technician creates test: selects meter → selects DUT mode (RS485 or manual) → reviews auto-populated Q1–Q8 → confirms. Test record: `source='bench'`, `status='pending'`. |
| 4 | Bench Touch UI | Technician taps "START TEST". Test enters execution engine (Scenario 3). |
| 5 | Bench Django | If LoRa link to lab is active, sends status update: "Test started locally". Lab gets notification. **If LoRa is down, bench proceeds without lab — no dependency.** |

---

## 7. Scenario 3 — Test Execution: Full State Machine

This is the heart of the system. The Bench Django test engine (`controller/state_machine.py`)
runs as an asyncio task on B1. It orchestrates all hardware through B2 (sensors + GPIO) and
B3 (VFD).

### 7.0 State Machine Overview

```
IDLE → PRE_CHECK → LINE_SELECT → PUMP_START
    → [Q-point loop: FLOW_STABILIZE → TARE_SCALE → MEASURE → CALCULATE → DRAIN → NEXT_POINT]
    → COMPLETE

EMERGENCY_STOP: reachable from ANY state.
ERROR: reachable from any active state (recoverable — operator can retry).
```

```
    ┌──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    │   ┌──────┐    ┌───────────┐    ┌─────────────┐    ┌──────────┐ │
    │   │ IDLE │───→│ PRE_CHECK │───→│ LINE_SELECT │───→│PUMP_START│ │
    │   └──────┘    └───────────┘    └─────────────┘    └────┬─────┘ │
    │       ↑                                                │       │
    │       │                                                ↓       │
    │       │   ┌─────────────────────────────────────────────────┐  │
    │       │   │           Q-POINT LOOP (Q1 → Q8)                │  │
    │       │   │                                                 │  │
    │       │   │  ┌────────────────┐    ┌────────────┐          │  │
    │       │   │  │FLOW_STABILIZE  │───→│ TARE_SCALE │          │  │
    │       │   │  └────────────────┘    └─────┬──────┘          │  │
    │       │   │                              │                 │  │
    │       │   │                              ↓                 │  │
    │       │   │  ┌────────────┐    ┌─────────────┐            │  │
    │       │   │  │ NEXT_POINT │←──│  DRAIN       │            │  │
    │       │   │  └──────┬─────┘    └──────↑──────┘            │  │
    │       │   │         │                 │                    │  │
    │       │   │    next Q?          ┌─────┴──────┐            │  │
    │       │   │    │ yes→loop       │ CALCULATE   │            │  │
    │       │   │    │ no ↓           └──────↑──────┘            │  │
    │       │   │    │                       │                   │  │
    │       │   │    │               ┌───────┴──────┐           │  │
    │       │   │    │               │   MEASURE     │           │  │
    │       │   │    │               │ (3 sub-phases)│           │  │
    │       │   │    │               └───────────────┘           │  │
    │       │   └────┼───────────────────────────────────────────┘  │
    │       │        ↓                                              │
    │       │   ┌──────────┐                                       │
    │       └───│ COMPLETE │                                       │
    │           └──────────┘                                       │
    │                                                              │
    │   ┌─────────────────┐  ← reachable from ANY state           │
    │   │ EMERGENCY_STOP  │                                        │
    │   └─────────────────┘                                        │
    │   ┌─────────────────┐  ← recoverable, operator retry        │
    │   │     ERROR       │                                        │
    │   └─────────────────┘                                        │
    └──────────────────────────────────────────────────────────────┘
```

---

### 7.1 State: IDLE

| Aspect | Detail |
|--------|--------|
| Entry | System ready. Pump off, all valves closed, diverter at BYPASS position. |
| Trigger | Test initiated from Touch UI (Scenario 2) or received from Lab via LoRa (Scenario 1). |
| Action | Load ISO 4064 Q1–Q8 parameters for the selected meter size and class. Create TestResult placeholder records for all 8 Q-points. Update `test.status='running'`, `test.started_at=now()`. |
| Tower Light | GREEN steady |
| Exit | → PRE_CHECK |

---

### 7.2 State: PRE_CHECK

| Aspect | Detail |
|--------|--------|
| Purpose | Validate all systems before starting. Prevent unsafe test starts. |
| Hardware Reads | B1→B2: Poll Bus 1 (EM meter status, scale status, 4-20mA module status). B1→B3: Poll Bus 2 (VFD status, fault code). B2 GPIOs: Read E-stop monitor (contactor aux contact). |
| Tower Light | YELLOW blink during checks. GREEN flash if all pass. RED if any fail. |
| Exit (pass) | All checks pass → LINE_SELECT |
| Exit (fail) | Show error on touch UI with specific message, return to IDLE |

**Safety Checks Performed:**

| # | Check | Threshold | Fail Action |
|---|-------|-----------|-------------|
| 1 | Contactor closed (power available) | Aux contact GPIO = HIGH | BLOCK. "Power off. Check E-stop and contactor." |
| 2 | E-stop not active | GPIO = HIGH (NC circuit) | BLOCK. "E-stop is pressed. Release and reset." |
| 3 | EM meter responding | Modbus addr 1 responds | BLOCK. "EM flow meter offline. Check Bus 1." |
| 4 | Weighing scale responding | Modbus addr 2 responds | BLOCK. "Weighing scale offline. Check Bus 1." |
| 5 | 4-20mA module responding | Modbus addr 3 responds | BLOCK. "Pressure module offline. Check Bus 1." |
| 6 | VFD responding, no faults | Modbus addr 1, fault=0 | BLOCK. "VFD fault. Check VFD panel." |
| 7 | Upstream pressure < max | < 8.0 bar (`SAFETY_PRESSURE_MAX`) | BLOCK. "High pressure. Check system." |
| 8 | Reservoir level > min | > 20% (`SAFETY_RESERVOIR_MIN`) | BLOCK. "Low reservoir. Refill before testing." |
| 9 | Scale weight reasonable | < 180 kg (`SAFETY_SCALE_MAX`) | BLOCK. "Scale overloaded. Empty collection tank." |
| 10 | Temperature in range | 5–40°C (`SAFETY_TEMP_MIN/MAX`) | BLOCK. "Temperature out of range." |

---

### 7.3 State: LINE_SELECT

| Aspect | Detail |
|--------|--------|
| Purpose | Open the correct ball valve for the DUT meter size. |
| Hardware | B1 → B2 GPIO: Close BV1, BV2, BV3 (all off first). Then open one: DN25→BV1, DN20→BV2, DN15→BV3. |
| Interlock | Mutual exclusion: only one BVx open at a time. Software enforces. Wait for GPIO position feedback. |
| Diverter | DV1 confirmed in BYPASS position (water returns to reservoir during startup). |
| Timeout | 5 seconds (`SAFETY_VALVE_TIMEOUT`). If no position feedback → ERROR: "Valve jam. Check mechanical." |
| Exit | → PUMP_START |

---

### 7.4 State: PUMP_START

| Aspect | Detail |
|--------|--------|
| Hardware | B1 → B3 → Bus 2 → VFD (addr=1): Write run command (register `0x2000`=`0x0001` Run Forward). Write initial frequency = 10 Hz (low start, register `0x2001`). |
| Confirmation | Read VFD status register. Wait for "running" flag. Read actual frequency from register `0x2103` ramping up. |
| Timeout | 10 seconds. If VFD doesn't confirm running → ERROR. |
| Tower Light | YELLOW steady (test in progress from here until COMPLETE). |
| Exit | → FLOW_STABILIZE (begins Q-point loop, starting with Q1) |

---

### 7.5 Q-Point Loop (repeats Q1 through Q8)

For each Q-point, the following 5 states execute in sequence. The pump stays running
between Q-points (no restart). Only the VFD frequency changes via PID to hit the new
target flow rate.

---

#### 7.5.1 State: FLOW_STABILIZE

Contains two sub-phases: **FLOW_RAMP** and **FLOW_STABLE**.

**Sub-phase A — FLOW_RAMP (PID Control Loop):**

Every 200ms (`PID_SAMPLE_RATE`):

```
1. READ:  B1 → B2 → RS485 Bus 1 → F1 (EM Meter, addr=1) → actual flow rate (L/h)
2. COMPARE: actual_flow vs target_flow (from ISO 4064 for current Q-point)
3. PID CALCULATE:
     error      = target_flow - actual_flow
     P          = Kp × error                    (Kp = 0.5)
     I          = Ki × ∫(error × dt)            (Ki = 0.1)
     D          = Kd × d(error)/dt              (Kd = 0.05)
     pid_output = P + I + D
     vfd_freq   = clamp(pid_output, 5.0, 50.0)  (PID_OUTPUT_MIN, PID_OUTPUT_MAX)
4. WRITE: B1 → B3 → RS485 Bus 2 → F5 (VFD, addr=1) → set frequency (register 0x2001)
5. ALSO READ (for monitoring/logging):
     - F3 (addr=3): upstream pressure, downstream pressure, temperature
     - F2 (addr=2): current scale weight
6. STORE: SensorReading record in Bench DB (time-series, 5Hz)
7. BROADCAST:
     - Bench: Redis → Django Channels → WebSocket → Touch LCD gauges (200ms real-time)
     - Lab: Every 5 seconds, send TEST_STATUS via LoRa ASP: {q_point, flow, pressure, state}
```

**Sub-phase B — FLOW_STABLE:**

Wait for **5 consecutive readings** (1 second) where:
```
|actual_flow - target_flow| / target_flow × 100 ≤ 2.0%
```
(`SAFETY_FLOW_STABILITY` = 2%, `SAFETY_STABILITY_COUNT` = 5)

Once stable, proceed to TARE_SCALE.

| Timeout | 60 seconds. If stability not achieved → ERROR with current process value. Operator can adjust PID gains or retry. |
|---------|------|
| Exit | → TARE_SCALE |

---

#### 7.5.2 State: TARE_SCALE

| Aspect | Detail |
|--------|--------|
| Purpose | Zero the weighing scale before collecting water. Critical for gravimetric accuracy. |
| Hardware | B1 → B2 → RS485 Bus 1 → F2 (Scale, addr=2): Send tare command. Read weight until stable at 0.000 ±0.020 kg. |
| Record | Store `tare_weight` and `tare_timestamp`. |
| Timeout | 5 seconds. If scale doesn't zero → ERROR: "Scale tare failed." |
| Exit | → MEASURE |

---

#### 7.5.3 State: MEASURE

Contains three sub-phases: **DIVERT_OPEN**, **COLLECTING**, and **DIVERT_CLOSE**.

**Sub-phase A — DIVERT_OPEN:**

```
1. Record start values:
   - DUT totalizer: RS485 read from addr=20 (if DUT mode='rs485')
                     OR prompt manual BEFORE reading on touch LCD (if DUT mode='manual')
                     Manual entry: large numeric keypad, validation (reasonable range)
   - EM meter totalizer: RS485 read from F1 (addr=1)
2. Switch diverter:
   B1 → B2 GPIO → DV1 relay pair → polarity for COLLECTION position
   (Water now flows into collection tank on weighing scale)
3. Record: divert_start_timestamp
```

**Sub-phase B — COLLECTING:**

```
Water flows through DUT into collection tank sitting on weighing scale.

Every 200ms (PID continues running):
  - F2 (Scale, addr=2): read current weight
  - F1 (EM Meter, addr=1): read flow rate + totalizer
  - F3 (4-20mA, addr=3): read pressures + temperature
  - PID continues maintaining target flow rate

Target weight calculation:
  target_weight_kg = target_volume_L × water_density(temperature_C)
  (Density lookup table per ISO 4064 Annex, e.g., 20°C → 0.99820 kg/L)

Continue until:
  current_weight ≥ target_weight → proceed to DIVERT_CLOSE
```

**Sub-phase C — DIVERT_CLOSE:**

```
1. Switch DV1 back to BYPASS position
   (Water now returns to reservoir via bypass)
2. Wait 2 seconds for flow to settle in collection tank
3. Record final values (stabilized):
   - F2 (Scale): final_weight (wait for scale reading to stabilize ±0.010 kg)
   - F1 (EM Meter): final_totalizer
   - DUT: final_totalizer (RS485 read from addr=20)
          OR prompt manual AFTER reading on touch LCD (if DUT mode='manual')
          Manual validation: after_reading > before_reading, reasonable range
4. Record: divert_end_timestamp
```

| Exit | → CALCULATE |
|------|-------------|

---

#### 7.5.4 State: CALCULATE

| Calculation | Formula |
|-------------|---------|
| Reference Volume | `ref_volume_L = (final_weight - tare_weight) / water_density(temperature_C)` |
| | Density from ISO 4064 lookup table. Example: 20°C → 0.99820 kg/L, 25°C → 0.99705 kg/L |
| DUT Volume | `dut_volume_L = final_dut_totalizer - start_dut_totalizer` |
| | For manual mode: `after_reading - before_reading` |
| Error % | `error_pct = ((dut_volume - ref_volume) / ref_volume) × 100` |
| Pass/Fail | `abs(error_pct) ≤ mpe_pct` → **PASS**, else → **FAIL** |
| | MPE from ISO 4064: ±5% for Q1 (lower zone), ±2% for Q2–Q4+ (upper zone) |

**Store:** Save `TestResult` record with all values:

```python
TestResult(
    test=test,
    q_point='Q3',                    # Current Q-point
    target_flow_lph=100.0,           # From ISO 4064 fixture
    actual_flow_lph=99.5,            # Average flow during collection
    ref_volume_l=10.050,             # Gravimetric reference (weight/density)
    dut_volume_l=10.120,             # DUT totalizer difference
    error_pct=0.696,                 # ((10.120-10.050)/10.050)×100
    mpe_pct=2.0,                     # From ISO 4064 (upper zone)
    passed=True,                     # |0.696| ≤ 2.0
    pressure_up_bar=2.5,             # Upstream pressure during test
    pressure_dn_bar=2.3,             # Downstream pressure during test
    temperature_c=22.1,              # Water temperature during test
    duration_s=360,                  # Seconds from divert_open to divert_close
    weight_kg=10.032,                # Net weight collected
    zone='Upper',                    # ISO 4064 zone classification
)
```

**Send to Lab:** If LoRa active, send individual Q-point `TEST_RESULT` via ASP. Lab stores and updates live monitor.

| Exit | → DRAIN |
|------|---------|

---

#### 7.5.5 State: DRAIN

| Aspect | Detail |
|--------|--------|
| Hardware | B1 → B2 GPIO: Open DRN (drain valve). Monitor scale weight via F2. Wait for weight to return to near-tare (±0.050 kg). Close DRN. |
| Duration | Depends on collected volume. Small Q-points (Q1: ~1L) drain fast. Large Q-points (Q4: ~100L) take longer. |
| Timeout | 120 seconds. If weight doesn't return → ERROR: "Drain timeout. Check drain valve." |
| Exit | → NEXT_POINT |

---

#### 7.5.6 State: NEXT_POINT

| Aspect | Detail |
|--------|--------|
| Logic | If current Q-point < Q8: increment to next Q-point. Pump stays running (no restart). → FLOW_STABILIZE with new target flow rate. |
| | If current Q-point = Q8: all points complete. → COMPLETE. |
| UI Update | Touch LCD: Q-point stepper advances. Green checkmark on completed points (pass) or red × (fail). Lab: updated via LoRa. |

---

### 7.6 State: COMPLETE

| Aspect | Detail |
|--------|--------|
| Pump Stop | B1 → B3 → VFD: Write stop command (register `0x2000`=`0x0005`). Wait for VFD stopped status. |
| Valves | Close all ball valves (BV1, BV2, BV3). DV1 to BYPASS. DRN closed. |
| Calculate Overall | `overall_pass = all 8 TestResult.passed are True`. Update Test record: `status='completed'`, `overall_pass=T/F`, `completed_at=now()`. |
| Tower Light | PASS: GREEN blink 3× then steady. FAIL: RED blink 3× then steady. |
| Touch UI | Show verdict banner: green "PASSED" or red "FAILED". Navigate to Results tab with Q-point result cards. |
| Lab Notification | If LoRa active: send `TEST_COMPLETE` message with `overall_pass` and summary of all 8 Q-points. |
| Certificate | If passed and operator has permission: generate certificate PDF. Otherwise pending manager approval (lab side). |
| Exit | → IDLE. System ready for next test. |

---

### 7.7 State: EMERGENCY_STOP

| Aspect | Detail |
|--------|--------|
| **Triggers** | **(a)** Hardware E-stop: contactor drops (B2 GPIO detects aux contact change). **(b)** Software: touch UI ABORT button, safety watchdog interlock violation, lab `EMERGENCY_STOP` command via LoRa. |
| **Hardware E-Stop** | Hardwired. Contactor coil breaks. VFD + pump + 24V rail lose power **instantly**. Valves spring-return to closed. **NO SOFTWARE INVOLVED.** B2 GPIO just detects it happened after the fact. |
| **Software E-Stop** | B1→B3: VFD emergency stop command. B1→B2 GPIO: close all valves, DV1 to bypass. Set `test.status='aborted'`. Log event with timestamp and reason. |
| **Safety Watchdog** | Runs every 200ms. Triggers software E-stop if: pressure > 8.0 bar, scale > 180 kg, temp outside 5–40°C, reservoir < 20%, any ESP32 communication timeout (>2 seconds). |
| **Tower Light** | RED steady. |
| **Touch UI** | Red blinking banner: "EMERGENCY STOP ACTIVE". Requires manual reset from touch UI to return to IDLE. |
| **Lab Notify** | If LoRa active: send `EMERGENCY_STOP` notification with reason code. |

---

### 7.8 State: ERROR (Recoverable)

| Aspect | Detail |
|--------|--------|
| Triggers | Non-critical failures: valve jam, sensor timeout, VFD fault (non-dangerous), scale tare failure, flow stability timeout, drain timeout. |
| Action | Pump remains at current state (not stopped unless dangerous). Touch UI shows orange error banner with specific message and "Retry" / "Abort" buttons. |
| Retry | Operator taps "Retry" → re-enters the failed state. Up to 3 retries per state. |
| Abort | Operator taps "Abort" → EMERGENCY_STOP sequence → IDLE. |
| Tower Light | YELLOW blink. |

---

## 8. Scenario 4 — Lab Receives Test Results

| # | Component | Action |
|---|-----------|--------|
| 1 | Bench Django | After each Q-point CALCULATE: packages individual `TestResult` as ASP message. Sends via B4 → LoRa → L1 → L2 → L3. |
| 2 | Lab Django (L3) | Receives each Q-point result. Decrypts, verifies. Stores `TestResult` in Lab DB. Updates dashboard (HTMX polling 2s picks up changes). |
| 3 | Bench Django | After Q8 COMPLETE: sends `TEST_COMPLETE` summary (overall_pass, all 8 points summary, timestamps). |
| 4 | Lab Django | Receives `TEST_COMPLETE`. Updates Test record: `status='completed'`. Sets `approval_status='pending'`. |
| 5 | Lab Portal | Dashboard shows notification badge. Manager sees "Pending Approval" in queue. |
| 6 | Lab Manager | Reviews Q1–Q8 results in Lab Portal. Views error curve chart (error % vs Q-point). Clicks Approve or Reject (with comments). |
| 7 | Lab Django | If approved: generates certificate PDF (reports app). Assigns certificate number (format: `IIITB-YYYYMMDD-NNNN`). Available for download. Sends approval status back to bench via LoRa. |
| 8 | Bench Django | Receives approval. Updates local Test record. Certificate available on bench too. |

### Selective Retransmission

If the lab misses any Q-point result (detected by gap in sequence), it sends a `RESULT_REQUEST`
message specifying the missing Q-point numbers. Bench retransmits only those specific results.
3 retry attempts before marking `COMM_FAILURE` on that Q-point (operator can manually sync later).

---

## 9. Scenario 5 — Emergency Stop

### 9.1 Hardware E-Stop (Primary — No Software)

```
Physical mushroom-head E-stop button
    │
    └── NC (Normally Closed) contact in series with contactor coil
        │
        └── Contactor drops out
            │
            ├── 415V cut → VFD loses power → Pump stops immediately
            ├── 24V cut → Valve solenoids de-energize → Spring-return to CLOSED
            ├── Exhaust fan stops
            │
            └── 5V rail STAYS powered (RPi5, ESP32s, Touch LCD remain on)
                │
                └── B2 GPIO detects contactor aux contact → LOW
                    │
                    └── Software logs event, updates UI "E-STOP ACTIVE",
                        sets test.status='aborted', notifies Lab via LoRa.
                        But the shutdown already happened electrically.
```

### 9.2 Software E-Stop (Secondary)

```
Touch UI "ABORT" button
    │
    ├── WebSocket → Django Channels → Test Engine
    │
    └── Test Engine executes:
        ├── B1→B3→Bus 2→VFD: Emergency stop command (reg 0x2000=0x0003)
        ├── B1→B2 GPIO: Close BV1, BV2, BV3, DRN
        ├── B1→B2 GPIO: DV1 to BYPASS
        ├── Set test.status='aborted', log reason="Operator abort"
        └── Notify Lab via LoRa (if active)
```

### 9.3 Safety Watchdog Auto-Trigger

Runs every 200ms during any active test state. Triggers software E-stop if:

| Condition | Threshold | Reason Code |
|-----------|-----------|-------------|
| Upstream pressure too high | > 8.0 bar | `PRESSURE_HIGH` |
| Scale overloaded | > 180 kg | `SCALE_OVERLOAD` |
| Temperature too low | < 5°C | `TEMP_LOW` |
| Temperature too high | > 40°C | `TEMP_HIGH` |
| Reservoir level too low | < 20% | `RESERVOIR_LOW` |
| B2 communication timeout | > 2 seconds no response | `B2_COMM_TIMEOUT` |
| B3 communication timeout | > 2 seconds no response | `B3_COMM_TIMEOUT` |
| Contactor aux contact lost | GPIO goes LOW | `POWER_LOST` |

### 9.4 Lab-Initiated Emergency Stop

```
Lab Portal → "EMERGENCY STOP" button (available to ALL roles)
    │
    └── Lab Django → ASP message {command: EMERGENCY_STOP, reason: "Lab operator"}
        → L3→L2→L1 → LoRa → B4→B1
        │
        └── Bench Django treats same as local software E-stop:
            VFD stop, valves close, test aborted.
```

---

## 10. Scenario 6 — Real-Time Monitoring

### 10.1 Bench Side (WebSocket — True Real-Time)

During an active test, every PID cycle (200ms), the sensor manager publishes readings to a
Redis channel. Django Channels WebSocket consumer pushes to the touch LCD browser.

```
Test Engine (asyncio task)
    │ every 200ms
    ├── Read all sensors (B2 Bus 1 + B3 Bus 2)
    ├── Store SensorReading in DB (5Hz time-series)
    ├── Publish to Redis channel: "test.{test_id}.sensors"
    │
    └── Django Channels Consumer
        │
        └── WebSocket push to Touch LCD browser
            │
            └── Alpine.js updates gauges with smooth needle animation:
                ├── Flow rate gauge (current value + target line)
                ├── Pressure gauge (upstream bar + downstream bar)
                ├── Temperature display (°C)
                ├── VFD frequency display (Hz)
                ├── PID output display (Hz)
                ├── Scale weight (real-time accumulation, kg)
                ├── Q-point stepper (Q1 ✓ Q2 ✓ Q3 ● Q4 ○ ... Q8 ○)
                └── State indicator (FLOW_STABILIZE / COLLECTING / etc.)
```

### 10.2 Lab Side (HTMX Polling — Near Real-Time)

Lab does NOT get 200ms data. LoRa bandwidth limits updates to periodic summaries.

```
Lab Portal Browser
    │
    ├── HTMX polls every 2 seconds:
    │   GET /api/tests/{id}/status/
    │
    ├── Lab Django responds with latest data received via LoRa:
    │   {
    │     "status": "running",
    │     "current_q_point": "Q3",
    │     "current_state": "COLLECTING",
    │     "flow_rate_lph": 100.2,
    │     "pressure_up_bar": 2.5,
    │     "temperature_c": 22.1,
    │     "weight_kg": 5.230,
    │     "updated_at": "2026-02-13T14:30:22Z"
    │   }
    │
    └── Browser updates:
        ├── Test status badge (Running / Completed / etc.)
        ├── Current Q-point indicator
        ├── Current state name
        └── Basic sensor readings (updated every ~5 seconds via LoRa)
```

Bench sends `TEST_STATUS` via LoRa every **5 seconds** during active test.

### 10.3 Tower Light States

| System State | Tower Light | Touch LCD Status Strip |
|-------------|-------------|------------------------|
| IDLE / Ready | GREEN steady | Green: "System Ready" |
| PRE_CHECK running | YELLOW blink | Yellow: "Running pre-checks..." |
| PRE_CHECK failed | RED steady (3s) → off | Red: "Pre-check failed: [reason]" |
| Test Running (Q-loop) | YELLOW steady | Blue: "TEST RUNNING — Q3 Flow Stabilize" |
| COMPLETE — PASS | GREEN blink 3× → steady | Green: "TEST COMPLETE — PASSED" |
| COMPLETE — FAIL | RED blink 3× → steady | Red: "TEST COMPLETE — FAILED" |
| ERROR (recoverable) | YELLOW blink | Orange: "ERROR — [message]. Tap to retry." |
| EMERGENCY_STOP | RED steady | Red blink: "EMERGENCY STOP ACTIVE" |

---

## 11. Communication Protocol Reference

### 11.1 USB Serial (RPi5 ↔ ESP32)

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 |
| Format | 8N1 |
| Protocol | JSON command/response |

**Command format:**

```json
{"cmd": "MB_READ", "bus": 1, "addr": 1, "reg": 0, "count": 2}
{"cmd": "MB_WRITE", "bus": 1, "addr": 1, "reg": 0, "value": 100}
{"cmd": "GPIO_SET", "pin": "BV1", "state": 1}
{"cmd": "GPIO_GET", "pin": "BV1"}
{"cmd": "VALVE", "valve": "BV1", "action": "OPEN"}
{"cmd": "DIVERTER", "position": "COLLECT"}
{"cmd": "STATUS"}
```

**Response format:**

```json
{"ok": true, "data": {"value": 123.45}}
{"ok": false, "error": "TIMEOUT", "message": "No response from addr 1"}
```

### 11.2 RS485 Bus 1 (B2 ↔ Sensors + DUT)

| Parameter | Value |
|-----------|-------|
| Baud rate | 9600 |
| Protocol | Modbus RTU |
| Parity | None (8N1) |

| Device | Address | Key Registers |
|--------|---------|---------------|
| EM Flow Meter | 1 | Flow rate (L/h), Totalizer (L), Status |
| Weighing Scale | 2 | Weight (kg), Tare command, Status |
| 4-20mA Module | 3 | Ch1: Upstream pressure, Ch2: Downstream pressure, Ch3: Temperature |
| DUT (meter under test) | 20 (configurable) | Totalizer (L) |

### 11.3 RS485 Bus 2 (B3 ↔ VFD)

| Parameter | Value |
|-----------|-------|
| Baud rate | 9600 |
| Protocol | Modbus RTU |
| Isolation | Electrically isolated bus (VFD noise protection) |

| Device | Address | Key Registers |
|--------|---------|---------------|
| VFD Delta VFD022EL43A | 1 | `0x2000`: Control word (0x0001=Run, 0x0003=E-Stop, 0x0005=Stop) |
| | | `0x2001`: Frequency setpoint (Hz × 100) |
| | | `0x2103`: Actual output frequency (Hz × 100) |
| | | `0x2104`: Actual output current (A × 100) |
| | | `0x2100`: Status word |
| | | `0x2105`: Fault code |

### 11.4 LoRa (L1 ↔ B4 via ASP)

| Parameter | Value |
|-----------|-------|
| Frequency | 865 MHz (IN865 band for India) |
| Chip | SX1262 (RA-01SH module) |
| Spreading Factor | SF10 (configurable SF7–SF12) |
| Bandwidth | 125 kHz |
| Coding Rate | 4/5 |
| TX Power | +22 dBm |
| Preamble | 8 symbols |
| Max LoRa payload | 255 bytes |
| Encryption | AES-256-CBC (16-byte IV prepended) |
| Authentication | HMAC-SHA256 (32-byte tag appended) |
| Replay protection | Sequence number (2 bytes, monotonically increasing) |
| Fragmentation | Payloads > ~200 bytes split into fragments |
| ACK timeout | 3 seconds |
| Max retries | 3 |

### 11.5 B2 GPIO Pin Map

| Function | Type | Notes |
|----------|------|-------|
| BV1 (DN25 valve) | Digital OUT (relay) | Line select |
| BV2 (DN20 valve) | Digital OUT (relay) | Line select |
| BV3 (DN15 valve) | Digital OUT (relay) | Line select |
| DV1+ (diverter +) | Digital OUT (relay) | Polarity pair for 3-way |
| DV1- (diverter -) | Digital OUT (relay) | Polarity pair for 3-way |
| DRN (drain valve) | Digital OUT (relay) | Collection tank drain |
| Tower RED | Digital OUT | Tower light |
| Tower YELLOW | Digital OUT | Tower light |
| Tower GREEN | Digital OUT | Tower light |
| E-Stop Monitor | Digital IN | Contactor aux contact (NC) |
| BV1 Position | Digital IN (optional) | Valve feedback |
| BV2 Position | Digital IN (optional) | Valve feedback |
| BV3 Position | Digital IN (optional) | Valve feedback |

*(GPIO pin numbers TBD — will be assigned during B2 firmware development)*

---

## 12. Data Storage & Sync

| Data | Bench DB | Lab DB | Sync Method |
|------|----------|--------|-------------|
| TestMeter registration | Yes (primary) | Yes (mirror) | LoRa ASP (meter info included in `START_TEST` request) |
| Test record | Yes (primary) | Yes (mirror) | LoRa ASP (status updates + completion) |
| TestResult (Q-points) | Yes (primary) | Yes (mirror) | LoRa ASP (per Q-point result + completion summary) |
| ISO4064Standard | Pre-loaded fixture | Pre-loaded fixture | Same JSON fixture loaded on both sides |
| SensorReading (5Hz) | Yes (time-series) | No | Not synced. Bench-only. Used for PID tuning + diagnostics. |
| Certificate PDF | Generated after approval | Generated after approval | Both can generate independently once approval is synced |
| User accounts | Independent | Independent | Not synced. Each side manages own users. |
| Audit log | Independent | Independent | Each side logs own actions. |

---

## 13. LoRa Message Types

| Message Type | Direction | Trigger | Payload Summary |
|-------------|-----------|---------|-----------------|
| `START_TEST` | Lab → Bench | Technician creates test | meter info, Q-point params, DUT mode |
| `START_TEST_ACK` | Bench → Lab | Bench receives START_TEST | test_id, status=acknowledged |
| `TEST_STATUS` | Bench → Lab | Every 5s during test | q_point, state, flow, pressure, temp |
| `TEST_RESULT` | Bench → Lab | After each Q-point | q_point, error_pct, passed, all measurements |
| `TEST_COMPLETE` | Bench → Lab | After Q8 done | overall_pass, summary of all 8 points |
| `RESULT_REQUEST` | Lab → Bench | Missing Q-point detected | list of missing Q-point numbers |
| `EMERGENCY_STOP` | Lab → Bench | Lab operator presses abort | reason string |
| `EMERGENCY_ACK` | Bench → Lab | Bench processes E-stop | status=aborted, reason |
| `APPROVAL_STATUS` | Lab → Bench | Manager approves/rejects | approval_status, certificate_number |
| `HEARTBEAT` | Bidirectional | Every 30s when idle | device_id, uptime, status |

---

## 14. Key Design Principles

1. **Bench is standalone**: Operates with zero lab connectivity. All hardware control is local to bench RPi5. Lab is a convenience layer, not a dependency.
2. **Lab never controls hardware**: Lab only sends requests (`START_TEST`, `EMERGENCY_STOP`) and receives results. No direct valve/pump/sensor commands ever traverse the LoRa link.
3. **Gravimetric reference**: Primary reference volume measured by weight (200 kg scale), not by EM flow meter. EM meter is for PID feedback and cross-check only.
4. **ISO 4064 compliance**: All 8 Q-points (Q1–Q8), MPE values (±5% lower zone, ±2% upper zone), water density correction by temperature, test procedures follow the standard.
5. **Defense in depth**: Hardware E-stop (electrical, no software in loop) → Software safety watchdog (200ms) → PID output clamping (5–50 Hz) → Valve mutual exclusion interlocks.
6. **Encrypted communication**: All LoRa traffic AES-256-CBC encrypted, HMAC-SHA256 authenticated, sequence-numbered for replay protection.
7. **Single codebase, dual deployment**: One Django project with shared apps (`accounts`, `meters`, `testing`, `comms`, `reports`, `audit`). Side-specific apps: `controller` + `bench_ui` (bench only), `lab_ui` (lab only). Configured via `settings_bench.py` / `settings_lab.py`.
8. **Graceful degradation**: If LoRa link goes down, bench continues testing without interruption. Results are queued and synced when link recovers.
