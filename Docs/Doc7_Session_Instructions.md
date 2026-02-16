# IIIT-B Water Meter Test Bench — Session Instructions for Claude Code

## PURPOSE
This document tells Claude Code exactly what to do at the start and end of every session. Follow these steps to stay on track across sessions.

---

## ON SESSION START — Do These First

### Step 1: Read Memory
Your auto-memory at `~/.claude/projects/.../memory/MEMORY.md` is auto-loaded. Skim it for current project state.

### Step 2: Read the Tracker
```
Read: Docs/Doc5_Project_Tracker.md
```
- Check "Current Status" section for phase, blockers, and last session summary.
- Check the session log for what happened in the last session.
- Identify the next tasks to work on.

### Step 3: Read the Sprint Board
```
Read: Docs/Doc6_Sprint_Board.md
```
- Find the current sprint.
- Look at task statuses — pick up the next "Not Started" or "In Progress" task.

### Step 4: Confirm with User
Tell the user:
- What was done last session
- What the current sprint/task is
- What you plan to do this session
- Ask if they want to continue or change direction

---

## DURING THE SESSION — Working Rules

### Code Standards
- **Python**: Django 5.0 conventions, PEP 8, type hints where helpful
- **HTML**: Django templates, Bootstrap 5.3 classes, HTMX attributes, Alpine.js directives
- **CSS**: Custom SCSS with design tokens from Doc3 (CSS variables)
- **JS**: Minimal — Alpine.js for reactivity, Chart.js for charts, no build step
- **ESP32**: Arduino C++, clear serial protocol, ModbusMaster library

### File Location Rules
- Project root: `/home/harshavardhan/I.R.A.S/Water Flow Meter Calibration System/`
- Django project root: to be confirmed (likely under one of the system folders or a new `iiitb-testbench/` dir)
- Docs always in: `Docs/`
- Firmware in: `firmware/` under project root

### Testing Each Step
- Every task has a "Test" column in the sprint board
- Run `python manage.py check` after model changes
- Run `python manage.py migrate` after new models
- Test views by running dev server and accessing in browser
- Test firmware by uploading to ESP32 and checking serial monitor

### Reference Docs (read when needed)
| Doc | When to Read |
|-----|-------------|
| Doc1_System_Architecture | System-wide questions, hydraulic flow, communication paths |
| Doc2_Hardware_Group_Mapping | ESP32 pin maps, Modbus addresses, component details |
| Doc3_UI_UX_Specification | Any UI work — colors, typography, icons, page layouts |
| Doc4_Claude_Code_Dev_Guide | Django models, API endpoints, project structure, build order |
| Doc5_Project_Tracker | Every session start/end — progress tracking |
| Doc6_Sprint_Board | Task details, user stories, priorities, dependencies |
| Doc7_Session_Instructions | This file — session protocol |

### Important Design Decisions
- ALL hardware behind abstraction layer (`HARDWARE_BACKEND = 'simulator' | 'real'`)
- Simulator first, real drivers later
- Single Django project, dual settings files
- Lab: SQLite (single user sufficient)
- Bench: PostgreSQL + Redis (production)
- Bench UI: WebSocket via Django Channels for real-time gauges
- Lab UI: HTMX polling every 2s for updates
- No cloud, no internet — LAN only

---

## ON SESSION END — Do These Before Closing

### Step 1: Update the Tracker
Edit `Docs/Doc5_Project_Tracker.md`:
- Update "Current Status" section
- Add a new entry to "Session Log" with:
  - Date
  - What was done (list of tasks completed)
  - Decisions made
  - Blockers encountered
  - Next steps for next session
- Update task statuses in the progress table
- Add any new decisions to "Key Decisions Log"
- Add any new open questions
- List all files created/modified under "Files Changed Per Session"

### Step 2: Update Sprint Board
Edit `Docs/Doc6_Sprint_Board.md`:
- Update task statuses (Not Started → In Progress → Done)
- Add notes to tasks if needed

### Step 3: Update Memory
Edit auto-memory `MEMORY.md`:
- Update "Current State" section
- Add any new conventions or patterns discovered
- Remove outdated information

### Step 4: Summary to User
Tell the user:
- What was accomplished this session
- Current sprint progress (X of Y tasks done)
- What's next
- Any blockers or decisions needed

---

## QUICK REFERENCE — Project Structure (from Doc4)

```
iiitb-testbench/
├── manage.py
├── config/           → settings_base, settings_lab, settings_bench, urls, wsgi, asgi
├── accounts/         → SHARED: CustomUser, login, permissions
├── meters/           → SHARED: TestMeter CRUD
├── testing/          → SHARED: Test, TestResult, ISO4064, services
├── comms/            → SHARED: ASP protocol, crypto, serial, message queue
├── reports/          → SHARED: PDF cert, error curve
├── audit/            → SHARED: AuditLog, middleware
├── controller/       → BENCH ONLY: state machine, PID, sensors, valves, VFD, safety, simulator
├── lab_ui/           → LAB ONLY: web portal views + templates
├── bench_ui/         → BENCH ONLY: touch LCD views + templates + WebSocket
├── static/           → CSS, JS, images
├── templates/        → base_lab.html, base_bench.html
└── firmware/         → ESP32 Arduino (bridge_sensor, bridge_vfd, linkmaster, bridge_lora)
```

## QUICK REFERENCE — User Roles
| Role | Lab Portal | Bench LCD | Key Permissions |
|------|-----------|-----------|-----------------|
| Admin | Full access | Setup tab | Manage users, settings, audit |
| Manager | Full access | View only | Approve results, generate certs |
| Lab Tech | Most pages | No access | Create tests, register meters |
| Bench Tech | Monitor only | Full access | Run tests, enter DUT readings |

## QUICK REFERENCE — Key Ports & Addresses
| Item | Value |
|------|-------|
| Web server | Port 8080 |
| USB to B2 | /dev/ttyBENCH_BUS (115200 baud) |
| USB to B3 | /dev/ttyVFD_BUS (115200 baud) |
| RS485 Bus 1 | 9600 baud (EM=addr 1, Scale=addr 2, 4-20mA=addr 3, DUT=addr 20) |
| RS485 Bus 2 | 9600 baud (VFD only) |
| LoRa | 433MHz, SX1262 |
| ASP Device IDs | Lab=0x0001, Bench=0x0002 |
