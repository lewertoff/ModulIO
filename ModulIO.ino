/* 
  ================================================
  ModulIO - Modular GPIO controller
  Version 0.02 May 22
  Description: Runtime creation & control of I/O devices via serial commands
  ================================================
*/

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// SETUP

#include "HX711.h"

struct Device {
    // Generic device class. Properties and methods herein are inherited by all device types.

    String type = "Generic"; // Override on subclasses based on device
    String name;
    int pin;

    Device(String n) : name(n) {} 

    virtual ~Device() {}

    virtual void configure() = 0; // Pure virtual method

    virtual void poll() {
        // Optional override
        // On real-time inputs like buttons, checks if an action was recorded since last read() call.
    }

    virtual String read() {
        // Optional override
        // Returns device's current status or recorded value.
        return "";
    }

    virtual void write(String value) {
        // Optional override
        // In individual functions, parse/interpret value according to device needs.
        // Analog writes: Non-PWM pins are limited to LOW (0-127) or HIGH (128-255)
        // Conversion of value from input is done inside the class to allow different data types.
    } 
};


// Device setup parameters
const int MAX_DEVICES = 10;
Device* devices[MAX_DEVICES];
int deviceCount = 0;

// Hardware parameters
const int reservedPins[] = {0, 1}; // Tx and Rx
const int resPinSize = 2; // Number of reserved pins
const int highestPin = 13;

// Command parsing parameters
const int MAX_ARGS = 10; // Max command length (ex. "s p p1 12 13" would be 5 args)
String cmdarr[MAX_ARGS];

// Sensor loop parameters
bool sensorSpam = false; // Controls continuous sensor data output via serial
unsigned long msLastExecution = 0; // millis
unsigned long sensorPeriod = 100; // ms waited before next loop

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// HELPER FUNCTIONS

bool isInArray(int value, const int* arr, int size) {
    for (int i = 0; i < size; i++) {
        if (arr[i] == value) {
            return true;
        }
    }
    return false;
}

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// DEVICE STRUCTS

struct ButtonDevice : public Device {
    // Standard pull-up button. Activated state = shorted to ground.

    int lastReading = HIGH;
    int lastStableState = HIGH;
    unsigned long lastDebounceTime = 0;
    const unsigned long debounceDelay = 50; // ms
    bool buttonPressed = false; // Tracks if press happened since last poll

    ButtonDevice(String n, int p) : Device(n) {
        type = "Button";
        pin = p;
    }

    static ButtonDevice* create(String n, int p) {
        // Performs validity check of args before creating object. Returns a nullptr if object invalid.

        if (isInArray(p, reservedPins, resPinSize) || p > highestPin || p < 0) {
            Serial.println(F("Errr: Invalid pins for button."));
            return nullptr;
        }
        return new ButtonDevice (n, p);
    }

    void configure() override {
        pinMode(pin, INPUT_PULLUP);
        Serial.println("Conf: Button " + name + " configured on pin " + String(pin) + " (index " + String(deviceCount - 1) + ").");
        lastReading = digitalRead(pin);
        lastStableState = lastReading;
    }

    void poll() override {
        // Essential to detect button presses outside of calls to read().

        int reading = digitalRead(pin);
        if (reading != lastStableState) { // If reading has changed
            lastDebounceTime = millis(); // Reset debounce timer
        }
        
        if ((millis() - lastDebounceTime) > debounceDelay) { // If button is pressed for long enough
            if (reading != lastReading) { // If state changed in that time
                lastReading = reading;
            
                if (lastReading == LOW) {
                    buttonPressed = true; // Indicates button press
                }
            }
        }
        lastStableState = reading;
    }

    String read() override {
        if (buttonPressed) {
            buttonPressed = false;
            return "1";
        } else {
            return "0";
        }
    }
};

struct PressureSensorDevice : public Device {
    // HX710B air pressure sensor with Chinese writing from Amazon.

    int clockPin;
    long zeroOffset = 0;
    float scaleFactor = 1.0;
    HX711 scale;

    PressureSensorDevice(String n, int data, int clk) : Device(n), clockPin(clk) {
        type = "PressureSensor";
        pin = data; // Data pin
    }

    static PressureSensorDevice* create(String n, int data, int clk) {
        // Performs validity check of args before creating object. Returns a nullptr if object invalid.

        if (isInArray(data, reservedPins, resPinSize) || data > highestPin || data < 0
         || isInArray(clk, reservedPins, resPinSize) || clk > highestPin || clk < 0) {
            Serial.println(F("Errr: Invalid pins for pressure sensor."));
            return nullptr;
        }
        return new PressureSensorDevice (n, data, clk);
    }

    void configure() override {
        scale.begin(pin, clockPin);
        Serial.println("Conf: Pressure sensor " + name + " configured on pins " 
        + String(pin) + " (data) & " + String(clockPin) + " (clock)" + " (index " + String(deviceCount - 1) + ").");
    }

    String read() override {
        // Returns raw pressure sensor value.

        if (scale.is_ready()) {
            return String(scale.read());
        } else {
            return "0"; // if sensor is not ready
        }
    }
};

struct LEDDevice : public Device {
    // Standard LED. Connect positive (long leg) to pin. Remember to include a 220Ω resistor.

    int brightness = 0; // 0 to 256

    LEDDevice(String n, int p) : Device(n) {
        type = "LED";
        pin = p;
    }

    static LEDDevice* create(String n, int p) {
    // Performs validity check of args before creating object. Returns a nullptr if object invalid.

    if (isInArray(p, reservedPins, resPinSize) || p > highestPin || p < 0) {
        Serial.println(F("Errr: Invalid pins for LED."));
        return nullptr;
        }
    return new LEDDevice (n, p);
    }

    void configure() override {
        pinMode(pin, OUTPUT);
        analogWrite(pin, brightness);
        Serial.println("Conf: LED " + name + " configured on pin " + String(pin) + " (index " + String(deviceCount - 1) + ").");
    }

    void write(String value) override {
        brightness = constrain(value.toInt(), 0, 255);
        analogWrite(pin, brightness);
    }

    String read() override {
        return String(brightness);
    }
};

struct DCMotorDevice : public Device {
    // Standard DC motor. DO NOT PLUG DIRECTLY INTO UNO! Need MOSFET or motor driver module.

    int speed = 0;

    DCMotorDevice(String n, int p) : Device(n) {
        type = "DCMotor";
        pin = p;
    }

    static DCMotorDevice* create(String n, int p) {
    // Performs validity check of args before creating object. Returns a nullptr if object invalid.

        if (isInArray(p, reservedPins, resPinSize) || p > highestPin || p < 0) {
            Serial.println(F("Errr: Invalid pins for motor."));
            return nullptr;
        }   
        return new DCMotorDevice (n, p);
    }

    void configure() override {
        pinMode(pin, OUTPUT);
        analogWrite(pin, speed);
        Serial.println("Conf: DC motor " + name + " configured on pin " + String(pin) + " (index " + String(deviceCount - 1) + ").");
    }

    void write(String value) override {
        speed = constrain(value.toInt(), 0, 255);
        analogWrite(pin, speed);
    }

    String read() override {
        return String(speed);
    }
};

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// MAIN SCRIPT

void setup() {
    // Begin serial comms.
    Serial.begin(115200);
    Serial.setTimeout(10);
}

void loop() {

    // Polling loop - for certain devices that need continuous polling
    for (int i = 0; i < deviceCount; i++) {
        devices[i]->poll();  // Only meaningful for devices where poll() is defined
    }

    // Serial output loop - to report device data through serial
    if (sensorSpam) {
        unsigned long msNow = millis();
        if (msNow - msLastExecution >= sensorPeriod) { // If enough time has passed, proceed w/ sensor loop
            sendData();
            msLastExecution = msNow; // Set 
        }
    } 

    // Prompted functions
    if (Serial.available()) {
        int arrlen = getCmd(cmdarr); // Fill command array & count values
        if (arrlen > 0) {

            switch (cmdarr[0].charAt(0)) {

                case 'c': // Control device
                    controlDevice(cmdarr[1].toInt(), cmdarr[2]);
                    break;

                case 'h': // Help - list commands
                    help();
                    break;
                
                case 'r': // Remove device
                    removeDevice(cmdarr[1].toInt());
                    break;
                
                case 's': // Setup device
                    setupWiz(cmdarr);
                    break;

                case 't': // Toggle data output
                    sensorSpam = !sensorSpam;
                    break;
                
                case 'u': // Update data output period
                    changeSensorPeriod(cmdarr[1].toInt());
                    break;

                case 'v': // View devices
                    viewDevices();
                    break;

                default:
                    Serial.println(F("Errr: Command selection invalid. Enter h for help."));

            }
        }
    }

}

int getCmd(String out[]) {
    // Assumes that Serial.available() is true.
    // Receives command from serial bitstream & adds it to cmd array. Sends it back to confirm.
    // Returns number of tokens parsed.
    // Additional invalid args are all put into last index.

    // Sanitize array before filling it again
    for (int i = 0; i < MAX_ARGS; i ++) {
        out[i] = "";
    }

    String command = Serial.readStringUntil('\n');
    command.trim(); // Remove leading or trailing whitespace
    Serial.print(F("Recv:"));
    int i = 0; // Counts number of entries into the cmd array

    while (command.indexOf(' ') != -1 && i < MAX_ARGS - 1) {
        int idx = command.indexOf(' '); // Position of next space
        out[i] = command.substring(0, idx);
        command = command.substring(idx + 1);
        Serial.print(" " + out[i++]); // Print out token and increase i
    }
    out[i] = command; // Store last token
    Serial.println(" " + command + "; length " + String(i + 1)); // Print out last token & length

    return i + 1; // Return array length
}

void setupWiz(String* sel) {
    // Handles setting up new devices.
    // Acts as a sub-menu of the main command list.

    if (deviceCount >= MAX_DEVICES) {
        Serial.println(F("Errr: Device limit reached."));
        return;
    }

    Device* d = nullptr;

    switch (sel[1].charAt(0)) {

        case 'b': // Button
            d = ButtonDevice::create(sel[2], sel[3].toInt());
            if (d != nullptr) {
                setupDevice(d);
            }
            break;

        case 'l': // LED
            d = LEDDevice::create(sel[2], sel[3].toInt());
            if (d != nullptr) {
                setupDevice(d);
            }
            break;

        case 'm': // Motor
            d = DCMotorDevice::create(sel[2], sel[3].toInt());
            if (d != nullptr) {
                setupDevice(d);
            }
            break;

        case 'p': // Pressure sensor
            d = PressureSensorDevice::create(sel[2], sel[3].toInt(), sel[4].toInt());
            if (d != nullptr) {
                setupDevice(d);
            }
            break;

        default:
            Serial.println(F("Errr: Device selection invalid."));
    }
}

void setupDevice(Device* d) {
    // Sets up device according to specified parameters and adds it to the devices array.
    if (deviceCount < MAX_DEVICES) {
        devices[deviceCount++] = d;
        d->configure();
    } else {
        Serial.println(F("Errr: Too many devices."));
    }
}

void viewDevices() {
    // Prints a list of device indexes, names, pins, and types.
    Serial.println(F("====CONNECTED DEVICES===="));
    for (int i = 0; i < deviceCount; i++) {
        Serial.println(String(i) + ": " + devices[i]->type + " " + devices[i]->name + " on pin " + devices[i]->pin);
    }
}

void removeDevice(int index) {
    // Deletes device at the specified index in the devices array.

    if (index < 0 || index >= deviceCount) {
        Serial.println(F("Errr: Invalid device index."));
        return;
    }

    // for confirmation purposes later
    String name = devices[index]->name;
    String type = devices[index]->type;

    delete devices[index]; // Free up memory

    // Shift remaining devices down
    int i;
    for (i = index; i < deviceCount - 1; i++) {
        devices[i] = devices[i + 1]; // Move POINTERS to objects down
    }
    devices[i] = nullptr; // Remove last pointer

    deviceCount--;

    Serial.println("Conf: " + type + " " + name + " successfully deleted.");
}

void controlDevice(int index, String value) {
    if (index < 0 || index >= deviceCount) {
        Serial.println(F("Errr: Invalid device index."));
    } else {
        devices[index]->write(value);
    }
}

void sendData() {
    // Prints a list of device names and their current readings/statuses to serial.
    String out = "Data:";

    for (int i = 0; i < deviceCount; i++) {
        out += " " + devices[i]->name + " ";
        out += devices[i]->read();  // Only meaningful for inputs like buttons/sensors. read() returns nothing otherwise
    }
    Serial.println(out + ";"); // semi-colon to indicate end of data
}

void changeSensorPeriod(int newPeriod) {
    // Changes the period of sensor data output.
    if (newPeriod < 1) {
        Serial.println(F("Errr: Period must be at least 1 ms."));
    } else {
        sensorPeriod = newPeriod;
        Serial.println("Conf: Sensor data output period changed to " + String(sensorPeriod) + " ms.");
    }
}

void help() {
    // For user guidance.
    Serial.println(F("====AVAILABLE FUNCTIONS===="));
    Serial.println(F("h - Help"));
    Serial.println(F("s - Set up device"));
    Serial.println(F("\tb - Button (s b [name] [pin])"));
    Serial.println(F("\tl - LED (s l [name] [pin]) - positive pin"));
    Serial.println(F("\tm - DC motor (s m [name] [pin])"));
    Serial.println(F("\tp - Pressure sensor (s p [name] [data pin] [clock pin])"));
    Serial.println(F("t - Toggle serial data output spam (t [period])"));
    Serial.println(F("u - Change data output period (u [period])"));
    Serial.println(F("\t   ("Default: 100 ms, no lower than 1 accepted)"));
    Serial.println(F("v - View devices & their indexes"));
    Serial.println(F("r - Remove device (r [index])"));
    Serial.println(F("c - Control device (c [index] [new value])"));
}