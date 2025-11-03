#include <Keyboard.h>


const int potPin = A0;  // Analog pin where the potentiometer is connected
int potValue = 0;       // Variable to store the potentiometer value
float angle = 0.0;


int OuterUpValue = 85; \\Variable to store the outer up position, can be adjusted
int UpValue = 110; \\Variable to store the up position, can be adjusted
int DownValue = 130; \\Variable to store the down position, can be adjusted
int OuterDownValue = 155; \\Variable to store the outer down position, can be adjusted

void setup() {
  Serial.begin(9600);  // Initialize Serial communication at 9600 baud
  Serial.println("Potentiometer Reader Started");
  Keyboard.begin(); //needed to start keyboard emulation
}

void Readpot() {
  potValue = analogRead(potPin);  // Read analog value (0 to 1023)

  angle = (270.0 / 1023.0) * potValue;  //map(potValue, 0, 1023, 0.0, 270.0);
  // Print values to Serial Monitor
  Serial.println(angle);
}

void loop() {
  Readpot();
  
}