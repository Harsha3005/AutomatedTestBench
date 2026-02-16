/**
 * B4/L1 LinkMaster LoRa — Configuration
 *
 * SX1262 (RA-01SH) SPI pins and LoRa parameters.
 * 865 MHz ISM band (India), SF10, BW 125kHz.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- USB Serial ---
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

// --- Status LED ---
#define LED_PIN 2  // May conflict with DIO1 — adjust if needed

#endif // CONFIG_H
