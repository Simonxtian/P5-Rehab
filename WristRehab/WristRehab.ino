// =============================== WristRehab.ino ===============================
#include <Arduino.h>
#include "Config.h"
#include "Control.h"
#include "SerialParser.h"

Control ctrl;
SerialParser parser(ctrl);

void setup() {
  Serial.begin(460800);  // game stream
  ctrl.begin();
  parser.begin();
  Serial.println(F("# wrist controller ready"));
  pinMode(11, INPUT_PULLUP);
}

void loop() {
  parser.poll();   // read any serial commands
  ctrl.update();   // run control loops
}
