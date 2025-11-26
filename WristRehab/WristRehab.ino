// =============================== WristRehab.ino ===============================
#include <Arduino.h>
#include "Config.h"
#include "Control.h"
#include "SerialParser.h"

Control ctrl;
SerialParser parser(ctrl);

void setup() {
  Serial.begin(115200);
  ctrl.begin();
  parser.begin();
  Serial.println(F("# wrist controller ready"));
}

void loop() {
  parser.poll();   //serial commands
  ctrl.update();   // control loops
}
