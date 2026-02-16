/**
 * B6 — GPIO Controller Firmware (Node 13)
 *
 * Upstream RS485 (Hub Ch 4) + GPIO control + environmental sensors.
 *
 * GPIO Outputs (relay-driven):
 *   SV1, BV-L1/L2/L3, DV1+/DV1-, SV-DRN, Tower R/Y/G
 *
 * GPIO Inputs:
 *   ESTOP_MON (contactor aux, active LOW), valve feedback (optional)
 *
 * Sensors:
 *   BME280 (I2C): ATM-TEMP, ATM-HUM, ATM-BARO
 *   DS18B20 (1-Wire): RES-TEMP
 *   HC-SR04 (ultrasonic): RES-LVL
 *
 * Commands:
 *   GPIO_SET, GPIO_GET, VALVE, DIVERTER, TOWER, SENSOR_READ, STATUS
 *
 * Events (unsolicited):
 *   ESTOP — sent on contactor state change
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#if HAS_SENSORS
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#endif
#include "config.h"

// --- Serial port ---
HardwareSerial HostRS485(2);  // UART2 — upstream to RPi5 via hub

// --- Sensors ---
#if HAS_SENSORS
Adafruit_BME280 bme;
OneWire oneWire(ONEWIRE_PIN);
DallasTemperature ds18b20(&oneWire);
#endif

// --- State ---
String inputBuffer;
bool bmeOk = false;
bool ds18b20Ok = false;
bool lastEstopState = false;  // false = normal, true = active (power lost)

// Valve states for STATUS reporting
bool sv1Open = false;
bool bvL1Open = false, bvL2Open = false, bvL3Open = false;
bool svDrnOpen = false;
String diverterPos = "UNKNOWN";

// --- Upstream RS485 host communication ---
void hostSendLine(const char *line) {
    digitalWrite(UP_DE_PIN, HIGH);
    delayMicroseconds(100);
    HostRS485.println(line);
    HostRS485.flush();
    delayMicroseconds(100);
    digitalWrite(UP_DE_PIN, LOW);
}

void hostSendJson(JsonDocument &doc) {
    digitalWrite(UP_DE_PIN, HIGH);
    delayMicroseconds(100);
    serializeJson(doc, HostRS485);
    HostRS485.println();
    HostRS485.flush();
    delayMicroseconds(100);
    digitalWrite(UP_DE_PIN, LOW);
}

void sendOk() {
    hostSendLine("{\"ok\":true}");
}

void sendOk(JsonDocument &data) {
    JsonDocument doc;
    doc["ok"] = true;
    doc["data"] = data;
    hostSendJson(doc);
}

void sendError(const char *msg) {
    JsonDocument doc;
    doc["ok"] = false;
    doc["error"] = msg;
    hostSendJson(doc);
}

// --- Pin name → number mapping ---
struct PinMap {
    const char *name;
    int pin;
    bool isOutput;
};

static const PinMap pinMap[] = {
    {"SV1",       PIN_SV1,          true},
    {"BV_L1",     PIN_BV_L1,        true},
    {"BV_L2",     PIN_BV_L2,        true},
    {"BV_L3",     PIN_BV_L3,        true},
    {"DV1_COLLECT", PIN_DV1_COLLECT, true},
    {"DV1_BYPASS",  PIN_DV1_BYPASS,  true},
    {"SV_DRN",    PIN_SV_DRN,       true},
    {"TOWER_R",   PIN_TOWER_R,      true},
    {"TOWER_Y",   PIN_TOWER_Y,      true},
    {"TOWER_G",   PIN_TOWER_G,      true},
    {"ESTOP_MON", PIN_ESTOP_MON,    false},
    {"BV_L1_FB",  PIN_BV_L1_FB,     false},
    {"BV_L2_FB",  PIN_BV_L2_FB,     false},
    {"BV_L3_FB",  PIN_BV_L3_FB,     false},
    {nullptr, -1, false}
};

int pinFromName(const char *name, bool *isOutput = nullptr) {
    for (int i = 0; pinMap[i].name != nullptr; i++) {
        if (strcmp(name, pinMap[i].name) == 0) {
            if (isOutput) *isOutput = pinMap[i].isOutput;
            return pinMap[i].pin;
        }
    }
    return -1;
}

// --- Command handlers ---

void handleGpioSet(JsonDocument &cmd) {
    const char *pin = cmd["pin"] | "";
    bool isOutput = false;
    int pinNum = pinFromName(pin, &isOutput);
    if (pinNum < 0) { sendError("unknown_pin"); return; }
    if (!isOutput)  { sendError("read_only_pin"); return; }

    int state = cmd["state"] | 0;
    digitalWrite(pinNum, state ? HIGH : LOW);
    sendOk();
}

void handleGpioGet(JsonDocument &cmd) {
    const char *pin = cmd["pin"] | "";
    int pinNum = pinFromName(pin);
    if (pinNum < 0) { sendError("unknown_pin"); return; }

    JsonDocument data;
    data["pin"] = pin;
    data["state"] = digitalRead(pinNum);
    sendOk(data);
}

void handleValve(JsonDocument &cmd) {
    const char *name = cmd["name"] | "";
    const char *action = cmd["action"] | "";
    bool open = (strcmp(action, "OPEN") == 0 || strcmp(action, "open") == 0);

    if (strcmp(name, "SV1") == 0) {
        digitalWrite(PIN_SV1, open ? HIGH : LOW);
        sv1Open = open;
    } else if (strcmp(name, "BV_L1") == 0) {
        digitalWrite(PIN_BV_L1, open ? HIGH : LOW);
        bvL1Open = open;
    } else if (strcmp(name, "BV_L2") == 0) {
        digitalWrite(PIN_BV_L2, open ? HIGH : LOW);
        bvL2Open = open;
    } else if (strcmp(name, "BV_L3") == 0) {
        digitalWrite(PIN_BV_L3, open ? HIGH : LOW);
        bvL3Open = open;
    } else if (strcmp(name, "SV_DRN") == 0) {
        digitalWrite(PIN_SV_DRN, open ? HIGH : LOW);
        svDrnOpen = open;
    } else {
        sendError("unknown_valve");
        return;
    }
    sendOk();
}

void handleDiverter(JsonDocument &cmd) {
    const char *pos = cmd["position"] | "";

    if (strcmp(pos, "COLLECT") == 0) {
        digitalWrite(PIN_DV1_COLLECT, HIGH);
        delay(DIVERTER_PULSE_MS);
        digitalWrite(PIN_DV1_COLLECT, LOW);
        diverterPos = "COLLECT";
        sendOk();
    } else if (strcmp(pos, "BYPASS") == 0) {
        digitalWrite(PIN_DV1_BYPASS, HIGH);
        delay(DIVERTER_PULSE_MS);
        digitalWrite(PIN_DV1_BYPASS, LOW);
        diverterPos = "BYPASS";
        sendOk();
    } else {
        sendError("invalid_position");
    }
}

void handleTower(JsonDocument &cmd) {
    int r = cmd["r"] | -1;
    int y = cmd["y"] | -1;
    int g = cmd["g"] | -1;

    if (r >= 0) digitalWrite(PIN_TOWER_R, r ? HIGH : LOW);
    if (y >= 0) digitalWrite(PIN_TOWER_Y, y ? HIGH : LOW);
    if (g >= 0) digitalWrite(PIN_TOWER_G, g ? HIGH : LOW);
    sendOk();
}

// --- Read ultrasonic distance (HC-SR04) ---
#if HAS_SENSORS
float readUltrasonicCm() {
    digitalWrite(US_TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(US_TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(US_TRIG_PIN, LOW);

    long duration = pulseIn(US_ECHO_PIN, HIGH, 30000);  // 30ms timeout
    if (duration == 0) return -1.0;
    return (duration * 0.0343) / 2.0;  // Speed of sound / 2
}
#endif

void handleSensorRead(JsonDocument &cmd) {
    JsonDocument data;

#if HAS_SENSORS
    // BME280
    if (bmeOk) {
        data["atm_temp_c"] = bme.readTemperature();
        data["atm_hum_pct"] = bme.readHumidity();
        data["atm_baro_hpa"] = bme.readPressure() / 100.0;
    } else {
        data["atm_temp_c"] = (char *)nullptr;
        data["atm_hum_pct"] = (char *)nullptr;
        data["atm_baro_hpa"] = (char *)nullptr;
    }

    // DS18B20 reservoir temperature
    if (ds18b20Ok) {
        ds18b20.requestTemperatures();
        float resTemp = ds18b20.getTempCByIndex(0);
        if (resTemp != DEVICE_DISCONNECTED_C) {
            data["res_temp_c"] = resTemp;
        } else {
            data["res_temp_c"] = (char *)nullptr;
        }
    } else {
        data["res_temp_c"] = (char *)nullptr;
    }

    // HC-SR04 reservoir level
    float distCm = readUltrasonicCm();
    if (distCm >= 0) {
        float levelPct = ((TANK_HEIGHT_CM - distCm) / TANK_HEIGHT_CM) * 100.0;
        if (levelPct < 0) levelPct = 0;
        if (levelPct > 100) levelPct = 100;
        data["res_level_pct"] = levelPct;
        data["res_dist_cm"] = distCm;
    } else {
        data["res_level_pct"] = (char *)nullptr;
        data["res_dist_cm"] = (char *)nullptr;
    }
#else
    data["atm_temp_c"] = (char *)nullptr;
    data["atm_hum_pct"] = (char *)nullptr;
    data["atm_baro_hpa"] = (char *)nullptr;
    data["res_temp_c"] = (char *)nullptr;
    data["res_level_pct"] = (char *)nullptr;
    data["res_dist_cm"] = (char *)nullptr;
#endif

    // E-stop state (always available — direct GPIO read)
    data["estop_active"] = (digitalRead(PIN_ESTOP_MON) == LOW);

    sendOk(data);
}

void handleStatus() {
    JsonDocument data;
    data["node_id"] = NODE_ID;
    data["fw"] = FW_NAME;
    data["ver"] = FW_VERSION;
    data["uptime_ms"] = millis();
    data["bme280_ok"] = bmeOk;
    data["ds18b20_ok"] = ds18b20Ok;
    data["estop_active"] = (digitalRead(PIN_ESTOP_MON) == LOW);
    data["diverter"] = diverterPos;

    JsonObject valves = data["valves"].to<JsonObject>();
    valves["SV1"] = sv1Open;
    valves["BV_L1"] = bvL1Open;
    valves["BV_L2"] = bvL2Open;
    valves["BV_L3"] = bvL3Open;
    valves["SV_DRN"] = svDrnOpen;

    JsonObject tower = data["tower"].to<JsonObject>();
    tower["r"] = digitalRead(PIN_TOWER_R);
    tower["y"] = digitalRead(PIN_TOWER_Y);
    tower["g"] = digitalRead(PIN_TOWER_G);

    sendOk(data);
}

// --- Process command ---
void processCommand(const String &line) {
    JsonDocument cmd;
    DeserializationError err = deserializeJson(cmd, line);
    if (err) {
        sendError("json_parse_error");
        return;
    }

    const char *cmdStr = cmd["cmd"] | "";

    if (strcmp(cmdStr, "GPIO_SET") == 0)         handleGpioSet(cmd);
    else if (strcmp(cmdStr, "GPIO_GET") == 0)     handleGpioGet(cmd);
    else if (strcmp(cmdStr, "VALVE") == 0)        handleValve(cmd);
    else if (strcmp(cmdStr, "DIVERTER") == 0)     handleDiverter(cmd);
    else if (strcmp(cmdStr, "TOWER") == 0)        handleTower(cmd);
    else if (strcmp(cmdStr, "SENSOR_READ") == 0)  handleSensorRead(cmd);
    else if (strcmp(cmdStr, "STATUS") == 0)       handleStatus();
    else sendError("unknown_command");
}

// --- Setup ---
void setup() {
    // Upstream RS485 (to RPi5 via hub)
    pinMode(UP_DE_PIN, OUTPUT);
    digitalWrite(UP_DE_PIN, LOW);
    HostRS485.begin(UP_BAUD, SERIAL_8N1, UP_RX_PIN, UP_TX_PIN);

    // GPIO outputs — valves
    pinMode(PIN_SV1, OUTPUT);         digitalWrite(PIN_SV1, LOW);
    pinMode(PIN_BV_L1, OUTPUT);       digitalWrite(PIN_BV_L1, LOW);
    pinMode(PIN_BV_L2, OUTPUT);       digitalWrite(PIN_BV_L2, LOW);
    pinMode(PIN_BV_L3, OUTPUT);       digitalWrite(PIN_BV_L3, LOW);
    pinMode(PIN_DV1_COLLECT, OUTPUT); digitalWrite(PIN_DV1_COLLECT, LOW);
    pinMode(PIN_DV1_BYPASS, OUTPUT);  digitalWrite(PIN_DV1_BYPASS, LOW);
    pinMode(PIN_SV_DRN, OUTPUT);      digitalWrite(PIN_SV_DRN, LOW);

    // GPIO outputs — tower light
    pinMode(PIN_TOWER_R, OUTPUT); digitalWrite(PIN_TOWER_R, LOW);
    pinMode(PIN_TOWER_Y, OUTPUT); digitalWrite(PIN_TOWER_Y, LOW);
    pinMode(PIN_TOWER_G, OUTPUT); digitalWrite(PIN_TOWER_G, LOW);

    // GPIO inputs
    pinMode(PIN_ESTOP_MON, INPUT);  // Input-only pin (35), no pullup available
    pinMode(PIN_BV_L1_FB, INPUT);
    pinMode(PIN_BV_L2_FB, INPUT);
    pinMode(PIN_BV_L3_FB, INPUT);

#if HAS_SENSORS
    // Ultrasonic
    pinMode(US_TRIG_PIN, OUTPUT);
    digitalWrite(US_TRIG_PIN, LOW);
    pinMode(US_ECHO_PIN, INPUT);

    // I2C + BME280
    Wire.begin(BME280_SDA, BME280_SCL);
    bmeOk = bme.begin(BME280_ADDR, &Wire);

    // DS18B20
    ds18b20.begin();
    ds18b20Ok = (ds18b20.getDeviceCount() > 0);
#endif

    // Status LED
    pinMode(LED_PIN, OUTPUT);
    inputBuffer.reserve(512);

    // Read initial E-stop state
    lastEstopState = (digitalRead(PIN_ESTOP_MON) == LOW);

    // Small delay for RS485 bus to settle
    delay(100);

    // Announce ready
    JsonDocument doc;
    doc["ok"] = true;
    JsonObject data = doc["data"].to<JsonObject>();
    data["fw"] = FW_NAME;
    data["ver"] = FW_VERSION;
    data["node_id"] = NODE_ID;
    data["bme280_ok"] = bmeOk;
    data["ds18b20_ok"] = ds18b20Ok;
    hostSendJson(doc);
}

// --- Main loop ---
void loop() {
    // Read upstream RS485 for JSON commands
    while (HostRS485.available()) {
        char c = HostRS485.read();
        if (c == '\n') {
            inputBuffer.trim();
            if (inputBuffer.length() > 0) {
                processCommand(inputBuffer);
            }
            inputBuffer = "";
        } else if (c != '\r') {
            inputBuffer += c;
            if (inputBuffer.length() > 1024) {
                inputBuffer = "";
                sendError("input_too_long");
            }
        }
    }

    // Poll E-stop for state changes (unsolicited event)
    static unsigned long lastEstopPoll = 0;
    unsigned long now = millis();
    if (now - lastEstopPoll >= ESTOP_POLL_MS) {
        lastEstopPoll = now;
        bool currentEstop = (digitalRead(PIN_ESTOP_MON) == LOW);
        if (currentEstop != lastEstopState) {
            lastEstopState = currentEstop;
            JsonDocument doc;
            doc["event"] = "ESTOP";
            doc["state"] = currentEstop ? "ACTIVE" : "CLEAR";
            hostSendJson(doc);
        }
    }

    // Heartbeat LED
    static unsigned long lastBlink = 0;
    if (now - lastBlink > 2000) {
        digitalWrite(LED_PIN, HIGH);
        lastBlink = now;
    } else if (now - lastBlink > 100) {
        digitalWrite(LED_PIN, LOW);
    }
}
