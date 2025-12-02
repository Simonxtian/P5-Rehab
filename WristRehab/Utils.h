#pragma once
#include <Arduino.h>

inline float saturate(float x, float lo, float hi){
  if (x < lo) return lo; if (x > hi) return hi; return x;
}

inline float emaStep(float prev, float x, float alpha) {
  return prev + alpha * (x - prev);
}
