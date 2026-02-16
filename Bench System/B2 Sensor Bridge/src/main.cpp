/**
 * B2 — Bench RS485 Sensor Bridge Firmware
 *
 * USB Serial ↔ RS485 Modbus RTU (Bus 1) + GPIO control.
 *
 * Modbus devices on Bus 1 (9600, 8N1):
 *   - EM (addr 1): Energy meter
 *   - Scale (addr 2): Weighing scale
 *   - 4-20mA (addr 3): Pressure/temperature module
 *   - DUT (addr 20): Device Under Test
 *
 * GPIO:
 *   - BV-L1/L2/L3: Lane ball valves (mutually exclusive, managed by RPi5)
 *   - DV1: Diverter valve (dual-coil latching, COLLECT/BYPASS)
 *   - SV-DRN: Drain solenoid valve
 *   - TOWER R/Y/G: Tower light channels
 *   - ESTOP_MON: E-stop contactor monitoring (input, active LOW)
 *
 * Protocol (USB Serial, 115200, JSON lines):
 *   {"cmd":"MB_READ","addr":1,"reg":0,"count":2}\n
 *   {"cmd":"MB_WRITE","addr":1,"reg":0,"value":100}\n
 *   {"cmd":"GPIO_SET","pin":"BV_L1","state":1}\n
 *   {"cmd":"GPIO_GET","pin":"ESTOP_MON"}\n
 *   {"cmd":"VALVE","name":"BV_L1","state":"open"}\n
 *   {"cmd":"DIVERTER","pos":"COLLECT"}\n
 *   {"cmd":"TOWER","r":1,"y":0,"g":0}\n
 *   {"cmd":"STATUS"}\n
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ModbusMaster.h>
#include "config.h"

// --- Globals ---
ModbusMaster node;
HardwareSerial RS485(2);
String inputBuffer;
uint8_t lastModbusError = 0;

// Track valve states
bool bvL1Open = false, bvL2Open = false, bvL3Open = false;
bool svDrnOpen = false;
String diverterPos = "UNKNOWN";

// --- RS485 direction control ---
void preTransmission() {
    digitalWrite(RS485_DE_PIN, HIGH);
    delayMicroseconds(50);
}

void postTransmission() {
    delayMicroseconds(50);
    digitalWrite(RS485_DE_PIN, LOW);
}

// --- JSON responses ---
void sendOk() {
    Serial.println("{\"ok\":true}");
}

void sendOk(JsonDocument &data) {
    JsonDocument doc;
    doc["ok"] = true;
    doc["data"] = data;
    serializeJson(doc, Serial);
    Serial.println();
}

void sendError(const char *msg) {
    JsonDocument doc;
    doc["ok"] = false;
    doc["error"] = msg;
    serializeJson(doc, Serial);
    Serial.println();
}

void sendModbusError(uint8_t result) {
    JsonDocument doc;
    doc["ok"] = false;
    doc["error"] = "modbus_error";
    doc["code"] = result;
    serializeJson(doc, Serial);
    Serial.println();
}

// --- Modbus commands ---

void handleMbRead(JsonDocument &cmd) {
    uint8_t addr = cmd["addr"] | 1;
    uint16_t reg = cmd["reg"] | 0;
    uint16_t count = cmd["count"] | 1;

    if (count == 0 || count > 125) {
        sendError("count must be 1-125");
        return;
    }

    node.begin(addr, RS485);
    uint8_t result = node.readHoldingRegisters(reg, count);
    lastModbusError = result;

    if (result == node.ku8MBSuccess) {
        JsonDocument data;
        JsonArray values = data["values"].to<JsonArray>();
        for (uint16_t i = 0; i < count; i++) {
            values.add(node.getResponseBuffer(i));
        }
        sendOk(data);
    } else {
        sendModbusError(result);
    }
}

void handleMbWrite(JsonDocument &cmd) {
    uint8_t addr = cmd["addr"] | 1;
    uint16_t reg = cmd["reg"] | 0;
    uint16_t value = cmd["value"] | 0;

    node.begin(addr, RS485);
    uint8_t result = node.writeSingleRegister(reg, value);
    lastModbusError = result;

    if (result == node.ku8MBSuccess) {
        sendOk();
    } else {
        sendModbusError(result);
    }
}

// --- GPIO commands ---

int pinFromName(const char *name) {
    if (strcmp(name, "BV_L1") == 0) return PIN_BV_L1;
    if (strcmp(name, "BV_L2") == 0) return PIN_BV_L2;
    if (strcmp(name, "BV_L3") == 0) return PIN_BV_L3;
    if (strcmp(name, "SV_DRN") == 0) return PIN_SV_DRN;
    if (strcmp(name, "TOWER_R") == 0) return PIN_TOWER_R;
    if (strcmp(name, "TOWER_Y") == 0) return PIN_TOWER_Y;
    if (strcmp(name, "TOWER_G") == 0) return PIN_TOWER_G;
    if (strcmp(name, "ESTOP_MON") == 0) return PIN_ESTOP_MON;
    return -1;
}

void handleGpioSet(JsonDocument &cmd) {
    const char *pin = cmd["pin"] | "";
    int pinNum = pinFromName(pin);
    if (pinNum < 0) {
        sendError("unknown_pin");
        return;
    }
    if (pinNum == PIN_ESTOP_MON) {
        sendError("read_only_pin");
        return;
    }
    int state = cmd["state"] | 0;
    digitalWrite(pinNum, state ? HIGH : LOW);
    sendOk();
}

void handleGpioGet(JsonDocument &cmd) {
    const char *pin = cmd["pin"] | "";
    int pinNum = pinFromName(pin);
    if (pinNum < 0) {
        sendError("unknown_pin");
        return;
    }
    JsonDocument data;
    data["pin"] = pin;
    data["state"] = digitalRead(pinNum);
    sendOk(data);
}

// --- Named valve control ---

void handleValve(JsonDocument &cmd) {
    const char *name = cmd["name"] | "";
    const char *state = cmd["state"] | "";
    bool open = (strcmp(state, "open") == 0);

    if (strcmp(name, "BV_L1") == 0) {
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

// --- Diverter control (dual-coil latching) ---

void handleDiverter(JsonDocument &cmd) {
    const char *pos = cmd["pos"] | "";

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

// --- Tower light control ---

void handleTower(JsonDocument &cmd) {
    int r = cmd["r"] | -1;
    int y = cmd["y"] | -1;
    int g = cmd["g"] | -1;

    if (r >= 0) digitalWrite(PIN_TOWER_R, r ? HIGH : LOW);
    if (y >= 0) digitalWrite(PIN_TOWER_Y, y ? HIGH : LOW);
    if (g >= 0) digitalWrite(PIN_TOWER_G, g ? HIGH : LOW);
    sendOk();
}

// --- Status ---

void handleStatus() {
    JsonDocument data;
    data["uptime_ms"] = millis();
    data["rs485_ok"] = (lastModbusError == 0);
    data["last_err"] = lastModbusError;
    data["estop"] = (digitalRead(PIN_ESTOP_MON) == LOW);  // Active LOW
    data["diverter"] = diverterPos;

    JsonObject valves = data["valves"].to<JsonObject>();
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

    if (strcmp(cmdStr, "MB_READ") == 0)        handleMbRead(cmd);
    else if (strcmp(cmdStr, "MB_WRITE") == 0)   handleMbWrite(cmd);
    else if (strcmp(cmdStr, "GPIO_SET") == 0)    handleGpioSet(cmd);
    else if (strcmp(cmdStr, "GPIO_GET") == 0)    handleGpioGet(cmd);
    else if (strcmp(cmdStr, "VALVE") == 0)       handleValve(cmd);
    else if (strcmp(cmdStr, "DIVERTER") == 0)    handleDiverter(cmd);
    else if (strcmp(cmdStr, "TOWER") == 0)       handleTower(cmd);
    else if (strcmp(cmdStr, "STATUS") == 0)      handleStatus();
    else sendError("unknown_command");
}

// --- Setup ---
void setup() {
    Serial.begin(USB_BAUD);
    while (!Serial) { delay(10); }

    // RS485
    pinMode(RS485_DE_PIN, OUTPUT);
    digitalWrite(RS485_DE_PIN, LOW);
    RS485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
    node.begin(ADDR_EM, RS485);
    node.preTransmission(preTransmission);
    node.postTransmission(postTransmission);

    // GPIO outputs — valves
    pinMode(PIN_BV_L1, OUTPUT); digitalWrite(PIN_BV_L1, LOW);
    pinMode(PIN_BV_L2, OUTPUT); digitalWrite(PIN_BV_L2, LOW);
    pinMode(PIN_BV_L3, OUTPUT); digitalWrite(PIN_BV_L3, LOW);
    pinMode(PIN_SV_DRN, OUTPUT); digitalWrite(PIN_SV_DRN, LOW);

    // GPIO outputs — diverter
    pinMode(PIN_DV1_COLLECT, OUTPUT); digitalWrite(PIN_DV1_COLLECT, LOW);
    pinMode(PIN_DV1_BYPASS, OUTPUT);  digitalWrite(PIN_DV1_BYPASS, LOW);

    // GPIO outputs — tower light
    pinMode(PIN_TOWER_R, OUTPUT); digitalWrite(PIN_TOWER_R, LOW);
    pinMode(PIN_TOWER_Y, OUTPUT); digitalWrite(PIN_TOWER_Y, LOW);
    pinMode(PIN_TOWER_G, OUTPUT); digitalWrite(PIN_TOWER_G, LOW);

    // GPIO input — E-stop monitor
    pinMode(PIN_ESTOP_MON, INPUT_PULLUP);

    // Status LED
    pinMode(LED_PIN, OUTPUT);
    inputBuffer.reserve(512);

    Serial.println("{\"ok\":true,\"data\":{\"fw\":\"B2-Sensor-Bridge\",\"ver\":\"1.0.0\"}}");
}

// --- Main loop ---
void loop() {
    while (Serial.available()) {
        char c = Serial.read();
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

    // Heartbeat
    static unsigned long lastBlink = 0;
    unsigned long now = millis();
    if (now - lastBlink > 2000) {
        digitalWrite(LED_PIN, HIGH);
        lastBlink = now;
    } else if (now - lastBlink > 100) {
        digitalWrite(LED_PIN, LOW);
    }
}
