// --- Pin configuration ---
const int in1 = 9;        // PWM output
const int in2 = 10;       // PWM output
const int potPin = A0;    // Potentiometer input

// --- Control parameters ---
const float Kp = 13.3;     // Proportional gain
const float Ki = 15.0;     // Integral gain (tune small)
const float Kd = 0.7;     // Derivative gain

int speed = 255;           // Max allowed PWM (0–255)

const float targetAngle = 53.5;  // Handle all the way up
const float angleTol = 1.0;      // Stop tolerance (deg)
const float Ts = 0.005;          // Sample time (s)

// --- Potentiometer calibration ---
const int potUpRaw = 203;   // 53.6 deg (handle up)
const int potDownRaw = 588; // 155 deg (handle down)

// --- Internal state ---
bool controlActive = false;
float angle = 0.0;
float errorPrev = 0.0;
float integral = 0.0;
unsigned long lastTime = 0;

void setup() {
  Serial.begin(9600);
  pinMode(in1, OUTPUT);
  pinMode(in2, OUTPUT);

  Serial.println("Ready. Send 'A' to start closed-loop PID control.");
}

float readAngle() {
  int potValue = analogRead(potPin);
  float angle = 53.6 + (potValue - potUpRaw) * (155.0 - 53.6) / (potDownRaw - potUpRaw);
  return angle;
}

void driveMotor(float controlSignal) {
  if (controlSignal > speed) controlSignal = speed;
  if (controlSignal < -speed) controlSignal = -speed;

  if (controlSignal > 0) {
    analogWrite(in1, (int)controlSignal);
    digitalWrite(in2, LOW);
  } else if (controlSignal < 0) {
    digitalWrite(in1, LOW);
    analogWrite(in2, (int)(-controlSignal));
  } else {
    analogWrite(in1, 0);
    analogWrite(in2, 0);
  }
}

void loop() {
  // Start command
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'A' || cmd == 'a') {
      controlActive = true;
      errorPrev = 0;
      integral = 0;
      lastTime = millis();
      Serial.println("Starting closed-loop PID control to 53.6 deg...");
    }
  }

  angle = readAngle();

  if (controlActive) {
    unsigned long now = millis();
    float dt = (now - lastTime) / 1000.0;
    if (dt <= 0) dt = Ts;
    lastTime = now;

    // PID calculations
    float error = targetAngle - angle;
    integral += error * dt;

    // Anti-windup clamp
    if (integral > 50) integral = 50;
    if (integral < -50) integral = -50;

    float derivative = (error - errorPrev) / dt;
    errorPrev = error;

    float controlSignal = Kp * error + Ki * integral + Kd * derivative;

    driveMotor(controlSignal);

    // Serial.print("Angle: ");
    // Serial.print(angle, 1);
    // Serial.print(" | Err: ");
    // Serial.print(error, 1);
    // Serial.print(" | Int: ");
    // Serial.print(integral, 2);
    // Serial.print(" | Deriv: ");
    // Serial.print(derivative, 1);
    // Serial.print(" | PWM: ");
    // Serial.println(controlSignal, 1);

    Serial.println(angle, 1);

    if (fabs(error) < angleTol) {
      driveMotor(0);
      Serial.println("Target reached. Motor stopped.");
      controlActive = false;
    }
  }

  delay(5); // ~200 Hz refresh
}
