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
    forceEma_ = 0.0f;
    tauExt_ = 0.0f;
    totalMassKg_ = 0.072f;
    thetaTareRad_ = 1.54f;  // Default reference angle, updated by calibration
  }
  void tare(uint8_t times=20){ scale_.tare(times); }
  void setTotalMass(float mass_kg){ totalMassKg_ = mass_kg; }
  void setArmLength(float length_m){ armLengthM_ = length_m; }
  
  // Set the reference angle for gravity compensation (called after tare)
  void setTareAngle(float theta_rad){ thetaTareRad_ = theta_rad; }

  // Update using current pot angle for gravity comp; returns tau_ext
  float updateAndGetTau(){
    if (!scale_.is_ready()) return tauExt_;
    float F_meas = scale_.get_units(1);  // N, relative to tare
    int adc = analogRead(PIN_POT);
    float theta = adcToThetaRad(adc);
    // Gravity change relative to tare angle (now dynamic)
    float gravDeltaN = totalMassKg_ * 9.82f * (sinf(theta) - sinf(thetaTareRad_));
    float F_ext = F_meas - gravDeltaN;
    forceEma_ = emaStep(forceEma_, F_ext, FORCE_EMA_ALPHA);
    tauExt_ = TORQUE_SIGN * forceEma_ * armLengthM_;
    return tauExt_;
  }

  float forceFiltered() const { return forceEma_; }
  float tauExt() const { return tauExt_; }
  float thetaTare() const { return thetaTareRad_; }
  float armLength() const { return armLengthM_; }

private:
  HX711 scale_;
  float forceEma_{0.0f};
  float tauExt_{0.0f};
  float totalMassKg_{0.072f};  // Dynamic mass for gravity compensation
  float thetaTareRad_{1.54f};  // Reference angle for gravity compensation
  float armLengthM_{ARM_LENGTH_M};  // Dynamic arm length for torque calculation
};