// =============================== WristRehab.ino ===============================
#include <Arduino.h>
#include "Config.h"
#include "Control.h"
#include "SerialParser.h"

Control ctrl;
SerialParser parser(ctrl);

void setup() {
  Serial.begin(460800);  // game stream
  Serial1.begin(115200); // full telemetry
  ctrl.begin();
  parser.begin();
  Serial.println(F("# wrist controller ready"));
  pinMode(11, INPUT_PULLUP);
}

void loop() {
  parser.poll();   //serial commands
  ctrl.update();   // control loops
}
