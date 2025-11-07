
const int potPin = A0;  // Analog pin where the potentiometer is connected
int potValue = 0;       // Variable to store the potentiometer value
float angle = 0.0;
unsigned long Current = 0;

int OuterUpValue = 85;
int UpValue = 110;
int DownValue = 130;
int OuterDownValue = 155;

int ButtonPin = 5;

void setup() {
  Serial.begin(9600);  // Initialize Serial communication at 9600 baud
  Serial.println("Potentiometer Reader Started");
  pinMode(ButtonPin, INPUT_PULLUP);
  Current = millis();
}

void ReadPot() {
  if (Current + 50 < millis()){
    potValue = analogRead(potPin);  // Read analog value (0 to 1023)

    //angle = (270.0 / 1023.0) * potValue;  //map(potValue, 0, 1023, 0.0, 300.0);
    angle = potValue;
    // Print values to Serial Monitor
    Serial.print("Pot: ");
    Serial.println(angle);
    Current = millis();
  }
}

void loop() {
  ReadPot();
  int Button = digitalRead(ButtonPin);
  if (Button < 1) {
    Serial.print("Button: ");
    Serial.println(2001);
    while (Button < 1) {
      Button = digitalRead(ButtonPin);
      ReadPot();
    }
    Serial.print("Button: ");
    Serial.println(2000);
  }
}