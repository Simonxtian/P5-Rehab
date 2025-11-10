#include <Arduino.h>
#include <HX711.h>

/* =================== Pins & hardware =================== */
const int PIN_IN1 = 9;     // H-bridge IN1 (PWM)
const int PIN_IN2 = 10;      // H-bridge IN2 (PWM)
const int PIN_POT = A0;     // potentiometer
const int PIN_HX_DOUT = 5;  // HX711 DOUT
const int PIN_HX_SCK  = 6;  // HX711 SCK

/* =================== Loop timing =================== */
const float LOOP_HZ = 1000.0f;
const unsigned long LOOP_DT_US = (unsigned long)(1e6f / LOOP_HZ);

/* =================== Angle limits (pot) =================== */
int POT_ADC_MIN = 0;
int POT_ADC_MAX = 1023;

const float THETA_MIN_DEG = 0.0f;
const float THETA_MAX_DEG = 180.0f;
const float THETA_MIN_RAD = THETA_MIN_DEG * DEG_TO_RAD;
const float THETA_MAX_RAD = THETA_MAX_DEG * DEG_TO_RAD;

/* =================== Motor drive =================== */
const int PWM_MAX = 255;            // keep your low PWM ceiling
const unsigned long REV_DEADTIME_US = 5;  // your current value (µs)
int lastSign = 0;

/* =================== Load cell & torque =================== */
HX711 scale;
float LC_CALIBRATION_FACTOR = 63800.0f;  // get_units() -> Newtons
const float ARM_LENGTH_M = 0.09f;
const float TORQUE_SIGN  = +1.0f;
const float FORCE_EMA_CUTOFF_HZ = 25.0f;  // gentle smoothing
float force_N_ema = 0.0f;

/* =================== Admittance =================== */
/*
   Jv * dw/dt + Bv * w + Kv*(theta - theta_eq) = tau_ext
   Backward-Euler step (your logic):
     spring = Kv*(theta - theta_eq)
     denom  = Jv + Bv*dt
     numer  = Jv*w_prev + (tau_ext - spring)*dt
     w_next = numer / denom
   Then Tustin integrate w -> theta_adm.
*/
float Jv = 0.02865f;
float Bv = 0.20257f;
float Kv = 0.35810f;
bool  USE_ADMITTANCE = true;

float theta_eq    = 0.0f;   // neutral angle (rad)
float w_adm       = 0.0f;   // admittance velocity (rad/s)
float w_adm_prev  = 0.0f;
float theta_adm   = 0.0f;

const float W_ADM_MAX      = 6.0f;       // |w_adm| [rad/s]
const float DW_ADM_MAX     = 30.0f;      // |dw/dt| [rad/s^2]
const float THETA_ADM_MAX  = 1.8f;       // |theta_adm| [rad]
const float DTHETA_MAX     = 2.0f;       // |Δtheta_adm|/s [rad/s]

/* =================== Command interface =================== */
enum CmdMode { CMD_POS, CMD_VEL };
CmdMode cmd_mode = CMD_POS;

// User command state
float theta_user = 0.0f;      // absolute position target (rad)
float w_user     = 0.0f;      // velocity command (rad/s)
float w_user_prev = 0.0f;
const float W_USER_MAX = 6.0f;

/* =================== Position PID (PWM units) =================== */
float Kp = 450.0f;   // PWM per rad      (your tuned gains kept)
float Ki = 150.0f;   // PWM per rad·s
float Kd = 17.0f;    // PWM per rad/s    (filtered derivative)
float iTerm = 0.0f;
float dTerm = 0.0f;
float err_prev = 0.0f;
const float D_TAU = 0.02f;         // derivative LPF time constant [s]
const float I_CLAMP = 0.6f * PWM_MAX;

/* =================== Runtime state =================== */
unsigned long lastLoopMicros = 0;

/* =================== Helpers =================== */
static inline float saturate(float x, float lo, float hi){
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

static inline float emaAlpha(float fc, float dt){
  if (fc <= 0.0f) return 1.0f;
  float tau = 1.0f / (2.0f * PI * fc);
  return dt / (tau + dt);
}

static inline float emaStep(float y_prev, float x, float alpha){
  return y_prev + alpha * (x - y_prev);
}

static inline float potNorm(int adc){
  int a = constrain(adc, POT_ADC_MIN, POT_ADC_MAX);
  float x = (float)(a - POT_ADC_MIN) / (float)(POT_ADC_MAX - POT_ADC_MIN);
  return saturate(x, 0.0f, 1.0f);
}

static inline float adcToThetaRad(int adc){
  float x = potNorm(adc);
  return THETA_MIN_RAD + x * (THETA_MAX_RAD - THETA_MIN_RAD);
}

void setMotorPWM(float u_pwm_signed){
  if (u_pwm_signed >  PWM_MAX) u_pwm_signed =  PWM_MAX;
  if (u_pwm_signed < -PWM_MAX) u_pwm_signed = -PWM_MAX;

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

/* =================== Serial command parser =================== */
/*
  p <deg>     : absolute position command (deg), uses position PID
  pr <rad>    : absolute position command (rad)
  vd <deg/s>  : velocity command (deg/s) -> integrated to position ref
  vr <rad/s>  : velocity command (rad/s) -> integrated to position ref
  adm on|off  : enable/disable admittance
  adm J B K   : set admittance parameters
  eq hold     : set theta_eq = current measured theta
*/
void parseSerial(){
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  // tokenize
  int sp1 = cmd.indexOf(' ');
  String op = (sp1 < 0) ? cmd : cmd.substring(0, sp1);
  op.trim();

  auto rest = [&](int start)->String { String r = cmd.substring(start); r.trim(); return r; };

  if (op.equalsIgnoreCase("p")){
    float deg = rest(sp1+1).toFloat();
    theta_user = deg * DEG_TO_RAD;
    cmd_mode = CMD_POS;
  }
  else if (op.equalsIgnoreCase("pr")){
    float rad = rest(sp1+1).toFloat();
    theta_user = rad;
    cmd_mode = CMD_POS;
  }
  else if (op.equalsIgnoreCase("vd")){
    float dps = rest(sp1+1).toFloat();
    w_user = dps * DEG_TO_RAD;
    cmd_mode = CMD_VEL;
  }
  else if (op.equalsIgnoreCase("vr")){
    float rps = rest(sp1+1).toFloat();
    w_user = rps;
    cmd_mode = CMD_VEL;
  }
  else if (op.equalsIgnoreCase("adm")){
    String arg = rest(sp1+1);
    if (arg.equalsIgnoreCase("on")) { USE_ADMITTANCE = true;  }
    else if (arg.equalsIgnoreCase("off")) { USE_ADMITTANCE = false; theta_adm = 0; w_adm = 0; w_adm_prev = 0; }
    else {
      // parse J B K
      int i1 = arg.indexOf(' ');
      int i2 = arg.indexOf(' ', i1+1);
      if (i1>0 && i2>i1) {
        Jv = arg.substring(0,i1).toFloat();
        Bv = arg.substring(i1+1,i2).toFloat();
        Kv = arg.substring(i2+1).toFloat();
      }
    }
  }
  else if (op.equalsIgnoreCase("eq")){
    String a = rest(sp1+1);
    if (a.equalsIgnoreCase("hold")) {
      int adc0 = analogRead(PIN_POT);
      theta_eq = adcToThetaRad(adc0);
    }
  }

  while (Serial.available()) Serial.read(); // flush remainder
}

/* =================== Setup =================== */
void setup(){
  Serial.begin(115200);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  analogWrite(PIN_IN1, 0);
  analogWrite(PIN_IN2, 0);

  scale.begin(PIN_HX_DOUT, PIN_HX_SCK);
  scale.set_scale(LC_CALIBRATION_FACTOR);
  scale.tare(20);

  int adc0 = analogRead(PIN_POT);
  float th0 = adcToThetaRad(adc0);
  theta_eq   = th0;
  theta_user = th0;      // start from current angle for smoothness

  lastLoopMicros = micros();
}

/* =================== Main loop =================== */
void loop(){
  unsigned long now = micros();
  if ((now - lastLoopMicros) < LOOP_DT_US) { parseSerial(); return; }
  float dt = (now - lastLoopMicros) * 1e-6f;
  lastLoopMicros = now;
  if (dt <= 0.0f) return;

  parseSerial();

  /* --- Measure angle --- */
  int   adc        = analogRead(PIN_POT);
  float theta_meas = adcToThetaRad(adc);

  /* --- Force → torque (EMA) --- */
  float force_N = force_N_ema;
  if (scale.is_ready()){
    force_N = scale.get_units(1);  // Newtons
  }
  float aF = emaAlpha(FORCE_EMA_CUTOFF_HZ, dt);
  force_N_ema = emaStep(force_N_ema, force_N, aF);
  float tau_ext = TORQUE_SIGN * force_N_ema * ARM_LENGTH_M;

  /* --- Admittance: your backward-Euler step for w_adm --- */
  float spring = Kv * (theta_meas - theta_eq);
  float denom  = Jv + Bv * dt;
  float numer  = Jv * w_adm + (tau_ext - spring) * dt;
  float w_next = numer / max(1e-6f, denom);

  // rate & magnitude clamps
  float dw_max = DW_ADM_MAX * dt;
  w_next = saturate(w_next, w_adm - dw_max, w_adm + dw_max);
  w_adm  = saturate(w_next, -W_ADM_MAX, W_ADM_MAX);

  // Tustin integration to theta_adm
  float dtheta_adm = 0.5f * dt * (w_adm + w_adm_prev);
  float dtheta_max = DTHETA_MAX * dt;
  dtheta_adm       = saturate(dtheta_adm, -dtheta_max, dtheta_max);
  theta_adm       += dtheta_adm;
  theta_adm        = saturate(theta_adm, -THETA_ADM_MAX, THETA_ADM_MAX);
  w_adm_prev       = w_adm;

  /* --- Command handling --- */
  if (cmd_mode == CMD_VEL){
    // integrate user velocity into position reference (Tustin); keep within mech limits
    w_user = saturate(w_user, -W_USER_MAX, W_USER_MAX);
    float dtheta_user = 0.5f * dt * (w_user + w_user_prev);
    float dtheta_user_max = DTHETA_MAX * dt;
    dtheta_user = saturate(dtheta_user, -dtheta_user_max, dtheta_user_max);
    theta_user += dtheta_user;
    theta_user  = saturate(theta_user, THETA_MIN_RAD, THETA_MAX_RAD);
    w_user_prev = w_user;
  }
  // else CMD_POS: theta_user is set directly via p/pr

  /* --- Position PID on θ_cmd = θ_user + θ_adm --- */
  float theta_cmd = USE_ADMITTANCE ? (theta_user + theta_adm) : theta_user;

  float e = theta_cmd - theta_meas;
  if (fabs(e) < 0.0262f){ e = 0.0f;}  // ~1.5° deadband (your value)

  // Integrator with clamp (anti-windup)
  iTerm += Ki * e * dt;
  iTerm  = saturate(iTerm, -I_CLAMP, I_CLAMP);

  // Filtered derivative: dTerm += α*(de/dt - dTerm)
  float de_dt   = (e - err_prev) / dt;
  float alpha_d = dt / (D_TAU + dt);
  dTerm += alpha_d * (de_dt - dTerm);
  err_prev = e;

  float u_pwm = Kp * e + iTerm + Kd * dTerm;
  u_pwm = saturate(u_pwm, -PWM_MAX, PWM_MAX);
  

  setMotorPWM(u_pwm);

  /* --- Telemetry (~10 Hz) --- */
  static uint32_t dbg_div = 0;
  if ((dbg_div++ % (uint32_t)(LOOP_HZ / 10)) == 0){
    Serial.print(F("mode "));   Serial.print((cmd_mode==CMD_POS)?"pos":"vel");
    Serial.print(F(" th "));    Serial.print(theta_meas, 4);
    Serial.print(F(" th_user "));Serial.print(e, 4);
    Serial.print(F(" th_adm "));Serial.print(theta_adm, 4);
    Serial.print(F(" th_cmd "));Serial.print(theta_cmd, 4);
    Serial.print(F(" w_adm ")); Serial.print(w_adm, 3);
    Serial.print(F(" F "));     Serial.print(force_N_ema, 3);
    Serial.print(F(" tau "));   Serial.print(tau_ext, 3);
    Serial.print(F(" pwm "));   Serial.println(u_pwm, 1);
  }
}
