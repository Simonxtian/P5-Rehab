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
  }
  void tare(uint8_t times=20){ scale_.tare(times); }
  void setTotalMass(float mass_kg){ totalMassKg_ = mass_kg; }

  // Update using current pot angle for gravity comp; returns tau_ext

  float updateAndGetTau(){
  if (!scale_.is_ready()) return tauExt_;

  float forceRawN = scale_.get_units(1);  // N, relative to tare

  int adc = analogRead(PIN_POT);
  float theta_pot = adcToThetaRad(adc);

  float tau_g =TORQUE_SIGN*( totalMassKg_ * 9.82f * ARM_LENGTH_M * sinf(theta_pot));
  float tau_meas = TORQUE_SIGN*(forceRawN * ARM_LENGTH_M);   // raw torque from load cell
  float           // external torque after gravity comp

  forceEma_ = emaStep(forceEma_, tau_meas, FORCE_EMA_ALPHA);
  tauExt_ = (tau_meas-tau_g) ;
  // if (fabs(tauExt_)<0.061f){
  //   tauExt_=0.0f;
  // }
  return tauExt_;}


  float forceFiltered() const { return forceEma_; }
  float tauExt() const { return tauExt_; }

private:
  HX711 scale_;
  float forceEma_{0.0f};
  float tauExt_{0.0f};
  float totalMassKg_{0.072f}; 
};