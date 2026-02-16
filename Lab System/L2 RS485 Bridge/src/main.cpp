/**
 * L2 — RS485 Bridge Firmware (Node 16)
 *
 * USB Serial ↔ RS485 transparent byte-level bridge.
 * Sits between Lab Server (USB) and L1 LinkMaster (RS485).
 * No protocol awareness — just forwards bytes in both directions.
 *
 * Data flow:
 *   Lab Server --USB--> L2 --RS485--> L1 LinkMaster --LoRa--> Bench
 *   Lab Server <-USB--- L2 <-RS485--- L1 LinkMaster <-LoRa--- Bench
 *
 * RS485 half-duplex: DE pin HIGH during TX, LOW during RX.
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#include <Arduino.h>
#include "config.h"

// --- RS485 on UART2 ---
HardwareSerial RS485(2);

// --- Buffers for bulk transfer ---
uint8_t usbBuf[BUF_SIZE];
uint8_t rs485Buf[BUF_SIZE];

// --- Statistics ---
unsigned long usbToRs485Bytes = 0;
unsigned long rs485ToUsbBytes = 0;

// --- Setup ---
void setup() {
    // USB Serial to Lab Server
    Serial.begin(USB_BAUD);
    while (!Serial) { delay(10); }

    // RS485 to L1 LinkMaster
    pinMode(RS485_DE_PIN, OUTPUT);
    digitalWrite(RS485_DE_PIN, LOW);  // Start in receive mode
    RS485.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);

    // Status LED
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    // Small delay for RS485 bus to settle
    delay(100);

    // Announce ready on USB (Lab Server can detect L2 is alive)
    Serial.print("{\"ok\":true,\"data\":{\"fw\":\"");
    Serial.print(FW_NAME);
    Serial.print("\",\"ver\":\"");
    Serial.print(FW_VERSION);
    Serial.print("\",\"node_id\":");
    Serial.print(NODE_ID);
    Serial.println("}}");
}

// --- Main loop ---
void loop() {
    // USB → RS485: Forward bytes from Lab Server to L1 LinkMaster
    int usbAvail = Serial.available();
    if (usbAvail > 0) {
        if (usbAvail > BUF_SIZE) usbAvail = BUF_SIZE;
        int bytesRead = Serial.readBytes(usbBuf, usbAvail);

        // Switch to transmit mode
        digitalWrite(RS485_DE_PIN, HIGH);
        delayMicroseconds(50);

        RS485.write(usbBuf, bytesRead);
        RS485.flush();  // Wait for TX complete

        // Switch back to receive mode
        delayMicroseconds(50);
        digitalWrite(RS485_DE_PIN, LOW);

        usbToRs485Bytes += bytesRead;
        digitalWrite(LED_PIN, HIGH);  // Blink on activity
    }

    // RS485 → USB: Forward bytes from L1 LinkMaster to Lab Server
    int rs485Avail = RS485.available();
    if (rs485Avail > 0) {
        if (rs485Avail > BUF_SIZE) rs485Avail = BUF_SIZE;
        int bytesRead = RS485.readBytes(rs485Buf, rs485Avail);

        Serial.write(rs485Buf, bytesRead);

        rs485ToUsbBytes += bytesRead;
        digitalWrite(LED_PIN, HIGH);  // Blink on activity
    }

    // LED off after brief flash
    static unsigned long ledOffTime = 0;
    if (digitalRead(LED_PIN) == HIGH) {
        if (ledOffTime == 0) {
            ledOffTime = millis() + 20;
        } else if (millis() >= ledOffTime) {
            digitalWrite(LED_PIN, LOW);
            ledOffTime = 0;
        }
    }
}
