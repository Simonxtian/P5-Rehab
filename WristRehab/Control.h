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
  void begin(){
    motor_.begin();
    enc_.begin();
    fs_.begin();
    adm_.begin();
    pid_.begin();  // Initialize PID controller - was missing!
    lastLoopUs_ = micros();
    lastLogMs_  = millis();   
  }

  void update(){
    unsigned long now = micros();
    const unsigned long dt_us_target = (unsigned long)(1e6f / LOOP_HZ);
    if ((now - lastLoopUs_) < dt_us_target) return;
    float dt = (now - lastLoopUs_) * 1e-6f; lastLoopUs_ = now;

    // --- Manual override for bring-up ---
    if (overrideActive_) {
      motor_.writePWM(overridePWM_);
      if (millis() > overrideEndMs_) { overrideActive_ = false; }
      if ((millis() - lastLogMs_) >= LOG_PERIOD_MS){
        lastLogMs_ = millis();
        int adc = analogRead(PIN_POT);
        float theta_pot_rad = adcToThetaRad(adc);
        //float theta_pot_deg = theta_pot_rad * RAD_TO_DEG;
        float theta_pot_deg = fabs(theta_pot_rad * RAD_TO_DEG);
        
        float theta_enc = enc_.thetaRad();
        enc_.updateSpeed();
        float w_meas = enc_.wRadPerSec();
        Serial.print(theta_pot_deg);          Serial.print(', ');
        Serial.print(digitalRead(11));        Serial.print(',');
        Serial.print(analogRead(A0));        Serial.print(',');
        Serial.print(theta_enc, 6);           Serial.print(',');
        Serial.print(0.0f, 6);                Serial.print(',');
        Serial.print(w_meas, 6);              Serial.print(',');
        Serial.print(overridePWM_, 1);        Serial.print(',');
        Serial.print(fs_.forceFiltered(),4);  Serial.print(',');
        Serial.print(fs_.tauExt(),5);         Serial.print(',');
        Serial.println(0.0f,5);
      }
      return;
    }

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
    if ((theta_enc >= POS_MAX_RAD && w_total > 0.0f) ||
        (theta_enc <= POS_MIN_RAD && w_total < 0.0f)) {
      w_total = 0.0f;
    }

    // inner PID -> PWM
    float u_pwm = pid_.step(w_total, w_meas, dt);
    motor_.writePWM(u_pwm);

    // telemetry
    if ((millis() - lastLogMs_) >= LOG_PERIOD_MS){
      lastLogMs_ = millis();
      int adc = analogRead(PIN_POT);
      float theta_pot_rad = adcToThetaRad(adc);
      //float theta_pot_deg = theta_pot_rad * RAD_TO_DEG;
      float theta_pot_deg = fabs(theta_pot_rad * RAD_TO_DEG);
      Serial.print(theta_pot_deg);          Serial.print(',');
      Serial.print(digitalRead(11));        Serial.print(',');
      Serial.print(analogRead(A0));        Serial.print(',');
      Serial.print(theta_enc, 6);           Serial.print(',');
      Serial.print(wUser_, 6);              Serial.print(',');
      Serial.print(w_meas, 6);              Serial.print(',');
      Serial.print(u_pwm, 1);               Serial.print(',');
      Serial.print(fs_.forceFiltered(),4);  Serial.print(',');
      Serial.print(tau_ext,5);              Serial.print(',');
      Serial.println(adm_.wAdm(),5);
    }
  }

  // ---- API used by SerialParser ----
  void setUserVel(float w){ wUser_ = w; }
  void admEnable(bool en){ adm_.setEnabled(en); }
  void admSet(float J,float B,float K){ adm_.setParams(J,B,K); }
  void admHoldEq(){ adm_.holdEq(enc_.thetaRad()); }
  void tareScale(){ fs_.tare(); }
  void setTotalMass(float mass_kg){ fs_.setTotalMass(mass_kg); }

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
