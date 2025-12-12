// =============================== ForceSensor.h ===============================
#pragma once
#include <Arduino.h>
#include <HX711.h>
#include "Config.h"
#include "Utils.h"
#include "Filters.h"

class ForceSensor {
public:
  void begin(){
    scale_.begin(HX_DOUT, HX_SCK);
    scale_.set_scale(COUNTS_PER_N);
    delay(100);
    tare(20);
    forceFilter_.begin(BUTTER_B0, BUTTER_B1, BUTTER_B2, BUTTER_A1, BUTTER_A2);
    forceFiltered_ = 0.0f;
    // forceEma_ = 0.0f;
    tauExt_ = 0.0f;
    totalMassKg_ = 0.00f;
    thetaTareRad_ = 1.54f;  
  }
  void tare(uint8_t times=20){ scale_.tare(times); }
  void setTotalMass(float mass_kg){ totalMassKg_ = mass_kg; }
  void setArmLength(float length_m){ armLengthM_ = length_m; }
  
  void setTareAngle(float theta_rad){ thetaTareRad_ = theta_rad; }

  float updateAndGetTau(){
    if (!scale_.is_ready()) return tauExt_;
    float F_meas = scale_.get_units(1);  
    int adc = analogRead(PIN_POT);
    float theta = adcToThetaRad(adc);
    float gravDeltaN = (totalMassKg_ * 9.82f * (sinf(theta) - sinf(thetaTareRad_)));
    float F_ext = F_meas - gravDeltaN;
    // forceEma_ = emaStep(forceEma_, F_ext, FORCE_EMA_ALPHA);
    // tauExt_ = TORQUE_SIGN * forceEma_ * armLengthM_;
    forceFiltered_ = forceFilter_.update(F_ext);
    tauExt_ = TORQUE_SIGN * forceFiltered_ * armLengthM_;
    if (fabs(tauExt_)< 0.02) tauExt_=0.0f;
    return tauExt_;
  }

  float forceFiltered() const { return forceEma_; }
  float tauExt() const { return tauExt_; }
  float thetaTare() const { return thetaTareRad_; }
  float armLength() const { return armLengthM_; }

private:
  HX711 scale_;
  float forceEma_{0.0f};
  ButterworthLP2 forceFilter_; 
  float forceFiltered_{0.0f};
  float tauExt_{0.0f};
  float totalMassKg_{0.072f};  
  float thetaTareRad_{1.54f};  
  float armLengthM_{ARM_LENGTH_M}; 
};