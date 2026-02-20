/**
 * B2 — Sensor Bridge Firmware (Node 10)
 *
 * Upstream RS485 (Hub Ch 1) ↔ Downstream RS485 Modbus RTU bridge.
 * Downstream devices: EM (addr 1), Scale (addr 2), 4-20mA (addr 3).
 *
 * Commands:
 *   MB_READ   — Read holding registers from downstream device
 *   MB_WRITE  — Write single register to downstream device
 *   STATUS    — Node status + last Modbus error
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ModbusMaster.h>
#include "config.h"

// --- Serial ports ---
HardwareSerial HostRS485(2);   // UART2 — upstream to RPi5 via hub
HardwareSerial MbusRS485(1);   // UART1 — downstream to sensors

// --- Globals ---
ModbusMaster node;
String inputBuffer;
uint8_t lastModbusError = 0;

// --- Downstream RS485 DE control (for ModbusMaster callbacks) ---
void preTransmission() {
    digitalWrite(DN_DE_PIN, HIGH);
    delayMicroseconds(50);
}

void postTransmission() {
    delayMicroseconds(50);
    digitalWrite(DN_DE_PIN, LOW);
}

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

void sendModbusError(uint8_t result) {
    JsonDocument doc;
    doc["ok"] = false;
    doc["error"] = "modbus_error";
    doc["code"] = result;
    hostSendJson(doc);
}

// --- Command handlers ---

void handleMbRead(JsonDocument &cmd) {
    uint8_t addr = cmd["addr"] | ADDR_EM;
    uint16_t reg = cmd["reg"] | 0;
    uint16_t count = cmd["count"] | 1;

    if (count == 0 || count > 125) {
        sendError("count must be 1-125");
        return;
    }

    node.begin(addr, MbusRS485);
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
    uint8_t addr = cmd["addr"] | ADDR_EM;
    uint16_t reg = cmd["reg"] | 0;
    uint16_t value = cmd["value"] | 0;

    node.begin(addr, MbusRS485);
    uint8_t result = node.writeSingleRegister(reg, value);
    lastModbusError = result;

    if (result == node.ku8MBSuccess) {
        sendOk();
    } else {
        sendModbusError(result);
    }
}

void handleStatus() {
    JsonDocument data;
    data["node_id"] = NODE_ID;
    data["fw"] = FW_NAME;
    data["ver"] = FW_VERSION;
    data["uptime_ms"] = millis();
    data["rs485_ok"] = (lastModbusError == 0);
    data["last_err"] = lastModbusError;
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
    else if (strcmp(cmdStr, "STATUS") == 0)      handleStatus();
    else sendError("unknown_command");
}

// --- Setup ---
void setup() {
    // Upstream RS485 (to RPi5 via hub)
    pinMode(UP_DE_PIN, OUTPUT);
    digitalWrite(UP_DE_PIN, LOW);
    HostRS485.begin(UP_BAUD, SERIAL_8N1, UP_RX_PIN, UP_TX_PIN);

    // Downstream RS485 (to EM, Scale, 4-20mA)
    pinMode(DN_DE_PIN, OUTPUT);
    digitalWrite(DN_DE_PIN, LOW);
    MbusRS485.begin(DN_BAUD, SERIAL_8N1, DN_RX_PIN, DN_TX_PIN);

    // ModbusMaster
    node.begin(ADDR_EM, MbusRS485);
    node.preTransmission(preTransmission);
    node.postTransmission(postTransmission);

    // Status LED
    pinMode(LED_PIN, OUTPUT);
    inputBuffer.reserve(512);

    // Small delay for RS485 bus to settle
    delay(100);

    // Announce ready
    JsonDocument doc;
    doc["ok"] = true;
    JsonObject data = doc["data"].to<JsonObject>();
    data["fw"] = FW_NAME;
    data["ver"] = FW_VERSION;
    data["node_id"] = NODE_ID;
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

    // Heartbeat LED
    static unsigned long lastBlink = 0;
    unsigned long now = millis();
    if (now - lastBlink > 2000) {
        digitalWrite(LED_PIN, HIGH);
        lastBlink = now;
    } else if (now - lastBlink > 100) {
        digitalWrite(LED_PIN, LOW);
    }
}
