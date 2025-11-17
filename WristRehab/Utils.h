#pragma once
#include <Arduino.h>

inline float saturate(float x, float lo, float hi){
  if (x < lo) return lo; if (x > hi) return hi; return x;
}

inline float emaAlpha(float fc_hz, float dt_s) {
  if (fc_hz <= 0.0f) return 1.0f; // bypass -> snap
  float tau = 1.0f / (2.0f * PI * fc_hz);
  return dt_s / (dt_s + tau);
}

inline float emaStep(float prev, float x, float alpha) {
  return prev + alpha * (x - prev);
}
