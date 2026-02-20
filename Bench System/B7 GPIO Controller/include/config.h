/**
 * B6 GPIO Controller — Configuration (Node 13)
 *
 * Upstream RS485 (Hub Ch 4) + all valve relays, tower light,
 * E-stop monitor, environmental sensors (BME280, DS18B20, HC-SR04).
 *
 * Copyright (c) 2026 A.C.M.I.S Technologies LLP. All rights reserved.
 */

#ifndef CONFIG_H
#define CONFIG_H

// --- Node identity ---
#define NODE_ID       13
#define FW_NAME       "B6-GPIO-Controller"
#define FW_VERSION    "1.0.0"

// --- Upstream RS485 (to RPi5 via Hub Ch 4) ---
#define UP_BAUD       115200
#define UP_RX_PIN     16   // UART2 RX
#define UP_TX_PIN     17   // UART2 TX
#define UP_DE_PIN     4    // Driver Enable (HIGH = transmit)

// --- GPIO Outputs: Valves (active HIGH, relay-driven) ---
#define PIN_SV1           32   // Main line solenoid valve
#define PIN_BV_L1         25   // Ball valve DN25 (1" lane)
#define PIN_BV_L2         26   // Ball valve DN20 (3/4" lane)
#define PIN_BV_L3         27   // Ball valve DN15 (1/2" lane)
#define PIN_DV1_COLLECT   33   // Diverter valve → COLLECT (pulse)
#define PIN_DV1_BYPASS    23   // Diverter valve → BYPASS (pulse)
#define PIN_SV_DRN        14   // Drain solenoid valve
#define DIVERTER_PULSE_MS 200  // Pulse duration for latching diverter

// --- GPIO Outputs: Tower Light ---
#define PIN_TOWER_R   12   // Red
#define PIN_TOWER_Y   18   // Yellow
#define PIN_TOWER_G   19   // Green

// --- GPIO Inputs ---
#define PIN_ESTOP_MON 35   // E-stop contactor aux (active LOW, input-only pin)
#define PIN_BV_L1_FB  36   // Valve DN25 feedback (optional, input-only)
#define PIN_BV_L2_FB  39   // Valve DN20 feedback (optional, input-only)
#define PIN_BV_L3_FB  34   // Valve DN15 feedback (optional, input-only)

// --- I2C: BME280 (ATM-TEMP, ATM-HUM, ATM-BARO) ---
#define BME280_SDA    21
#define BME280_SCL    22
#define BME280_ADDR   0x76

// --- 1-Wire: DS18B20 (RES-TEMP) ---
#define ONEWIRE_PIN   15

// --- Ultrasonic: HC-SR04 (RES-LVL) ---
#define US_TRIG_PIN   13
#define US_ECHO_PIN   5
#define TANK_HEIGHT_CM 100.0  // Reservoir height for % calculation

// --- Status LED ---
#define LED_PIN 2

// --- E-Stop polling ---
#define ESTOP_POLL_MS 50   // Poll E-stop every 50ms

// --- Feature flags (set via build_flags or uncomment here) ---
// Requires: Adafruit BME280, OneWire, DallasTemperature libraries
#ifndef HAS_SENSORS
#define HAS_SENSORS 1      // 0 = GPIO-only build (no I2C/1-Wire/ultrasonic libs)
#endif

#endif // CONFIG_H
