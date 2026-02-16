/**
 * L2 — Lab RS485 Bridge Firmware
 *
 * USB Serial ↔ RS485 Modbus RTU generic transparent bridge.
 * Any Modbus address can be targeted per-command.
 *
 * Protocol (USB Serial, 115200, JSON lines):
 *   Request:  {"cmd":"MB_READ","addr":1,"reg":0,"count":2}\n
 *   Response: {"ok":true,"data":{"values":[100,200]}}\n
 *
 *   Request:  {"cmd":"MB_WRITE","addr":1,"reg":0,"value":100}\n
 *   Response: {"ok":true}\n
 *
 *   Request:  {"cmd":"SET_BAUD","baud":19200}\n
 *   Response: {"ok":true}\n
 *
 *   Request:  {"cmd":"STATUS"}\n
 *   Response: {"ok":true,"data":{"uptime_ms":...,"baud":9600}}\n
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
uint32_t currentBaud = RS485_BAUD_DEFAULT;

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

// --- Command handlers ---

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

void handleSetBaud(JsonDocument &cmd) {
    uint32_t baud = cmd["baud"] | 0;
    if (baud < 1200 || baud > 115200) {
        sendError("baud must be 1200-115200");
        return;
    }
    RS485.end();
    RS485.begin(baud, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
    currentBaud = baud;
    sendOk();
}

void handleStatus() {
    JsonDocument data;
    data["uptime_ms"] = millis();
    data["rs485_ok"] = (lastModbusError == 0);
    data["last_err"] = lastModbusError;
    data["baud"] = currentBaud;
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

    if (strcmp(cmdStr, "MB_READ") == 0) {
        handleMbRead(cmd);
    } else if (strcmp(cmdStr, "MB_WRITE") == 0) {
        handleMbWrite(cmd);
    } else if (strcmp(cmdStr, "SET_BAUD") == 0) {
        handleSetBaud(cmd);
    } else if (strcmp(cmdStr, "STATUS") == 0) {
        handleStatus();
    } else {
        sendError("unknown_command");
    }
}

// --- Setup ---
void setup() {
    Serial.begin(USB_BAUD);
    while (!Serial) { delay(10); }

    pinMode(RS485_DE_PIN, OUTPUT);
    digitalWrite(RS485_DE_PIN, LOW);

    RS485.begin(RS485_BAUD_DEFAULT, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);

    node.begin(1, RS485);
    node.preTransmission(preTransmission);
    node.postTransmission(postTransmission);

    pinMode(LED_PIN, OUTPUT);
    inputBuffer.reserve(512);

    Serial.println("{\"ok\":true,\"data\":{\"fw\":\"L2-Lab-Bridge\",\"ver\":\"1.0.0\"}}");
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
