# CHANGELOG - in reverse chronological order
## Future plans
- Unit testing

- COMPLETE rework of terminologies & documentation of .ino file - ex: sensor loop / serial spam / data stream, and multiple more inconsistencies in naming. Also, we should define those terms somewhere for documentation purposes.

- add a delay between any messages sent out! Sending data over serial could benefit from running in its own thread. That would allow it to run asynchronously and we could tell it to wait a millisecond or so between lines. And other functions would send their data not by calling _safe_write() but by updating a queue that feeds into this thread. This setup should eliminate a lot of communication inefficiency.

- Right now baud rate is pretty high. Determine lowest working baud rate & document minimum advisable. Also, figure out why long messages (like "help" message from Arduino) do not show fully.
- Timeout should be whatever time it takes for baud rate to transmit 512 characters plus a few ms. Busy idle wait time should be a fraction of timeout (maybe a quarter or half).

- Figure out why Arduino keeps seeing blank messages.

- See if there are any weaknesses in the code in how data reception & transmission works. Really, we are looking for examples of data that, if not communicated properly over serial (ex: bad connection or random dropout) will not be error-checked. Examle: device creation data being garbled when sent out, leading to Python having one extra device than the Arduino. In this example, the device errors if Arduino does not confirm. Implement more of this.

- New lighter recording algorithm: if recording_active is true, take a copy of the "Data:" string from receive_data function, cut it into a list, and remove every first out of two columns. This will heavily reduve the number of ._get_data() calls, freeing up those functions for more external use.

- Add toggle for logging data stream to not overload log file

## v0.4.2 - 2025/05/31 4:35 PM
- Preparations to implement most of the above ideas
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
- Added logging for info & errors
- Added docstrings to functions

## v0.2 - 2025/05/25 11:40 pm
- Various bug & edge case fixes
- Improved internal documentation & structure
- Added safety measures to prevent different threads from writing to serial at once
- Added promised ability to record data to CSV
- Added ability to change data stream period separately & added minimum period of 1ms

## Initial commit - 2025/05/24

