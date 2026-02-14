#include <Arduino.h>

#define LED_PIN   2
#define PWM_PIN   4

int pwmTarget = 0;
int pwmCurrent = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  ledcAttach(PWM_PIN, 20000, 10);
  
  Serial.println("ESP32 Ready");
}

void loop() {
  processSerial();
  
  // 平滑PWM
  if (pwmCurrent != pwmTarget) {
    int step = (pwmTarget - pwmCurrent) / 4;
    if (step == 0) step = (pwmTarget > pwmCurrent) ? 1 : -1;
    pwmCurrent += step;
    ledcWrite(PWM_PIN, pwmCurrent);
    delay(2);
  } else {
    delay(1);
  }
}

void processSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    
    // PWM命令: Pxxxx
    if (c == 'P') {
      String num = "";
      for (int i = 0; i < 4 && Serial.available(); i++) {
        num += (char)Serial.read();
      }
      pwmTarget = constrain(num.toInt(), 0, 1000);
      Serial.print("PWM->");
      Serial.println(pwmTarget);
    }
    else {
      switch(c) {
        case 'A': digitalWrite(LED_PIN, HIGH); Serial.println("LED ON"); break;
        case 'a': digitalWrite(LED_PIN, LOW);  Serial.println("LED OFF"); break;
        case 'B': digitalWrite(4, HIGH); break;
        case 'b': digitalWrite(4, LOW);  break;
        case 'R': Serial.print("ADC="); Serial.println(analogRead(34)); break;
      }
    }
  }
}