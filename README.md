# ModulIO
  ModulIO - GPIO Controller Over Serial

  Description:
  This project enables user-friendly control of most GPIO devices over serial communications.
  The command and output format is designed so that to be easy to understand for humans, as well as easy to parse for computers.
  Every type of device inherits from the same generic Device class, allowing each GPIO device to be managed the same way.
  
# Adding your own devices
  To add your own devices:
  1) Write a struct inheriting from Device struct and add your customized properties & methods
  2) Add an initiator inside loop() with the corresponding letter
  3) (optional) Add line in Help command
  4) Write matching class in Python file

  Idea for devices with multiple settings you can control:
  The controlDevice command syntax is c [index] [value] where "value" is a string.
  Because the parsing of this value is done inside the write() method of the device struct, you can pass in something like "115,200" and have your internal function split that into 115 and 200.
