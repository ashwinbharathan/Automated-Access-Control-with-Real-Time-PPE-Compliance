#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Keypad.h>
#include <esp_sleep.h>

// --- OLED display setup ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// --- Pin assignments ---
#define RELAY_PIN 5
#define PIR_PIN   4

// --- Keypad setup ---
const byte ROWS = 4;
const byte COLS = 3;
char keys[ROWS][COLS] = {
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'},
  {'*','0','#'}
};

byte rowPins[ROWS] = {25, 26, 27, 32};  // Rows: R1–R4
byte colPins[COLS] = {33, 14, 12};      // Columns: C1–C3
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// --- Valid user IDs ---
String IDs[] = {"0001", "0002", "0003", "0004"};
String inputBuffer = "";

// --- Setup ---
void setup() {
  Serial.begin(115200);

  pinMode(RELAY_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  digitalWrite(RELAY_PIN, HIGH);  // Relay OFF (Active LOW)

  Wire.begin(21, 22);  // SDA, SCL
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED init failed");
    while (1);
  }

  displayStatus("System Ready");
}

// --- Loop ---
void loop() {
  gpio_wakeup_enable(GPIO_NUM_4, GPIO_INTR_HIGH_LEVEL);
  esp_sleep_enable_gpio_wakeup();

  displayStatus("Sleeping...");
  delay(100);
  esp_light_sleep_start();

  if (pirStatus()) {
    Serial.println("Motion detected!");
    IDInput();
    delay(2000);  // Cool down before next cycle
  }
}

// --- Check motion detected ---
bool pirStatus() {
  return digitalRead(PIR_PIN) == HIGH;
}

// --- Check if ID is valid ---
bool isValidID(String input) {
  int idCount = sizeof(IDs) / sizeof(IDs[0]);
  for (int i = 0; i < idCount; i++) {
    if (IDs[i] == input) {
      return true;
    }
  }
  return false;
}

// --- Call PC for helmet check ---
void callPC() {
  displayStatus("Checking helmet...");

  unsigned long start = millis();
  while (millis() - start < 10000) {  // Wait up to 10 seconds
    if (Serial.available()) {
      char result = Serial.read();  // Expect either '1' or '0'
      Serial.read(); // to consume '\n'
      if (result == '1') {
        displayStatus("Access Granted");
        digitalWrite(RELAY_PIN, LOW);   // Relay ON
        delay(3000);
        digitalWrite(RELAY_PIN, HIGH);  // Relay OFF
      } else {
        displayStatus("Helmet Missing");
        delay(3000);
        displayStatus("Access Denied!!!");
      }
      return;
    }
  }

  displayStatus("PC Timeout...");
  delay(2000);
}

// --- Handle keypad entry and authentication ---
void IDInput() {
  inputBuffer = "";
  displayStatus("Enter ID:");

  while (inputBuffer.length() < 4) {
    char key = keypad.getKey();
    if (key) {
      if (key == '*' || key == '#') {
        inputBuffer = "";
        displayStatus("Cleared");
      } else {
        inputBuffer += key;
        displayStatus("ID: " + inputBuffer);
      }
    }
  }

  if (isValidID(inputBuffer)) {
    Serial.println("ID_OK");
    callPC();  // Proceed to helmet detection
  } else {
    displayStatus("Invalid ID");
    Serial.println("Invalid ID: " + inputBuffer);
    delay(2000);
  }
}

// --- OLED Utility ---
void displayStatus(String msg) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(msg);
  display.display();
}
