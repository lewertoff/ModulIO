# CHANGELOG - in reverse chronological order

## Future Plans - Known Issues and Roadmap
- Figure out exact minimum time needed between set_value calls
- Add device support for rotary encoder knob. Use this addition to make a PDF guide on how to add your own custom modules. Also, show that a rotary encoder w/ click can be programmed as a button device plus an encoder device. Two outputs, two statuses, two devices.

## 2025/06/09 - Implement checksums, priority sending, userMode
- Implemented CRC8 Checksums for commands sent from Python to Arduino
- Added userMode toggle in Arduino file. userMode=false triggers more redundancy for automated high-speed operation.
- Arduino will now set device value to 0 before removing. Since Python does the same, this was only an issue when in userMode.
- Arduino will now reject serial commands if not enough arguments are present.
- Added high-priority sending queue that skips normal queue and waits for confirmation of action from Arduino.
- Reworded some logging messages to be more precise
- More updates to README

## 2025/06/02 - Rewrite recording system improve docs
- Refactored Arduino variable names for consistency
- Heavily improved .ino file documentation
- Heavy updates to README
- Added info() function on Arduino
- Created new, much lighter, queue-based recording algorithm
- Revamped Python → Arduino serial communications for robustness
- Removed redundant internal recording_active flag
- In Arduino, invalid commands will no longer return error keyword, potentially interfering with other actions.
- Introduced new "Warn:" keyword in Arduino communication.
- Fixed threads not terminating properly on stop function calls

## 2025/05/31 - Refactor Python serial API
- Preparations to implement lots of new ideas
- Data stream period is now reset to default on disconnect
- Renamed change_data_stream_delay function to change_data_stream_period
- Tweaked license
- Heavily improved documentation of Python library
- All devices will now be removed when disconnecting
- Serial port is now specified in connect() instead of globally
- changed names of some function calls for consistency
- Data stream will now automatically be enabled on connection.
- Removed toggle_data_stream and split it into two internal functions.

## 2025/05/26 - Add logging, optimize Arduino RAM, improve docs
- Fixed typos in readme
- Record thread will now stop when disconnect() is called
- Added global constants for serial port, baudrate, and timeout
- Updated README to include more detailed instructions (more to come)
- Arduino will now display version when connecting
- Removed unnecessary global initializations in Python
- Disconnecting serial in Python will now stop recording
- Memory allocation improvements for Arduino - now storing config variables in flash
- Added logging for info and errors
- Added docstrings to functions

## 2025/05/25 - Add CSV recording, safer serial comms
- Various bug and edge case fixes
- Improved internal documentation and structure
- Added safety measures to prevent different threads from writing to serial at once
- Added promised ability to record data to CSV
- Added ability to change data stream period separately & added minimum period of 1ms
- Tweak license wording

## 2025/05/23 - Initial Commit
- Hi