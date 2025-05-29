# CHANGELOG - in reverse chronological order
## Future plans
- Unit testing
- Look into recording data with Queue instead of bool flag
- Rework terminologies & documentation of .ino file - ex: sensor loop / serial spam / data stream inconsistency

## v0.4 - 2025/05/29 2:27 AM
- Tweaked license
- Heavily improved documentation of Python library
- All devices will now be removed when disconnecting
- Serial port is now specified in connect() instead of globally
- changed names of some function calls for consistency
- Data stream will now automatically be enabled on connection.
- Removed toggle_data_stream and split it into two internal functions.

## v0.3 - 2025/05/26 11:15 pm
- Fixed typos in readme
- Record thread will now stop when disconnect() is called
- Added global constants for serial port, baudrate, and timeout
- Updated README to include more detailed instructions (more to come)
- Arduino will now display version when connecting
- Removed unnecessary global initializations in Python
- Disconnecting serial in Python will now stop recording
- Memory allocation improvements for Arduino - now storing config variables in flash
- Added logging for info & errors
- Added docstrings to functions

## v0.2 - 2025/05/25 11:40 pm
- Various bug & edge case fixes
- Improved internal documentation & structure
- Added safety measures to prevent different threads from writing to serial at once
- Added promised ability to record data to CSV
- Added ability to change data stream period separately & added minimum period of 1ms

## Initial commit - 2025/05/24

