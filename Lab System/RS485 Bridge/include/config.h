/**
 * L2 Lab RS485 Bridge — Configuration
 *
 * Generic RS485 Modbus RTU bridge for the lab PC.
 * Can talk to any Modbus device (configurable address).
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- USB Serial (to Lab PC) ---
#define USB_BAUD 115200

// --- RS485 Serial ---
#define RS485_BAUD_DEFAULT 9600
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_DE_PIN 4  // Driver Enable (HIGH = transmit)

// --- Status LED ---
#define LED_PIN 2

#endif // CONFIG_H
