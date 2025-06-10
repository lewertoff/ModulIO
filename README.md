# 🔌 ModulIO

**GPIO Controller Over Serial — Python & Arduino**

User-friendly, programmable control of GPIO devices over serial, with automatic logging and CRC-safe messaging.

## 📚 Table of Contents
- [Introduction](#introduction)
- [Using the Python Library](#using-the-python-library)
- [Using the Arduino Program](#using-the-arduino-program)
- [Creating Your Own Devices](#creating-your-own-devices)
- [Internal Code Documentation](#internal-code-documentation)

## Introduction

**ModulIO takes care of all the intricacies of each specific type of GPIO device. It simplifies device interactions into just a few basic commands, so your code can remain concise and straightforward.**

ModulIO has very wide applications, but was designed for general hobbyist and research uses.

The basic principle behind ModulIO's design is universalized device control. No matter what GPIO device types you need for your project, you can manage, control, and read using the same core commands. (Each device is created as an object which inherits from ModulIO's generic Device class.)

Thank you for checking out ModulIO! Suggestions and contributions are always welcome.

## Using the Python Library
  The ModulIO Python library is where ModulIO really shines. It is designed to be imported into your own Python script, allowing device control to be completely automated according to your logic. The sky is the limit here.

  After importing the library:
  1) Connect serial using `connect` function. Specify your port (ex: "COM5" if on Windows).
  2) Use `change_data_stream_period` function to set your desired time between data updates. Default is 5000 ms.
  3) Add your devices using `create_device` function.
  4) (optional) Enable recording to CSV with `start_recording` function.
  5) Read and write as needed with `[Device].get_value` and `[Device].set_value` functions.
  6) Before terminating your script, make sure to call `disconnect()`. If `stop_recording()` is not called, recording will be stopped on disconnect.

  **With current algorithms, communication is known to be stable with no less than an average of 100ms between `set_value` calls. Sudden spikes in calls (ex: 5-10 calls with no delay in between) are fine as long as the average delay is still maintained around 100ms.**

  #### Python Library - Example Usage
  ```Python
  import ModulIO                         # Required import

  connect("COM5")                        # Attempts to connect to port "COM5" and start comms
  led = create_device("l", "LED1", [3])    # Creates LED device named "LED1" on pin 3
  led.set_value(255)                     # Sets LED to full brightness

  time.sleep(10)     

  disconnect()                           # Removes all devices & closes serial comms                  
  ```

## Using the Arduino Program
  Although the Python file offers more flexibility, you can also interact directly with the Arduino program by using a serial terminal such as PuTTY or the Arduino IDE. This mode allows more direct control over GPIO devices and the microcontroller's operations.

  The Serial Monitor tool in the Arduino IDE is recommended, but any serial console should work. If you use a Bluetooth module like the HC-05, there is an app on the Play Store called Arduino Bluetooth Control.
  1) Connect your Arduino to the serial terminal of your choosing. You should see its startup message once communication is active.
  2) Enter `h` for a list of commands and their syntaxes.
  3) Use commands to set up your devices and control them as needed.

  Note: A key difference between the Arduino and Python programs is the way they address devices. The Python library addresses each device by name, while the Arduino addresses them by index. From the serial terminal, the index of each device can be viewed by entering `v`.

## Creating Your Own Devices
  Generally, device addition is made easy by the repeatability of the code. Most of the work comes down to creating the Arduino class and linking it to the rest of the Arduino code. Once that is done, the Python setup should in most cases be quite straightforward.

  #### Step 1 - Creating the Struct in ModulIO.ino
  This is by far the most challenging step since the majority of device-specific logic is here. You can use the four included custom structs as examples.
   
  All structs follow the same basic format:
  1) A constructor to set variables native to the overarching Device struct.
  2) A **static** `create()` function to verify pins and ensure device can be created before doing so.
  3) A `configure()` function override to fill in substruct-specific variables and confirm creation.
  4) As needed, overrides for `poll()`, `read()`, or `write()` functions. Not all devices need all 3 - for example, buttons may use `poll()` and `read()`, sensors may only use `read()`, and actuators may use `read()` and `write()`. More info below.

  The `poll()` function is used by latched devices like buttons to update their internal state based on hardware input, allowing `read()` to return information about events that occurred asynchronously since the last call.
  Note that when an override is not defined, the functions under the generic Device class are run. This is fine because the generic functions are all empty.
 
  #### Step 2 - Linking Struct to Rest of Code
  - Choose a single-letter character to represent your device. It must not be used already!
  - In the `SetupWiz` function, add a call to your `.create()` method when your character is matched.
  - Optionally, add a line in `help()` to document your device. 

  #### Step 3 - Modifying ModulIO.py
  - Write a class of the same name as your struct. Most devices can simply inherit from Device without any more logic required. Depending on your use case, you may want to overwrite `get_value()` to cast the value to a more fitting type.
  - In `create_device`, add the case with your single character to call your class constructor.
  - Also in `create_device`, add your device character to the `type_map` dictionary.

## Internal Code Documentation
  This section documents important information to keep in mind for anyone wanting to contribute to ModulIO. **Work in progress!** Updated regularly. Feel free to ask if the information you are looking for is not listed here yet.

  #### Terminology
  - Device: Refers to any GPIO device connected to pins on the Arduino.
  - Data stream: Refers not to the serial connection, but rather the communication of device statuses from the Arduino. Messages of this type start with the keyword "Data:".

  #### Baud Rate
  - Setting a baud rate other than 115200 is currently EXPERIMENTAL and may not yield stable results.

  #### Serial Communication - Sending Queues
  - Normal send queue - Use for bulk messages (ex: controlling devices repeatedly, like blinking an LED).
  - Priority send queue - Use for system-critical messages (ex: setting up or removing devices). Messages in this queue are verified with CRC-8 checksums AS WELL AS confirmation from Arduino that the action took place (more details on how this works below). Do not use for controlling devices (commands starting with keyword "c"). 

  #### Serial Communication - Data Validation
  - Messages are split into two main types: data stream messages and command messages.
  - Data stream messages sent by Arduino are not validated for integrity; only checked for completeness. If Python finds that the "Data:" message has an incorrect number of "words" (groups of chars separated by spaces) it rejects the data and waits for the next.
  - Python sends commands to Arduino with more data integrity. When Python connects to Arduino, it sets userMode bool on Arduino to false. This signals to Arduino that it should also perform higher-order validation. Following are the major steps taken in order.

  1. Each command Python sends out is preceded by a hexadecimal CRC-8 checksum of the rest of the message.
  2. Arduino receives the message, computes the checksum itself, and compares the two. If comparison matches, Arduino sends back a confirmation before parsing the command. Else, it sends back the checksum it calculated.
  3. If Python receives the confirmation, Python sends the next message or waits for confirmation that the action took place, depending on the send queue the message was in. If confirmation is not reached, Python requeues the message for sending again later.

  Note: Currently, unconfirmed high-priority messages will only add a critical log message. If system states do not match between Python and Arduino (ex: an extra device on the Arduino side), unexpected behaviour will probably occur.


  
