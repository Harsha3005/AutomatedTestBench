/**
 * B2 Bench Sensor Bridge — Configuration
 *
 * RS485 (Bus 1) + GPIO pin assignments.
 * Pin numbers are PROVISIONAL — update after hardware wiring.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- USB Serial (to RPi5) ---
#define USB_BAUD 115200

// --- RS485 Serial (Bus 1) ---
#define RS485_BAUD 9600
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_DE_PIN 4  // Driver Enable

// --- Modbus device addresses ---
#define ADDR_EM    1   // Energy meter (F1)
#define ADDR_SCALE 2   // Weighing scale (F2)
#define ADDR_420MA 3   // 4-20mA module (F3, pressure/temp)
#define ADDR_DUT   20  // Device Under Test

// --- GPIO Outputs: Lane Ball Valves (active HIGH) ---
#define PIN_BV_L1 25   // 1" lane
#define PIN_BV_L2 26   // 3/4" lane
#define PIN_BV_L3 27   // 1/2" lane

// --- GPIO Outputs: Diverter Valve (dual-coil latching) ---
#define PIN_DV1_COLLECT 32  // Pulse HIGH → COLLECT position
#define PIN_DV1_BYPASS  33  // Pulse HIGH → BYPASS position
#define DIVERTER_PULSE_MS 200

// --- GPIO Outputs: Drain Solenoid ---
#define PIN_SV_DRN 14  // Drain solenoid (active HIGH)

// --- GPIO Outputs: Tower Light ---
#define PIN_TOWER_R 12  // Red
#define PIN_TOWER_Y 13  // Yellow
#define PIN_TOWER_G 15  // Green

// --- GPIO Inputs ---
#define PIN_ESTOP_MON 34  // E-stop contactor aux (active LOW, INPUT_PULLUP)

// --- Status LED ---
#define LED_PIN 2

#endif // CONFIG_H
