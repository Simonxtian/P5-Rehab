#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"

class VelocityPID {
public:
  void begin(){ Kp_=KP_INIT; Ki_=KI_INIT; Kd_=KD_INIT; reset(); }
  void reset(){ iTerm_=0.0f; dTerm_=0.0f; ePrev_=0.0f; }

  void setGains(float kp,float ki,float kd){ Kp_=kp; Ki_=ki; Kd_=kd; }

  // Returns signed PWM command (clamped to +/- PWM_MAX)
  float step(float w_cmd, float w_meas, float dt){
    float e = w_cmd - w_meas;
    if (fabs(e) < 0.15f) e = 0.0f; // deadband
    iTerm_ += Ki_ * e * dt;
    iTerm_ = saturate(iTerm_, -INT_CLAMP, INT_CLAMP);

    float raw_d = (e - ePrev_) / dt;
    float alpha_d = dt / (D_TAU_VEL + dt);
    dTerm_ += alpha_d * (raw_d - dTerm_);
    ePrev_ = e;

    float u = Kp_*e + iTerm_ + Kd_*dTerm_;
    return saturate(u, -PWM_MAX, PWM_MAX);
  }

private:
  float Kp_{0}, Ki_{0}, Kd_{0};
  float iTerm_{0}, dTerm_{0}, ePrev_{0};
};
