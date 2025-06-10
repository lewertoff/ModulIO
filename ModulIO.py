"""
  ==================================================================================================
  ModulIO - A Python/Arduino program for managing devices over a serial connection.
  Version 0.5 June 2 2025
  Description: Simplified universal control of GPIO devices through an Arduino host.
  ==================================================================================================

    This file includes callable functions to connect & disconnect serial, create & remove devices,
    record device data to a CSV, and more.
    Device instances can also be read and written to, allowing for interaction with the devices.

    https://github.com/lewertoff/ModulIO

    See README for information on how to add your own customizable devices.

  ==================================================================================================
"""
####################################################################################################
# SETUP

import time
from datetime import datetime
import threading
import serial
import crcmod
import csv
import logging
import queue

class Device:
    def __init__ (self, char: str, name: str, pins: list[int]):
        """Initializes a device with the given name and pins.

        Args:
            char (str): Sinle character representing device type (e.g., 'b' for button, 'p' for
                pressure sensor).
            name (str): Name of the device. Must be uniqe against all other devices.
            pins (list[int]): List of pins associated with the device.

        Raises:
            RuntimeError: If Arduino errors or does not confirm creation.

        Notes:
            This function sends a command to the Arduino to initialize the device and waits for confirmation.
        """
        global names_in_order

        self.value = None
        self.index = None
        self.name = None
        self.pin = None
        self.lock = threading.Lock() # For data integrity
        
        try:
            # Convert list of pins into string separating pins with spaces
            pin_str = " ".join(map(str, pins)) if isinstance(pins, list) else str(pins)

            _serial_write(f"s {char} {name} {pin_str}", priority=True)

            self.name = name
            self.pin = pin_str

            self.index = len(names_in_order)
            names_in_order.append(name)

            self.value = None # will be filled by thread_receive_data

        except Exception as e:
            logging.error(f"Failed to initialize device {name}: {e}")
            raise

    def get_value(self):
        """Gets sensed or actuated value.
        
        Returns:
            str: Sensors return their sensed value, while actuators return their current
                state.
        """
        with self.lock:
            return self.value
    
    def set_value(self, value: str | int):
        """Tells Arduino to change device's value. Sensors do not need this function.

        Args:
            value (str | int): The value to set the device to. For example, a motor or LED 
            accepts a PWM value (0-255).

        Notes:
            This function does NOT change the self.value property. This property is only changed 
            once the data stream coming back from the Arduino confirms the new status. It is 
            updated via a call to the internal self._update function.
        """
        _serial_write(f"c {self.index} {value}")

    def get_index(self):
        """Gets the index of the device in the Arduino's devices array.

        Returns:
            int: The index of the device in the Arduino's devices array.

        Notes:
            This index is used to identify the device in serial communication.
        """
        with self.lock:
            return self.index

    def _update(self, value: str):
        """Sets the self.value property of the device.

        Args:
            value (str): The new value to update the device with. 
        
        Notes:
            This function is typically called by the receive_data thread.
        """
        with self.lock:
            self.value = value

    def _set_index(self, new_idx: int):
        """Changes the index of the device. 

        Args:
            new_idx (int): The new desired index for the device.

        Notes:
            DOES NOT NEED TO BE TOUCHED EXTERNALLY! Python<-->Arduino communication uses indexes 
            to distinguish devices while the ModulIO Python library converts them to objects 
            identified by names. This function is used to keep indexes across Python & Arduino 
            matching after removing a device.
        """
        with self.lock:
            self.index = new_idx

# MUST MATCH ARDUINO VALUES
SERIAL_BAUD_RATE = 115200 # Baud rate for serial communication. Must match Arduino setting!
SERIAL_TIMEOUT = 60 # Timeout for serial communication in ms. Must match Arduino setting!
MAX_DEVICES = 10  # Maximum devices that can be created. Must match Arduino setitng!

# Serial setup
STARTUP_DELAY = 2 # How long it takes for the microcontroller to begin loop() calls
ser = None # Connection instance
serial_lock = threading.Lock() # For thread-safe serial communication

# Sending setup
SENDING_DEADLINE = 1 # s, how long to wait for confirmation of sent messages
PRIORITY_CONFIRM_TIMEOUT = 1 # s, how long to wait for confirmation of actions taken
crc8 = crcmod.predefined.mkCrcFun('crc-8') # For msg checksums
send_queue = queue.Queue(maxsize = 100) # For sending messages out
priority_send_queue = queue.Queue(maxsize=10) # For high priority messages
recv_queue = queue.Queue(maxsize = 1) # For comparing sent messages to Recv'd messages
thread_send_serial = None # Thread for sending data to Arduino
stop_send_event = threading.Event() # Tells send data thread to stop

# Receiving setup
thread_receive_serial = None # Thread for receiving data from Arduino
stop_receive_event = threading.Event() # Tells receive data thread to stop

# General setup
IDLE_WAIT_DELAY = 0.015 # Short delay to avoid busy waiting
conf_event = threading.Event() # Signifies general action confirmed

# Device setup
device_dict = {} # Names to device instances
names_in_order = [] # Names in order of indexes

# Data stream setup
DEFAULT_DATA_STREAM_PERIOD = 5000 # ms, must match Arduino dataStreamPeriod value.
data_stream_period = None # ms
data_stream_active = False # Status variable

# Recording setup
thread_record_data = None # Thread for recording data to CSV
stop_record_event = threading.Event() # Tells record data thread to stop
recording_queue = queue.Queue()

# Logging setup
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] - %(message)s", 
                    handlers=[logging.FileHandler("modulio.log")])

####################################################################################################  
# CUSTOM DEVICE CLASSES

class ButtonDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("b", name, pin)

class PressureSensorDevice(Device): # HX710B Pressure Sensor. Values begin a few seconds after initialization.
    def __init__ (self, name, data, clk):
        super().__init__("p", name, [data, clk])

class LEDDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("l", name, pin)

class DCMotorDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("m", name, pin)

####################################################################################################
# FUNCTIONS

def connect(port: str) -> None: 
    """Initializes serial connection.
    On connection, the following is started:
    - Serial receive thread
    - Serial send thread
    - Serial data stream (starts at default rate)
    All of these are meant to run until disconnect() is called.
    
    Args:
        port (str): The serial port to connect to (e.g., "COM5").
    """
    global ser

    logging.info(f"Connecting to {port}...")

    try:
        ser = serial.Serial(port, SERIAL_BAUD_RATE, timeout=SERIAL_TIMEOUT)
        logging.info(f"Connected to {port}.")
        
        time.sleep(STARTUP_DELAY) # IMPORTANT! Wait for Arduino to reboot (it automatically resets when serial port is opened)
        
        ser.reset_input_buffer() # Empty input buffer to avoid reading startup junk

        _start_send_thread()
        _start_receive_thread()

        # Tell Arduino to disable userMode & perform check
        logging.info("Disabling userMode on Arduino...")
        conf_event.clear()
        with serial_lock:
            ser.write("z 0".encode('ascii')) 
        logging.debug("Python -> Sent: \"z 0\"")
        confirmed = conf_event.wait(timeout=2)
        if not confirmed:
            logging.critical("Failed to confirm userMode disabled.")
            raise RuntimeError("Failed to confirm userMode disabled. Check Arduino connection.")

        _enable_data_stream() # Tell Arduino to start sending data

    except Exception as e:
        logging.error(f"Error connecting to {port}: {e}")
        raise

def disconnect() -> None:
    """Removes all devices and disconnects from the currently connected serial port.

    Notes:
        Call this before terminating main program.
        If recording is active, calling disconnect() will stop recording.
    """
    global ser

    logging.info("Disconnect() called. Cleaning up...")

    # Stop recording
    if thread_record_data:
        _stop_record_thread()

    # Set data stream back to default
    change_data_stream_period(DEFAULT_DATA_STREAM_PERIOD)

    # Tell Arduino to stop sending data
    _disable_data_stream() 

    # Remove all devices
    for name in names_in_order[:]:  # Copy the list to avoid modifying it while iterating
        remove_device(name)

    # Set userMode back to True
    logging.info("Re-enabling userMode on Arduino...")
    _serial_write("z 1", priority=True)

    # Wait for queues to finish sending (must do before closing threads)
    while not priority_send_queue.empty():
        time.sleep(IDLE_WAIT_DELAY)
    # Wait for any remaining confirmation's deadline to pass
    deadline = time.time() + PRIORITY_CONFIRM_TIMEOUT 
    while not conf_event.is_set() and time.time() < deadline:
        time.sleep(IDLE_WAIT_DELAY)
    while not send_queue.empty(): # Wait for normal queue to be sent
        time.sleep(IDLE_WAIT_DELAY)
    time.sleep(0.1) # Add one more slight delay for safety margin

    # Stop all running threads
    _stop_receive_thread()
    _stop_send_thread()
    
    if ser and ser.is_open:
        ser.close()
        logging.info("Serial disconnected.")

    else:
        logging.warning("Disconnect called when serial port is not open or already closed.")
    
    ser = None  # Reset the serial connection

def create_device(device_char: str, name: str, pins: list[int]) -> Device | None:
    """Creates a device of the specified type and adds it to the device dictionary.
    
    Args:
        char (str): Sinle character representing device type (e.g., 'b' for button, 'p' for
            pressure sensor).
        name (str): Name of the device. Must be uniqe against all other devices.
        pins (list[int]): List of pins associated with the device.

    Returns:
        Device: A new Device instance of the appropriate subclass.
        None: if an error occurred during creation.

    Notes:
        May cause logging warnings in the short time where device is created in Python but not yet in Arduino.
    """
    global device_dict

    logging.info(f"Creating device '{name}'...")

    # Recording check
    if thread_record_data:
        logging.warning("Cannot create a device while recording.")
        raise RuntimeError("Cannot create a device while recording. Please stop recording first.")
    
    # Name check
    if name in device_dict:
        logging.warning(f"Device '{name}' already exists.")
        raise ValueError(f"Device '{name}' already exists. Please choose a different name.")
    
    # Device number check
    if len(names_in_order) >= MAX_DEVICES:
        logging.error(f"Maximum number of devices reached.")
        raise RuntimeError(f"Maximum number of devices ({MAX_DEVICES}) reached. Cannot add more devices.")

    match device_char:
        case 'b':
            device = ButtonDevice(name, pins[0])
        case 'p':
            device = PressureSensorDevice(name, pins[0], pins[1]) # data pin, clock pin
        case 'l':
            device = LEDDevice(name, pins[0])
        case 'm':
            device = DCMotorDevice(name, pins[0])
        case _:
            logging.warning(f"Unknown device type: {device_char}")
            raise Exception(f"Unknown device type: {device_char}.")
        
    type_map = {"b": "Button", "p": "PressureSensor", "l": "LED", "m": "DCMotor"} # For printed message
    
    if device: # If a device is created successfully
        device_dict[name] = device

        logging.info(f"Adding {type_map.get(device_char)} '{name}' on pin(s) {pins}.")

        return device
    else:
        logging.warning(f"Failed to create {type_map.get(device_char)} '{name}'.")

def remove_device(name: str) -> None:
    """Deletes a device from the available devices.

    Args:
        name (str): Name of the device to remove.

    Raises:
        RuntimeError: If recording, or if device removal failed.
        ValueError: If device name is not found.

    Notes:
        Devices are removed from both Arduino and Python to keep parity.
        May cause logging warnings in the short time where device is removed from Arduino but not yet from Python.
    """
    global device_dict, names_in_order

    logging.info(f"Removing device '{name}'...")

    # Recording check
    if thread_record_data:
        logging.warning("Cannot delete a device while recording.")
        raise RuntimeError("Cannot detete a device while recording. Please stop recording first.")

    if name in device_dict:
        idx = device_dict[name].get_index()

        try:
            # Delete device from Arduino
            _serial_write(f"r {idx}", priority=True) # Arduino should know to turn off device first
            
            # Delete device from Python
            del device_dict[name]

            # Remove the name at the device's index
            names_in_order.pop(idx)

            # Update the index of all devices after the removed one
            for i in range(idx, len(names_in_order)):
                device_dict[names_in_order[i]]._set_index(i)
            
        except Exception as e:
            logging.error(f"Error while removing device '{name}': {e}")
            raise

    else:
        logging.warning(f"Device '{name}' not found.")
        raise ValueError(f"Cannot remove device. '{name}' not found.")

def change_data_stream_period(delay: int) -> None:
    """Changes the delay between data stream updates.
    
    Args:
        delay (int): Milliseconds in between each data stream update.
    
    Notes:
        Arduino's default is 5000ms to not overload I/O. It is advised to set your own value.
    """
    global data_stream_period

    logging.info(f"Changing data stream period to {delay} ms...")

    if not isinstance(delay, int) or delay < 1:
        logging.error("Delay ms value invalid.")
        raise Exception("Delay must be an integer above 0.")
    
    _serial_write(f"u {delay}", priority=True)
    data_stream_period = delay

def start_recording(filename:str) -> None:
    """Starts recording data to a CSV file.
    
    Args:
        filename: Name of the CSV file to record data to.

    Notes:    
        Data stream must be active to record data.
        If file already exists, it will be overwritten.
    """
    # Serial connection check
    if not ser or not ser.is_open:
        logging.error("Cannot start recording: serial port is not open. ")
        raise Exception("Cannot start recording: serial port is not open. Use connect() first.")
    
    _start_record_thread(filename)

def stop_recording() -> None:
    """Stops recording data to a CSV file.
    """
    _stop_record_thread()

def _serial_write(cmd: str, priority=False) -> None:
    """Adds message to serial output queue.

    Args:
        msg (str): String to transmit. Does not include checksum or CR/NL characters.
        priority (bool): If True, message is sent using high priority queue with extra security checks.
        
    Notes:
        High priofaster plus waits for confirmation from 
    """
    cmd = cmd.strip()

    if priority:
        if priority_send_queue.full():
            logging.critical("Priority send queue is full.")
            raise RuntimeError("Priority send queue is full!")
        else:
            priority_send_queue.put(cmd)
            logging.debug(f"added \"{cmd}\" to priority send queue")
            return
    else:
        if send_queue.full():
            logging.critical("Send queue is full.")
            raise RuntimeError("Send queue is full! Ensure enough delay is implemented between control_device calls!")
        else:
            send_queue.put(cmd)  
            logging.debug(f"added \"{cmd}\" to send queue")

def _enable_data_stream() -> None:
    """Enable data stream from Arduino.
    """
    global data_stream_active

    logging.info("Activating data stream...")

    _serial_write("t 1", priority=True) 
    data_stream_active = True  # Update status variable
    
def _disable_data_stream() -> None:
    """Disables data stream from Arduino. 
    """
    global data_stream_active

    logging.info("Deactivating data stream...")

    _serial_write("t 0", priority=True)
    data_stream_active = False  # Update status variable

def _update_data(datalist: list) -> None:
    """Updates values of all connected devices with new readings. Also updates recording queue if recording.

    Args:
        datalist (list): List of new data organized as [name:str, value, name2:str, value2, ...]

    Notes:
        If data integrity is not guaranteed, data is discarded and values are not updated.
    """
    global new_data_to_record
    
    # Ensure device-value pairs are complete
    if len(datalist) % 2 == 0 and len(datalist) / 2 == len(names_in_order): 

        # If recording is active, send list to queue
        if thread_record_data:
            recording_queue.put([datetime.now().strftime("%H:%M:%S.%f")[:-3]] + datalist[1::2])

        # Update device values
        while datalist:
            key = datalist.pop(0) # Pop first index, which is the device name
            value = datalist.pop(0) # Pop first index again, which is now its value
        
            if key in device_dict:
                device_dict[key]._update(value)
            else:
                logging.warning(f"{key} not found in device_dict")

    else:
        logging.warning("Received data list is not complete or does not match device count.")
        # Silently continue, as this can happen if the Arduino sends incomplete data.

####################################################################################################
# THREADING

# Receive_serial: Receives msgs & calls required actions.
def _receive_serial() -> None:
    """Handles incoming data from Arduino & calls required actions.
    """
    logging.info("Serial receive thread now active!")

    while not stop_receive_event.is_set():

        if ser and ser.is_open:
            if ser.in_waiting > 0:

                try:
                    data = ser.readline().decode('ascii').strip()
                    if data:
                        match data[0:5]:

                            case "Conf:":
                                logging.info("Arduino -> " + data)
                                conf_event.set()

                            case "Data:":
                                logging.debug("Arduino -> "+ data) # set under debug flag since this is spammy
                                # Check for complete data
                                assert data.endswith(";"), "Incomplete data (missing semicolon)"
                                # Pass data to device instances
                                _update_data(data[6:-1].split())

                            case "Errr:":
                                logging.warning("Arduino -> " + data) # only warn since usually handled by Python

                            case "Warn:":
                                logging.warning("Arduino -> " + data)

                            case "Recv:":
                                logging.info("Arduino -> " + data) 
                                recv_queue.put(data[6:].split(";")[0])

                            case _:
                                logging.error("_receive_serial: Received data not matched: " + data)

                except Exception as e:
                    logging.error(f"_receive_serial: Error while receiving data: {e}")
        else:
            time.sleep(IDLE_WAIT_DELAY)  # Sleep for a short time to avoid busy waiting

def _start_receive_thread() -> None:
    """Starts a _receive_data thread.
    """
    global thread_receive_serial

    # Check if called when thread already exists
    if thread_receive_serial and thread_receive_serial.is_alive():
        logging.info("Stopping existing receive thread before starting a new one.")
        _stop_receive_thread() # Delete thread so it can be created again

    stop_receive_event.clear()

    thread_receive_serial = threading.Thread(target=_receive_serial, daemon=True)
    thread_receive_serial.start()

def _stop_receive_thread() -> None:
    """Stops current _receive_data thread if running.
    """
    global thread_receive_serial

    stop_receive_event.set()

    if thread_receive_serial and thread_receive_serial.is_alive():
        thread_receive_serial.join(timeout=1)  # give it a second to clean up
        logging.info("Serial receive thread stopped.")
    else:
        logging.info("Serial receive thread was not running or already stopped.")

    thread_receive_serial = None

# Send_serial: Sends msgs in send_queue & confirms that they were received.
def _send_serial() -> None:
    """Handles outgoing serial communications including data integrity checks & thread safety.
    """
    logging.info("Serial send thread now active!")

    while not stop_send_event.is_set() or (stop_send_event.is_set() and (not send_queue.empty() or not priority_send_queue.empty())):
        # Ensure revc queue is empty
        if not recv_queue.empty():
            recv_queue.get()
        
        priority = False # Default to normal priority
        
        # Get message (try to take from priority first)
        try:
            if not priority_send_queue.empty():
                command = priority_send_queue.get_nowait()
                priority = True
                conf_event.clear()
            elif not send_queue.empty():
                command = send_queue.get_nowait()
            else:
                time.sleep(IDLE_WAIT_DELAY)
                continue
        except queue.Empty: # Expected error, all good
            continue

        # Build full message
        checksum = crc8(command.encode("ascii")) # int
        checksum_hex = f"{checksum:02X}"  # Format as 2-digit uppercase hex
        msg = f"{checksum_hex}; {command}\r\n"

        # Send message over serial
        with serial_lock:
            ser.write(msg.encode('ascii'))
            ser.flush() # Ensure the message is sent immediately
        logging.info(f"Python -> Sent: \"{msg[0:-2]}\"") # Exclude "\r\n" to avoid messy logs

        # Make sure messgae was received properly
        deadline = time.time() + SENDING_DEADLINE
        while True: # Time-critical While loop ∴ no idle wait delays!
            remaining = deadline - time.time()

            if remaining <= 0:
                logging.warning(f"_send_serial: Command \"{command}\" not confirmed from Arduino (timeout)")
                
                # Put message back in queue
                if priority:
                    priority_send_queue.put(command)
                else:
                    send_queue.put(command)

                break # Failure, try again later

            try:
                # Parse received message for checksum
                recv = recv_queue.get(timeout = SENDING_DEADLINE) 
                arduino_checksum_hex = recv[0:2]
                
                # Check if message was received as expected
                if checksum_hex == arduino_checksum_hex: 
                    break # Success

                else:
                    logging.warning(f"_send_serial: Transmitted checksum \"{checksum_hex}\" not matched with received \"{arduino_checksum_hex}\"")

            except queue.Empty: # Expected error, all good
                continue # Wait until deadline
        
        # If priority, check if command was confirmed
        if priority:
            confirmed = conf_event.wait(timeout=PRIORITY_CONFIRM_TIMEOUT)
            if not confirmed:
                logging.critical(f"_send_serial: Failed to confirm high-priority command \"{command}\".")
            
        # Check queue sizes
        if send_queue.qsize() > send_queue.maxsize * 0.95:
            logging.warning("_send_serial: Send queue is over 95 percent full!")
        if priority_send_queue.qsize() > priority_send_queue.maxsize * 0.80:
            logging.warning("_send_serial: Priority send queue is over 80 percent full!")

def _start_send_thread() -> None:
    """Starts a _send_serial thread.
    """
    global thread_send_serial

    # Check if called when thread already exists
    if thread_send_serial and thread_send_serial.is_alive():
        logging.info("Stopping existing sending thread before starting a new one.")
        _stop_send_thread()
    
    # Clear stop event to ensure thread can start
    stop_send_event.clear()

    thread_send_serial = threading.Thread(target=_send_serial, daemon=True)
    thread_send_serial.start()

def _stop_send_thread() -> None:
    """Stops current _send_serial thread if running.
    """
    global thread_send_serial

    stop_send_event.set()

    if thread_send_serial and thread_send_serial.is_alive():
        thread_send_serial.join(timeout=1) # give it a second to clean up
        logging.info("Sending thread stopped.")
    else:
        logging.info("Sending thread was not running or already stopped.")

    thread_send_serial = None

# Record_data_to_csv: Writes device data as it comes in to a CSV.
def _record_data_to_csv(filename: str) -> None:
    """Records data stream w/ timestamp to a CSV file.

    Args:
        filename (str):Desired name of file to record to (e.g. "data.csv")

    Notes:
        If a file of the same name already exists, it will be overwritten.
        While recording is enabled, new devices cannot be created.
    """
    try:
        with open(filename, mode='w', newline='') as csvfile:

            logging.info(f"Now recording to {filename}...")

            writer = csv.writer(csvfile)

            fieldnames = ['Time'] + names_in_order # List for CSV header
            writer.writerow(fieldnames)

            while not stop_record_event.is_set():
                try:
                    row = (recording_queue.get(timeout=data_stream_period)) # wait for upto a cycle
                    writer.writerow(row)
                except queue.Empty: # Expected error, all good
                    pass # no logic required
            
            # When stop flag is set, catch any leftover rows before terminating
            logging.info("_record_data_to_csv: Recording stop signaled, emptying queue...")
            while not recording_queue.empty():
                writer.writerow(recording_queue.get())

    except Exception as e:
        logging.error(f"_record_data_to_csv: Error while recording data: {e}")

def _start_record_thread(filename: str) -> None:
    """Starts a _record_data_to_csv thread and updates recording flag.
    """
    global thread_record_data

    # Check if called when thread already exists
    if thread_record_data and thread_record_data.is_alive():
        logging.info("Stopping existing record thread before starting a new one.")
        _stop_record_thread()

    # Clear the stop event to ensure the thread can start
    stop_record_event.clear()

    thread_record_data = threading.Thread(target=_record_data_to_csv, args=(filename,), daemon=True)
    thread_record_data.start()

def _stop_record_thread() -> None:
    """ Stops current _record_data_to_csv thread if running.
    """  
    global thread_record_data

    stop_record_event.set()

    if thread_record_data and thread_record_data.is_alive():
        thread_record_data.join(timeout=1)  # give it a second to clean up
        logging.info("Recording stopped.")
    else:
        logging.info("Recording thread was not running or already stopped.")

    thread_record_data = None