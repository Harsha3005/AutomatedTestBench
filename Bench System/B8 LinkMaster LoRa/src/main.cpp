/**
 * B4 — LinkMaster LoRa Firmware (Bench Side, Node 14)
 *
 * Upstream RS485 (Hub Ch 5) ↔ LoRa SX1262 bridge with fragmentation and ACK.
 * Connects to Bench RPi5 via Waveshare 8-CH RS485 Hub.
 *
 * Transport protocol:
 *   - Messages <=254 bytes: sent as single DATA packet
 *   - Messages >254 bytes: split into FRAG packets (<=252 bytes each)
 *   - Every packet gets ACKed by the receiver
 *   - Retry up to 3 times on ACK timeout (3 seconds)
 *   - Receiver reassembles fragments before forwarding
 *
 * Packet format (over LoRa air):
 *   DATA:     [0x00|seq:6] [payload 1-254 bytes]
 *   FRAG:     [0x40|seq:6] [frag_idx] [frag_total] [payload 1-252 bytes]
 *   ACK:      [0x80|seq:6]
 *   FRAG_ACK: [0xC0|seq:6] [frag_idx]
 *
 * JSON protocol (RS485 upstream, 115200):
 *   TX: {"cmd":"LORA_SEND","data":"<base64>"}\n
 *       -> {"ok":true,"data":{"seq":5,"frags":1,"retries":0}}\n
 *       -> {"ok":false,"error":"no_ack","seq":5,"frag":0}\n
 *
 *   RX: {"event":"LORA_RX","data":"<base64>","rssi":-45,"snr":8,"len":120}\n
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

// ============================================================
// Host serial interface — RS485 upstream to RPi5 via hub
// ============================================================
HardwareSerial HostRS485(2);  // UART2

void hostSendJson(JsonDocument &doc) {
    digitalWrite(UP_DE_PIN, HIGH);
    delayMicroseconds(100);
    serializeJson(doc, HostRS485);
    HostRS485.println();
    HostRS485.flush();
    delayMicroseconds(100);
    digitalWrite(UP_DE_PIN, LOW);
}

void hostPrintln(const char *msg) {
    digitalWrite(UP_DE_PIN, HIGH);
    delayMicroseconds(100);
    HostRS485.println(msg);
    HostRS485.flush();
    delayMicroseconds(100);
    digitalWrite(UP_DE_PIN, LOW);
}

// ============================================================
// Base64 encode / decode
// ============================================================
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
            if (c == '=') { n <<= 6; }
            else if (c >= 0 && c < 128) {
                uint8_t val = b64_decode_table[(uint8_t)c];
                if (val == 255) return -1;
                n = (n << 6) | val;
            } else { return -1; }
        }
        if (outIdx < maxLen) output[outIdx++] = (n >> 16) & 0xFF;
        if (input[i + 2] != '=' && outIdx < maxLen) output[outIdx++] = (n >> 8) & 0xFF;
        if (input[i + 3] != '=' && outIdx < maxLen) output[outIdx++] = n & 0xFF;
    }
    return outIdx;
}

// ============================================================
// Globals
// ============================================================
SX126x lora(LORA_SS, LORA_RST, LORA_BUSY);
String inputBuffer;
uint8_t loraBuf[RX_BUF_SIZE];
uint8_t txSeq = 0;
unsigned long txCount = 0;
unsigned long rxCount = 0;
unsigned long ackCount = 0;
unsigned long retryCount = 0;

// Reassembly state for incoming fragmented messages
struct Reassembly {
    bool     active;
    uint8_t  seq;
    uint8_t  totalFrags;
    uint8_t  receivedCount;
    bool     received[MAX_FRAGMENTS];
    uint16_t fragLen[MAX_FRAGMENTS];
    uint8_t  data[MAX_MSG_SIZE];
    int8_t   lastRssi;
    int8_t   lastSnr;
    unsigned long lastFragTime;
} reasm = {0};

// ACK signal for TX wait loop
volatile bool     ackReceived = false;
volatile uint8_t  ackSeq = 0;
volatile uint8_t  ackFragIdx = 0;
volatile bool     ackIsFrag = false;

// ============================================================
// Low-level LoRa send (raw bytes, no protocol)
// ============================================================
bool loraSendRaw(const uint8_t *data, uint8_t len) {
    bool ok = lora.Send((uint8_t *)data, len, SX126x_TXMODE_SYNC);
    lora.ReceiveMode();
    return ok;
}

// ============================================================
// Send ACK / FRAG_ACK
// ============================================================
void sendAck(uint8_t seq) {
    uint8_t pkt[1] = { (uint8_t)(PKT_ACK | (seq & PKT_SEQ_MASK)) };
    loraSendRaw(pkt, 1);
}

void sendFragAck(uint8_t seq, uint8_t fragIdx) {
    uint8_t pkt[2] = {
        (uint8_t)(PKT_FRAG_ACK | (seq & PKT_SEQ_MASK)),
        fragIdx
    };
    loraSendRaw(pkt, 2);
}

// ============================================================
// Wait for ACK with timeout — polls LoRa RX
// ============================================================
void handleIncomingPacket(uint8_t *buf, uint8_t len, int8_t rssi, int8_t snr);

bool waitForAck(uint8_t expectedSeq, bool isFrag, uint8_t fragIdx) {
    ackReceived = false;
    unsigned long start = millis();

    while (millis() - start < ACK_TIMEOUT_MS) {
        uint8_t len = lora.Receive(loraBuf, sizeof(loraBuf));
        if (len > 0) {
            int8_t rssi, snr;
            lora.GetPacketStatus(&rssi, &snr);

            uint8_t type = loraBuf[0] & PKT_TYPE_MASK;
            uint8_t seq  = loraBuf[0] & PKT_SEQ_MASK;

            if (type == PKT_ACK && !isFrag && seq == expectedSeq) {
                ackCount++;
                return true;
            }
            if (type == PKT_FRAG_ACK && isFrag && seq == expectedSeq
                && len >= 2 && loraBuf[1] == fragIdx) {
                ackCount++;
                return true;
            }

            // Not our ACK — could be incoming data from other side
            handleIncomingPacket(loraBuf, len, rssi, snr);
        }
        delay(1);
    }
    return false;  // Timeout
}

// ============================================================
// Send data with ACK+retry (single packet)
// ============================================================
bool sendSingleWithAck(uint8_t seq, const uint8_t *data, uint16_t len) {
    uint8_t pkt[MAX_LORA_PKT];
    pkt[0] = PKT_DATA | (seq & PKT_SEQ_MASK);
    memcpy(&pkt[1], data, len);
    uint8_t pktLen = 1 + len;

    for (int attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        if (attempt > 0) retryCount++;
        if (!loraSendRaw(pkt, pktLen)) continue;
        if (waitForAck(seq, false, 0)) return true;
    }
    return false;
}

// ============================================================
// Send data with fragmentation + ACK+retry
// ============================================================
bool sendFragmented(uint8_t seq, const uint8_t *data, uint16_t totalLen,
                    uint8_t &failedFrag, int &totalRetries) {
    uint8_t numFrags = (totalLen + MAX_FRAG_DATA - 1) / MAX_FRAG_DATA;
    if (numFrags > MAX_FRAGMENTS) return false;

    totalRetries = 0;
    uint8_t pkt[MAX_LORA_PKT];

    for (uint8_t f = 0; f < numFrags; f++) {
        uint16_t offset = f * MAX_FRAG_DATA;
        uint16_t fragLen = totalLen - offset;
        if (fragLen > MAX_FRAG_DATA) fragLen = MAX_FRAG_DATA;

        pkt[0] = PKT_FRAG | (seq & PKT_SEQ_MASK);
        pkt[1] = f;
        pkt[2] = numFrags;
        memcpy(&pkt[3], &data[offset], fragLen);
        uint8_t pktLen = 3 + fragLen;

        bool acked = false;
        for (int attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            if (attempt > 0) { retryCount++; totalRetries++; }
            if (!loraSendRaw(pkt, pktLen)) continue;
            if (waitForAck(seq, true, f)) { acked = true; break; }
        }
        if (!acked) {
            failedFrag = f;
            return false;
        }
    }
    return true;
}

// ============================================================
// Handle incoming LoRa packet (DATA, FRAG, or unexpected ACK)
// ============================================================
void deliverMessage(const uint8_t *data, uint16_t len, int8_t rssi, int8_t snr) {
    rxCount++;
    String b64 = base64_encode(data, len);

    JsonDocument doc;
    doc["event"] = "LORA_RX";
    doc["data"] = b64;
    doc["rssi"] = rssi;
    doc["snr"] = snr;
    doc["len"] = len;
    hostSendJson(doc);
}

void handleIncomingPacket(uint8_t *buf, uint8_t len, int8_t rssi, int8_t snr) {
    if (len < 1) return;

    uint8_t type = buf[0] & PKT_TYPE_MASK;
    uint8_t seq  = buf[0] & PKT_SEQ_MASK;

    switch (type) {
    case PKT_DATA:
        sendAck(seq);
        if (len > 1) {
            deliverMessage(&buf[1], len - 1, rssi, snr);
        }
        break;

    case PKT_FRAG: {
        if (len < 4) break;
        uint8_t fragIdx   = buf[1];
        uint8_t fragTotal = buf[2];

        if (fragTotal == 0 || fragTotal > MAX_FRAGMENTS || fragIdx >= fragTotal) {
            break;
        }

        sendFragAck(seq, fragIdx);

        if (!reasm.active || reasm.seq != seq) {
            memset(&reasm, 0, sizeof(reasm));
            reasm.active = true;
            reasm.seq = seq;
            reasm.totalFrags = fragTotal;
        }

        if (reasm.totalFrags != fragTotal) break;

        if (!reasm.received[fragIdx]) {
            uint16_t dataLen = len - FRAG_HEADER_SIZE;
            uint16_t offset = fragIdx * MAX_FRAG_DATA;
            if (offset + dataLen <= MAX_MSG_SIZE) {
                memcpy(&reasm.data[offset], &buf[3], dataLen);
                reasm.fragLen[fragIdx] = dataLen;
                reasm.received[fragIdx] = true;
                reasm.receivedCount++;
            }
        }
        reasm.lastRssi = rssi;
        reasm.lastSnr = snr;
        reasm.lastFragTime = millis();

        if (reasm.receivedCount >= reasm.totalFrags) {
            uint16_t totalLen = 0;
            for (uint8_t i = 0; i < reasm.totalFrags; i++) {
                totalLen += reasm.fragLen[i];
            }
            deliverMessage(reasm.data, totalLen, reasm.lastRssi, reasm.lastSnr);
            reasm.active = false;
        }
        break;
    }

    case PKT_ACK:
    case PKT_FRAG_ACK:
        break;
    }
}

// ============================================================
// Command handlers
// ============================================================
void handleLoraSend(JsonDocument &cmd) {
    const char *b64data = cmd["data"] | "";
    if (strlen(b64data) == 0) {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "missing_data";
        hostSendJson(doc);
        return;
    }

    uint8_t msgBuf[MAX_MSG_SIZE];
    int len = base64_decode(b64data, msgBuf, sizeof(msgBuf));
    if (len < 0) {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "base64_decode_error";
        hostSendJson(doc);
        return;
    }
    if (len > (int)MAX_MSG_SIZE) {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "payload_too_large";
        hostSendJson(doc);
        return;
    }

    uint8_t seq = txSeq;
    txSeq = (txSeq + 1) & PKT_SEQ_MASK;

    if (len <= MAX_SINGLE_DATA) {
        if (sendSingleWithAck(seq, msgBuf, len)) {
            txCount++;
            JsonDocument doc;
            doc["ok"] = true;
            JsonObject data = doc["data"].to<JsonObject>();
            data["seq"] = seq;
            data["frags"] = 1;
            data["retries"] = 0;
            hostSendJson(doc);
        } else {
            JsonDocument doc;
            doc["ok"] = false;
            doc["error"] = "no_ack";
            doc["seq"] = seq;
            hostSendJson(doc);
        }
    } else {
        uint8_t failedFrag = 0;
        int totalRetries = 0;
        uint8_t numFrags = (len + MAX_FRAG_DATA - 1) / MAX_FRAG_DATA;

        if (sendFragmented(seq, msgBuf, len, failedFrag, totalRetries)) {
            txCount++;
            JsonDocument doc;
            doc["ok"] = true;
            JsonObject data = doc["data"].to<JsonObject>();
            data["seq"] = seq;
            data["frags"] = numFrags;
            data["retries"] = totalRetries;
            hostSendJson(doc);
        } else {
            JsonDocument doc;
            doc["ok"] = false;
            doc["error"] = "no_ack";
            doc["seq"] = seq;
            doc["frag"] = failedFrag;
            hostSendJson(doc);
        }
    }
}

void handleStatus() {
    JsonDocument doc;
    doc["ok"] = true;
    JsonObject data = doc["data"].to<JsonObject>();
    data["node_id"] = NODE_ID;
    data["fw"] = FW_NAME;
    data["ver"] = FW_VERSION;
    data["uptime_ms"] = millis();
    data["freq_hz"] = LORA_FREQ_HZ;
    data["sf"] = LORA_SF;
    data["bw_khz"] = 125;
    data["tx_power"] = LORA_TX_POWER;
    data["tx_count"] = txCount;
    data["rx_count"] = rxCount;
    data["ack_count"] = ackCount;
    data["retry_count"] = retryCount;
    hostSendJson(doc);
}

// ============================================================
// Process command from host
// ============================================================
void processCommand(const String &line) {
    JsonDocument cmd;
    DeserializationError err = deserializeJson(cmd, line);
    if (err) {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "json_parse_error";
        hostSendJson(doc);
        return;
    }

    const char *cmdStr = cmd["cmd"] | "";
    if (strcmp(cmdStr, "LORA_SEND") == 0) {
        handleLoraSend(cmd);
    } else if (strcmp(cmdStr, "STATUS") == 0) {
        handleStatus();
    } else {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "unknown_command";
        hostSendJson(doc);
    }
}

// ============================================================
// Setup
// ============================================================
void setup() {
    // Upstream RS485 (to RPi5 via hub)
    pinMode(UP_DE_PIN, OUTPUT);
    digitalWrite(UP_DE_PIN, LOW);
    HostRS485.begin(UP_BAUD, SERIAL_8N1, UP_RX_PIN, UP_TX_PIN);

    SPI.begin();

    int16_t ret = lora.begin(LORA_FREQ_HZ, LORA_TX_POWER);
    if (ret != ERR_NONE) {
        JsonDocument doc;
        doc["ok"] = false;
        doc["error"] = "lora_init_failed";
        doc["code"] = ret;
        hostSendJson(doc);
        while (1) { delay(1000); }
    }

    lora.LoRaConfig(LORA_SF, LORA_BW, LORA_CR, LORA_PREAMBLE,
                    LORA_PAYLOAD_LEN, LORA_CRC, LORA_INVERT_IQ);
    lora.ReceiveMode();

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
    data["freq"] = 865;
    data["sf"] = LORA_SF;
    hostSendJson(doc);
}

// ============================================================
// Main loop
// ============================================================
void loop() {
    // Check upstream RS485 for commands from RPi5
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
                JsonDocument doc;
                doc["ok"] = false;
                doc["error"] = "input_too_long";
                hostSendJson(doc);
            }
        }
    }

    // Check for incoming LoRa packets
    uint8_t len = lora.Receive(loraBuf, sizeof(loraBuf));
    if (len > 0) {
        int8_t rssi, snr;
        lora.GetPacketStatus(&rssi, &snr);
        handleIncomingPacket(loraBuf, len, rssi, snr);
    }

    // Reassembly timeout
    if (reasm.active && (millis() - reasm.lastFragTime > REASM_TIMEOUT_MS)) {
        reasm.active = false;
    }
}
