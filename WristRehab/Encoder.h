#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"

class Encoder {
public:
  void begin(){
    pinMode(PIN_ENC_A, INPUT_PULLUP);
    pinMode(PIN_ENC_B, INPUT_PULLUP);
    lastAB_ = readAB_();
    instance_ = this;
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), isrA_, CHANGE);
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_B), isrB_, CHANGE);
    encCount_ = 0;
    lastEnc_ = 0;
    lastSpeedUs_ = micros();
    accCounts_ = 0;
    for (uint8_t k=0;k<W_MED_WIN;++k) wMedBuf_[k]=0.0f;
    wMedIdx_=0; wMedFilled_=false; wEMA_=0.0f; wMeas_=0.0f;
  }

  inline long counts() const { return encCount_; }
  inline float thetaRad() const { return encCount_ * COUNT_TO_RAD; }
  inline float wRadPerSec() const { return wMeas_; }

  void updateSpeed(){
    unsigned long now = micros();
    long dC = encCount_ - lastEnc_;
    lastEnc_ = encCount_;
    accCounts_ += dC;
    if ((now - lastSpeedUs_) >= SPEED_WIN_US){
      float dtw = (now - lastSpeedUs_) * 1e-6f;
      lastSpeedUs_ = now;
      float revs = (float)accCounts_ / (float)(AMT_CPR * 4L);
      float wInst = (dtw > 0.0f) ? (revs * 2.0f * PI / dtw) : 0.0f;
      accCounts_ = 0;
      if (W_MED_WIN==1){
        wEMA_ = wInst; wMeas_=wEMA_;
      } else {
        wMedBuf_[wMedIdx_] = wInst;  
        if (++wMedIdx_>=W_MED_WIN){ wMedIdx_=0; wMedFilled_=true; }
        uint8_t n = wMedFilled_ ? W_MED_WIN : (wMedIdx_==0 ? 1 : wMedIdx_);
        float wMed = median_(wMedBuf_, n);
        wEMA_ += Omega_EMA_ALPHA * (wMed - wEMA_);
        wMeas_ = wEMA_;
      }
    }
  }

  void zero(){ noInterrupts(); encCount_=0; interrupts(); }

private:
  static Encoder* instance_;
  static void isrA_(){ if (instance_) instance_->handle_(); }
  static void isrB_(){ if (instance_) instance_->handle_(); }

  void handle_(){
    uint8_t ab = readAB_();
    static const int8_t lut[16] = {
      0,  -1, +1,  0,
      +1,  0,  0, -1,
      -1,  0,  0, +1,
       0, +1, -1,  0
    };
    static uint8_t last = 0;
    uint8_t idx = (last << 2) | ab;
    encCount_ += lut[idx];
    last = ab;
  }
  uint8_t readAB_(){
    uint8_t a = (uint8_t)digitalRead(PIN_ENC_A);
    uint8_t b = (uint8_t)digitalRead(PIN_ENC_B);
    return (a << 1) | b;
  }

  static float median_(float* buf, uint8_t n){
    // tiny insertion sort copy
    float tmp[W_MED_WIN];
    for (uint8_t k=0;k<n;++k) tmp[k]=buf[k];
    for (uint8_t i=1;i<n;++i){
      float key=tmp[i]; int8_t j=i-1; while(j>=0 && tmp[j]>key){ tmp[j+1]=tmp[j]; j--; }
      tmp[j+1]=key; }
    if (n & 1) return tmp[n>>1];
    return 0.5f * (tmp[(n>>1)-1] + tmp[n>>1]);
  }

  volatile long encCount_{0};
  volatile uint8_t lastAB_{0};
  long lastEnc_{0};
  unsigned long lastSpeedUs_{0};
  long accCounts_{0};
  float wMedBuf_[W_MED_WIN];
  uint8_t wMedIdx_{0};
  bool wMedFilled_{false};
  float wEMA_{0.0f};
  float wMeas_{0.0f};
};

inline Encoder* Encoder::instance_ = nullptr;