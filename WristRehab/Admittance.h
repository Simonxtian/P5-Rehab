#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"

struct AdmParams { float Jv, Bv, Kv; };

class Admittance {
public:
  void begin(){
    params_.Jv = Jv_INIT; params_.Bv = Bv_INIT; params_.Kv = Kv_INIT;
    thetaEq_ = 0.0f; wAdm_ = 0.0f; 
    lastPosUs_ = micros();
    enabled_ = true;

    // timing stats init
    accDtUs_ = 0;
    count_   = 0;
    loopHz_  = 0.0f;
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

    // --- real dt used for this admittance step ---
    unsigned long dt_us = now - lastPosUs_;
    lastPosUs_ = now;
    float dt = dt_us * 1e-6f;

    float spring = params_.Kv * (theta_enc - thetaEq_);
    float denom  = params_.Jv + params_.Bv * dt; 
    if (denom < 1e-6f) denom = 1e-6f;
    float numer  = params_.Jv * wAdm_ + (tau_ext - spring) * dt;
    float wNext  = numer / denom;
    wAdm_ = wNext; // optionally saturate here

    // --- timing stats: accumulate dt of *actual* updates ---
    accDtUs_ += dt_us;
    count_++;

    // update frequency estimate roughly once per "second" of accumulated time
    if (accDtUs_ >= 1000000UL) {
      if (count_ > 0) {
        float avgDtUs = accDtUs_ / (float)count_;
        loopHz_ = 1e6f / avgDtUs;
      }
      accDtUs_ = 0;
      count_   = 0;
    }
  }

  float wAdm() const { return enabled_ ? wAdm_ : 0.0f; }
  float thetaEq() const { return thetaEq_; }

  // --- new: expose effective admittance loop frequency in Hz ---
  float loopHz() const { return loopHz_; }

private:
  AdmParams params_{};
  float thetaEq_{0.0f};
  float wAdm_{0.0f};
  unsigned long lastPosUs_{0};
  bool enabled_{true};

  // --- timing stats ---
  unsigned long accDtUs_{0};
  uint32_t      count_{0};
  float         loopHz_{0.0f};
};






