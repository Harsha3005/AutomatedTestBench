/**
 * B5 DUT Bridge — Configuration (Node 12)
 *
 * Upstream RS485 (Hub Ch 3) ↔ Downstream RS485 Modbus RTU (DUT meter).
 * DUT address configurable via SET_ADDR command.
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- Node identity ---
#define NODE_ID       12
#define FW_NAME       "B5-DUT-Bridge"
#define FW_VERSION    "1.0.0"

// --- Upstream RS485 (to RPi5 via Hub Ch 3) ---
#define UP_BAUD       115200
#define UP_RX_PIN     16   // UART2 RX
#define UP_TX_PIN     17   // UART2 TX
#define UP_DE_PIN     4    // Driver Enable (HIGH = transmit)

// --- Downstream RS485 (to DUT meter) ---
#define DN_BAUD       9600
#define DN_RX_PIN     32   // UART1 RX
#define DN_TX_PIN     33   // UART1 TX
#define DN_DE_PIN     25   // Driver Enable (HIGH = transmit)

// --- Modbus ---
#define DEFAULT_DUT_ADDR  20
#define MODBUS_TIMEOUT_MS 1000

// --- Status LED ---
#define LED_PIN 2

#endif // CONFIG_H
