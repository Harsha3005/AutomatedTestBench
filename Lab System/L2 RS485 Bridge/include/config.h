/**
 * L2 Lab RS485 Bridge — Configuration
 *
 * Transparent serial bridge: USB ↔ RS485.
 * Forwards bytes bidirectionally between Lab Server and L1 LinkMaster.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- USB Serial (to Lab Server) ---
#define USB_BAUD 115200

// --- RS485 Serial (to L1 LinkMaster) ---
#define RS485_BAUD 115200   // Must match L1 LinkMaster RS485 baud
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_DE_PIN 4      // Driver Enable (HIGH = transmit, LOW = receive)

// --- Status LED ---
#define LED_PIN 2

// --- Buffer ---
#define BUF_SIZE 512

#endif // CONFIG_H
