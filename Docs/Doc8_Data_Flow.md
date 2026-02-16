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
| Hardware Control | Full (VFD, valves, sensors, PID, safety) via 5 ESP32 nodes | **NONE** — never directly controls hardware |
| Connectivity Required | None (standalone) | LoRa link to Bench (graceful degradation if down) |
| Django Settings | `config.settings_bench` | `config.settings_lab` |
| RPi5 Unit | B1 | L3 |
| Database | `db_bench.sqlite3` (primary) | `db_lab.sqlite3` (mirror) |
| Real-time | WebSocket via Django Channels (200ms) | HTMX polling (2s) |
| Communication | Via B4 LinkMaster (LoRa 865MHz ASP) | Via L1 LinkMaster (LoRa 865MHz ASP) |
| Host ↔ ESP32 | USB → Waveshare 8-CH RS485 Hub → 5 ESP32 nodes | USB Serial → L2 → RS485 → L1 |

---

## 2. Physical Architecture

```
╔════════════════════════════════════════════════════════════════════════════╗
║                             LAB BUILDING                                  ║
║                                                                            ║
║  ┌───────────────────────────────────────────────────────────┐            ║
║  │                L3: RPi5 — Lab Server                       │            ║
║  │  Django (settings_lab) │ db_lab.sqlite3 │ Ethernet LAN     │            ║
║  │                        │ USB Serial                        │            ║
║  │            ┌───────────┴────────────┐                      │            ║
║  │            │ L2: ESP32 RS485 Bridge  │  Indoor              │            ║
║  │            │ USB ↔ RS485 transparent │                      │            ║
║  │            └───────────┬────────────┘                      │            ║
║  │                        │ RS485                              │            ║
║  │            ┌───────────┴────────────┐                      │            ║
║  │            │ L1: ESP32 + RA-01SH    │  Rooftop              │            ║
║  │            │ Lab LinkMaster          │                      │            ║
║  │            │ LoRa ↔ RS485 gateway   │                      │            ║
║  │            └───────────┬────────────┘                      │            ║
║  └────────────────────────┼────────────────────────────────────┘           ║
║                           │                                                ║
╚═══════════════════════════╪════════════════════════════════════════════════╝
                            │  LoRa 865 MHz — ASP Encrypted (AES-256-CBC + HMAC-SHA256)
                    ~~~~~~~~│~~~~~~~~ Air Gap (200m+) ~~~~~~~~~~~~~~~~~~~~~~~~~~
                            │
╔═══════════════════════════╪════════════════════════════════════════════════╗
║                           │        TEST BENCH BUILDING                     ║
║                           │                                                ║
║   ┌───────────────────────┴─────────────────────┐  Rooftop                ║
║   │  B4: ESP32 + RA-01SH  (Node 14)             │                         ║
║   │  Bench LinkMaster — LoRa ↔ RS485            │                         ║
║   └───────────────────────┬─────────────────────┘                         ║
║                           │ RS485 (Hub Ch 5)                               ║
║                           │                                                ║
║   ┌───────────────────────┴──────────────────────────────────────────┐    ║
║   │                    B1: RPi5 — Bench Controller                    │    ║
║   │  Django (settings_bench) + Test Engine + PID + Safety             │    ║
║   │  7" HDMI Touch LCD (Chromium kiosk) │ db_bench.sqlite3            │    ║
║   │                                                                    │    ║
║   │  USB ──→ [Waveshare USB-to-8CH-RS485 Hub (CH348L)]               │    ║
║   │           8 independent electrically-isolated RS485 channels       │    ║
║   │           ├── Ch 1 ── Ch 2 ── Ch 3 ── Ch 4 ── Ch 5              │    ║
║   │           │                                    └── B4 (above)     │    ║
║   └───────────┼──────┼──────┼──────┼─────────────────────────────────┘    ║
║               │      │      │      │                                       ║
║   ┌───────────┴──┐┌──┴───────────┐┌┴─────────────┐┌─────────────────────┐║
║   │ B2: Sensor   ││ B3: VFD      ││ B5: DUT      ││ B6: GPIO Controller ││
║   │ Bridge       ││ Bridge       ││ Bridge       ││ (Node 13)           ││
║   │ (Node 10)    ││ (Node 11)    ││ (Node 12)    ││                     ││
║   │              ││              ││              ││ Relay OUT:          ││
║   │ ↓ Downstream ││ ↓ Downstream ││ ↓ Downstream ││  SV1, BV-L1/L2/L3  ││
║   │   RS485 Bus  ││   RS485 Bus  ││   RS485      ││  DV1, SV-DRN       ││
║   │              ││   (isolated) ││              ││  Tower R/Y/G        ││
║   │ ├ EM    (1)  ││              ││ └ DUT  (20)  ││ Digital IN:         ││
║   │ ├ Scale (2)  ││ └ VFD   (1)  ││   (or manual)││  ESTOP_MON         ││
║   │ └ 4-20mA(3)  ││              ││              ││ I2C: BME280         ││
║   │              ││              ││              ││ Analog: RES-LVL     ││
║   └──────────────┘└──────────────┘└──────────────┘│ 1-Wire: RES-TEMP   ││
║                                                    └─────────────────────┘║
║                                                                            ║
║   Hardwired (NO software):           F6: Pump Kirloskar 3HP              ║
║   ├─ E-Stop Button → Contactor (NC)  (3-phase via VFD, no software)      ║
║   ├─ Contactor (415V + 24V rail)                                          ║
║   └─ Exhaust Fan (direct MCB)                                             ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
```

### 2.1 RS485 Hub Architecture

The Bench RPi5 (B1) connects to all 5 ESP32 nodes via a **single USB cable** to a
**Waveshare USB-to-8CH-RS485** converter module:

| Parameter | Value |
|-----------|-------|
| Module | Waveshare USB TO 8CH RS485 |
| Chip | CH348L (8-port UART to USB) |
| Channels | 8 independent, electrically-isolated RS485 |
| Connector | USB-A (to RPi5) |
| OS Driver | Standard CH348 (built into Linux 6.x) |
| Appears as | `/dev/ttyACM0` through `/dev/ttyACM7` (or `/dev/ttyUSB0-7`) |
| Baud rate | 115200 (per channel, configurable) |
| Isolation | Each channel independently isolated (500V) |

**Channel Assignments:**

| Hub Channel | Node | Udev Symlink | Purpose |
|-------------|------|--------------|---------|
| Ch 1 | B2 (Sensor Bridge) | `/dev/ttyB2_SENSOR` | EM, Scale, 4-20mA |
| Ch 2 | B3 (VFD Bridge) | `/dev/ttyB3_VFD` | VFD Delta (isolated) |
| Ch 3 | B5 (DUT Bridge) | `/dev/ttyB5_DUT` | Device Under Test |
| Ch 4 | B6 (GPIO Controller) | `/dev/ttyB6_GPIO` | Valves, tower, sensors |
| Ch 5 | B4 (LoRa LinkMaster) | `/dev/ttyB4_LORA` | Rooftop LoRa gateway |
| Ch 6 | — (spare) | — | Future expansion |
| Ch 7 | — (spare) | — | Future expansion |
| Ch 8 | — (spare) | — | Future expansion |

Each channel is point-to-point (one RPi5 port ↔ one ESP32). No addressing
needed on the upstream link — the RPi5 identifies each node by its serial port.
Node IDs (10–14) are included in STATUS responses for verification.

---

## 3. Unit Reference

| ID | Node ID | Unit | Location | Role |
|----|---------|------|----------|------|
| L1 | — | Lab LinkMaster | Lab rooftop | ESP32 + RA-01SH (SX1262, 865 MHz). LoRa ↔ RS485 gateway. |
| L2 | — | Lab RS485 Bridge | Lab indoor | ESP32. USB ↔ RS485 transparent byte bridge to L1. |
| L3 | — | Lab RPi5 | Lab indoor | Django web portal. Accessed via LAN by lab staff. |
| B1 | — | Bench RPi5 + Touch LCD | Bench indoor | Main controller. Django + test engine. USB → Waveshare 8-CH RS485 Hub → 5 ESP32 nodes. 7" HDMI kiosk. |
| B2 | 10 | Sensor Bridge ESP32 | Bench | Hub Ch 1. Downstream RS485 Modbus: EM (addr 1), Scale (addr 2), 4-20mA (addr 3). |
| B3 | 11 | VFD Bridge ESP32 | Bench | Hub Ch 2. Downstream RS485 Modbus: VFD Delta (addr 1). Electrically isolated bus. |
| B4 | 14 | Bench LinkMaster | Bench rooftop | Hub Ch 5. ESP32 + RA-01SH (SX1262, 865 MHz). LoRa ↔ RS485 gateway. |
| B5 | 12 | DUT Bridge ESP32 | Bench | Hub Ch 3. Downstream RS485 Modbus: DUT meter (addr 20, configurable). |
| B6 | 13 | GPIO Controller ESP32 | Bench | Hub Ch 4. All valve relays (SV1, BV-L1/L2/L3, DV1, SV-DRN), tower light (R/Y/G), E-stop monitor, BME280 (ATM-TEMP/HUM/BARO), RES-LVL, RES-TEMP. |

---

## 4. Field Devices & I/O Map

### 4.1 Modbus RS485 Devices

| Device ID | Device | Interface | Modbus Addr | Connected To | Notes |
|-----------|--------|-----------|-------------|--------------|-------|
| FT-01 | EM Flow Meter DN25 (±0.5%) | RS485 Modbus RTU | 1 | B2 downstream bus | Flow rate (L/h), totalizer (L), status |
| WT-01 | Weighing Scale 200 kg | RS485 Modbus RTU | 2 | B2 downstream bus | Weight (kg), tare command, status |
| — | 4-20mA Modbus Module (3-ch) | RS485 Modbus RTU | 3 | B2 downstream bus | Ch1: PT-01, Ch2: PT-02, Ch3: water temp |
| PT-01 | Pressure Transmitter (upstream) | 4-20 mA analog | Module Ch 1 | Via 4-20mA module | 0–10 bar range |
| PT-02 | Pressure Transmitter (downstream) | 4-20 mA analog | Module Ch 2 | Via 4-20mA module | 0–10 bar range |
| P-01 | VFD Delta VFD022EL43A | RS485 Modbus RTU | 1 | B3 downstream bus (isolated) | Pump speed control, registers 0x2000–0x2105 |
| DUT | Device Under Test | RS485 Modbus RTU | 20 (configurable) | B5 downstream bus | Totalizer reading, or manual entry via Touch UI |

### 4.2 B6 GPIO Outputs (Relay-Driven Actuators)

| Device ID | Device | Type | B6 GPIO | Notes |
|-----------|--------|------|---------|-------|
| SV1 | Main Line Solenoid Valve | Relay (active HIGH) | GPIO 32 | Opens/closes flow to test section |
| BV-L1 | Ball Valve DN25 (1" lane) | Relay (active HIGH) | GPIO 25 | Lane select — DN25 meters |
| BV-L2 | Ball Valve DN20 (3/4" lane) | Relay (active HIGH) | GPIO 26 | Lane select — DN20 meters |
| BV-L3 | Ball Valve DN15 (1/2" lane) | Relay (active HIGH) | GPIO 27 | Lane select — DN15 meters |
| DV1+ | Diverter Valve (COLLECT) | Relay pulse | GPIO 33 | Pulse HIGH → COLLECT position |
| DV1- | Diverter Valve (BYPASS) | Relay pulse | GPIO 23 | Pulse HIGH → BYPASS position |
| SV-DRN | Drain Solenoid Valve | Relay (active HIGH) | GPIO 14 | Collection tank drain |
| TOWER-R | Tower Light Red | Digital OUT | GPIO 12 | Status indicator |
| TOWER-Y | Tower Light Yellow | Digital OUT | GPIO 18 | Status indicator |
| TOWER-G | Tower Light Green | Digital OUT | GPIO 19 | Status indicator |

### 4.3 B6 GPIO Inputs

| Device ID | Device | Type | B6 GPIO | Notes |
|-----------|--------|------|---------|-------|
| CONT | E-Stop Monitor | Digital IN (active LOW) | GPIO 35 | Contactor aux contact (NC circuit). LOW = power lost. |
| BV-L1_FB | Valve DN25 Feedback | Digital IN (optional) | GPIO 36 | Position confirmation |
| BV-L2_FB | Valve DN20 Feedback | Digital IN (optional) | GPIO 39 | Position confirmation |
| BV-L3_FB | Valve DN15 Feedback | Digital IN (optional) | GPIO 34 | Position confirmation |

### 4.4 B6 Environmental Sensors

| Device ID | Device | Interface | B6 Pins | Notes |
|-----------|--------|-----------|---------|-------|
| ATM-TEMP | Atmospheric Temperature | I2C (BME280) | SDA=21, SCL=22 | BME280 addr 0x76 |
| ATM-HUM | Atmospheric Humidity | I2C (BME280) | (shared) | Same BME280 sensor |
| ATM-BARO | Atmospheric Pressure | I2C (BME280) | (shared) | Same BME280 sensor |
| RES-TEMP | Reservoir Temperature | 1-Wire (DS18B20) | DATA=15 | Waterproof probe |
| RES-LVL | Reservoir Level | Ultrasonic (HC-SR04) | TRIG=13, ECHO=5 | Percentage level (0–100%) |

### 4.5 Non-Software Devices

| Device ID | Device | Interface | Notes |
|-----------|--------|-----------|-------|
| BV-BP | Bypass Ball Valve | Manual | Currently manual. Future: electric actuator. |
| MCB | Main Circuit Breaker | Hardwired | Panel-mounted. No software control. |
| CONT | Contactor | Hardwired | E-stop breaks coil → all power cut (415V + 24V). 5V stays for RPi5/ESP32. |
| — | E-Stop Button | Hardwired NC | Mushroom-head. NC contact in series with contactor coil. |
| — | Exhaust Fan | Direct MCB | No software control. |
| F6 | Pump Kirloskar 3HP | 3-phase via VFD | No direct software interface. Controlled indirectly via VFD on B3. |

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
| 7 | B4 → Hub Ch5 → B1 | B4 receives LoRa, forwards via RS485 (Hub Ch 5) to Bench Django on B1. |
| 8 | Bench Django (B1) | Verifies HMAC signature. Decrypts AES payload. Checks sequence number (replay protection). Creates/mirrors Test record in Bench DB: `source='lab'`, `status='pending'`. |
| 9 | Bench Django (B1) | Sends ACK back: B1 → Hub Ch5 → B4 → LoRa → L1 → L2 → L3. |
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
runs as an asyncio task on B1. It orchestrates all hardware through:
- **B2** (sensors: EM, scale, 4-20mA)
- **B3** (VFD pump speed)
- **B5** (DUT meter reading)
- **B6** (valves, tower light, E-stop monitor, environmental sensors)

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
| Tower Light | B1 → B6: GREEN steady |
| Exit | → PRE_CHECK |

---

### 7.2 State: PRE_CHECK

| Aspect | Detail |
|--------|--------|
| Purpose | Validate all systems before starting. Prevent unsafe test starts. |
| Hardware Reads | B1→B2: Poll EM status, scale status, 4-20mA module status. B1→B3: Poll VFD status + fault code. B1→B5: Poll DUT communication (if RS485 mode). B1→B6: Read E-stop monitor, read BME280, read RES-LVL, read RES-TEMP. |
| Tower Light | B1→B6: YELLOW blink during checks. GREEN flash if all pass. RED if any fail. |
| Exit (pass) | All checks pass → LINE_SELECT |
| Exit (fail) | Show error on touch UI with specific message, return to IDLE |

**Safety Checks Performed:**

| # | Check | Node | Threshold | Fail Action |
|---|-------|------|-----------|-------------|
| 1 | Contactor closed (power available) | B6 | ESTOP_MON GPIO = HIGH | BLOCK. "Power off. Check E-stop and contactor." |
| 2 | E-stop not active | B6 | ESTOP_MON GPIO = HIGH (NC circuit) | BLOCK. "E-stop is pressed. Release and reset." |
| 3 | EM meter responding | B2 | Modbus addr 1 responds | BLOCK. "EM flow meter offline. Check B2 sensor bus." |
| 4 | Weighing scale responding | B2 | Modbus addr 2 responds | BLOCK. "Weighing scale offline. Check B2 sensor bus." |
| 5 | 4-20mA module responding | B2 | Modbus addr 3 responds | BLOCK. "Pressure module offline. Check B2 sensor bus." |
| 6 | VFD responding, no faults | B3 | Modbus addr 1, fault=0 | BLOCK. "VFD fault. Check VFD panel." |
| 7 | Upstream pressure < max | B2 | < 8.0 bar (`SAFETY_PRESSURE_MAX`) | BLOCK. "High pressure. Check system." |
| 8 | Reservoir level > min | B6 | > 20% (`SAFETY_RESERVOIR_MIN`) | BLOCK. "Low reservoir. Refill before testing." |
| 9 | Scale weight reasonable | B2 | < 180 kg (`SAFETY_SCALE_MAX`) | BLOCK. "Scale overloaded. Empty collection tank." |
| 10 | Temperature in range | B6 | 5–40°C (`SAFETY_TEMP_MIN/MAX`) | BLOCK. "Temperature out of range." |
| 11 | DUT responding (RS485 mode) | B5 | Modbus addr 20 responds | BLOCK. "DUT meter offline. Check B5 DUT bus." |

---

### 7.3 State: LINE_SELECT

| Aspect | Detail |
|--------|--------|
| Purpose | Open the correct ball valve for the DUT meter size. |
| Hardware | B1 → B6 GPIO: Close BV-L1, BV-L2, BV-L3 (all off first). Then open one: DN25→BV-L1, DN20→BV-L2, DN15→BV-L3. Open SV1 (main line solenoid). |
| Interlock | Mutual exclusion: only one BV-Lx open at a time. Software enforces. Wait for GPIO position feedback (if available). |
| Diverter | B1 → B6 GPIO: DV1 confirmed in BYPASS position (water returns to reservoir during startup). |
| Timeout | 5 seconds (`SAFETY_VALVE_TIMEOUT`). If no position feedback → ERROR: "Valve jam. Check mechanical." |
| Exit | → PUMP_START |

---

### 7.4 State: PUMP_START

| Aspect | Detail |
|--------|--------|
| Hardware | B1 → B3 → VFD (addr=1): Write run command (register `0x2000`=`0x0001` Run Forward). Write initial frequency = 10 Hz (low start, register `0x2001`). |
| Confirmation | Read VFD status register. Wait for "running" flag. Read actual frequency from register `0x2103` ramping up. |
| Timeout | 10 seconds. If VFD doesn't confirm running → ERROR. |
| Tower Light | B1 → B6: YELLOW steady (test in progress from here until COMPLETE). |
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
1. READ:  B1 → B2 → Modbus addr 1 (EM Meter FT-01) → actual flow rate (L/h)
2. COMPARE: actual_flow vs target_flow (from ISO 4064 for current Q-point)
3. PID CALCULATE:
     error      = target_flow - actual_flow
     P          = Kp × error                    (Kp = 0.5)
     I          = Ki × ∫(error × dt)            (Ki = 0.1)
     D          = Kd × d(error)/dt              (Kd = 0.05)
     pid_output = P + I + D
     vfd_freq   = clamp(pid_output, 5.0, 50.0)  (PID_OUTPUT_MIN, PID_OUTPUT_MAX)
4. WRITE: B1 → B3 → VFD (addr=1) → set frequency (register 0x2001)
5. ALSO READ (for monitoring/logging):
     - B2 → addr 3 (4-20mA module): upstream pressure, downstream pressure, temperature
     - B2 → addr 2 (Scale WT-01): current weight
     - B6: BME280 (atmospheric), RES-LVL (reservoir), RES-TEMP (reservoir)
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
| Hardware | B1 → B2 → Modbus addr 2 (Scale WT-01): Send tare command. Read weight until stable at 0.000 ±0.020 kg. |
| Record | Store `tare_weight` and `tare_timestamp`. |
| Timeout | 5 seconds. If scale doesn't zero → ERROR: "Scale tare failed." |
| Exit | → MEASURE |

---

#### 7.5.3 State: MEASURE

Contains three sub-phases: **DIVERT_OPEN**, **COLLECTING**, and **DIVERT_CLOSE**.

**Sub-phase A — DIVERT_OPEN:**

```
1. Record start values:
   - DUT totalizer: B1 → B5 → Modbus addr 20 (if DUT mode='rs485')
                     OR prompt manual BEFORE reading on touch LCD (if DUT mode='manual')
                     Manual entry: large numeric keypad, validation (reasonable range)
   - EM meter totalizer: B1 → B2 → Modbus addr 1 (FT-01)
2. Switch diverter:
   B1 → B6 GPIO → DV1+ relay pulse → COLLECTION position
   (Water now flows into collection tank on weighing scale)
3. Record: divert_start_timestamp
```

**Sub-phase B — COLLECTING:**

```
Water flows through DUT into collection tank sitting on weighing scale.

Every 200ms (PID continues running):
  - B2 → addr 2 (Scale WT-01): read current weight
  - B2 → addr 1 (EM Meter FT-01): read flow rate + totalizer
  - B2 → addr 3 (4-20mA module): read pressures + temperature
  - B3 → VFD: PID continues maintaining target flow rate

Target weight calculation:
  target_weight_kg = target_volume_L × water_density(temperature_C)
  (Density lookup table per ISO 4064 Annex, e.g., 20°C → 0.99820 kg/L)

Continue until:
  current_weight ≥ target_weight → proceed to DIVERT_CLOSE
```

**Sub-phase C — DIVERT_CLOSE:**

```
1. Switch DV1 back to BYPASS position
   B1 → B6 GPIO → DV1- relay pulse → BYPASS position
   (Water now returns to reservoir via bypass)
2. Wait 2 seconds for flow to settle in collection tank
3. Record final values (stabilized):
   - B2 → addr 2 (Scale WT-01): final_weight (wait for reading to stabilize ±0.010 kg)
   - B2 → addr 1 (EM Meter FT-01): final_totalizer
   - DUT: B1 → B5 → addr 20: final_totalizer (RS485 read)
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

**Send to Lab:** If LoRa active, send individual Q-point `TEST_RESULT` via ASP (B1 → B4 → LoRa → L1 → L2 → L3). Lab stores and updates live monitor.

| Exit | → DRAIN |
|------|---------|

---

#### 7.5.5 State: DRAIN

| Aspect | Detail |
|--------|--------|
| Hardware | B1 → B6 GPIO: Open SV-DRN (drain valve). Monitor scale weight via B2 → addr 2 (WT-01). Wait for weight to return to near-tare (±0.050 kg). B1 → B6 GPIO: Close SV-DRN. |
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
| Valves | B1 → B6 GPIO: Close all ball valves (BV-L1, BV-L2, BV-L3). Close SV1. DV1 to BYPASS. SV-DRN closed. |
| Calculate Overall | `overall_pass = all 8 TestResult.passed are True`. Update Test record: `status='completed'`, `overall_pass=T/F`, `completed_at=now()`. |
| Tower Light | B1 → B6: PASS: GREEN blink 3× then steady. FAIL: RED blink 3× then steady. |
| Touch UI | Show verdict banner: green "PASSED" or red "FAILED". Navigate to Results tab with Q-point result cards. |
| Lab Notification | If LoRa active: send `TEST_COMPLETE` via B1 → B4 → LoRa → L1 → L2 → L3 with `overall_pass` and summary of all 8 Q-points. |
| Certificate | If passed and operator has permission: generate certificate PDF. Otherwise pending manager approval (lab side). |
| Exit | → IDLE. System ready for next test. |

---

### 7.7 State: EMERGENCY_STOP

| Aspect | Detail |
|--------|--------|
| **Triggers** | **(a)** Hardware E-stop: contactor drops (B6 GPIO detects ESTOP_MON change). **(b)** Software: touch UI ABORT button, safety watchdog interlock violation, lab `EMERGENCY_STOP` command via LoRa. |
| **Hardware E-Stop** | Hardwired. Contactor coil breaks. VFD + pump + 24V rail lose power **instantly**. Valve solenoids de-energize → spring-return to closed. **NO SOFTWARE INVOLVED.** B6 GPIO just detects it happened after the fact. |
| **Software E-Stop** | B1→B3: VFD emergency stop command. B1→B6 GPIO: close all valves (SV1, BV-L1/L2/L3, SV-DRN), DV1 to BYPASS. Set `test.status='aborted'`. Log event with timestamp and reason. |
| **Safety Watchdog** | Runs every 200ms. Triggers software E-stop if any threshold exceeded (see Section 9.3). |
| **Tower Light** | B1→B6: RED steady. |
| **Touch UI** | Red blinking banner: "EMERGENCY STOP ACTIVE". Requires manual reset from touch UI to return to IDLE. |
| **Lab Notify** | If LoRa active: send `EMERGENCY_STOP` notification via B4 with reason code. |

---

### 7.8 State: ERROR (Recoverable)

| Aspect | Detail |
|--------|--------|
| Triggers | Non-critical failures: valve jam, sensor timeout, VFD fault (non-dangerous), scale tare failure, flow stability timeout, drain timeout. |
| Action | Pump remains at current state (not stopped unless dangerous). Touch UI shows orange error banner with specific message and "Retry" / "Abort" buttons. |
| Retry | Operator taps "Retry" → re-enters the failed state. Up to 3 retries per state. |
| Abort | Operator taps "Abort" → EMERGENCY_STOP sequence → IDLE. |
| Tower Light | B1→B6: YELLOW blink. |

---

## 8. Scenario 4 — Lab Receives Test Results

| # | Component | Action |
|---|-----------|--------|
| 1 | Bench Django | After each Q-point CALCULATE: packages individual `TestResult` as ASP message. Sends via B1 → Hub Ch5 → B4 → LoRa → L1 → L2 → L3. |
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
                └── B6 GPIO detects contactor aux contact → ESTOP_MON = LOW
                    │
                    └── B1 polls B6 → detects ESTOP_MON LOW
                        → Software logs event, updates UI "E-STOP ACTIVE",
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
        ├── B1 → B3: VFD emergency stop command (reg 0x2000=0x0003)
        ├── B1 → B6 GPIO: Close SV1, BV-L1, BV-L2, BV-L3, SV-DRN
        ├── B1 → B6 GPIO: DV1 to BYPASS (DV1- pulse)
        ├── Set test.status='aborted', log reason="Operator abort"
        └── Notify Lab via LoRa (B1→B4, if active)
```

### 9.3 Safety Watchdog Auto-Trigger

Runs every 200ms during any active test state. Triggers software E-stop if:

| Condition | Node Polled | Threshold | Reason Code |
|-----------|-------------|-----------|-------------|
| Upstream pressure too high | B2 (4-20mA) | > 8.0 bar | `PRESSURE_HIGH` |
| Scale overloaded | B2 (Scale) | > 180 kg | `SCALE_OVERLOAD` |
| Water temperature too low | B2 (4-20mA) | < 5°C | `TEMP_LOW` |
| Water temperature too high | B2 (4-20mA) | > 40°C | `TEMP_HIGH` |
| Reservoir level too low | B6 (RES-LVL) | < 20% | `RESERVOIR_LOW` |
| B2 communication timeout | B2 | > 2 seconds no response | `B2_COMM_TIMEOUT` |
| B3 communication timeout | B3 | > 2 seconds no response | `B3_COMM_TIMEOUT` |
| B5 communication timeout | B5 | > 2 seconds no response | `B5_COMM_TIMEOUT` |
| B6 communication timeout | B6 | > 2 seconds no response | `B6_COMM_TIMEOUT` |
| Contactor aux contact lost | B6 (ESTOP_MON) | GPIO goes LOW | `POWER_LOST` |

### 9.4 Lab-Initiated Emergency Stop

```
Lab Portal → "EMERGENCY STOP" button (available to ALL roles)
    │
    └── Lab Django → ASP message {command: EMERGENCY_STOP, reason: "Lab operator"}
        → L3→L2→L1 → LoRa → B4 → Hub Ch5 → B1
        │
        └── Bench Django treats same as local software E-stop:
            VFD stop (B3), valves close (B6), test aborted.
```

---

## 10. Scenario 6 — Real-Time Monitoring

### 10.1 Bench Side (WebSocket — True Real-Time)

During an active test, every PID cycle (200ms), the sensor manager publishes readings to a
Redis channel. Django Channels WebSocket consumer pushes to the touch LCD browser.

```
Test Engine (asyncio task)
    │ every 200ms
    ├── Read sensors:
    │   ├── B2: EM flow (addr 1), Scale weight (addr 2), 4-20mA pressures (addr 3)
    │   ├── B3: VFD status + actual frequency
    │   ├── B6: E-stop monitor, BME280, RES-LVL, RES-TEMP
    │   └── B5: DUT totalizer (if RS485 mode, periodic read)
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

| System State | Tower Light (B6) | Touch LCD Status Strip |
|-------------|-------------------|------------------------|
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

### 11.1 Upstream: RPi5 ↔ ESP32 (via RS485 Hub)

All 5 ESP32 nodes communicate with B1 RPi5 through the Waveshare 8-CH RS485 hub.
Each hub channel is an independent, isolated RS485 link. Communication uses **JSON
command/response** over RS485 at 115200 baud.

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 |
| Format | 8N1 |
| Protocol | JSON lines (one JSON object per line, terminated by `\n`) |
| Direction | Half-duplex (RPi5 sends command, ESP32 responds) |
| Physical | RS485 (via hub channel). ESP32 uses UART2 + DE pin. |

**Command format (RPi5 → ESP32):**

```json
{"cmd": "MB_READ", "addr": 1, "reg": 0, "count": 2}
{"cmd": "MB_WRITE", "addr": 1, "reg": 0, "value": 100}
{"cmd": "GPIO_SET", "pin": "BV_L1", "state": 1}
{"cmd": "GPIO_GET", "pin": "ESTOP_MON"}
{"cmd": "VALVE", "valve": "BV_L1", "action": "OPEN"}
{"cmd": "DIVERTER", "position": "COLLECT"}
{"cmd": "TOWER", "r": 0, "y": 1, "g": 0}
{"cmd": "SENSOR_READ"}
{"cmd": "LORA_SEND", "data": "<base64>"}
{"cmd": "SET_ADDR", "addr": 20}
{"cmd": "STATUS"}
```

**Response format (ESP32 → RPi5):**

```json
{"ok": true, "data": {"value": 123.45}}
{"ok": true, "data": {"node_id": 10, "fw": "B2-Sensor-Bridge", "ver": "2.0.0", "uptime": 3600}}
{"ok": false, "error": "TIMEOUT", "message": "No response from addr 1"}
```

**Asynchronous events (ESP32 → RPi5, unsolicited):**

```json
{"event": "LORA_RX", "data": "<base64>", "rssi": -67, "snr": 9.5}
{"event": "ESTOP", "state": "ACTIVE"}
```

### 11.2 Node Command Sets

| Node | Supported Commands | Notes |
|------|--------------------|-------|
| B2 (Sensor Bridge) | `MB_READ`, `MB_WRITE`, `STATUS` | Downstream addresses: 1 (EM), 2 (Scale), 3 (4-20mA) |
| B3 (VFD Bridge) | `MB_READ`, `MB_WRITE`, `STATUS` | Downstream address: 1 (VFD Delta). Isolated bus. |
| B5 (DUT Bridge) | `MB_READ`, `MB_WRITE`, `SET_ADDR`, `STATUS` | Downstream address: 20 (configurable via SET_ADDR) |
| B6 (GPIO Controller) | `GPIO_SET`, `GPIO_GET`, `VALVE`, `DIVERTER`, `TOWER`, `SENSOR_READ`, `STATUS` | All valves, tower, E-stop, BME280, RES-LVL, RES-TEMP |
| B4 (LoRa LinkMaster) | `LORA_SEND`, `STATUS` | Events: `LORA_RX`. LoRa SX1262 bridge. |

### 11.3 Downstream: B2 Sensor Bus (RS485 Modbus RTU)

| Parameter | Value |
|-----------|-------|
| Baud rate | 9600 |
| Protocol | Modbus RTU |
| Parity | None (8N1) |

| Device | Address | Key Registers |
|--------|---------|---------------|
| EM Flow Meter (FT-01) | 1 | Flow rate (L/h), Totalizer (L), Status |
| Weighing Scale (WT-01) | 2 | Weight (kg), Tare command, Status |
| 4-20mA Module | 3 | Ch1: Upstream pressure (PT-01), Ch2: Downstream pressure (PT-02), Ch3: Water temperature |

### 11.4 Downstream: B3 VFD Bus (RS485 Modbus RTU, Isolated)

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

### 11.5 Downstream: B5 DUT Bus (RS485 Modbus RTU)

| Parameter | Value |
|-----------|-------|
| Baud rate | 9600 |
| Protocol | Modbus RTU |

| Device | Address | Key Registers |
|--------|---------|---------------|
| DUT (Device Under Test) | 20 (configurable) | Totalizer (L). Address configurable per meter model via `SET_ADDR` command. |

### 11.6 LoRa (L1 ↔ B4 via ASP)

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
| Fragmentation | Payloads > ~200 bytes: 4 packet types (DATA, FRAG, ACK, FRAG_ACK) |
| ACK timeout | 3 seconds |
| Max retries | 3 |
| Reassembly timeout | 30 seconds |

### 11.7 Lab: L3 ↔ L2 ↔ L1

| Link | Protocol | Baud | Notes |
|------|----------|------|-------|
| L3 → L2 | USB Serial | 115200 | JSON lines, same as bench hub protocol |
| L2 → L1 | RS485 | 115200 | Transparent byte bridge (L2 forwards all bytes) |
| L1 ↔ LoRa | SPI | — | SX1262 LoRa radio, ASP encrypted |

---

## 12. Hardware Pinout Reference

### 12.1 B2 Sensor Bridge — ESP32 Pinout

| Function | Pin | UART | Direction | Notes |
|----------|-----|------|-----------|-------|
| Upstream RS485 RX | GPIO 16 | UART2 | IN | From hub Ch 1 |
| Upstream RS485 TX | GPIO 17 | UART2 | OUT | To hub Ch 1 |
| Upstream RS485 DE | GPIO 4 | — | OUT | HIGH = transmit |
| Downstream RS485 RX | GPIO 32 | UART1 | IN | From EM/Scale/4-20mA bus |
| Downstream RS485 TX | GPIO 33 | UART1 | OUT | To EM/Scale/4-20mA bus |
| Downstream RS485 DE | GPIO 25 | — | OUT | HIGH = transmit |
| Status LED | GPIO 2 | — | OUT | Onboard LED |

### 12.2 B3 VFD Bridge — ESP32 Pinout

| Function | Pin | UART | Direction | Notes |
|----------|-----|------|-----------|-------|
| Upstream RS485 RX | GPIO 16 | UART2 | IN | From hub Ch 2 |
| Upstream RS485 TX | GPIO 17 | UART2 | OUT | To hub Ch 2 |
| Upstream RS485 DE | GPIO 4 | — | OUT | HIGH = transmit |
| Downstream RS485 RX | GPIO 32 | UART1 | IN | From VFD (isolated bus) |
| Downstream RS485 TX | GPIO 33 | UART1 | OUT | To VFD (isolated bus) |
| Downstream RS485 DE | GPIO 25 | — | OUT | HIGH = transmit |
| Status LED | GPIO 2 | — | OUT | Onboard LED |

### 12.3 B5 DUT Bridge — ESP32 Pinout

| Function | Pin | UART | Direction | Notes |
|----------|-----|------|-----------|-------|
| Upstream RS485 RX | GPIO 16 | UART2 | IN | From hub Ch 3 |
| Upstream RS485 TX | GPIO 17 | UART2 | OUT | To hub Ch 3 |
| Upstream RS485 DE | GPIO 4 | — | OUT | HIGH = transmit |
| Downstream RS485 RX | GPIO 32 | UART1 | IN | From DUT meter |
| Downstream RS485 TX | GPIO 33 | UART1 | OUT | To DUT meter |
| Downstream RS485 DE | GPIO 25 | — | OUT | HIGH = transmit |
| Status LED | GPIO 2 | — | OUT | Onboard LED |

### 12.4 B6 GPIO Controller — ESP32 Pinout

| Function | Pin | Interface | Direction | Notes |
|----------|-----|-----------|-----------|-------|
| Upstream RS485 RX | GPIO 16 | UART2 | IN | From hub Ch 4 |
| Upstream RS485 TX | GPIO 17 | UART2 | OUT | To hub Ch 4 |
| Upstream RS485 DE | GPIO 4 | — | OUT | HIGH = transmit |
| SV1 (main line solenoid) | GPIO 32 | Relay | OUT | Active HIGH |
| BV-L1 (DN25 ball valve) | GPIO 25 | Relay | OUT | Active HIGH |
| BV-L2 (DN20 ball valve) | GPIO 26 | Relay | OUT | Active HIGH |
| BV-L3 (DN15 ball valve) | GPIO 27 | Relay | OUT | Active HIGH |
| DV1+ (diverter COLLECT) | GPIO 33 | Relay | OUT | Pulse HIGH 200ms |
| DV1- (diverter BYPASS) | GPIO 23 | Relay | OUT | Pulse HIGH 200ms |
| SV-DRN (drain solenoid) | GPIO 14 | Relay | OUT | Active HIGH |
| Tower RED | GPIO 12 | Digital | OUT | — |
| Tower YELLOW | GPIO 18 | Digital | OUT | — |
| Tower GREEN | GPIO 19 | Digital | OUT | — |
| ESTOP_MON | GPIO 35 | Digital | IN | Input-only pin. Active LOW = power lost. |
| BV-L1 Feedback | GPIO 36 | Digital | IN | Input-only pin. Optional valve position. |
| BV-L2 Feedback | GPIO 39 | Digital | IN | Input-only pin. Optional valve position. |
| BV-L3 Feedback | GPIO 34 | Digital | IN | Input-only pin. Optional valve position. |
| BME280 SDA | GPIO 21 | I2C | I/O | BME280 addr 0x76 |
| BME280 SCL | GPIO 22 | I2C | OUT | — |
| RES-TEMP (DS18B20) | GPIO 15 | 1-Wire | I/O | Waterproof temperature probe |
| RES-LVL Trigger | GPIO 13 | Digital | OUT | HC-SR04 ultrasonic |
| RES-LVL Echo | GPIO 5 | Digital | IN | HC-SR04 ultrasonic |
| Status LED | GPIO 2 | Digital | OUT | Onboard LED |

### 12.5 B4 LoRa LinkMaster — ESP32 Pinout

| Function | Pin | Interface | Direction | Notes |
|----------|-----|-----------|-----------|-------|
| Upstream RS485 RX | GPIO 16 | UART2 | IN | From hub Ch 5 |
| Upstream RS485 TX | GPIO 17 | UART2 | OUT | To hub Ch 5 |
| Upstream RS485 DE | GPIO 13 | — | OUT | HIGH = transmit |
| LoRa NSS/CS | GPIO 5 | SPI | OUT | SX1262 chip select |
| LoRa RST | GPIO 14 | — | OUT | SX1262 reset |
| LoRa BUSY | GPIO 4 | — | IN | SX1262 busy indicator |
| LoRa DIO1 | GPIO 2 | — | IN | SX1262 interrupt |
| SPI SCK | GPIO 18 | SPI | OUT | VSPI default |
| SPI MISO | GPIO 19 | SPI | IN | VSPI default |
| SPI MOSI | GPIO 23 | SPI | OUT | VSPI default |

### 12.6 L1 Lab LinkMaster — ESP32 Pinout

| Function | Pin | Interface | Direction | Notes |
|----------|-----|-----------|-----------|-------|
| RS485 RX (to L2) | GPIO 16 | UART2 | IN | From L2 bridge |
| RS485 TX (to L2) | GPIO 17 | UART2 | OUT | To L2 bridge |
| RS485 DE | GPIO 15 | — | OUT | HIGH = transmit |
| LoRa NSS/CS | GPIO 5 | SPI | OUT | SX1262 chip select |
| LoRa RST | GPIO 14 | — | OUT | SX1262 reset |
| LoRa BUSY | GPIO 4 | — | IN | SX1262 busy indicator |
| LoRa DIO1 | GPIO 2 | — | IN | SX1262 interrupt |
| SPI SCK | GPIO 18 | SPI | OUT | VSPI default |
| SPI MISO | GPIO 19 | SPI | IN | VSPI default |
| SPI MOSI | GPIO 23 | SPI | OUT | VSPI default |

### 12.7 L2 Lab RS485 Bridge — ESP32 Pinout

| Function | Pin | Interface | Direction | Notes |
|----------|-----|-----------|-----------|-------|
| USB Serial | GPIO 1, 3 | UART0 | I/O | To L3 RPi5 via USB |
| RS485 RX (to L1) | GPIO 16 | UART2 | IN | From L1 LinkMaster |
| RS485 TX (to L1) | GPIO 17 | UART2 | OUT | To L1 LinkMaster |
| RS485 DE | GPIO 4 | — | OUT | HIGH = transmit |

---

## 13. Data Storage & Sync

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

## 14. LoRa Message Types

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

## 15. Key Design Principles

1. **Bench is standalone**: Operates with zero lab connectivity. All hardware control is local to bench RPi5. Lab is a convenience layer, not a dependency.
2. **Lab never controls hardware**: Lab only sends requests (`START_TEST`, `EMERGENCY_STOP`) and receives results. No direct valve/pump/sensor commands ever traverse the LoRa link.
3. **Gravimetric reference**: Primary reference volume measured by weight (200 kg scale), not by EM flow meter. EM meter is for PID feedback and cross-check only.
4. **ISO 4064 compliance**: All 8 Q-points (Q1–Q8), MPE values (±5% lower zone, ±2% upper zone), water density correction by temperature, test procedures follow the standard.
5. **Defense in depth**: Hardware E-stop (electrical, no software in loop) → Software safety watchdog (200ms) → PID output clamping (5–50 Hz) → Valve mutual exclusion interlocks.
6. **Encrypted communication**: All LoRa traffic AES-256-CBC encrypted, HMAC-SHA256 authenticated, sequence-numbered for replay protection.
7. **Single codebase, dual deployment**: One Django project with shared apps (`accounts`, `meters`, `testing`, `comms`, `reports`, `audit`). Side-specific apps: `controller` + `bench_ui` (bench only), `lab_ui` (lab only). Configured via `settings_bench.py` / `settings_lab.py`.
8. **Graceful degradation**: If LoRa link goes down, bench continues testing without interruption. Results are queued and synced when link recovers.
9. **Modular ESP32 architecture**: Each ESP32 node is a single-purpose microcontroller connected via its own isolated RS485 channel. Failure of one node doesn't affect others. Nodes are individually replaceable.
10. **Single-cable simplicity**: All 5 ESP32 nodes connect to B1 through a single USB cable to the Waveshare 8-CH RS485 hub. Clean cable management, single point of physical connection.
