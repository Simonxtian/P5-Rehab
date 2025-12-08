// =============================== WristRehab.ino ===============================
#include <Arduino.h>
#include "Config.h"
#include "Control.h"
#include "SerialParser.h"
#include "Filters.h"  

Control ctrl;
SerialParser parser(ctrl);

void setup() {
  Serial.begin(460800);  
  ctrl.begin();
  parser.begin();
  Serial.println(F("# wrist controller ready"));
  pinMode(11, INPUT_PULLUP);
  
  delay(500);  
  
  int adc_sum = 0;
  const int samples = 20;
  for(int i = 0; i < samples; i++) {
    adc_sum += analogRead(PIN_POT);
    delay(10);
  }
  int adc_avg = adc_sum / samples;
  float initial_theta = adcToThetaRad(adc_avg);
  
  ctrl.setTareAngle(initial_theta);
  

}

void loop() {
  parser.poll();   
  ctrl.update();   
}
