

#include <Arduino.h>
#include <HX711.h>
#include <math.h>

/* ========================== USER CONFIGURATION ========================= */

// Motor driver pins (dual PWM on an H-bridge)
const int PIN_IN1 = 10;      // PWM capable
const int PIN_IN2 = 9;       // PWM capable
float theta_meas_po =0.0f;
// Encoder pins (external interrupts)
const int PIN_ENC_A = 1;     // Leonardo supports 0,1,2,3,7
const int PIN_ENC_B = 2;

// Potentiometer pin for homing angle
const int PIN_POT = A0;

// HX711 pins
const int HX_DOUT = 5;
const int HX_SCK  = 6;
static HX711 scale;

// === Encoder parameters ===
constexpr long AMT_CPR = 2048;                   // encoder PPR per channel
// x4 decoding → counts per rev = AMT_CPR * 4
// Count-to-rad: (2π) / (AMT_CPR*4). We compute inline where needed.

// Dead-time on H-bridge reversal (us)
constexpr unsigned long REV_DEADTIME_US = 5;

// Calibration for HX711: counts per Newton.
// Set this so scale.get_units() returns Newtons directly.
const float COUNTS_PER_N = 62150.0f;

// Geometry
const float ARM_LENGTH_M = 0.09f;

// Torque sign (flip if direction is inverted for your mechanics)
const float TORQUE_SIGN = -1.0f;

// Potentiometer usage range (for mapping ADC→angle)
int   POT_ADC_MIN = 0;
int   POT_ADC_MAX = 1023;
const float THETA_MIN_DEG = 0.0f;
const float THETA_MAX_DEG = 270.0f;
const float THETA_MIN_RAD = THETA_MIN_DEG * DEG_TO_RAD;
const float THETA_MAX_RAD = THETA_MAX_DEG * DEG_TO_RAD;

// === Gravity compensation ===
// Total mass (kg) of handle + wrist (+ tool)
const float TOTAL_MASS_KG = 0.5f;   // <-- set this for your rig
// Phase offset between pot angle and true horizontal (radians)
const float DELTA_OFFSET_RAD = 0.0f;  // tweak if needed

// === Position clamps (radians, encoder-based) ===
const float POS_MIN_RAD = -1.2f;
const float POS_MAX_RAD =  1.2f;

// Speed filter parameters
const unsigned long SPEED_WIN_US = 1000;   // oversampling window (5 ms)
constexpr uint8_t W_MED_WIN = 3;           // median window length (1,3,5,…)

// Force low-pass filter cutoff (Hz)
const float FORCE_EMA_CUTOFF_HZ = 20.0f;

// Control loop frequencies
const float LOOP_HZ = 1000.0f;             // inner velocity loop (Hz)
const unsigned long POS_DT_US = 10000;      // admittance update (~200 Hz)
const unsigned long LOG_PERIOD_MS = 100;   // telemetry period (ms)

// Velocity command shaping and saturation
const float W_CMD_MAX  = 250.0f;            // max commanded velocity [rad/s]
const float DW_CMD_MAX = 800.0f;           // max accel [rad/s²] for w_cmd
const uint8_t PWM_MAX  = 255;              // 8-bit PWM
const uint8_t PWM_LIMIT = 255;             // soft limit; can be < PWM_MAX

// Velocity PID gains (inner loop)
float Kp = 20.0f;
float Ki = 100.6634f;
float Kd = 0.076268f;
const float INT_CLAMP = 150.0f;            // integral clamp (PWM)
const float D_TAU_VEL = 0.002f;            // derivative LPF time constant [s]

// Admittance model parameters: Jv [kg·m²], Bv [N·m·s/rad], Kv [N·m/rad]
float Jv = 0.057296f;
float Bv = 0.16273f;
float Kv = 0.095493f;
bool  USE_ADMITTANCE = true;
const float W_ADM_MAX  = 30.0f;            // clamp for admittance velocity
const float DW_ADM_MAX = 1000.0f;          // rate limit for admittance

/* ========================= INTERNAL STATE ========================= */

// Encoder state (x4 quadrature)
volatile long encCount = 0;
volatile uint8_t lastAB = 0;
long lastEnc = 0;

// Motor drive state
int lastSign = 0;

// Velocity PID state
float iTerm = 0.0f;
float dTerm = 0.0f;
float e_prev = 0.0f;

// Admittance state
float theta_eq = 0.0f;   // equilibrium angle for spring term (rad)
float w_adm = 0.0f;      // admittance-generated velocity (rad/s)
float w_adm_prev = 0.0f;

// User command state
float w_user = 0.0f;     // commanded velocity (rad/s)
float last_w_cmd = 0.0f; // previous command for rate limiting

// Speed filter state
static unsigned long lastSpeedMicros = 0;
static long accCounts = 0;
float w_med_buf[W_MED_WIN];
uint8_t w_med_idx = 0;
bool w_med_filled = false;
float w_ema = 0.0f;
float alphaW = -1.0f;
float w_meas = 0.0f;

// HX711 / force state
float force_N_ema = 0.0f;
float tau_ext = 0.0f;

// Loop timing
unsigned long lastLoopMicros = 0;
unsigned long lastPosLoopMicros = 0;
unsigned long lastLogMs = 0;

// Potentiometer home angle (captured at startup)
float theta_home = 0.0f;

/* ========================= HELPER FUNCTIONS ========================= */

static inline float saturate(float x, float lo, float hi){
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}
static inline float emaAlpha(float fc_hz, float dt_s) {
  if (fc_hz <= 0.0f) return 1.0f;
  float tau = 1.0f / (2.0f * PI * fc_hz);
  return dt_s / (dt_s + tau);
}
static inline float emaStep(float prev, float x, float alpha) {
  return prev + alpha * (x - prev);
}
inline uint8_t readAB() {
  uint8_t a = (uint8_t)digitalRead(PIN_ENC_A);
  uint8_t b = (uint8_t)digitalRead(PIN_ENC_B);
  return (a << 1) | b;
}
void handleEnc() {
  uint8_t ab = readAB();
  static const int8_t deltaLUT[16] = {
    0,  -1, +1,  0,
    +1,  0,  0, -1,
    -1,  0,  0, +1,
     0, +1, -1,  0
  };
  static uint8_t last = 0;
  uint8_t idx = (last << 2) | ab;
  encCount += deltaLUT[idx];
  last = ab;
}
void ISR_A(){ handleEnc(); }
void ISR_B(){ handleEnc(); }

// Potentiometer normalization (0..1)
static inline float potNorm(int adc){
  int a = constrain(adc, POT_ADC_MIN, POT_ADC_MAX);
  float x = (float)(a - POT_ADC_MIN) / (float)(POT_ADC_MAX - POT_ADC_MIN);
  if (x < 0.0f) x = 0.0f;
  if (x > 1.0f) x = 1.0f;
  return x;
}

// Map pot ADC → radians; 0 rad ≈ horizontal; negative up, positive down
static inline float adcToThetaRad(int adc){
  float x = potNorm(adc);
  float theta_raw = THETA_MIN_RAD + x * (THETA_MAX_RAD - THETA_MIN_RAD);
  return theta_raw  - 2.48f;   // match your previous alignment
}

// Motor command: signed PWM on IN1/IN2 with dead-time on reversal
void setMotorPWM(float u_pwm_signed){
  u_pwm_signed = saturate(u_pwm_signed, -PWM_LIMIT, PWM_LIMIT);
  int sign = (u_pwm_signed > 0) - (u_pwm_signed < 0);
  int mag  = (int)(fabs(u_pwm_signed) + 0.5f);

  if (sign && sign != lastSign && lastSign != 0){
    analogWrite(PIN_IN1, 0);
    analogWrite(PIN_IN2, 0);
    delayMicroseconds(REV_DEADTIME_US);
  }
  if      (sign > 0) { analogWrite(PIN_IN1, mag); analogWrite(PIN_IN2, 0); }
  else if (sign < 0) { analogWrite(PIN_IN1, 0);   analogWrite(PIN_IN2, mag); }
  else               { analogWrite(PIN_IN1, 0);   analogWrite(PIN_IN2, 0); }

  lastSign = sign;
}

// Simple insertion sort for tiny median window
void insertionSort(float* a, uint8_t n) {
  for (uint8_t i = 1; i < n; ++i) {
    float key = a[i];
    int8_t j = i - 1;
    while (j >= 0 && a[j] > key) { a[j + 1] = a[j]; j--; }
    a[j + 1] = key;
  }
}
float medianOfBuffer(float* buf, uint8_t n) {
  float tmp[W_MED_WIN];
  for (uint8_t k = 0; k < n; ++k) tmp[k] = buf[k];
  insertionSort(tmp, n);
  if (n & 1) return tmp[n >> 1];
  return 0.5f * (tmp[(n >> 1) - 1] + tmp[n >> 1]);
}

/* ========================== SERIAL PARSER ========================== */
/*
 * Commands:
 *   w <rad_s>      : velocity command (rad/s)
 *   vd <deg_s>     : velocity command (deg/s → rad/s)
 *   tare           : tare HX711 (do at level pose if possible)
 *   adm on|off     : enable/disable admittance
 *   adm J B K      : set admittance params
 *   eq hold        : set theta_eq to current encoder angle
 */
void parseSerial() {
  if (!Serial.available()) return;
  String token = Serial.readStringUntil(' ');
  token.trim();
  if (token.length() == 0) return;

  if (token.equalsIgnoreCase("w")) {
    w_user = Serial.parseFloat();
  } else if (token.equalsIgnoreCase("vd")) {
    float dps = Serial.parseFloat();
    w_user = dps * DEG_TO_RAD;
  } else if (token.equalsIgnoreCase("tare")) {
    scale.tare(20);
    Serial.println(F("# scale tared"));
  } else if (token.equalsIgnoreCase("adm")) {
    String rest = Serial.readStringUntil('\n');
    rest.trim();
    if (rest.equalsIgnoreCase("on")) {
      USE_ADMITTANCE = true;
      Serial.println(F("# admittance ON"));
    } else if (rest.equalsIgnoreCase("off")) {
      USE_ADMITTANCE = false;
      w_adm = 0.0f; w_adm_prev = 0.0f;
      Serial.println(F("# admittance OFF"));
    } else {
      int i1 = rest.indexOf(' ');
      int i2 = rest.indexOf(' ', i1 + 1);
      if (i1 > 0 && i2 > i1) {
        Jv = rest.substring(0, i1).toFloat();
        Bv = rest.substring(i1 + 1, i2).toFloat();
        Kv = rest.substring(i2 + 1).toFloat();
        Serial.print(F("# adm set Jv=")); Serial.print(Jv, 6);
        Serial.print(F(" Bv=")); Serial.print(Bv, 6);
        Serial.print(F(" Kv=")); Serial.println(Kv, 6);
      }
    }
  } else if (token.equalsIgnoreCase("eq")) {
    String rest = Serial.readStringUntil('\n');
    rest.trim();
    if (rest.equalsIgnoreCase("hold")) {
      long cNow = encCount;
      float count2rad = (2.0f * PI) / (float)(AMT_CPR * 4.0f);
      theta_eq = cNow * count2rad;
      Serial.println(F("# theta_eq updated"));
    }
  }

  while (Serial.available()) Serial.read();
}

/* ============================== SETUP ============================== */
void setup() {
  Serial.begin(115200);

  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  analogWrite(PIN_IN1, 0);
  analogWrite(PIN_IN2, 0);

  pinMode(PIN_ENC_A, INPUT_PULLUP);
  pinMode(PIN_ENC_B, INPUT_PULLUP);
  lastAB = readAB();
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), ISR_A, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_B), ISR_B, CHANGE);

  // HX711 → Newtons
  scale.begin(HX_DOUT, HX_SCK);
  scale.set_scale(COUNTS_PER_N);
  delay(100);

  // Potentiometer home angle (for gravity comp reference)
  int adc0 = analogRead(PIN_POT);
 

  // Zero encoder at startup so clamps refer to this boot pose
  noInterrupts();
  encCount = 0;
  interrupts();

  // Tare once to remove constant bias (ideally at level pose)
  scale.tare(20);
  force_N_ema = 0.0f;
  tau_ext = 0.0f;

  // Speed filter init
  for (uint8_t k = 0; k < W_MED_WIN; ++k) w_med_buf[k] = 0.0f;
  w_med_idx = 0;
  w_med_filled = false;
  w_ema = 0.0f;
  alphaW = -1.0f;
  w_meas = 0.0f;

  lastLoopMicros = micros();
  lastPosLoopMicros = lastLoopMicros;
  lastLogMs = millis();

  Serial.println(F("# velocity_gravity_comp ready"));
  Serial.println(F("# Commands: w <rad/s>, vd <deg/s>, tare, adm on|off, adm J B K, eq hold"));
}

/* =============================== LOOP =============================== */
void loop() {
  unsigned long now = micros();
  const unsigned long dt_us_target = (unsigned long)(1e6f / LOOP_HZ);
  if ((now - lastLoopMicros) < dt_us_target) {
    parseSerial();
    return;
  }
  float dt = (now - lastLoopMicros) * 1e-6f;
  lastLoopMicros = now;

  // Encoder position (radians)
  long cNow_counts = encCount;
  float count2rad = (2.0f * PI) / (float)(AMT_CPR * 4.0f);
  float theta_meas_enc = cNow_counts * count2rad;

  // Speed filtering: oversampling window -> median -> EMA
  long dC = cNow_counts - lastEnc;
  lastEnc = cNow_counts;
  accCounts += dC;
  if ((now - lastSpeedMicros) >= SPEED_WIN_US) {
    float dtw = (now - lastSpeedMicros) * 1e-6f;
    lastSpeedMicros = now;
    float revs = (float)accCounts / (float)(AMT_CPR * 4.0f);
    float w_inst = (dtw > 0.0f) ? (revs * 2.0f * PI / dtw) : 0.0f;
    accCounts = 0;

    // median filter
    uint8_t n_med;
    if (W_MED_WIN == 1) {
      w_ema = w_inst;           // skip extra work when window=1
      w_meas = w_ema;
    } else {
      w_med_buf[w_med_idx] = w_inst;
      w_med_idx++;
      if (w_med_idx >= W_MED_WIN) { w_med_idx = 0; w_med_filled = true; }
      n_med = w_med_filled ? W_MED_WIN : (w_med_idx == 0 ? 1 : w_med_idx);
      float w_med = medianOfBuffer(w_med_buf, n_med);
      float alphaW =0.8f;
      w_ema += alphaW * (w_med - w_ema);
      w_meas = w_ema;
    }
  }
    int adc = analogRead(PIN_POT);
    float theta_meas_pot = adcToThetaRad(adc) ;
  // HX711 reading and simple gravity compensation
  if (scale.is_ready()) {
    // Raw force in Newtons (because set_scale = counts per N)
    float force_raw_N = scale.get_units(1);

    // Pot angle relative to home (radians) for gravity term


    // Gravity of handle+wrist/tool projected on axis
    float grav = TOTAL_MASS_KG * 9.81f * sinf(theta_meas_pot );

    // External force (subtract gravity component)
    float force_ext = force_raw_N - grav;

    // Low-pass the external force
    force_N_ema = emaStep(force_N_ema, force_ext, 0.8);

    // External torque at joint
    tau_ext = TORQUE_SIGN * force_N_ema * ARM_LENGTH_M;
  }

  // Admittance update (~200 Hz)
  if ((now - lastPosLoopMicros) >= POS_DT_US) {
    float dt_pos = (now - lastPosLoopMicros) * 1e-6f;
    lastPosLoopMicros = now;

    float spring = Kv * (theta_meas_enc - theta_eq);
    float denom  = Jv + Bv * dt_pos;
    if (denom < 1e-6f) denom = 1e-6f;
    float numer  = Jv * w_adm + (tau_ext - spring) * dt_pos;
    float w_next = numer / denom;

    // float dw_max = DW_ADM_MAX * dt_pos;
    // w_next = saturate(w_next, w_adm - dw_max, w_adm + dw_max);
    w_adm  = w_next; //saturate(w_next, -W_ADM_MAX, W_ADM_MAX);
  }

  // Combine user velocity and admittance velocity
  float w_total = USE_ADMITTANCE ? (w_user + w_adm) : w_user;

  // // Rate limit & saturate commanded velocity
  // float dw = w_total - last_w_cmd;
  // float dw_lim = DW_CMD_MAX * dt;
  // if (dw >  dw_lim) w_total = last_w_cmd + dw_lim;
  // if (dw < -dw_lim) w_total = last_w_cmd - dw_lim;
  w_total =  w_total;  // saturate(w_total, -W_CMD_MAX, W_CMD_MAX);

  // position limits important 
  if ((theta_meas_enc >= POS_MAX_RAD && w_total > 0.0f) ||
      (theta_meas_enc <= POS_MIN_RAD && w_total < 0.0f)) {
    w_total = 0.0f;
  }
  last_w_cmd = w_total;

  // Inner velocity PID
  float e = w_total - w_meas;
  if (fabs(e) < 0.15f) e = 0.0f;  // small deadband
  iTerm += Ki * e * dt;
  iTerm = saturate(iTerm, -INT_CLAMP, INT_CLAMP);
  float raw_d = (e - e_prev) / dt;
  float alpha_d = dt / (D_TAU_VEL + dt);
  dTerm += alpha_d * (raw_d - dTerm);
  e_prev = e;
  float u_pwm = Kp * e + iTerm + Kd * dTerm;
  u_pwm = saturate(u_pwm, -PWM_MAX, PWM_MAX);
  setMotorPWM(u_pwm);

  // Telemetry (~10 Hz)
  static unsigned long lastLog = 0;
  if ((millis() - lastLogMs) >= LOG_PERIOD_MS) {
    lastLogMs = millis();
    Serial.print(theta_meas_pot);           Serial.print(',');
    Serial.print(theta_meas_enc, 6);   Serial.print(',');
    Serial.print(w_user, 6);           Serial.print(',');
    Serial.print(w_meas, 6);           Serial.print(',');
    Serial.print(u_pwm, 1);            Serial.print(',');
    Serial.print(force_N_ema, 4);      Serial.print(',');
    Serial.print(tau_ext, 5);          Serial.print(',');
    Serial.println(w_adm, 5);
  }
}