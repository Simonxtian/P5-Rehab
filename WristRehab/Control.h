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
  void clearFault() { faultLatched_ = false; }
  bool isFault() const { return faultLatched_; }

  void update(){
    if (faultLatched_) {
      motor_.writePWM(0.0f);
      return;
    }

    unsigned long now = micros();
    const unsigned long dt_us_target = (unsigned long)(1e6f / LOOP_HZ);
    if ((now - lastLoopUs_) < dt_us_target) return;
    float dt = (now - lastLoopUs_) * 1e-6f; lastLoopUs_ = now;

    

    // encoder & speed
    float theta_enc = enc_.thetaRad();
    enc_.updateSpeed();
    float w_meas = enc_.wRadPerSec();


  // ===== 3) Admittance timing + sine-torque excitation =====
  // outer admittance loop at ~200 Hz (5 ms)
  // static unsigned long lastAdmUs = 0;
  // static float t_sec  = 0.0f;        // time for sine [s]
  // static float tau_ext = 0.0f;       // last torque used (for logging)

  // const unsigned long ADM_PERIOD_US = 10000;   // 200 Hz
  // const float F_TEST = 0.10f;                  // test frequency [Hz]
  // const float A_TAU  = 0.40f;                // torque amplitude [Nm]

  // if ((now - lastAdmUs) >= ADM_PERIOD_US) {
  //   unsigned long dt_adm_us = now - lastAdmUs;
  //   lastAdmUs = now;

  //   t_sec += dt_adm_us * 1e-6f;   //  time in seconds

  //   // --- TEST INPUT: pure sine torque instead of load cell ---
  //   tau_ext = A_TAU * sinf(2.0f * PI * F_TEST * t_sec);

  //   // If you want real sensor + test later:
  //   // float tau_meas = fs_.updateAndGetTau();
  //   // tau_ext = tau_meas + A_TAU * sinf(...);

  //   adm_.update(theta_enc, tau_ext);
  // }




    // // // force/torque & admittance
    float tau_ext = fs_.updateAndGetTau();
    adm_.update(theta_enc, tau_ext);

    float w_total = (adm_.enabled() ? (wUser_ + adm_.wAdm()) : wUser_);


//  // ===== 3) velocity sine command for test =====
//     static float t_sec = 0.0f;
//     t_sec += dt;



//     const float f_test = 0.05f;          // [Hz] example near your bandwidth
//     const float omega  = 2.0f * PI * f_test;

//     const float W_amp  = 0.8;   // stays within ROM by design

//     float w_cmd_sine = W_amp * sinf(omega * t_sec);

//     // For pure velocity-loop test, ignore admittance:
//     float w_total = w_cmd_sine;

        // position limits
    if ((theta_enc >= 1.0f && w_total > 0.0f) ||
        (theta_enc <= -1.0f && w_total < 0.0f)) {
      w_total = 0.0f;
    }


    float u_pwm = pid_.step(w_total, w_meas, dt);
    const float TAU_FAULT_LIMIT = 1.0f;   // Nm, your chosen limit
    if (fabsf(tau_ext) > TAU_FAULT_LIMIT) {
      faultLatched_ = true;
      u_pwm = 0.0f;
    }

    

  
    motor_.writePWM(u_pwm);

    // // --- Loop frequency logging (velocity + admittance) ---
    // static unsigned long statsStartMs = millis();
    // static unsigned long velAccUs     = 0;
    // static uint32_t      velCount     = 0;

    // // dt is in seconds; convert back to µs for stats
    // velAccUs += (unsigned long)(dt * 1e6f);
    // velCount++;

    // unsigned long nowMs = millis();
    // if (nowMs - statsStartMs >= 1000UL) {   // about once per second
    //   float velHz = 0.0f;
    //   if (velCount > 0 && velAccUs > 0) {
    //     float avgDtUs = velAccUs / (float)velCount;
    //     velHz = 1e6f / avgDtUs;
    //   }

    //   Serial.print(F("velLoop_Hz="));
    //   Serial.print(velHz, 1);
    //   Serial.print(F(", admLoop_Hz="));
    //   Serial.println(adm_.loopHz(), 1);

    //   velAccUs = 0;
    //   velCount = 0;
    //   statsStartMs = nowMs;
    // }



    // --- Telemetry for game (minimal stream) ---
    if ((millis() - lastLogMs_) >= LOG_PERIOD_MS){
      lastLogMs_ = millis();
      int adc = analogRead(PIN_POT);
      float theta_pot_rad = adcToThetaRad(adc);
      //float theta_pot_deg = theta_pot_rad * RAD_TO_DEG;
      float theta_pot_deg = fabs(theta_pot_rad * RAD_TO_DEG);
      Serial.print(theta_pot_deg-90);   Serial.print(',');
      // Serial.print(theta_pot_rad);   // angle in degrees
      
      Serial.print(digitalRead(11));        Serial.print(',');// button state: 0 or 1
      // Serial.print(theta_pot_rad);          Serial.print(',');
      // Serial.println(digitalRead(11));  // Serial.print(',');
      // Serial.print(theta_enc, 6);        Serial.print(',');
      // Serial.print(w_total, 6);          Serial.print(',');
      // Serial.print(wUser_, 6);           Serial.print(',');
      // Serial.print(w_meas, 6);           Serial.print(',');
      // Serial.print(u_pwm, 1);            Serial.print(',');
      // Serial.print(fs_.forceFiltered(),4);Serial.print(',');
      Serial.println(tau_ext,5);        // Serial.print(',');
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
  void setTareAngle(float theta_rad){ fs_.setTareAngle(theta_rad); }
  void setArmLength(float length_m){ fs_.setArmLength(length_m); }

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

  // safety fault (latched)
  bool faultLatched_{false};
};