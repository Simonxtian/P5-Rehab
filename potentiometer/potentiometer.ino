int potPin = A0;
float voltage = 0;
float angle = 0;

const float minV = 0.4;   // adjust to your measured minimum
const float maxV = 4.7;   // adjust to your measured maximum

void setup() {
  Serial.begin(9600);
}

void loop() {
  int sensorValue = analogRead(potPin);
  //voltage = sensorValue * (5.0 / 1023.0);

  // Constrain voltage within your usable range
  // voltage = constrain(voltage, minV, maxV);

  // Map voltage to 40°–150°
  // angle = 40 + (voltage - minV) * (110.0 / (maxV - minV));

  Serial.println(sensorValue);
  delay(50);
}