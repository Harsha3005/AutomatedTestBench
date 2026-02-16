/**
 * B3 VFD Bridge — Configuration
 *
 * RS485 pins and Modbus parameters for Delta VFD022EL43A.
 * Bus 2: isolated VFD-only bus.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- USB Serial (to RPi5) ---
#define USB_BAUD 115200

// --- RS485 Serial (to VFD) ---
#define RS485_BAUD 9600
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_DE_PIN 4  // Driver Enable (HIGH = transmit)

// --- Modbus ---
#define VFD_ADDR 1
#define MODBUS_TIMEOUT_MS 1000

// --- Status LED ---
#define LED_PIN 2  // Built-in LED on most ESP32 dev boards

#endif // CONFIG_H
