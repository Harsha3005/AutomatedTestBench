/*
 * =============================================================================
 * Maxsense LoRa Receiver - Reference Implementation
 * =============================================================================
 * Receives and decodes Maxsense protocol packets
 *
 * Hardware: ESP32 + RA-01SH (SX1262)
 *
 * Wiring:
 *   RA-01SH    ESP32
 *   --------   -----
 *   VCC        3.3V
 *   GND        GND
 *   SCK        GPIO18 (VSPI CLK)
 *   MISO       GPIO19 (VSPI MISO)
 *   MOSI       GPIO23 (VSPI MOSI)
 *   NSS        GPIO5  (Chip Select)
 *   RST        GPIO14 (Reset)
 *   BUSY       GPIO26 (Busy Status)
 *
 * Copyright (c) 2026 Maxsense. ACMIS Technologies LLP
 * All rights reserved.
 * =============================================================================
 */

#include <Arduino.h>
#include <Ra01S.h>

// =============================================================================
// MAXSENSE PACKET HEADER DEFINITIONS
// =============================================================================
#define MX_HEADER_SIZE          7       // Header + DeviceID(4) + SeqNum(2)

// Header byte flags (byte 0)
#define MX_VERSION_MASK         0xC0    // bits 7-6
#define MX_ENCRYPTED_FLAG       0x20    // bit 5
#define MX_ACK_REQ_FLAG         0x10    // bit 4
#define MX_TYPE_MASK            0x0F    // bits 3-0

// Packet types
#define MX_TYPE_DATA            0x00
#define MX_TYPE_CONFIG          0x01
#define MX_TYPE_STATUS          0x02
#define MX_TYPE_ACK             0x03
#define MX_TYPE_COMMAND         0x04

// Get packet type name
const char* getPacketTypeName(uint8_t type) {
    switch (type & MX_TYPE_MASK) {
        case MX_TYPE_DATA:    return "DATA";
        case MX_TYPE_CONFIG:  return "CONFIG";
        case MX_TYPE_STATUS:  return "STATUS";
        case MX_TYPE_ACK:     return "ACK";
        case MX_TYPE_COMMAND: return "COMMAND";
        default:              return "UNKNOWN";
    }
}

// =============================================================================
// LORA CONFIGURATION - MUST MATCH TRANSMITTER SETTINGS!
// =============================================================================
#define RF_FREQUENCY            866000000   // Hz (IN865: 865-867 MHz)
#define TX_OUTPUT_POWER         22          // dBm (not used for RX, but needed for init)
#define LORA_SPREADING_FACTOR   10          // SF7-SF12 (MUST MATCH TX!)
#define LORA_BANDWIDTH          4           // 4=125kHz, 5=250kHz, 6=500kHz
#define LORA_CODINGRATE         1           // 1=4/5, 2=4/6, 3=4/7, 4=4/8
#define LORA_PREAMBLE_LENGTH    8           // Preamble symbols
#define LORA_PAYLOADLENGTH      0           // 0=Variable length (explicit header)

// =============================================================================
// SF vs Sensitivity Reference (BW=125kHz)
// =============================================================================
// SF7:  -123 dBm sensitivity (shortest range, fastest)
// SF8:  -126 dBm sensitivity
// SF9:  -129 dBm sensitivity
// SF10: -132 dBm sensitivity
// SF11: -134.5 dBm sensitivity
// SF12: -137 dBm sensitivity (longest range, slowest)
//
// RSSI Guidelines:
//   > -70 dBm  = Excellent signal
//   -70 to -85 = Good signal
//   -85 to -100 = Fair signal
//   < -100 dBm = Weak signal
//
// SNR Guidelines:
//   > 10 dB = Excellent
//   5-10 dB = Good
//   0-5 dB  = Fair
//   < 0 dB  = Poor (but still decodable with LoRa)
// =============================================================================

// Hardware pins for ESP32 + RA-01SH
#define LORA_NSS_PIN    5
#define LORA_RST_PIN    14
#define LORA_BUSY_PIN   26

// LoRa radio instance
SX126x lora(LORA_NSS_PIN, LORA_RST_PIN, LORA_BUSY_PIN);

// Statistics
uint32_t rxCount = 0;
uint32_t rxErrors = 0;
int8_t lastRssi = 0;
int8_t lastSnr = 0;
int8_t minRssi = 0;
int8_t maxRssi = -128;

// =============================================================================
// PRINT CONFIGURATION
// =============================================================================
void printConfig() {
    Serial.println();
    Serial.println("╔═══════════════════════════════════════════════════════════╗");
    Serial.println("║          LoRa Receiver - Reference Implementation         ║");
    Serial.println("║                      Maxsense 2026                        ║");
    Serial.println("╠═══════════════════════════════════════════════════════════╣");
    Serial.printf("║  Frequency:    %lu Hz (%.1f MHz)                    ║\n",
                  RF_FREQUENCY, RF_FREQUENCY / 1000000.0);
    Serial.printf("║  SF:           %d                                          ║\n", LORA_SPREADING_FACTOR);
    Serial.printf("║  Bandwidth:    %s                                     ║\n",
                  LORA_BANDWIDTH == 4 ? "125 kHz" :
                  LORA_BANDWIDTH == 5 ? "250 kHz" : "500 kHz");
    Serial.printf("║  Coding Rate:  4/%d                                         ║\n", 4 + LORA_CODINGRATE);
    Serial.printf("║  Preamble:     %d symbols                                   ║\n", LORA_PREAMBLE_LENGTH);
    Serial.println("╠═══════════════════════════════════════════════════════════╣");
    Serial.println("║  Hardware: ESP32 + RA-01SH (SX1262)                       ║");
    Serial.printf("║  Pins: NSS=%d, RST=%d, BUSY=%d                             ║\n",
                  LORA_NSS_PIN, LORA_RST_PIN, LORA_BUSY_PIN);
    Serial.println("╚═══════════════════════════════════════════════════════════╝");
    Serial.println();
}

// =============================================================================
// PRINT STATISTICS
// =============================================================================
void printStats() {
    Serial.println("┌─────────────────────────────────────────┐");
    Serial.printf("│ STATISTICS - Packets RX: %-6lu         │\n", rxCount);
    Serial.printf("│ RSSI Range: %d to %d dBm               │\n", minRssi, maxRssi);
    Serial.printf("│ Last RSSI: %d dBm, SNR: %d dB          │\n", lastRssi, lastSnr);
    Serial.println("└─────────────────────────────────────────┘");
}

// =============================================================================
// GET SIGNAL QUALITY STRING
// =============================================================================
const char* getSignalQuality(int8_t rssi, int8_t snr) {
    if (rssi > -70 && snr > 10) return "EXCELLENT";
    if (rssi > -85 && snr > 5)  return "GOOD";
    if (rssi > -100 && snr > 0) return "FAIR";
    return "WEAK";
}

// =============================================================================
// SETUP
// =============================================================================
void setup() {
    delay(2000);  // Allow time for serial monitor to connect
    Serial.begin(115200);

    printConfig();

    Serial.println("[INIT] Initializing LoRa module...");

    // Initialize LoRa
    int16_t ret = lora.begin(RF_FREQUENCY, TX_OUTPUT_POWER);
    if (ret != ERR_NONE) {
        Serial.printf("[ERROR] LoRa init failed with code: %d\n", ret);
        Serial.println("[ERROR] Check wiring and module!");
        while(1) { delay(1000); }
    }

    // Configure LoRa modulation
    lora.LoRaConfig(
        LORA_SPREADING_FACTOR,
        LORA_BANDWIDTH,
        LORA_CODINGRATE,
        LORA_PREAMBLE_LENGTH,
        LORA_PAYLOADLENGTH,
        true,   // CRC enabled
        false   // Standard IQ (not inverted)
    );

    Serial.println("[INIT] LoRa initialized successfully!");
    Serial.println();
    Serial.println("╔═══════════════════════════════════════╗");
    Serial.println("║     LISTENING FOR LORA MESSAGES...    ║");
    Serial.println("╚═══════════════════════════════════════╝");
    Serial.println();
}

// =============================================================================
// PARSE MAXSENSE PACKET
// =============================================================================
struct MaxsensePacket {
    uint8_t version;
    uint8_t type;
    bool encrypted;
    bool ackRequired;
    char deviceId[12];      // "XXYYZZ" format (hex of last 4 MAC bytes)
    uint16_t seqNum;
    uint8_t* payload;
    uint8_t payloadLen;
    bool valid;
};

MaxsensePacket parseMaxsensePacket(uint8_t* data, uint8_t len) {
    MaxsensePacket pkt = {0};
    pkt.valid = false;

    // Check minimum packet size
    if (len < MX_HEADER_SIZE) {
        return pkt;
    }

    // Parse header byte
    uint8_t header = data[0];
    pkt.version = (header & MX_VERSION_MASK) >> 6;
    pkt.type = header & MX_TYPE_MASK;
    pkt.encrypted = (header & MX_ENCRYPTED_FLAG) != 0;
    pkt.ackRequired = (header & MX_ACK_REQ_FLAG) != 0;

    // Parse device ID (bytes 1-4, format as hex string)
    snprintf(pkt.deviceId, sizeof(pkt.deviceId), "%02X%02X%02X%02X",
             data[1], data[2], data[3], data[4]);

    // Parse sequence number (bytes 5-6, big endian)
    pkt.seqNum = (data[5] << 8) | data[6];

    // Payload starts at byte 7
    pkt.payload = &data[MX_HEADER_SIZE];
    pkt.payloadLen = len - MX_HEADER_SIZE;

    pkt.valid = true;
    return pkt;
}

// =============================================================================
// LOOP
// =============================================================================
void loop() {
    uint8_t rxData[256];
    uint8_t rxLen = lora.Receive(rxData, 255);

    if (rxLen > 0) {
        rxCount++;

        // Get signal quality
        lora.GetPacketStatus(&lastRssi, &lastSnr);

        // Update min/max RSSI
        if (lastRssi < minRssi || rxCount == 1) minRssi = lastRssi;
        if (lastRssi > maxRssi) maxRssi = lastRssi;

        // Try to parse as Maxsense packet
        MaxsensePacket pkt = parseMaxsensePacket(rxData, rxLen);

        if (pkt.valid) {
            // Null-terminate the payload for string display
            pkt.payload[pkt.payloadLen] = '\0';

            // Print Maxsense packet
            Serial.println();
            Serial.println("╔═══════════════════════════════════════════════════════════╗");
            Serial.println("║              MAXSENSE PACKET RECEIVED                     ║");
            Serial.println("╠═══════════════════════════════════════════════════════════╣");
            Serial.printf("║  Packet #%-6lu                                           ║\n", rxCount);
            Serial.printf("║  Device:    MXS-%s                                  ║\n", pkt.deviceId);
            Serial.printf("║  Type:      %-10s  Seq: %-6u                       ║\n",
                          getPacketTypeName(pkt.type), pkt.seqNum);
            Serial.printf("║  RSSI:      %-4d dBm    SNR: %-3d dB    [%s]          ║\n",
                          lastRssi, lastSnr, getSignalQuality(lastRssi, lastSnr));
            Serial.println("╠═══════════════════════════════════════════════════════════╣");
            Serial.println("║  PAYLOAD:                                                 ║");
            Serial.println("╠═══════════════════════════════════════════════════════════╣");

            // Print payload - the actual message!
            Serial.println();
            Serial.println((char*)pkt.payload);
            Serial.println();

            Serial.println("╚═══════════════════════════════════════════════════════════╝");
            Serial.println();
        } else {
            // Raw packet (not Maxsense format)
            rxData[rxLen] = '\0';

            Serial.println();
            Serial.println("┌───────────────── RAW MESSAGE ─────────────────┐");
            Serial.printf("│ Packet #%-6lu                  Length: %-3d bytes │\n", rxCount, rxLen);
            Serial.println("├────────────────────────────────────────────────┤");
            Serial.print("│ ");
            Serial.println((char*)rxData);
            Serial.println("├────────────────────────────────────────────────┤");
            Serial.printf("│ RSSI: %-4d dBm    SNR: %-3d dB                  │\n", lastRssi, lastSnr);
            Serial.println("└────────────────────────────────────────────────┘");
            Serial.println();
        }

        // Print statistics every 10 packets
        if (rxCount % 10 == 0) {
            printStats();
            Serial.println();
        }
    }

    delay(10);  // Small delay to prevent tight loop
}
