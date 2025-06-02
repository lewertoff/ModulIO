# CHANGELOG - in reverse chronological order

## Future Plans - Known Issues and Roadmap
- Unit testing
- Figure out why CSV file is empty  
- Refine send/recv algorithm EVEN MORE using checksums
- Figure out minimum time needed between set_value calls
- Add a toggle for user-facing outgoing serial messages in Arduino 

## v0.5 - 2025/06/02 6:38 PM
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

## v0.4.2 - 2025/05/31 4:35 PM
- Preparations to implement lots of new ideas
- Data stream period is now reset to default on disconnect

## v0.4.1 Hotfix - 2025/05/29 10:40 PM
- Renamed change_data_stream_delay function to change_data_stream_period
- Fix several communication issues due to renamed functions

## v0.4 - 2025/05/29 2:27 AM
- Tweaked license
- Heavily improved documentation of Python library
- All devices will now be removed when disconnecting
- Serial port is now specified in connect() instead of globally
- changed names of some function calls for consistency
- Data stream will now automatically be enabled on connection.
- Removed toggle_data_stream and split it into two internal functions.

## v0.3 - 2025/05/26 11:15 PM
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

## v0.2 - 2025/05/25 11:40 pm
- Various bug and edge case fixes
- Improved internal documentation and structure
- Added safety measures to prevent different threads from writing to serial at once
- Added promised ability to record data to CSV
- Added ability to change data stream period separately & added minimum period of 1ms

## Initial commit - 2025/05/24

