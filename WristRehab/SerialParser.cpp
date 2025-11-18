// =============================== SerialParser.cpp ===============================
#include "SerialParser.h"
#include "Control.h"

void SerialParser::poll(){
  if (!Serial.available()) return;
  String token = Serial.readStringUntil(' ');
  token.trim();
  if (!token.length()) return;

  if (token.equalsIgnoreCase("w")){
    ctrl_.setUserVel(Serial.parseFloat());

  } else if (token.equalsIgnoreCase("vd")){
    ctrl_.setUserVel(Serial.parseFloat() * DEG_TO_RAD);

  } else if (token.equalsIgnoreCase("tare")){
    ctrl_.tareScale();
    Serial.println(F("# scale tared"));

  } else if (token.equalsIgnoreCase("totalmass")){
    float mass = Serial.parseFloat();
    ctrl_.setTotalMass(mass);
    Serial.print(F("# total mass set to "));
    Serial.print(mass, 4);
    Serial.println(F(" kg"));

  } else if (token.equalsIgnoreCase("adm")){
    String rest = Serial.readStringUntil('\n');
    rest.trim();
    if (rest.equalsIgnoreCase("on")){
      ctrl_.admEnable(true);
      Serial.println(F("# adm ON"));
    } else if (rest.equalsIgnoreCase("off")){
      ctrl_.admEnable(false);
      Serial.println(F("# adm OFF"));
    } else {
      int i1 = rest.indexOf(' ');
      int i2 = rest.indexOf(' ', i1 + 1);
      if (i1 > 0 && i2 > i1){
        float J = rest.substring(0, i1).toFloat();
        float B = rest.substring(i1 + 1, i2).toFloat();
        float K = rest.substring(i2 + 1).toFloat();
        ctrl_.admSet(J, B, K);
        Serial.print(F("# adm set Jv=")); Serial.print(J, 6);
        Serial.print(F(" Bv=")); Serial.print(B, 6);
        Serial.print(F(" Kv=")); Serial.println(K, 6);
      }
    }

  } else if (token.equalsIgnoreCase("eq")){
    String rest = Serial.readStringUntil('\n');
    rest.trim();
    if (rest.equalsIgnoreCase("hold")){
      ctrl_.admHoldEq();
      Serial.println(F("# theta_eq updated"));
    }

  } else if (token.equalsIgnoreCase("pwm")){
    // manual PWM override: pwm <signed -255..255> [ms]
    float pwm = Serial.parseFloat();
    long ms = Serial.parseInt();
    ctrl_.overridePWM(pwm, (ms > 0) ? (uint32_t)ms : 0);
    Serial.print(F("# override PWM=")); Serial.print(pwm);
    if (ms > 0){
      Serial.print(F(" for ")); Serial.print(ms); Serial.println(F(" ms"));
    } else {
      Serial.println(F(" indefinitely"));
    }

  } else if (token.equalsIgnoreCase("mode")){
    String rest = Serial.readStringUntil('\n');
    rest.trim();
    if (rest.equalsIgnoreCase("pid")){
      ctrl_.overrideOff();
      Serial.println(F("# override OFF (PID mode)"));
    }

  } else if (token.equalsIgnoreCase("test")){
    // simple bring-up self test: +120 PWM 1s, -120 PWM 1s, stop
    ctrl_.overridePWM(+120, 1000);
    delay(1050);
    ctrl_.overridePWM(-120, 1000);
    delay(1050);
    ctrl_.overridePWM(0, 1);
    Serial.println(F("# test sequence done"));
    
  } 



  // flush any leftover chars on the line
  while (Serial.available()) Serial.read();
}
