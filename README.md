# ModulIO
  ModulIO - GPIO Controller Over Serial

  Description:
  This project enables user-friendly control of most GPIO devices over serial communications.
  The command and output format is designed so that to be easy to understand for humans, as well as easy to parse for computers.
  Every type of device inherits from the same generic Device class, allowing each GPIO device to be managed the same way.

### How to get it working?
  1) Connect serial:
  2) Add devices:
  3) (optional) Enable recording:
  4) Read & write as needed with [Device].read() & [Device].write()
  
### How to add your own devices
  In Arduino code:
  1) Write a struct inheriting from the generic Device struct and add your customized properties & methods
  2) Add an initiator inside loop() with a letter corresponding to the device
  3) Add line in Help command (Not needed for functionality)

  In Python code:
  4) Write device class in Python file - most devices should only need to inherit directly from Device
  5) In create_device function, add your case with a corresponding letter
  6) Also in create_device, add your letter and device type to the type_map variable.

  Generally, device addition is made easy by the repeatability of the code. Most basic devices won't need any complex setup.


