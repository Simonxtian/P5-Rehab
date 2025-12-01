// =============================== WristRehab.ino ===============================
#include <Arduino.h>
#include "Config.h"
#include "Control.h"
#include "SerialParser.h"
#include "Filters.h"  // for adcToThetaRad

Control ctrl;
SerialParser parser(ctrl);

void setup() {
  Serial.begin(460800);  // game stream
  ctrl.begin();
  parser.begin();
  Serial.println(F("# wrist controller ready"));
  pinMode(11, INPUT_PULLUP);
  
  // Automatic load cell calibration at startup
  delay(500);  // Let hardware stabilize
  
  // Capture initial potentiometer angle for gravity compensation reference
  int adc_sum = 0;
  const int samples = 20;
  for(int i = 0; i < samples; i++) {
    adc_sum += analogRead(PIN_POT);
    delay(10);
  }
  int adc_avg = adc_sum / samples;
  float initial_theta = adcToThetaRad(adc_avg);
  
  // Set this as the tare angle for gravity compensation
  ctrl.setTareAngle(initial_theta);
  
  Serial.print(F("# Auto-calibrated at startup: theta_tare = "));
  Serial.print(initial_theta, 4);
  Serial.println(F(" rad"));
}

void loop() {
  parser.poll();   // read any serial commands
  ctrl.update();   // run control loops
}
