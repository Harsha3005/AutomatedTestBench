/**
 * L1 LinkMaster LoRa — Configuration
 *
 * RS485 ↔ LoRa SX1262 bridge (Lab side).
 * Receives JSON commands from L2 RS485 Bridge, sends/receives LoRa.
 * 865 MHz ISM band (India), SF10, BW 125kHz.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- RS485 Serial (to L2 RS485 Bridge) ---
#define RS485_BAUD 115200
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_DE_PIN 15     // Driver Enable (HIGH = transmit, LOW = receive)

// --- USB Serial (debug only) ---
#define USB_BAUD 115200

// --- SX1262 SPI Pins ---
#define LORA_SS   5    // SPI CS / NSS
#define LORA_RST  14   // Reset
#define LORA_BUSY 4    // Busy indicator
#define LORA_DIO1 2    // DIO1 (IRQ)

// --- LoRa Parameters ---
#define LORA_FREQ_HZ     865000000  // 865 MHz (India ISM)
#define LORA_TX_POWER    22         // +22 dBm (max for SX1262)
#define LORA_SF          10         // Spreading Factor 10
#define LORA_BW          4          // 125 kHz (Ra01S lib: 4 = 125kHz)
#define LORA_CR          1          // Coding Rate 4/5 (Ra01S lib: 1 = 4/5)
#define LORA_PREAMBLE    8          // Preamble length
#define LORA_PAYLOAD_LEN 0          // 0 = variable length
#define LORA_CRC         true       // Enable CRC
#define LORA_INVERT_IQ   false      // Normal IQ

// --- Receive buffer ---
#define RX_BUF_SIZE 256

#endif // CONFIG_H
