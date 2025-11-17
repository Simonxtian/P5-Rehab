#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"

inline float potNorm(int adc){
  int a = constrain(adc, POT_ADC_MIN, POT_ADC_MAX);
  float x = (float)(a - POT_ADC_MIN) / (float)(POT_ADC_MAX - POT_ADC_MIN);
  return saturate(x, 0.0f, 1.0f);
}

inline float adcToThetaRad(int adc){
  float x = potNorm(adc);
  float theta_raw = THETA_MIN_RAD + x * (THETA_MAX_RAD - THETA_MIN_RAD);
  return theta_raw + POT_OFFSET_RAD; // align to horizontal
}

