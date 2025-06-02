# ModulIO
GPIO Controller Over Serial
  
This project enables user-friendly control of most GPIO devices over serial communications.

ModulIO has very wide applications, but was designed for general hobbyist and research uses.
The command and output format is designed to be easy to understand for humans, as well as easy to parse for computers.
It was designed such that each type of GPIO device added can be controlled and managed easily and reliably with the same set of basic commands.

## How to use the Python library
  The ModulIO Python library is where ModulIO really shines. It is designed to be imported into your own Python script, allowing device control to be completely automated according to your logic. The sky is the limit here.

  After importing the library:
  1) Connect serial using connect(). Specify your port (e.g. "COM5" if on Windows).
  2) Use change_data_stream_period function to set your desired time between data updates. Default is 5000 ms.
  3) Add your devices using create_device function.
  4) (optional) Enable recording to CSV with start_recording function.
  5) Read & write as needed with \[Device].get_value & \[Device].set_value functions.
  6) Before terminating your script, make sure to call disconnect(). If stop_recording() is not called, recording will be stopped on disconnect.

**With current algorithms, communication is known to be stable with no less than an average of 100ms between set_value callls. Sudden spikes in calls (ex: 5-10 calls with no delay in between) are fine as long as the average delay is still maintained around 100ms.**

## How to use the Arduino program
  Although the Python file offers more flexibility, you can also interact directly with the Arduino program by using a serial terminal such as PuTTY or the Arduino IDE. This mode allows more direct control over GPIO devices and the microcontroller's operations.

  The Serial Monitor tool in the Arduino IDE is recommended, but any serial console should work. If you use a Bluetooth module like the HC-05, there is an app on the Play Store called Arduino Bluetooth Control.
  1) Connect your Arduino to the serial terminal of your choosing. You should see its startup message once communication is active.
  2) Press "h" for a list of commands and their syntaxes.
  3) Use commands to set up your devices and control them as needed!

  Note: A key difference between the Arduino and Python programs is the way they address devices. The Python library addresses each device by name, while the Arduino addresses them by index. From the serial terminal, the index of each device can be viewed by entering "v".

## Creating Your Own Devices
  Generally, device addition is made easy by the repeatability of the code. Most of the work comes down to creating the Arduino class and linking it to the rest of the Arduino code. Once that is done, the Python setup should in most cases be quite straightforward.

  #### Step 1 - Creating the Struct in ModulIO.ino
    This is by far the most challenging step since the majority of device-specific logic is here. You can use the four included custom structs as examples.
   
    All structs follow the same basic format:
    1) A constructor to set variables native to the overarching Device struct.
    2) A static create() function to verify pins & ensure device can be created before doing so.
    3) A configure() function override to fill in substruct-specific variables & confirm creation.
    4) As needed, overrides for poll(), read(), or write() functions. Not all devices need all 3.
	    - Ex: Buttons may se poll() and read(), sensors may only use read(), and actuators may use read() and write().
	    - The poll() function is used by latched devices like buttons to update their internal state based on hardware input, allowing read() to return information about events that occurred asynchronously since the last call.
  
    Note that when an override is not defined, the functions under the generic Device class are run. This is fine because the generic functions are all empty
 
  #### Step 2 - Linking Struct to Rest of Code
    - Choose a single-letter character to represent your device.
    - In the SetupWiz function, add a call to your .create() method when your character is matched.
    - Optionally, add a line in help() to document your device. 

 #### Step 3 - Modifying ModulIO.py
    - Write a class of the same name as your struct. Most devices can simply inherit from Device without any more logic required.
    - In create_device, add the case with your single character to call your class constructor.
    - Also in create_device, add your device character to the type_map dictionary.

## Internal Code Documentation
  #### Baud Rate
  - Setting baud rate any lower than 115200 is currently EXPERIMENTAL and may not yield stable results.

  #### Delays
  - Serial timeout: Time to transmit 512 bytes at the configured baud rate (10 bits per char) plus a few ms margin. (at 115200 baud, this equals roughly 60ms)
  - Data stream period: Time interval between data stream transmissions. Minimum is serial timeout.
  - Idle wait delay: Should be around a quarter of data stream period, or less if a large period (>1s) is used.
  
  #### Terminology
  - Device: Refers to any GPIO device connected to pins on the Arduino.
  - Data stream: Refers not to the serial connection, but rather the communication of device statuses from the Arduino. Messages of this type start with the keyword "Data:".
