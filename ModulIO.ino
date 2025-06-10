/* 
  ==================================================================================================
  ModulIO - Modular GPIO controller
  Version 1.0 June 9 2025
  Description: Runtime creation & control of I/O devices via serial commands
  ==================================================================================================

    This file, designed for an Arduino Uno R3, contains several functions accessible through a basic 
    command system via serial connection. 
    Its main purpose is to simplify GPIO device interactions such that all device interactions can 
    be generalized for easy management. Through serial interactions, devices can be controlled 
    manually, or control can be automated by the ModulIO Python library.

    https://github.com/lewertoff/ModulIO 

    See README for information on how to add your own customizable devices.

  ==================================================================================================
*/

////////////////////////////////////////////////////////////////////////////////////////////////////
// SETUP

#include "HX711.h"

struct Device {
    // Generic device class. Properties and methods herein are inherited by all device types.

    String type = "Generic"; // Override on subclasses based on device
    String name;
    int pin;

    Device(String n) : name(n) {
        /**
        * Device constructor.
        * Used by other structs to fill in variables inherited from generic struct.
        */
    }

    virtual ~Device() { 
        /**
        * Device destructor.
        */
    }

    virtual void configure() = 0;
        /**
        * Sets up GPIO pin & fills in struct-specific variables.
        * Confirms device creation by sending a message over serial.
        */
    
    virtual void poll() {
        /** 
        * Optional override.
        * Checks if an action was recorded since last read() call.
        *
        * @note Only needed for latched inputs like buttons that may otherwise be missed.
        *
        * The poll() function is used by latched devices like buttons to update their internal 
        * state based on hardware input, allowing read() to return information about events that 
        * occurred asynchronously since the last read() call.
        */ 
    }

    virtual String read() {
        /** 
        * Optional override.
        * 
        * @return The device's current status or recorded value.
        */
        return "";
    }

    virtual void write(String value) {
        /** 
        * Optional override.
        * Sets the device's value.
        *
        * @param value The value to set. Parse however needed from string.
        * @note If device is an actuator, set the value to be returned in read() here.
        * @note Conversion of value from input is done inside each device class to allow different data types.
        */
    } 
};

// If using Python, all these must match!
constexpr unsigned long serialBaudRate = 115200;
constexpr unsigned int serialTimeout = 60; // ms
constexpr unsigned int maxDevices = 10;

// ModulIO Configuration
bool userMode = true; // Who will be interacting with this program? true = user, False = Python script built with ModulIO.py.

// Hardware setup
constexpr int reservedPins[] = {0, 1}; // Tx and Rx
constexpr int resPinSize = 2; // Number of reserved pins
constexpr int highestPin = 13;

// Device setup
Device* devices[maxDevices];
int deviceCount = 0;

// Command parsing setup
constexpr int maxArgs = 10; // Max command length (ex. "s p p1 12 13" would be 5 args)
String cmdarr[maxArgs];

// Data stream setup
unsigned long dataStreamPeriod = 5000; // ms waited before next loop
bool dataStreamEnable = false; // Controls continuous sensor data output via serial
unsigned long msLastDataSent = 0; // ms

////////////////////////////////////////////////////////////////////////////////////////////////////
// HELPER FUNCTIONSs

bool isInArray(int value, const int* arr, int size) {
    /**
    * Helper function. Checks if an integer is in an array of integers.
    *
    * @param value The integer to check for.
    * @param arr The integer array to check.
    * @param size The number of integer elements in arr.
    * @return true if value is found in arr, false otherwise.
    */

    for (int i = 0; i < size; i++) {
        if (arr[i] == value) {
            return true;
        }
    }
    return false;
}

uint8_t computeCRC8(const char *data, size_t length) {
    uint8_t crc = 0x00;
    while (length--) {
        crc ^= *data++;
        for (uint8_t i = 0; i < 8; i++) {
            crc = (crc & 0x80) ? (crc << 1) ^ 0x07 : (crc << 1);
        }
    }
    return crc;
}

////////////////////////////////////////////////////////////////////////////////////////////////////
// CUSTOM DEVICE STRUCTS

struct ButtonDevice : public Device {
    // Standard pull-up button. Activated state = shorted to ground.

    int lastReading = HIGH;
    int lastStableState = HIGH;
    unsigned long lastDebounceTime = 0;
    const unsigned long debounceDelay = 50; // ms
    bool buttonPressed = false; // Tracks if press happened since last poll

    ButtonDevice(String n, int p) : Device(n) {
        /**
        * Fills in generic Device variables.
        * @brief ButtonDevice constructor.
        */

        type = "Button";
        pin = p;
    }

    static ButtonDevice* create(String n, int p) {
        /**
        * Performs validity check of args before creating button object.
        * @brief factory function for ButtonDevice. 
        *
        * @param n The name of the device.
        * @param p The pin number of the device.
        * @return pointer to a ButtonDevice object, or a nullptr if object is invalid.
        */

        // Make sure pins are valid
        if (isInArray(p, reservedPins, resPinSize) || p > highestPin || p < 0) {
            Serial.println(F("Errr: Invalid pins for button."));
            return nullptr;
        }

        return new ButtonDevice (n, p);
    }

    void configure() override {
        /**
        * Fills in button-specific variables & confirms creation.
        */

        pinMode(pin, INPUT_PULLUP);
        Serial.println("Conf: Button " + name + " configured on pin " + String(pin) + " (index " + String(deviceCount - 1) + ").");
        lastReading = digitalRead(pin);
        lastStableState = lastReading;
    }

    void poll() override {
        /**
        * Checks for button press & updates internal variables.
        * 
        * @note Essential to detect button presses between read() calls.
        */

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
        /**
        * Returns whether button was pressed.
        * 
        * @return 0 if not pressed, 1 if pressed; both as strings.
        */

        if (buttonPressed) {
            buttonPressed = false;
            return "1";
        } else {
            return "0";
        }
    }
};

struct PressureSensorDevice : public Device {
    // HX710B air pressure sensor with chinese writing on back of PCB. Purchased from Amazon. 
    // See https://www.edn.com/pressure-sensor-guide/

    int clockPin;
    long zeroOffset = 0;
    float scaleFactor = 1.0;
    HX711 scale;

    PressureSensorDevice(String n, int data, int clk) : Device(n), clockPin(clk) {
        /**
        * Fills in generic Device variables.
        * @brief PressureSensorDevice constructor.
        */

        type = "PressureSensor";
        pin = data; // Data pin
    }

    static PressureSensorDevice* create(String n, int data, int clk) {
        /**
        * Performs validity check of args before creating pressure sensor device.
        * @brief factory function for PressureSensorDevice. 
        *
        * @param n The name of the device.
        * @param data The pin number of the 'OUT' pin.
        * @param clk The pin number of the 'CLK' pin.
        * @return pointer to a PressureSensoDevice object, or a nullptr if object is invalid.
        */

        // Make sure pins are valid
        if (isInArray(data, reservedPins, resPinSize) || data > highestPin || data < 0
         || isInArray(clk, reservedPins, resPinSize) || clk > highestPin || clk < 0) {
            Serial.println(F("Errr: Invalid pins for pressure sensor."));
            return nullptr;
        }
        return new PressureSensorDevice (n, data, clk);
    }

    void configure() override {
        /**
        * Fills in pressure sensor specific variables & confirms creation.
        */

        scale.begin(pin, clockPin);
        Serial.println("Conf: Pressure sensor " + name + " configured on pins " 
        + String(pin) + " (data) & " + String(clockPin) + " (clock)" + " (index " + String(deviceCount - 1) + ").");
    }

    String read() override {
        /**
        * Returns raw pressure sensor value.
        * 
        * @return 0 if not ready, or raw received value, as a string.
        */

        if (scale.is_ready()) {
            return String(scale.read() * scaleFactor + zeroOffset);
        } else {
            return "0"; // if sensor is not ready
        }
    }
};

struct LEDDevice : public Device {
    // Standard LED. Connect positive (long leg) to pin. Remember to include a 220Ω resistor.

    int brightness = 0; // 0 to 256

    LEDDevice(String n, int p) : Device(n) {
        /**
        * Fills in generic Device variables.
        * @brief LEDDevice constructor.
        */

        type = "LED";
        pin = p;
    }

    static LEDDevice* create(String n, int p) {
        /**
        * Performs validity check of args before creating LED device.
        * @brief factory function for LEDDevice. 
        *
        * @param n The name of the device.
        * @param p The pin number of the device.
        * @return pointer to an LEDDevice object, or a nullptr if object is invalid.
        */

    // Make sure pins are valid
    if (isInArray(p, reservedPins, resPinSize) || p > highestPin || p < 0) {
        Serial.println(F("Errr: Invalid pins for LED."));
        return nullptr;
        }
    return new LEDDevice (n, p);
    }

    void configure() override {
        /**
        * Fills in LED-specific variables & confirms creation.
        */

        pinMode(pin, OUTPUT);
        analogWrite(pin, brightness);
        Serial.println("Conf: LED " + name + " configured on pin " + String(pin) + " (index " + String(deviceCount - 1) + ").");
    }

    void write(String value) override {
        /**
        * Sets LED's brightness to given value.
        *
        * @param value The brightness level to set, as a string. Values are constrained (0-255).
        */

        brightness = constrain(value.toInt(), 0, 255);
        analogWrite(pin, brightness);
    }

    String read() override {
        /**
        * Returns LED's set brightness.
        * 
        * @return LED's brightness (0-255) converted to a string.
        */

        return String(brightness);
    }
};

struct DCMotorDevice : public Device {
    // Standard DC motor. DO NOT PLUG DIRECTLY INTO UNO! Need MOSFET or motor driver module.

    int speed = 0;

    DCMotorDevice(String n, int p) : Device(n) {
        /**
        * Fills in generic Device variables.
        * @brief DCMotorDevice constructor.
        */

        type = "DCMotor";
        pin = p;
    }

    static DCMotorDevice* create(String n, int p) {
        /**
        * Performs validity check of args before creating motor device.
        * @brief factory function for DCMotorDevice. 
        *
        * @param n The name of the device.
        * @param p The pin number of the device.
        * @return pointer to an DCMotorDevice object, or a nullptr if object is invalid.
        */

        // Make sure pins are valid
        if (isInArray(p, reservedPins, resPinSize) || p > highestPin || p < 0) {
            Serial.println(F("Errr: Invalid pins for motor."));
            return nullptr;
        }   
        return new DCMotorDevice (n, p);
    }

    void configure() override {
        /**
        * Fills in motor-specific variables & confirms creation.
        */

        pinMode(pin, OUTPUT);
        analogWrite(pin, speed);
        Serial.println("Conf: DC motor " + name + " configured on pin " + String(pin) + " (index " + String(deviceCount - 1) + ").");
    }

    void write(String value) override {
        /**
        * Sets motor's speed to given value.
        *
        * @param value The speed to set, as a string. Values are constrained (0-255).
        */

        speed = constrain(value.toInt(), 0, 255);
        analogWrite(pin, speed);
    }

    String read() override {
        /**
        * Returns motor's set speed.
        * 
        * @return Motor's speed (0-255) converted to a string.
        */

        return String(speed);
    }
};

////////////////////////////////////////////////////////////////////////////////////////////////////
// FUNCTIONS

void setup() {
    /**
    * Begins serial communication & sends intro message.
    */
    Serial.begin(serialBaudRate);
    Serial.setTimeout(serialTimeout);
    Serial.println(F("ModulIO v1.0 - Modular GPIO controller ready. Enter 'h' for help."));
}

void loop() {

    // Polling - To update latched-input devices like buttons
    for (int i = 0; i < deviceCount; i++) {
        devices[i]->poll();  // Only meaningful for devices where poll() is defined
    }

    // Data stream - To report device data through serial
    if (dataStreamEnable) {
        unsigned long msNow = millis();

        // If enough time has passed, send data out
        if (msNow - msLastDataSent >= dataStreamPeriod) { 
            sendData();
            msLastDataSent = msNow; // Set 
        }
    } 

    // Check for incoming commands
    if (Serial.available()) {
        int arrlen = getCmd(cmdarr); // Fill command array & count tokens
        if (arrlen > 0) {

            switch (cmdarr[0].charAt(0)) { // Switch based on first token

                case 'c': // Control device
                    if (arrlen < 3) {
                        Serial.println(F("Warn: Not enough arguments for \"c\" command."));
                        break;
                    }
                    controlDevice(cmdarr[1].toInt(), cmdarr[2]);
                    break;

                case 'h': // Help - list commands
                    help();
                    break;
                
                case 'i': // Info - Name, version, & repo link
                    info();
                    break;

                case 'r': // Remove device
                    removeDevice(cmdarr[1].toInt());
                    break;
                
                case 's': // Setup device
                    setupWiz(cmdarr);
                    break;

                case 't': // Data stream toggle
                    if (arrlen < 2) {
                            Serial.println(F("Warn: Not enough arguments for \"t\" command."));
                            break;
                    }   
                    dataStreamSwitch(bool(cmdarr[1].toInt()));
                    break;
                
                case 'u': // Update data output period
                    if (arrlen < 2) {
                            Serial.println(F("Warn: Not enough arguments for \"u\" command."));
                            break;
                    }
                    changeDataStreamPeriod(cmdarr[1].toInt());
                    break;

                case 'v': // View devices
                    viewDevices();
                    break;

                case 'z': // User mode toggle
                    if (arrlen < 2) {
                        Serial.println(F("Warn: Not enough arguments for \"z\" command."));
                        break;
                    }
                    userModeSwitch(bool(cmdarr[1].toInt()));
                    break;

                default:
                    Serial.println(F("Warn: Command selection invalid. Enter h for help."));

            }
        }
    }

}

int getCmd(String out[]) {
    /**
    * Fills command array (cmdarr) while counting tokens. If Python sent command, verifies checksum & rejects command if bad.
    * @brief Parses incoming serial commands into tokens while verifying data integrity.
    *
    * @param out[] The global array to fill with tokens.
    * @return The number of tokens in the array, or 0 if data verification failed.
    * @note This function assumes serial.available() is true when called.
    * @note If more than [maxArgs] tokens are received, the last index in the array receives the unparsed portion of the command.
    */

    // Sanitize array before filling it again
    for (int i = 0; i < maxArgs; i ++) {
        out[i] = "";
    }

    String msg = Serial.readStringUntil('\n');
    msg.trim(); // Remove leading or trailing whitespace

    if (!userMode) { // If Python is sending command

        // Character length check
        if (msg.length() > 128) {
            Serial.println("Recv: <too long>; BAD");
            return 0;
        }

        // Ensure msg is properly formatted
        int sepIndex = msg.indexOf(';');
        if (sepIndex == -1) { // If no seperator was found
            Serial.println("Recv: <no seperator>; BAD");
            return 0;
        }

        // Separate Python checksum from command
        String checksumStr = msg.substring(0, sepIndex);
        msg = msg.substring(sepIndex + 1);
        msg.trim();

        // Compute & compare checksums
        uint8_t receivedCRC = strtoul(checksumStr.c_str(), nullptr, 16); // Parse hex
        uint8_t computedCRC = computeCRC8(msg.c_str(), msg.length());

        if (computedCRC != receivedCRC) { // If no match, send fail message & disregard command
            Serial.println("Recv: " + String(computedCRC) + "; BAD");
            return 0; 
        } 

        // If CRCs match, confirm & continue parsing msg
        Serial.println("Recv: " + checksumStr + "; OK");
    }

    // Parse command into tokens based on spaces
    int i = 0;
    while (msg.indexOf(' ') != -1 && i < maxArgs - 1) {

        int idx = msg.indexOf(' '); // Position of next space

        out[i++] = msg.substring(0, idx);
        msg = msg.substring(idx + 1);
    }
    out[i] = msg; // Store last token or remaining unparsed command
    return i + 1; // Return array length
}

void setupWiz(String* sel) {
    /**
    * Handles setting up new devices.
    * This logic would be under case 's' in loop() but is split into a separate function for memory efficiency.
    *
    * @param sel The entire command array as constructed by getCmd().
    */

    if (deviceCount >= maxDevices) {
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
    /**
    * Configures a device and adds it to the devices array.
    *
    * @param d The device to configure.
    * @note This function assumes it is able to create a device (must be checked by whatever calls it).
    */

    devices[deviceCount++] = d;
    d->configure();
}

void viewDevices() {
    /**
    * Prints a list of device indexes, names, pins, and types to serial.
    */
    
    Serial.println(F("====CONNECTED DEVICES===="));
    for (int i = 0; i < deviceCount; i++) {
        Serial.println(String(i) + ": " + devices[i]->type + " " + devices[i]->name + " on pin " + devices[i]->pin);
    }
}

void removeDevice(int index) {
    /**
    * Deletes the device at the specified index in the devices array.
    *
    * @param index the index of device to remove.
    * @note use viewDevices() to determine index.
    */

    if (index < 0 || index >= deviceCount) {
        Serial.println(F("Errr: Invalid device index."));
        return;
    }

    // Ensure device is turned off before deleting it
    devices[index]->write("0"); 

    // for confirmation purposes after deletion
    String name = devices[index]->name;
    String type = devices[index]->type;

    delete devices[index]; // Delete device - free up memory

    // Shift device indexes after removed one
    int i;
    for (i = index; i < deviceCount - 1; i++) {
        devices[i] = devices[i + 1]; // Move POINTERS to objects down
    }
    devices[i] = nullptr; // Remove last pointer

    deviceCount--;

    Serial.println("Conf: " + type + " " + name + " successfully deleted.");
}

void controlDevice(int index, String value) {
    /**
    * Writes the given value to the given GPIO device.
    * 
    * @param index The index of the device to control.
    * @param value The value to write to the device.
    */
    
    if (index < 0 || index >= deviceCount) {
        Serial.println(F("Errr: Invalid device index."));
    } else {
        devices[index]->write(value);
    }
}

void sendData() {
    /**
    * Prints a list of device names and their current readings/statuses to serial.
    * This function is essential for the serial data stream.
    */
    
    String out = "Data:";

    for (int i = 0; i < deviceCount; i++) {
        out += " " + devices[i]->name + " ";
        out += devices[i]->read();  // Only meaningful for inputs like buttons/sensors. read() returns nothing otherwise
    }
    Serial.println(out + ";"); // semi-colon to indicate end of data
}

void dataStreamSwitch(bool enable) {
    /**
    * Enables or disables the serial data stream. Confirms the change via serial.
    *
    * @param enable true to enable, false to disable.
    */
    dataStreamEnable = enable;
    if (enable) Serial.println(F("Conf: Data stream enabled."));
    else Serial.println(F("Conf: Data stream disabled."));
}

void changeDataStreamPeriod(int newPeriod) {
    /**
    * Changes the period of sensor data output. Confirms the change via serial.
    *
    * @param newPeriod The new data stream period in ms.
    */

    if (newPeriod < 1) {
        Serial.println(F("Errr: Period must be at least 1 ms."));
    } else {
        dataStreamPeriod = newPeriod;
        Serial.println("Conf: Data stream period changed to " + String(dataStreamPeriod) + " ms.");
    }
}

void userModeSwitch(bool enable) {
    /**
    * Enables or disables user mode. Confirms the change via serial.
    *
    * @param enable true to enable, false to disable.
    * @note User mode is intended for human interaction with the program, via serial commands.
    *       When disabled, the program assumes it is being controlled by the ModulIO Python library.
    */
    
    userMode = enable;
    if (enable) Serial.println(F("Conf: userMode enabled."));
    else Serial.println(F("Conf: userMode disabled."));
}

void help() {
    /** 
    * Displays available commands & syntaxes for user guidance.
    */

    if (userMode) {
        Serial.println(F("====AVAILABLE FUNCTIONS===="));
        Serial.println(F("h - Help"));
        Serial.println(F("i - Info"));
        Serial.println();
        Serial.println(F("c - Control device (c [index] [new value])"));
        Serial.println(F("r - Remove device (r [index])"));
        Serial.println(F("s - Set up device"));
        Serial.println(F("\tb - Button (s b [name] [pin])"));
        Serial.println(F("\tl - LED (s l [name] [pin]) - positive pin"));
        Serial.println(F("\tm - DC motor (s m [name] [pin])"));
        Serial.println(F("\tp - Pressure sensor (s p [name] [data pin] [clock pin])"));
        Serial.println(F("v - View devices & their indexes"));
        Serial.println();
        Serial.println(F("t - Enable or disable serial data stream (t [0 or 1])"));
        Serial.println(F("u - Change data output period (u [ms period])"));
        Serial.println(F("\t   (Default: 5000 ms, no lower than 1 accepted)"));
        Serial.println(F("z - Toggle user mode (z [0 or 1])"));
        Serial.println(F("\t   (Only intended to be used by Python script. Don't touch unless you know what you're doing)"));
    }
}

void info() {
    /** 
    Displays program title, brief description, version, & repo link.
    */
        if (userMode) {
        Serial.println(F("====ModulIO - Version 1.0===="));
        Serial.println(F("Simplified control of GPIO devices via serial commands"));
        Serial.println(F("Get the associated Python library!:"));
        Serial.println(F("https://github.com/lewertoff/ModulIO"));
        Serial.println(F("More info available in README.md"));
    }
}