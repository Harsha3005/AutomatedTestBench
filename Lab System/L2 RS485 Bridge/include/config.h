/**
 * L2 RS485 Bridge — Configuration (Node 16)
 *
 * Transparent serial bridge: USB (Lab Server) ↔ RS485 (L1 LinkMaster).
 * Forwards bytes bidirectionally. No protocol parsing.
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- Node identity ---
#define NODE_ID       16
#define FW_NAME       "L2-RS485-Bridge"
#define FW_VERSION    "2.0.0"

// --- USB Serial (to Lab Server) ---
#define USB_BAUD 115200

// --- RS485 Serial (to L1 LinkMaster) ---
#define RS485_BAUD    115200   // Must match L1 upstream baud
#define RS485_RX_PIN  16       // UART2 RX
#define RS485_TX_PIN  17       // UART2 TX
#define RS485_DE_PIN  4        // Driver Enable (HIGH = transmit, LOW = receive)

// --- Status LED ---
#define LED_PIN 2

// --- Buffer ---
#define BUF_SIZE 512

#endif // CONFIG_H
