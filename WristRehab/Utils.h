#pragma once
#include <Arduino.h>

inline float saturate(float x, float lo, float hi){
  if (x < lo) return lo; if (x > hi) return hi; return x;
}

inline float emaStep(float prev, float x, float alpha) {
  return prev + alpha * (x - prev);
}

// 2nd-order low-pass Butterworth IIR filter
// y[k] = b0 x[k] + b1 x[k-1] + b2 x[k-2]
//        - a1 y[k-1] - a2 y[k-2];
class ButterworthLP2 {
public:
  // Initialize with coefficients from Config.h
  void begin(float b0_val, float b1_val, float b2_val, float a1_val, float a2_val) {
    b0 = b0_val;
    b1 = b1_val;
    b2 = b2_val;
    a1 = a1_val;
    a2 = a2_val;

    // reset state
    x1 = x2 = 0.0f;
    y1 = y2 = 0.0f;
  }

  // Call once per sample (e.g. every 1/Fs seconds)
  float update(float x) {
    float y = b0 * x + b1 * x1 + b2 * x2
                    - a1 * y1 - a2 * y2;

    // shift state
    x2 = x1;
    x1 = x;
    y2 = y1;
    y1 = y;

    return y;
  }

  void reset(float value = 0.0f) {
    x1 = x2 = y1 = y2 = value;
  }

  // coefficients
  float b0, b1, b2;
  float a1, a2;

private:
  // state
  float x1, x2;
  float y1, y2;
};
