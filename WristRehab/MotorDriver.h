#pragma once
#include <Arduino.h>
#include "Config.h"
#include "Utils.h"

class MotorDriver {
public:
  void begin(){
    pinMode(PIN_IN1, OUTPUT);
    pinMode(PIN_IN2, OUTPUT);
    analogWrite(PIN_IN1, 0);
    analogWrite(PIN_IN2, 0);
    lastSign_ = 0;
  }

  void writePWM(float u_pwm){
    u_pwm = saturate(u_pwm, -PWM_LIMIT, PWM_LIMIT);
    int sign = (u_pwm > 0) - (u_pwm < 0);
    int mag  = (int)(fabs(u_pwm) + 0.5f);

    if (sign && sign != lastSign_ && lastSign_ != 0){
      analogWrite(PIN_IN1, 0);
      analogWrite(PIN_IN2, 0);
      delayMicroseconds(REV_DEADTIME_US);
    }
    if      (sign > 0) { analogWrite(PIN_IN1, mag); analogWrite(PIN_IN2, 0); }
    else if (sign < 0) { analogWrite(PIN_IN1, 0);   analogWrite(PIN_IN2, mag); }
    else               { analogWrite(PIN_IN1, 0);   analogWrite(PIN_IN2, 0); }

    lastSign_ = sign;
  }

private:
  int lastSign_{0};
};
