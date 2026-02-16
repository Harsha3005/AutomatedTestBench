/**
 * L1 — LinkMaster LoRa Firmware (Lab Side)
 *
 * RS485 ↔ LoRa SX1262 bridge.
 * Receives JSON commands from L2 RS485 Bridge, transmits via LoRa.
 * Receives LoRa packets, forwards as JSON events via RS485 to L2.
 * Acts as a dumb radio pipe — all ASP encryption/decryption
 * is handled on the Lab Server side.
 *
 * Data flow:
 *   Lab Server --USB--> L2 --RS485--> L1 --LoRa RF--> B4 (Bench)
 *   Lab Server <-USB--- L2 <-RS485--- L1 <-LoRa RF--- B4 (Bench)
 *
 * Protocol (RS485, 115200, JSON lines):
 *   TX: {"cmd":"LORA_SEND","data":"<base64>"}\n
 *       → {"ok":true}\n
 *
 *   RX: (async event from radio)
 *       → {"event":"LORA_RX","data":"<base64>","rssi":-45,"snr":8}\n
 *
 *   Status: {"cmd":"STATUS"}\n
 *       → {"ok":true,"data":{"uptime_ms":...,"freq_hz":865000000,"sf":10}}\n
 *
 * LoRa: SX1262 (RA-01SH), 865 MHz, SF10, BW 125kHz, CR 4/5, +22 dBm
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <Ra01S.h>
#include "config.h"

// --- RS485 on UART2 ---
HardwareSerial RS485(2);

// --- Base64 lookup tables ---
static const char b64_chars[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static const uint8_t b64_decode_table[128] = {
    255,255,255,255,255,255,255,255,255,255,255,255,255,255,255,255,
    255,255,255,255,255,255,255,255,255,255,255,255,255,255,255,255,
    255,255,255,255,255,255,255,255,255,255,255, 62,255,255,255, 63,
     52, 53, 54, 55, 56, 57, 58, 59, 60, 61,255,255,255,  0,255,255,
    255,  0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14,
     15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,255,255,255,255,255,
    255, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
     41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51,255,255,255,255,255,
};

String base64_encode(const uint8_t *data, size_t len) {
    String result;
    result.reserve(((len + 2) / 3) * 4);

    for (size_t i = 0; i < len; i += 3) {
        uint32_t n = ((uint32_t)data[i]) << 16;
        if (i + 1 < len) n |= ((uint32_t)data[i + 1]) << 8;
        if (i + 2 < len) n |= data[i + 2];

        result += b64_chars[(n >> 18) & 0x3F];
        result += b64_chars[(n >> 12) & 0x3F];
        result += (i + 1 < len) ? b64_chars[(n >> 6) & 0x3F] : '=';
        result += (i + 2 < len) ? b64_chars[n & 0x3F] : '=';
    }
    return result;
}

int base64_decode(const char *input, uint8_t *output, size_t maxLen) {
    size_t inLen = strlen(input);
    if (inLen % 4 != 0) return -1;

    size_t outIdx = 0;
    for (size_t i = 0; i < inLen; i += 4) {
        uint32_t n = 0;
        for (int j = 0; j < 4; j++) {
            char c = input[i + j];
            if (c == '=') {
                n <<= 6;
            } else if (c >= 0 && c < 128) {
                uint8_t val = b64_decode_table[(uint8_t)c];
                if (val == 255) return -1;
                n = (n << 6) | val;
            } else {
                return -1;
            }
        }
        if (outIdx < maxLen) output[outIdx++] = (n >> 16) & 0xFF;
        if (input[i + 2] != '=' && outIdx < maxLen) output[outIdx++] = (n >> 8) & 0xFF;
        if (input[i + 3] != '=' && outIdx < maxLen) output[outIdx++] = n & 0xFF;
    }
    return outIdx;
}

// --- Globals ---
SX126x lora(LORA_SS, LORA_RST, LORA_BUSY);
String inputBuffer;
uint8_t rxBuf[RX_BUF_SIZE];
unsigned long txCount = 0;
unsigned long rxCount = 0;

// --- RS485 TX helper (handles DE pin) ---
void rs485Print(const char *str) {
    digitalWrite(RS485_DE_PIN, HIGH);
    delayMicroseconds(50);
    RS485.print(str);
    RS485.flush();
    delayMicroseconds(50);
    digitalWrite(RS485_DE_PIN, LOW);
}

void rs485Println(const char *str) {
    digitalWrite(RS485_DE_PIN, HIGH);
    delayMicroseconds(50);
    RS485.println(str);
    RS485.flush();
    delayMicroseconds(50);
    digitalWrite(RS485_DE_PIN, LOW);
}

void rs485SendJson(JsonDocument &doc) {
    digitalWrite(RS485_DE_PIN, HIGH);
    delayMicroseconds(50);
    serializeJson(doc, RS485);
    RS485.println();
    RS485.flush();
    delayMicroseconds(50);
    digitalWrite(RS485_DE_PIN, LOW);
}

// --- JSON responses (sent over RS485) ---
void sendOk() {
    rs485Println("{\"ok\":true}");
}

void sendError(const char *msg) {
    JsonDocument doc;
    doc["ok"] = false;
    doc["error"] = msg;
    rs485SendJson(doc);
}

// --- Command handlers ---

void handleLoraSend(JsonDocument &cmd) {
    const char *b64data = cmd["data"] | "";
    if (strlen(b64data) == 0) {
        sendError("missing_data");
        return;
    }

    uint8_t txBuf[RX_BUF_SIZE];
    int len = base64_decode(b64data, txBuf, sizeof(txBuf));
    if (len < 0) {
        sendError("base64_decode_error");
        return;
    }
    if (len > 255) {
        sendError("payload_too_large");
        return;
    }

    bool ok = lora.Send(txBuf, (uint8_t)len, SX126x_TXMODE_SYNC);
    if (ok) {
        txCount++;
        sendOk();
    } else {
        sendError("tx_failed");
    }

    // Return to receive mode after TX
    lora.ReceiveMode();
}

void handleStatus() {
    JsonDocument doc;
    doc["ok"] = true;
    JsonObject data = doc["data"].to<JsonObject>();
    data["uptime_ms"] = millis();
    data["freq_hz"] = LORA_FREQ_HZ;
    data["sf"] = LORA_SF;
    data["bw_khz"] = 125;
    data["tx_power"] = LORA_TX_POWER;
    data["tx_count"] = txCount;
    data["rx_count"] = rxCount;
    rs485SendJson(doc);
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

    if (strcmp(cmdStr, "LORA_SEND") == 0) {
        handleLoraSend(cmd);
    } else if (strcmp(cmdStr, "STATUS") == 0) {
        handleStatus();
    } else {
        sendError("unknown_command");
    }
}

// --- Setup ---
void setup() {
    // USB Serial for debug output only
    Serial.begin(USB_BAUD);

    // RS485 to L2 Bridge — this is the command interface
    pinMode(RS485_DE_PIN, OUTPUT);
    digitalWrite(RS485_DE_PIN, LOW);  // Start in receive mode
    RS485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);

    SPI.begin();

    int16_t ret = lora.begin(LORA_FREQ_HZ, LORA_TX_POWER);
    if (ret != ERR_NONE) {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "lora_init_failed";
        doc["code"] = ret;
        rs485SendJson(doc);
        Serial.println("[ERROR] LoRa init failed!");
        while (1) { delay(1000); }  // Halt on init failure
    }

    lora.LoRaConfig(
        LORA_SF,
        LORA_BW,
        LORA_CR,
        LORA_PREAMBLE,
        LORA_PAYLOAD_LEN,
        LORA_CRC,
        LORA_INVERT_IQ
    );

    lora.ReceiveMode();

    inputBuffer.reserve(512);

    // Boot message over RS485 to Lab Server
    rs485Println("{\"ok\":true,\"data\":{\"fw\":\"L1-LinkMaster-LoRa\",\"ver\":\"1.0.0\",\"freq\":865}}");
    Serial.println("[INIT] L1 LinkMaster LoRa ready (RS485 + LoRa 865MHz SF10)");
}

// --- Main loop ---
void loop() {
    // Check RS485 for commands from L2 Bridge / Lab Server
    while (RS485.available()) {
        char c = RS485.read();
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

    // Check for incoming LoRa packets
    uint8_t len = lora.Receive(rxBuf, sizeof(rxBuf));
    if (len > 0) {
        rxCount++;
        int8_t rssi, snr;
        lora.GetPacketStatus(&rssi, &snr);

        String b64 = base64_encode(rxBuf, len);

        JsonDocument doc;
        doc["event"] = "LORA_RX";
        doc["data"] = b64;
        doc["rssi"] = rssi;
        doc["snr"] = snr;
        doc["len"] = len;
        rs485SendJson(doc);
    }
}
