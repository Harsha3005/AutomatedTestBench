/*
 * LoRa Transmitter - Reference Implementation
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
 * Author: Maxsense
 * Date: 2026
 */

#include <Arduino.h>
#include <Ra01S.h>

// =============================================================================
// LORA CONFIGURATION - CHANGE THESE TO TEST DIFFERENT SETTINGS
// =============================================================================
#define RF_FREQUENCY            866000000   // Hz (IN865: 865-867 MHz)
#define TX_OUTPUT_POWER         22          // dBm (max: 22)
#define LORA_SPREADING_FACTOR   12          // SF7-SF12 (higher = longer range, slower)
#define LORA_BANDWIDTH          4           // 4=125kHz, 5=250kHz, 6=500kHz
#define LORA_CODINGRATE         1           // 1=4/5, 2=4/6, 3=4/7, 4=4/8
#define LORA_PREAMBLE_LENGTH    8           // Preamble symbols
#define LORA_PAYLOADLENGTH      0           // 0=Variable length (explicit header)

// Transmission interval (increase for larger payloads at higher SF)
#define TX_INTERVAL_MS          5000        // Send every 5 seconds

// =============================================================================
// SF vs Max Payload & Airtime Reference (BW=125kHz, CR=4/5)
// =============================================================================
// SF7:  Max 255 bytes, ~100ms airtime for 50 bytes  (fastest)
// SF8:  Max 255 bytes, ~180ms airtime for 50 bytes
// SF9:  Max 255 bytes, ~330ms airtime for 50 bytes
// SF10: Max 255 bytes, ~650ms airtime for 50 bytes
// SF11: Max 255 bytes, ~1.3s airtime for 50 bytes
// SF12: Max 255 bytes, ~2.5s airtime for 50 bytes  (longest range)
//
// Note: Higher SF = Better sensitivity = Longer range but slower data rate
// =============================================================================

// Hardware pins for ESP32 + RA-01SH
#define LORA_NSS_PIN    5
#define LORA_RST_PIN    14
#define LORA_BUSY_PIN   26

// LoRa radio instance
SX126x lora(LORA_NSS_PIN, LORA_RST_PIN, LORA_BUSY_PIN);

// Statistics
uint32_t txCount = 0;
uint32_t txSuccess = 0;
uint32_t txFail = 0;

// =============================================================================
// PRINT CONFIGURATION
// =============================================================================
void printConfig() {
    Serial.println();
    Serial.println("╔═══════════════════════════════════════════════════════════╗");
    Serial.println("║         LoRa Transmitter - Reference Implementation       ║");
    Serial.println("║                      Maxsense 2026                        ║");
    Serial.println("╠═══════════════════════════════════════════════════════════╣");
    Serial.printf("║  Frequency:    %lu Hz (%.1f MHz)                    ║\n",
                  RF_FREQUENCY, RF_FREQUENCY / 1000000.0);
    Serial.printf("║  TX Power:     %d dBm                                      ║\n", TX_OUTPUT_POWER);
    Serial.printf("║  SF:           %d                                          ║\n", LORA_SPREADING_FACTOR);
    Serial.printf("║  Bandwidth:    %s                                     ║\n",
                  LORA_BANDWIDTH == 4 ? "125 kHz" :
                  LORA_BANDWIDTH == 5 ? "250 kHz" : "500 kHz");
    Serial.printf("║  Coding Rate:  4/%d                                         ║\n", 4 + LORA_CODINGRATE);
    Serial.printf("║  Preamble:     %d symbols                                   ║\n", LORA_PREAMBLE_LENGTH);
    Serial.printf("║  Max Payload:  255 bytes                                   ║\n");
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
    float successRate = txCount > 0 ? (txSuccess * 100.0 / txCount) : 0;
    Serial.printf("[STATS] TX: %lu | OK: %lu | FAIL: %lu | Rate: %.1f%%\n",
                  txCount, txSuccess, txFail, successRate);
}

// =============================================================================
// SETUP
// =============================================================================
void setup() {
    delay(1000);
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
    Serial.println("=== TRANSMITTING ===");
    Serial.println();
}

// =============================================================================
// TEST PAYLOAD SIZE - Change this to test different sizes
// =============================================================================
#define TEST_PAYLOAD_SIZE   255     // 1-255 bytes (255 = max for SX1262)

// =============================================================================
// LOOP
// =============================================================================
void loop() {
    static uint32_t lastTxTime = 0;
    uint32_t now = millis();

    if (now - lastTxTime >= TX_INTERVAL_MS) {
        lastTxTime = now;
        txCount++;

        // Build test message - fill to TEST_PAYLOAD_SIZE bytes
        char txData[256];

        // Start with JSON header
        int headerLen = snprintf(txData, sizeof(txData),
            "{\"seq\":%lu,\"ms\":%lu,\"len\":%d,\"data\":\"",
            txCount, now, TEST_PAYLOAD_SIZE);

        // Fill remaining space with pattern (leave room for closing "})
        int dataLen = TEST_PAYLOAD_SIZE - headerLen - 2;  // -2 for "}
        if (dataLen > 0) {
            for (int i = 0; i < dataLen; i++) {
                // Repeating pattern: A-Z, a-z, 0-9
                char c;
                int idx = i % 62;
                if (idx < 26) c = 'A' + idx;
                else if (idx < 52) c = 'a' + (idx - 26);
                else c = '0' + (idx - 52);
                txData[headerLen + i] = c;
            }
        }

        // Close JSON
        txData[headerLen + dataLen] = '"';
        txData[headerLen + dataLen + 1] = '}';
        txData[headerLen + dataLen + 2] = '\0';

        int len = strlen(txData);

        Serial.printf("[TX #%lu] Sending %d bytes\n", txCount, len);
        Serial.printf("  First 60 chars: %.60s...\n", txData);

        // Transmit (synchronous - waits for completion)
        uint32_t txStart = millis();
        bool success = lora.Send((uint8_t*)txData, len, SX126x_TXMODE_SYNC);
        uint32_t txTime = millis() - txStart;

        if (success) {
            txSuccess++;
            Serial.printf("[TX #%lu] SUCCESS - Airtime: %lu ms (%.1f bytes/sec)\n",
                          txCount, txTime, (len * 1000.0) / txTime);
        } else {
            txFail++;
            Serial.printf("[TX #%lu] FAILED!\n", txCount);
        }

        // Print statistics every 10 packets
        if (txCount % 10 == 0) {
            printStats();
        }

        Serial.println();
    }
}
