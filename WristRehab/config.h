// =============================== Config.h ===============================
#pragma once
#include <Arduino.h>

// -------------------- Pins --------------------
static constexpr int PIN_IN1 = 10;   // H-bridge PWM
static constexpr int PIN_IN2 = 9;    // H-bridge PWM
static constexpr int PIN_ENC_A = 3;  // Leonardo supports 0,1,2,3,7
static constexpr int PIN_ENC_B = 2;
static constexpr int PIN_POT   = A0;
static constexpr int HX_DOUT   = 5;
static constexpr int HX_SCK    = 6;

// ----------------- Position clamps (encoder space) -----------------
static constexpr float POS_MIN_RAD = -1.0f;
static constexpr float POS_MAX_RAD =  1.0f;

// ----------------- Encoder params -----------------
static constexpr long AMT_CPR = 2048;             // PPR per channel
static constexpr float COUNT_TO_RAD = (2.0f * PI) / (float)(AMT_CPR * 4L);

// H-bridge dead-time on reversal
static constexpr unsigned long REV_DEADTIME_US = 5;

// ----------------- HX711 calibration -----------------
static constexpr float COUNTS_PER_N = 62150.0f;   // set so get_units() returns N

// ----------------- Geometry + signs -----------------
static constexpr float ARM_LENGTH_M = 0.09f;      // [m]
static constexpr float TORQUE_SIGN  = -1.0f;      // flip if needed

// ----------------- Potentiometer mapping -----------------
static constexpr int   POT_ADC_MIN   = 0;
static constexpr int   POT_ADC_MAX   = 1023;
static constexpr float THETA_MIN_DEG = 0.0f;
static constexpr float THETA_MAX_DEG = 270.0f;
static constexpr float THETA_MIN_RAD = THETA_MIN_DEG * DEG_TO_RAD;
static constexpr float THETA_MAX_RAD = THETA_MAX_DEG * DEG_TO_RAD;
static constexpr float POT_OFFSET_RAD =   -1.56f;   // align to your home

// ----------------- Gravity comp -----------------
static constexpr float DELTA_OFFSET_RAD = 0.0f;   // phase offset if needed



// ----------------- Filters & timing -----------------
static constexpr unsigned long SPEED_WIN_US =1000;  // speed oversampling window
static constexpr uint8_t W_MED_WIN = 3;               // median length (1,3,5,…)
static constexpr float FORCE_EMA_ALPHA = 1.0f;        // LPF for force (lower = more filtering)
static constexpr float Omega_EMA_ALPHA = 0.10f;

// Butterworth 2nd-order LPF coefficients for force filtering
static constexpr float BUTTER_B0 = 0.0675f;
static constexpr float BUTTER_B1 = 0.1349f;
static constexpr float BUTTER_B2 = 0.0675f;
static constexpr float BUTTER_A1 = -1.1430f;
static constexpr float BUTTER_A2 = 0.4128f;

// ----------------- Loop rates -----------------
static constexpr float LOOP_HZ      = 1000.0f;        // inner velocity loop
static constexpr unsigned long POS_DT_US = 10000.0f;     // ~100 Hz admittance
static constexpr unsigned long LOG_PERIOD_MS = 100;   // telemetry period

// -----------------Limits-----------------
static constexpr float W_ADM_MAX = 6.0f;   
static constexpr float DW_ADM_MAX = 30.0f;  
static constexpr uint8_t PWM_MAX   = 255;            
static constexpr uint8_t PWM_LIMIT = 255;           

// ----------------- Velocity PID -----------------
static constexpr float KP_INIT = 29.2825f;
static constexpr float KI_INIT = 1416.7f;
static constexpr float KD_INIT = 0.0140f;
static constexpr float INT_CLAMP = 50.0f;           // integral clamp (PWM)
static constexpr float D_TAU_VEL = 0.002f;           // deriv. LPF [s]

// ----------------- Admittance -----------------
static constexpr float Jv_INIT =0.01790f;
static constexpr float Bv_INIT =0.18492f;
static constexpr float Kv_INIT =0.47746f;
// static constexpr float Kv_INIT = 0.0f;

const float TAU_FAULT_LIMIT = 50.3f;   







