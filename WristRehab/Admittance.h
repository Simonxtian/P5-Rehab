#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"

struct AdmParams { float Jv, Bv, Kv; };

class Admittance {
public:
  void begin(){
    params_.Jv = Jv_INIT; params_.Bv = Bv_INIT; params_.Kv = Kv_INIT;
    thetaEq_ = 0.0f; wAdm_ = 0.0f; lastPosUs_ = micros();
    enabled_ = true;
  }
  void setEnabled(bool en){ enabled_ = en; if(!en){ wAdm_=0.0f; }}
  bool enabled() const { return enabled_; }

  void setParams(float J, float B, float K){ params_.Jv=J; params_.Bv=B; params_.Kv=K; }
  AdmParams getParams() const { return params_; }

  void holdEq(float theta_now){ thetaEq_ = theta_now; }

  // Call at ~200 Hz; supply encoder theta and external torque
  void update(float theta_enc, float tau_ext){
    unsigned long now = micros();
    if ((now - lastPosUs_) < POS_DT_US) return;
    float dt = (now - lastPosUs_) * 1e-6f; lastPosUs_ = now;
    float spring = params_.Kv * (theta_enc - thetaEq_);
    float denom  = params_.Jv + params_.Bv * dt; if (denom < 1e-6f) denom = 1e-6f;
    float numer  = params_.Jv * wAdm_ + (tau_ext - spring) * dt;
    float wNext  = numer / denom;
    // optional rate/amp limits (commented in your original)
    // float dw_max = DW_ADM_MAX * dt; wNext = saturate(wNext, wAdm_-dw_max, wAdm_+dw_max);
    wAdm_ = wNext; //saturate(wNext, -W_ADM_MAX, W_ADM_MAX);
  }

  float wAdm() const { return enabled_ ? wAdm_ : 0.0f; }
  float thetaEq() const { return thetaEq_; }

private:
  AdmParams params_{};
  float thetaEq_{0.0f};
  float wAdm_{0.0f};
  unsigned long lastPosUs_{0};
  bool enabled_{true};
};
