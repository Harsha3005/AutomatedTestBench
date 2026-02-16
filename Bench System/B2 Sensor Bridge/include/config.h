/**
 * B2 Sensor Bridge — Configuration (Node 10)
 *
 * Upstream RS485 (Hub Ch 1) ↔ Downstream RS485 Modbus RTU.
 * Downstream devices: EM (addr 1), Scale (addr 2), 4-20mA (addr 3).
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- Node identity ---
#define NODE_ID       10
#define FW_NAME       "B2-Sensor-Bridge"
#define FW_VERSION    "2.0.0"

// --- Upstream RS485 (to RPi5 via Hub Ch 1) ---
#define UP_BAUD       115200
#define UP_RX_PIN     16   // UART2 RX
#define UP_TX_PIN     17   // UART2 TX
#define UP_DE_PIN     4    // Driver Enable (HIGH = transmit)

// --- Downstream RS485 (to EM, Scale, 4-20mA) ---
#define DN_BAUD       9600
#define DN_RX_PIN     32   // UART1 RX
#define DN_TX_PIN     33   // UART1 TX
#define DN_DE_PIN     25   // Driver Enable (HIGH = transmit)

// --- Modbus device addresses ---
#define ADDR_EM    1   // EM flow meter (FT-01)
#define ADDR_SCALE 2   // Weighing scale (WT-01)
#define ADDR_420MA 3   // 4-20mA module (PT-01, PT-02, water temp)

// --- Status LED ---
#define LED_PIN 2

#endif // CONFIG_H
