#pragma once
#include <Arduino.h>
#include "Admittance.h"

class Control; 

class SerialParser {
public:
  explicit SerialParser(Control& ctrl): ctrl_(ctrl) {}
  void begin(){}
  void poll();
private:
  Control& ctrl_;
};
