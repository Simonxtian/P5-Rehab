/* ===== Cascaded Position->Velocity Control + Rotational Admittance (HX711 load cell) =====
 * Inner loop: PID velocity (1 kHz) with Oversampling -> Median -> EMA speed filter
 * Outer loop (200 Hz): PID position -> w_des  [rad/s]
 * Admittance: Jv * d(w_adm)/dt + Bv * w_adm + Kv * (theta_meas - theta_eq) = tau_ext
 * Command sent to inner loop: w_cmd = clamp(w_des + w_adm)
 *
 * Board:   Arduino Leonardo (ATmega32U4)
 * Driver:  Dual-PWM H-bridge (IN1/IN2)  [signed PWM]
 * Encoder: CUI AMT103 (Quadrature x4), AMT_CPR = 2048 (per channel)
 * Loadcell: HX711 on pins D4 (DOUT) / D5 (SCK). Non-blocking read.
 * CSV (10 Hz): t_ms,theta_cmd,theta_meas,w_cmd,w_meas,u_pwm,force_N,tau_ext,w_adm
 */

#include <Arduino.h>
#include <HX711.h>

/* ===== USER CONFIG ===== */
// --- Motor driver pins (dual-PWM) ---
const int PIN_IN1 = 10;      // PWM-capable (Timer1 on Leonardo)
const int PIN_IN2 = 9;       // PWM-capable (Timer1 on Leonardo)

// --- Encoder pins (external interrupts) ---
const int PIN_ENC_A = 1;     // Leonardo supports 0,1,2,3,7
const int PIN_ENC_B = 2;

// --- HX711 pins (avoid 2/3 which are used by encoder) ---
const int HX_DOUT = 5;
const int HX_SCK  = 6;
HX711 scale;

// Calibration: set so that scale.get_units(1) returns grams
float LC_CALIBRATION_FACTOR = 63800.0f; // counts per gram (from your previous calibration)
const float G2N = 0.00980665f;        // gram -> Newton
const float ARM_LENGTH_M = 0.09f;     // lever arm [m] from load to joint (EDIT to your rig)
const float TORQUE_SIGN  = -1.0f;     // flip to +1/-1 so positive force yields desired direction

// Optional force low-pass (EMA)
const float FORCE_EMA_CUTOFF_HZ = 80.0f;

// --- Encoder parameters ---
const long AMT_CPR = 2048;                           // PPR per channel (pre-x4)
const float COUNTS_PER_REV = AMT_CPR * 4.0f;         // x4 decoding
const float COUNT2RAD = (2.0f * PI) / COUNTS_PER_REV;

// --- Control & timing ---
const float LOOP_HZ = 1000.0f;                       // inner velocity loop
const unsigned long LOG_PERIOD_MS = 100;             // CSV log at 10 Hz
const uint8_t PWM_MAX = 255;                         // 8-bit PWM

// --- Inner PID (velocity) ---
// Units: Kp ~ PWM per (rad/s), Ki ~ PWM per rad, Kd ~ PWM per (rad/s^2)
float Kp = 1.21f;
float Ki = 96.9f;
float Kd = 0.0f;
const float INT_CLAMP = 150.0f;                      // anti-windup clamp (PWM units)
const float D_TAU_VEL = 0.002f;                      // derivative LPF time constant [s]

// --- Outer PID (position) ---
// Units: Kp_pos ~ (rad/s)/rad, Ki_pos ~ (rad/s)/(rad*s), Kd_pos ~ dimensionless on d(e)/dt
float Kp_pos = 17.0f;
float Ki_pos = 0.0f;
float Kd_pos = 0.0f;
const float POS_INT_CLAMP = 50.0f;                   // clamp on position I-term [rad/s]
const float D_TAU_POS = 0.010f;                      // derivative LPF time constant [s]

// --- Velocity command shaping (safety/comfort) ---
const float W_CMD_MAX = 25.0f;                       // [rad/s] velocity cap
const float DW_CMD_MAX = 800.0f;                     // [rad/s^2] accel cap for w_cmd

// --- Feedforward parameters ---
const float KE   = 0.75f;                            // back-EMF const [V per rad/s]
const float vBUS = 12.0f;                            // supply voltage [V]
const bool  USE_FEEDFORWARD = false;

// --- Command inputs (defaults) ---
float theta_cmd = 0.0f;                              // [rad] position target
float w_cmd = 0.0f;                                  // [rad/s] velocity target (from outer loop/admittance)
bool  position_mode = true;                          // default to position control

// --- Safety / drive niceties ---
const unsigned long REV_DEADTIME_US = 5;          // 3 ms dead-time on reversal
const uint8_t PWM_LIMIT = 255;                       // soft cap (can = PWM_MAX)

/* ===== Speed filtering knobs ===== */
// Stage 1: oversampling window (counts accumulated over this time)
const unsigned long SPEED_WIN_US = 2500;             // 5 ms window
// Stage 2: temporal median window (odd size)
const uint8_t W_MED_WIN = 1;                         // 3,5,7…
// Stage 3: EMA cutoff AFTER median
const float W_EMA_CUTOFF_HZ = 60.0f;                 // 10–40 Hz typical

/* ===== Rotational Admittance (virtual dynamics) ===== */
// Jv [kg·m^2], Bv [N·m·s/rad], Kv [N·m/rad] on the joint
// Start conservative; increase Bv first, then add Kv, adjust Jv last.
float Jv =0.02865f;   // virtual inertia
float Bv =0.20257f;     // virtual damping
float Kv = 0.35810f;     // virtual stiffness
bool  USE_ADMITTANCE = true;
float theta_eq = 0.0f;    // equilibrium angle for the spring term (can be tied to theta_cmd if desired)
const float W_ADM_MAX = 30.0f;   // clamp for admittance velocity [rad/s]
const float DW_ADM_MAX = 1000.0f; // rate limit for admittance velocity [rad/s^2]

/* ===== INTERNAL STATE ===== */
volatile long encCount = 0;                          // x4 quadrature count
volatile uint8_t lastAB = 0;

long lastEnc = 0;                                    // for speed window
int lastSign = 0;                                    // -1,0,+1 for H-bridge state

// Velocity PID state
float iTerm = 0.0f;
float dTerm = 0.0f;
float e_prev = 0.0f;

// Position PID state
float i_pos = 0.0f;
float d_pos = 0.0f;
float e_pos_prev = 0.0f;

// Loop timing
unsigned long lastLoopMicros = 0;
unsigned long lastLogMs = 0;

// Outer loop timing
unsigned long lastPosLoopMicros = 0;
const unsigned long POS_DT_US = 5000;                // 200 Hz outer loop
float last_w_cmd = 0.0f;                             // for rate limiting

/* ----- Speed filter state ----- */
// Stage 1 (oversampling/window)
static unsigned long lastSpeedMicros = 0;
static long accCounts = 0;                           // accumulate encoder counts inside window
// Stage 2 (median)
float w_med_buf[W_MED_WIN];
uint8_t w_med_idx = 0;
bool w_med_filled = false;
// Stage 3 (EMA)
float w_ema = 0.0f;
float alphaW = -1.0f;                                // computed from dt
// Final measured speed
float w_meas = 0.0f;

/* ----- HX711 / Force state ----- */
bool   scale_ready = false;
float  force_N_raw = 0.0f;
float  force_N_ema = 0.0f;
float  tau_ext = 0.0f;       // external torque at joint [N·m]

/* ----- Admittance state ----- */
float w_adm = 0.0f;          // admittance-generated velocity [rad/s]
float last_w_adm = 0.0f;

/* ===== UTIL ===== */
inline float emaAlpha(float fc_hz, float dt_s) {
  if (fc_hz <= 0.0f) return 1.0f;
  float tau = 1.0f / (2.0f * PI * fc_hz);
  return dt_s / (dt_s + tau);
}
void insertionSort(float* a, uint8_t n) {
  for (uint8_t i = 1; i < n; ++i) {
    float key = a[i];
    int8_t j = i - 1;
    while (j >= 0 && a[j] > key) { a[j + 1] = a[j]; j--; }
    a[j + 1] = key;
  }
}
float medianOfBuffer(float* buf, uint8_t filled_n) {
  uint8_t n = filled_n;
  float tmp[W_MED_WIN];
  for (uint8_t k = 0; k < n; ++k) tmp[k] = buf[k];
  insertionSort(tmp, n);
  if (n & 1) return tmp[n >> 1];
  return 0.5f * (tmp[(n >> 1) - 1] + tmp[n >> 1]);
}

/* ===== QUADRATURE ISR (x4 decoding) ===== */
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

/* ===== MOTOR CMD (signed PWM on IN1/IN2) ===== */
void setMotorPWM(float u_pwm_signed){
  if (u_pwm_signed >  PWM_LIMIT) u_pwm_signed =  PWM_LIMIT;
  if (u_pwm_signed < -PWM_LIMIT) u_pwm_signed = -PWM_LIMIT;

  int sign = (u_pwm_signed > 0) - (u_pwm_signed < 0);
  int mag  = (int)(fabs(u_pwm_signed) + 0.5f);

  if (sign && sign != lastSign && lastSign != 0) {
    analogWrite(PIN_IN1, 0);
    analogWrite(PIN_IN2, 0);
    delayMicroseconds(REV_DEADTIME_US);
  }

  if (sign > 0) { analogWrite(PIN_IN1, mag); analogWrite(PIN_IN2, 0); }
  else if (sign < 0) { analogWrite(PIN_IN1, 0); analogWrite(PIN_IN2, mag); }
  else { analogWrite(PIN_IN1, 0); analogWrite(PIN_IN2, 0); }

  lastSign = sign;
}

/* ===== SERIAL PARSER =====
 * Commands:
 *  "p <deg>"      -> position target in degrees
 *  "pr <rad>"     -> position target in radians
 *  "w <rad_s>"    -> velocity target (switches to velocity mode)
 *  "tare"         -> tare load cell
 *  "adm on|off"   -> enable/disable admittance
 *  "adm m b k"    -> set Jv Bv Kv (float float float)
 */
void parseSerial() {
  if (!Serial.available()) return;

  // Peek first non-space token
  String token = Serial.readStringUntil(' ');
  token.trim();

  if (token.length() == 0) return;

  if (token.equalsIgnoreCase("p")) {
    float deg = Serial.parseFloat();
    theta_cmd = deg * (PI / 180.0f);
    position_mode = true;
  } else if (token.equalsIgnoreCase("pr")) {
    float rad = Serial.parseFloat();
    theta_cmd = rad;
    position_mode = true;
  } else if (token.equalsIgnoreCase("w")) {
    float w = Serial.parseFloat();
    w_cmd = w;
    position_mode = false;
  } else if (token.equalsIgnoreCase("tare")) {
    scale.tare(20);
    Serial.println(F("# scale tared"));
  } else if (token.equalsIgnoreCase("adm")) {
    // read rest of the line
    String rest = Serial.readStringUntil('\n');
    rest.trim();
    if (rest.equalsIgnoreCase("on")) {
      USE_ADMITTANCE = true;
      Serial.println(F("# admittance ON"));
    } else if (rest.equalsIgnoreCase("off")) {
      USE_ADMITTANCE = false;
      w_adm = 0.0f; last_w_adm = 0.0f;
      Serial.println(F("# admittance OFF"));
    } else {
      // try parse three floats: Jv Bv Kv
      float m = rest.toFloat(); // reads up to first non-numeric; we’ll re-tokenize properly:
      // Better: manual parsing
      int i1 = rest.indexOf(' ');
      int i2 = rest.indexOf(' ', i1 + 1);
      if (i1 > 0 && i2 > i1) {
        Jv = rest.substring(0, i1).toFloat();
        Bv = rest.substring(i1 + 1, i2).toFloat();
        Kv = rest.substring(i2 + 1).toFloat();
        Serial.print(F("# set adm: Jv=")); Serial.print(Jv,6);
        Serial.print(F(" Bv=")); Serial.print(Bv,6);
        Serial.print(F(" Kv=")); Serial.println(Kv,6);
      } else {
        Serial.println(F("# usage: adm on|off | adm <Jv> <Bv> <Kv>"));
      }
    }
  } else {
    // legacy: just a number -> velocity setpoint
    float w = token.toFloat();
    if (!isnan(w)) { w_cmd = w; position_mode = false; }
  }

  while (Serial.available()) Serial.read(); // flush
}

/* ===== FORCE / HX711 HELPERS ===== */
inline float emaStep(float prev, float x, float alpha) {
  return prev + alpha * (x - prev);
}

/* ===== SETUP ===== */
void setup(){
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

  // HX711 init
  scale.begin(HX_DOUT, HX_SCK);
  scale.set_scale(LC_CALIBRATION_FACTOR);
  delay(100);
  scale.tare(20);  // average 20 samples
  scale_ready = scale.is_ready();

  // Init median buffer
  for (uint8_t k = 0; k < W_MED_WIN; ++k) w_med_buf[k] = 0.0f;
  w_med_idx = 0; w_med_filled = false;

  lastLoopMicros = micros();
  lastSpeedMicros = lastLoopMicros;
  lastLogMs = millis();
  lastPosLoopMicros = lastLoopMicros;

  Serial.println(F("# Commands: 'p <deg>' | 'pr <rad>' | 'w <rad/s>' | tare | adm on/off | adm <Jv> <Bv> <Kv>"));
  Serial.println(F("# CSV: t_ms,theta_cmd,theta_meas,w_cmd,w_meas,u_pwm,force_N,tau_ext,w_adm"));
}

/* ===== LOOP ===== */
void loop(){
  // fixed-rate inner loop at LOOP_HZ
  const float dt_s_target = 1.0f / LOOP_HZ;
  const unsigned long dt_us_target = (unsigned long)(dt_s_target * 1e6f);

  unsigned long now = micros();
  if ((now - lastLoopMicros) < dt_us_target) {
    parseSerial();
    return;
  }
  float dt = (now - lastLoopMicros) * 1e-6f;
  lastLoopMicros = now;

  // --- Position measurement (absolute from counts) ---
  long cNow_counts = encCount; // atomic read of volatile
  float theta_meas = cNow_counts * COUNT2RAD;

  // === SPEED FILTERING: Oversampling -> Median -> EMA ===
  long dC = cNow_counts - lastEnc;     // raw increment since last fast loop
  lastEnc = cNow_counts;
  accCounts += dC;

  if ((now - lastSpeedMicros) >= SPEED_WIN_US) {
    float dtw = (now - lastSpeedMicros) * 1e-6f;
    lastSpeedMicros = now;

    // Instantaneous speed from windowed counts
    float revs = (float)accCounts / COUNTS_PER_REV;
    float w_inst = (dtw > 0.0f) ? (revs * 2.0f * PI / dtw) : 0.0f;
    accCounts = 0;

    // Stage 2: median
    w_med_buf[w_med_idx] = w_inst;
    w_med_idx++;
    if (w_med_idx >= W_MED_WIN) { w_med_idx = 0; w_med_filled = true; }
    uint8_t n_med = w_med_filled ? W_MED_WIN : (w_med_idx == 0 ? 1 : w_med_idx);
    float w_med = medianOfBuffer(w_med_buf, n_med);

    // Stage 3: EMA
    float a = emaAlpha(W_EMA_CUTOFF_HZ, dtw);
    if (alphaW < 0.0f) alphaW = a; else alphaW = a;
    w_ema += alphaW * (w_med - w_ema);
    w_meas = w_ema;
  }
  // If window not elapsed yet, w_meas holds last EMA output.

  // === NON-BLOCKING HX711 READ (runs at its own sample rate ~10–80 Hz) ===
  // If not ready, we keep last force value.
  if (scale.is_ready()) {
      float force_N = scale.get_units(1);        // direct Newtons now

      // Low-pass filter (same as before, just using force_N directly)
      float alphaF = emaAlpha(FORCE_EMA_CUTOFF_HZ, dt);
      force_N_ema = emaStep(force_N_ema, force_N, alphaF);

      // Compute torque: τ = F × r
      tau_ext = TORQUE_SIGN * force_N_ema * ARM_LENGTH_M;

      scale_ready = true;
  }

  // === OUTER POSITION LOOP (200 Hz) ===
  if ((now - lastPosLoopMicros) >= POS_DT_US) {
    float dt_pos = (now - lastPosLoopMicros) * 1e-6f;
    lastPosLoopMicros = now;

    float w_des = 0.0f;

    if (position_mode) {
      float e_pos = theta_cmd - theta_meas;

      if (fabs(e_pos)< 0.0262){
        e_pos = 0.0;
      }

      i_pos += Ki_pos * e_pos * dt_pos;
      if (i_pos >  POS_INT_CLAMP) i_pos =  POS_INT_CLAMP;
      if (i_pos < -POS_INT_CLAMP) i_pos = -POS_INT_CLAMP;

      float raw_d_pos = (e_pos - e_pos_prev) / dt_pos;
      float alpha_d_pos = dt_pos / (D_TAU_POS + dt_pos);
      d_pos += alpha_d_pos * (raw_d_pos - d_pos);

      w_des = Kp_pos * e_pos + i_pos + Kd_pos * d_pos;
      e_pos_prev = e_pos;
    } else {
      w_des = w_cmd; // velocity mode
    }

    // >>> Anchor the virtual spring to your command <<<
    theta_eq = theta_cmd;  // <-- add this line

    // === ROTATIONAL ADMITTANCE UPDATE (semi-implicit Euler recommended) ===
    if (USE_ADMITTANCE) {
      float spring = Kv * (theta_meas - theta_eq);
      float denom  = Jv + Bv * dt_pos;
      float numer  = Jv * w_adm + (tau_ext - spring) * dt_pos;
      float w_next = numer / max(1e-6f, denom);

      // rate & magnitude clamps
      float dw_max = DW_ADM_MAX * dt_pos;
      w_next = constrain(w_next, w_adm - dw_max, w_adm + dw_max);
      w_adm  = constrain(w_next, -W_ADM_MAX, W_ADM_MAX);
    } else {
      w_adm = 0.0f;
    }

    // Combine and limit
    float w_total =  w_adm;
    float dw_max_cmd = DW_CMD_MAX * dt_pos;
    float dw = w_total - last_w_cmd;
    if (dw >  dw_max_cmd) w_total = last_w_cmd + dw_max_cmd;
    if (dw < -dw_max_cmd) w_total = last_w_cmd - dw_max_cmd;
    w_total = constrain(w_total, -W_CMD_MAX, W_CMD_MAX);

    w_cmd = w_total;
    last_w_cmd = w_cmd;
  }

  // === INNER VELOCITY PID (+ optional back-EMF FF) ===
  float e = w_cmd - w_meas;                 // [rad/s]
  if (fabs(e) < 0.15 ){
    e=0.0f;
  }
  // Integral
  iTerm += Ki * e * dt;                     // PWM units
  if (iTerm >  INT_CLAMP) iTerm =  INT_CLAMP;
  if (iTerm < -INT_CLAMP) iTerm = -INT_CLAMP;

  // Derivative (dirty)
  float raw_d = (e - e_prev) / dt;          // [rad/s^2]
  float alpha_d = dt / (D_TAU_VEL + dt);
  dTerm += alpha_d * (raw_d - dTerm);
  e_prev = e;

  float u_ff = 0.0f;
  if (USE_FEEDFORWARD && vBUS > 0.0f) {
    float pwm_per_volt = (float)PWM_MAX / vBUS;
    u_ff = pwm_per_volt * (KE * w_cmd);     // steady-state V ≈ Ke*w
  }

  float u_pwm = Kp * e + iTerm + Kd * dTerm + u_ff;      // signed PWM command
  if (u_pwm >  PWM_MAX) u_pwm =  PWM_MAX;
  if (u_pwm < -PWM_MAX) u_pwm = -PWM_MAX;

  setMotorPWM(u_pwm);

  // === Telemetry (10 Hz) ===
  if ((millis() - lastLogMs) >= LOG_PERIOD_MS) {
    lastLogMs = millis();
    Serial.print(lastLogMs);         Serial.print(',');
    Serial.print(theta_cmd, 6);      Serial.print(',');
    Serial.print(theta_meas, 6);     Serial.print(',');
    Serial.print(w_cmd, 6);          Serial.print(',');
    Serial.print(w_meas, 6);         Serial.print(',');
    Serial.print(u_pwm, 1);          Serial.print(',');
    Serial.print(force_N_ema, 4);    Serial.print(',');
    Serial.print(tau_ext, 5);        Serial.print(',');
    Serial.println(w_adm, 5);
  }
}
