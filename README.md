# ModulIO
  ModulIO - GPIO Controller Over Serial

  Description:
  This project enables user-friendly control of most GPIO devices over serial communications.
  ModulIO has very wide applications, but was designed for general hobbyist and research uses.
  The command and output format is designed to be easy to understand for humans, as well as easy to parse for computers.
  Every type of device inherits from the same generic Device class, allowing each GPIO device to be managed the same way.

### How to use the Python library
  The Python library offers a more computer-friendly way to use ModulIO. It is designed to be imported into your own Python script, or used as-is depending on your needs.
  1) Assign your port to SERIAL_PORT constant.
  2) Connect serial using connect()
  3) Add devices using create_device()
  4) (optional) Enable recording to CSV with start_recording()
  5) Read & write as needed with [Device].read() & [Device].write()

### How to use the Arduino code
  Although the Python file is more flexible, you can also talk directly to the Arduino using a serial terminal. This alows more direct control over the devices and the microcontroller's operations.
  The Serial Monitor tool in the Arduino IDE is recommended, but any should work.
  1) Press "h" for a list of commands syntaxes.
  2) Use commands to set up your devices and control them as needed.
  Note: The Arduino program uses indexes to control and manage devices while the Python code uses their assigned names. The index of a device is shown after it is set up. The indexes of all devices can be viewed with "v".
  
  
### How to add your own devices
  Generally, device addition is made easy by the repeatability of the code. Most basic devices won't need any complex setup.

  In Arduino code:
  1) Write a struct inheriting from the generic Device struct and add your customized properties & methods
  2) Add an initiator inside loop() with a letter corresponding to the device
  3) Add line in Help command (Not needed for functionality)

  In Python code:
  4) Write device class in Python file - most devices should only need to inherit directly from Device
  5) In create_device function, add your case with a corresponding letter
  6) Also in create_device, add your letter and device type to the type_map variable.

