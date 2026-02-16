/**
 * B3 — VFD Bridge Firmware
 *
 * USB Serial ↔ RS485 Modbus RTU bridge for Delta VFD022EL43A.
 * Receives JSON commands over USB, translates to Modbus RTU on Bus 2.
 *
 * Protocol (USB Serial, 115200, JSON lines):
 *   Request:  {"cmd":"MB_READ","addr":1,"reg":8192,"count":1}\n
 *   Response: {"ok":true,"data":{"values":[0]}}\n
 *
 *   Request:  {"cmd":"MB_WRITE","addr":1,"reg":8192,"value":18}\n
 *   Response: {"ok":true}\n
 *
 *   Request:  {"cmd":"STATUS"}\n
 *   Response: {"ok":true,"data":{"uptime_ms":12345,"rs485_ok":true,"last_err":0}}\n
 *
 * Hardware: ESP32 DevKit → MAX485/SP3485 → Delta VFD022EL43A
 * RS485 Bus 2: 9600 baud, 8N1
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ModbusMaster.h>
#include "config.h"

// --- Globals ---
ModbusMaster node;
HardwareSerial RS485(2);  // UART2 for RS485
String inputBuffer;
uint8_t lastModbusError = 0;
unsigned long lastActivityMs = 0;

// --- RS485 direction control ---
void preTransmission() {
    digitalWrite(RS485_DE_PIN, HIGH);
    delayMicroseconds(50);
}

void postTransmission() {
    delayMicroseconds(50);
    digitalWrite(RS485_DE_PIN, LOW);
}

// --- Send JSON response ---
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
    uint8_t addr = cmd["addr"] | VFD_ADDR;
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
    uint8_t addr = cmd["addr"] | VFD_ADDR;
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

void handleStatus() {
    JsonDocument data;
    data["uptime_ms"] = millis();
    data["rs485_ok"] = (lastModbusError == 0);
    data["last_err"] = lastModbusError;
    data["vfd_addr"] = VFD_ADDR;
    data["rs485_baud"] = RS485_BAUD;
    sendOk(data);
}

// --- Process a single JSON line ---
void processCommand(const String &line) {
    JsonDocument cmd;
    DeserializationError err = deserializeJson(cmd, line);

    if (err) {
        sendError("json_parse_error");
        return;
    }

    const char *cmdStr = cmd["cmd"] | "";
    lastActivityMs = millis();

    if (strcmp(cmdStr, "MB_READ") == 0) {
        handleMbRead(cmd);
    } else if (strcmp(cmdStr, "MB_WRITE") == 0) {
        handleMbWrite(cmd);
    } else if (strcmp(cmdStr, "STATUS") == 0) {
        handleStatus();
    } else {
        sendError("unknown_command");
    }
}

// --- Setup ---
void setup() {
    // USB Serial
    Serial.begin(USB_BAUD);
    while (!Serial) { delay(10); }

    // RS485 direction control
    pinMode(RS485_DE_PIN, OUTPUT);
    digitalWrite(RS485_DE_PIN, LOW);  // Default: receive mode

    // RS485 UART
    RS485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);

    // ModbusMaster callbacks
    node.begin(VFD_ADDR, RS485);
    node.preTransmission(preTransmission);
    node.postTransmission(postTransmission);

    // Status LED
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    inputBuffer.reserve(512);

    // Announce ready
    Serial.println("{\"ok\":true,\"data\":{\"fw\":\"B3-VFD-Bridge\",\"ver\":\"1.0.0\"}}");
}

// --- Main loop ---
void loop() {
    // Read USB Serial for JSON commands
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
            // Prevent buffer overflow
            if (inputBuffer.length() > 1024) {
                inputBuffer = "";
                sendError("input_too_long");
            }
        }
    }

    // Blink LED as heartbeat (on 100ms every 2s)
    static unsigned long lastBlink = 0;
    unsigned long now = millis();
    if (now - lastBlink > 2000) {
        digitalWrite(LED_PIN, HIGH);
        lastBlink = now;
    } else if (now - lastBlink > 100) {
        digitalWrite(LED_PIN, LOW);
    }
}
