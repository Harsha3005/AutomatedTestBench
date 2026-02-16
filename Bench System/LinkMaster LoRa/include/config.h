/**
 * B4 LinkMaster LoRa — Configuration (Bench Side)
 *
 * USB Serial ↔ LoRa SX1262 bridge with fragmentation + ACK.
 * 865 MHz ISM band (India), SF10, BW 125kHz.
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- USB Serial (to Bench RPi5) ---
#define USB_BAUD 115200

// --- SX1262 SPI Pins ---
#define LORA_SS   5    // SPI CS / NSS
#define LORA_RST  14   // Reset
#define LORA_BUSY 4    // Busy indicator
#define LORA_DIO1 2    // DIO1 (IRQ)

// --- LoRa Parameters (865 MHz SF10 — standard across all nodes) ---
#define LORA_FREQ_HZ     865000000  // 865 MHz (India ISM)
#define LORA_TX_POWER    22         // +22 dBm (max for SX1262)
#define LORA_SF          10         // Spreading Factor 10
#define LORA_BW          4          // 125 kHz (Ra01S lib: 4 = 125kHz)
#define LORA_CR          1          // Coding Rate 4/5 (Ra01S lib: 1 = 4/5)
#define LORA_PREAMBLE    8          // Preamble length
#define LORA_PAYLOAD_LEN 0          // 0 = variable length
#define LORA_CRC         true       // Enable CRC
#define LORA_INVERT_IQ   false      // Normal IQ

// --- Transport Protocol ---
#define MAX_LORA_PKT     255        // Max LoRa packet size
#define FRAG_HEADER_SIZE 3          // [type|seq] [frag_idx] [frag_total]
#define SINGLE_HEADER    1          // [type|seq]
#define MAX_SINGLE_DATA  (MAX_LORA_PKT - SINGLE_HEADER)   // 254
#define MAX_FRAG_DATA    (MAX_LORA_PKT - FRAG_HEADER_SIZE) // 252
#define MAX_FRAGMENTS    20         // Max fragments per message
#define MAX_MSG_SIZE     (MAX_FRAGMENTS * MAX_FRAG_DATA)    // ~5040 bytes
#define ACK_TIMEOUT_MS   3000       // Wait for ACK (SF10 ~650ms for 50 bytes)
#define MAX_RETRIES      3          // Retries per packet/fragment
#define REASM_TIMEOUT_MS 30000      // Discard partial reassembly after 30s

// --- Packet types (bits 7-6 of byte 0) ---
#define PKT_DATA         0x00       // Single complete packet
#define PKT_FRAG         0x40       // Fragment of a larger message
#define PKT_ACK          0x80       // ACK for single packet
#define PKT_FRAG_ACK     0xC0       // ACK for a fragment
#define PKT_TYPE_MASK    0xC0
#define PKT_SEQ_MASK     0x3F       // 6-bit sequence (0-63)

// --- Receive buffer ---
#define RX_BUF_SIZE 256

#endif // CONFIG_H
