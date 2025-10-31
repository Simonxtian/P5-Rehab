#include <Keyboard.h>


const int potPin = A0;  // Analog pin where the potentiometer is connected
int potValue = 0;       // Variable to store the potentiometer value
float angle = 0.0;


int OuterUpValue = 85;
int UpValue = 110;
int DownValue = 130;
int OuterDownValue = 155;

void setup() {
  Serial.begin(9600);  // Initialize Serial communication at 9600 baud
  Serial.println("Potentiometer Reader Started");
  Keyboard.begin();
}

void Readpot() {
  potValue = analogRead(potPin);  // Read analog value (0 to 1023)

  angle = (270.0 / 1023.0) * potValue;  //map(potValue, 0, 1023, 0.0, 300.0);
  // Print values to Serial Monitor
  Serial.println(angle);
}

void loop() {
  Readpot();
}