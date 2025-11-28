#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"
#include "MotorDriver.h"
#include "Encoder.h"
#include "ForceSensor.h"
#include "Admittance.h"
#include "VelocityPID.h"
#include "Filters.h"   // for adcToThetaRad used in telemetry

class Control {
public:
  void begin() {
    motor_.begin();
    enc_.begin();
    fs_.begin();
    adm_.begin();
    pid_.begin();  // Initialize PID controller
    lastLoopUs_ = micros();
    lastLogMs_  = millis();
  }

  void update(){
    unsigned long now = micros();
    const unsigned long dt_us_target = (unsigned long)(1e6f / LOOP_HZ);
    if ((now - lastLoopUs_) < dt_us_target) return;
    float dt = (now - lastLoopUs_) * 1e-6f; lastLoopUs_ = now;

    

    // encoder & speed
    float theta_enc = enc_.thetaRad();

    enc_.updateSpeed();
    float w_meas = enc_.wRadPerSec();

    // force/torque & admittance
    float tau_ext = fs_.updateAndGetTau();
    adm_.update(theta_enc, tau_ext);

    // compose command
    float w_total = (adm_.enabled() ? (wUser_ + adm_.wAdm()) : wUser_);

    // position limits
    if ((theta_enc >= 1.00f && w_total > 0.0f) ||
        (theta_enc <= -1.00f && w_total < 0.0f)) {
      w_total = 0.0f;
    }

    float u_pwm = pid_.step(w_total, w_meas, dt);

  
    motor_.writePWM(u_pwm);


    // --- Telemetry for game (minimal stream) ---
    if ((millis() - lastLogMs_) >= LOG_PERIOD_MS){
      lastLogMs_ = millis();
      int adc = analogRead(PIN_POT);
      float theta_pot_rad = adcToThetaRad(adc);
      //float theta_pot_deg = theta_pot_rad * RAD_TO_DEG;
      float theta_pot_deg = (theta_pot_rad * RAD_TO_DEG);
      Serial.println(theta_pot_deg);   // angle in degrees
      // Serial.print(',');
      // Serial.println(digitalRead(11));  // button state: 0 or 1
      // Serial.print(theta_pot_rad);           Serial.print(',');
      // Serial.println(digitalRead(11));  // Serial.print(',');
      // Serial.print(theta_enc, 6);        Serial.print(',');
      // Serial.print(wUser_, 6);           Serial.print(',');
      // Serial.print(w_meas, 6);           Serial.print(',');
      // Serial.print(u_pwm, 1);            Serial.print(',');
      // Serial.print(fs_.forceFiltered(),4);Serial.print(',');
      // Serial.print(tau_ext,5);           Serial.print(',');
      // Serial.println(adm_.wAdm(),5);
    }
  }
  // ---- API used by SerialParser ----
  void setUserVel(float w){ wUser_ = w; }
  void admEnable(bool en){ adm_.setEnabled(en); }
  void admSet(float J,float B,float K){ adm_.setParams(J,B,K); }
  void admHoldEq(){ adm_.holdEq(enc_.thetaRad()); }
  void tareScale(){ fs_.tare(); }
  void setTotalMass(float mass_kg){ fs_.setTotalMass(mass_kg); }

  // Query whether admittance control is currently enabled.  This exposes
  // the state of the underlying Admittance object for use by
  // calibration routines.
  bool admIsEnabled() const { return adm_.enabled(); }

  // Return the current user velocity command (rad/s).
  float getUserVel() const { return wUser_; }

  // Expose the underlying ForceSensor for calibration routines.  This
  // method should be used sparingly as it breaks encapsulation; the
  // Calibrator class relies on it to adjust calibration factors and
  // offsets.
  ForceSensor& forceSensor() { return fs_; }

  // Expose encoder for calibration without re-initializing interrupts.
  Encoder& encoder() { return enc_; }

  // ---- Manual override controls ----
  void overridePWM(float pwm, uint32_t ms){
    overridePWM_ = saturate(pwm, -PWM_MAX, PWM_MAX);
    if (ms==0){ overrideActive_ = true; overrideEndMs_ = UINT32_MAX; }
    else { overrideActive_ = true; overrideEndMs_ = millis() + ms; }
  }
  void overrideOff(){ overrideActive_ = false; }

private:
  MotorDriver motor_;
  Encoder     enc_;
  ForceSensor fs_;
  Admittance  adm_;
  VelocityPID pid_;

  float wUser_{0.0f};
  unsigned long lastLoopUs_{0};
  unsigned long lastLogMs_{0};

  // override state
  bool overrideActive_{false};
  float overridePWM_{0.0f};
  uint32_t overrideEndMs_{0};
};
