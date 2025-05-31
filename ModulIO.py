"""
  ==================================================================================================
  ModulIO - A Python/Arduino program for managing devices over a serial connection.
  Version 0.4.1 May 29 2025
  Description: Simplified universal control of GPIO devices through an Arduino host.
  ==================================================================================================

    This file includes callable functions to connect & disconnect serial, create & remove devices, 
    toggle data stream, and record data stream to a CSV.
    Device instances can also be read and written to, allowing for interaction with the devices.

    See README for information on how to add your own customizable devices.

  ==================================================================================================
"""
####################################################################################################
# SETUP

import time
from datetime import datetime
import threading
import serial
import csv
import logging

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

        conf_event.clear()
        errr_event.clear()

        self.value = None
        self.index = None
        self.name = None
        self.pin = None
        self.lock = threading.Lock() # For data integrity
        
        try:
            # Convert list of pins into string separating pins with spaces
            pin_str = " ".join(map(str, pins)) if isinstance(pins, list) else str(pins)

            _safe_write(f"s {char} {name} {pin_str}")

            # error check before confirming device
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()
            if not confirmed or errored:
                raise RuntimeError(f"Device unconfirmed or errored.")

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
        _safe_write(f"c {self.index} {value}")

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

# Serial setup
BOOTUP_DELAY = 2 # How long it takes for the microcontroller to begin loop() calls
SERIAL_BAUD_RATE = 115200 # Baud rate for serial communication. Must match Arduino setting!
SERIAL_TIMEOUT = 100 # Timeout for serial communication in ms. Must match Arduino setting!
ser = None # Connection instance

IDLE_WAIT_DELAY = 0.002 # Short delay to avoid busy waiting
DEFAULT_DATA_STREAM_PERIOD = 5000 # ms

# Device setup
MAX_DEVICES = 10  # Maximum devices that can be created
device_dict = {} # Names to device instances
names_in_order = [] # Names in order of indexes

# Threading setup
thread_receive_serial = None # Thread for receiving data from Arduino
stop_receive_event = threading.Event() # Tells receive data thread to stop
thread_record_data = None # Thread for recording data to CSV
stop_record_event = threading.Event() # Tells record data thread to stop
conf_event = threading.Event() # Signifies general action confirmed
errr_event = threading.Event() # Signifies general error
serial_lock = threading.Lock() # For thread-safe serial communication

# Recording setup
recording = False # Status flag for recording data to CSV
new_data_to_record = threading.Event() # Alerts recording threat of new data

# Logging setup
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] - %(message)s", 
                    handlers=[logging.FileHandler("modulio.log")])

####################################################################################################  
# CUSTOM DEVICE CLASSES

class ButtonDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("b", name, pin)

class PressureSensorDevice(Device): # HX710B Pressure Sensor
    def __init__ (self, name, data, clk):
        super().__init__("p", name, [data, clk])

class LEDDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("l", name, pin)

class DCMotorDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("m", name, pin)

####################################################################################################
# CALLABLE FUNCTIONS

def connect(port: str) -> None:
    """Initializes serial connection, then starts data stream and reception.
    
    Args:
        port (str): The serial port to connect to (e.g., "COM5").
    """
    global ser

    try:
        ser = serial.Serial(port, SERIAL_BAUD_RATE, timeout=SERIAL_TIMEOUT)
        logging.info(f"Connected to {port}.")
        
        time.sleep(BOOTUP_DELAY) # IMPORTANT! Wait for Arduino to reboot (it automatically resets when serial port is opened)
        
        ser.reset_input_buffer() # Empty input buffer to avoid reading startup junk

        _start_receive_thread() # Start thread to read messages from Arduino

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

    # Remove all devices
    for name in names_in_order[:]:  # Copy the list to avoid modifying it while iterating
        device_dict[name].set_value(0)  # Turn off all devices before removing
        remove_device(name)

    # Set data stream back to default
    change_data_stream_period(DEFAULT_DATA_STREAM_PERIOD)

    # Stop all running threads
    _stop_record_thread()
    time.sleep(0.1) # Give some time for the thread to stop
    _stop_receive_thread()

    _disable_data_stream() # Tell Arduino to stop sending data

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
    """
    global device_dict

    # Recording check
    if recording:
        logging.warning("Cannot create a device while recording.")
        raise Exception("Cannot create a device while recording. Please stop recording first.")
    
    # Name check
    if name in device_dict:
        logging.warning(f"Device '{name}' already exists.")
        raise Exception(f"Device '{name}' already exists. Please choose a different name.")
    
    # Device number check
    if len(names_in_order) >= MAX_DEVICES:
        logging.error(f"Maximum number of devices reached.")
        raise Exception(f"Maximum number of devices ({MAX_DEVICES}) reached. Cannot add more devices.")

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

        logging.info(f"Added {type_map.get(device_char)} '{name}' on pin(s) {pins}.")

        return device
    else:
        logging.warning(f"Failed to add {type_map.get(device_char)} '{name}'.")

def remove_device(name: str) -> None:
    """Deletes a device from the available devices.

    Args:
        name (str): Name of the device to remove.

    Raises:
        RuntimeError: If recording, or if device removal failed.
        ValueError: If device name is not found.

    Notes:
        Devices are removed from both Arduino and Python to keep parity.
    """
    global device_dict, names_in_order

    # Recording check
    if recording:
        logging.warning("Cannot delete a device while recording.")
        raise RuntimeError("Cannot detete a device while recording. Please stop recording first.")

    if name in device_dict:
        conf_event.clear()
        errr_event.clear()
        
        idx = device_dict[name].get_index()

        try:
            # Delete device from Arduino
            _safe_write(f"r {idx}")

            # Error check to see if it was actually deleted
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()
            if not confirmed or errored:
                raise RuntimeError(f"Failed to remove device {name}.")
            
            # Delete device from Python
            del device_dict[name]
            logging.info(f"Removed device '{name}'.")

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
    if not isinstance(delay, int) or delay < 1:
        logging.error("Tried to set an invalid data stream delay.")
        raise Exception("Delay must be an integer above 0.")
    
    _safe_write(f"u {delay}")
    logging.info(f"Data stream delay set to {delay} ms.")

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

def _safe_write(msg: str) -> None:
    """Safely transmits string through serial.

    Args:
        msg (str): String to transmit.

    Notes:
        Thread-safe. Use for all transmissions.
    """
    if ser and ser.is_open:
        with serial_lock:
            ser.write(f"{msg}\n\r".encode('ascii'))
            ser.flush()  # Ensure the message is sent immediately
        logging.info(f"Python -> Sent: {msg}")

def _enable_data_stream() -> None:
    """Enable data stream from Arduino.
    """
    global data_stream_active

    _safe_write("t 1")
    logging.info("Data stream activated")
    
def _disable_data_stream() -> None:
    """Disables data stream from Arduino. 
    """
    global data_stream_active

    _safe_write("t 0")
    logging.info("Data stream deactivated'")

def _update_data(datalist: list) -> None:
    """Updates values of all connected devices with new readings.

    Args:
        datalist (list): List of new data organized as [name:str, value, name2:str, value2, ...]

    Notes:
        If data integrity is not guaranteed, data is discarded and values are not updated.
    """
    global new_data_to_record
    
    # Ensure device-value pairs are complete
    if len(datalist) % 2 == 0 and len(datalist) / 2 == len(names_in_order): 

        while datalist:
            key = datalist.pop(0) # Pop first index, which is the device name
            value = datalist.pop(0) # Pop first index again, which is now its value
        
            if key in device_dict:
                device_dict[key]._update(value)
            else:
                logging.warning(f"{key} not found in device_dict")
        
        # If recording is active, set the flag to record new data
        if recording:
            new_data_to_record = True

    else:
        logging.warning("Received data list is not complete or does not match device count.")
        # Silently continue, as this can happen if the Arduino sends incomplete data.

####################################################################################################
# THREADING

def _receive_serial() -> None:
    """Handles incoming data from Arduino & calls required actions.
    """
    logging.info("Python can now receive data from Arduino")

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
                                errr_event.set()

                            case "Recv:":
                                logging.info("Arduino -> " + data) # For logging/debugging purposes only

                            case _:
                                logging.error("Received data not matched: " + data)

                except Exception as e:
                    logging.error(f"Error while receiving data: {e}")
        else:
            time.sleep(IDLE_WAIT_DELAY)  # Sleep for a short time to avoid busy waiting

def _start_receive_thread():
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

def _stop_receive_thread():
    """Stops current _receive_data thread if running.
    """
    global thread_receive_serial

    stop_receive_event.set()

    if thread_receive_serial and thread_receive_serial.is_alive():
        thread_receive_serial.join(timeout=1)  # give it a second to clean up
        logging.info("Receive thread stopped.")
    else:
        logging.info("Receive thread was not running or already stopped.")
    thread_receive_serial = None

def _record_data_to_csv(filename: str) -> None:
    """Records data stream to a timestamped CSV.

    Args:
        filename (str):Desired name of file to record to (e.g. "data.csv")

    Notes:
        If a file of the same name already exists, it will be overwritten.
        While recording is enabled, new devices cannot be created.
    """
    global new_data_to_record

    with open(filename, mode='w', newline='') as csvfile:

        logging.info(f"Python now recording to {filename}...")

        writer = csv.writer(csvfile)

        fieldnames = ['Time'] + names_in_order # List for CSV header

        writer.writerow(fieldnames)

        try:
            while not stop_record_event.is_set():
                if new_data_to_record:
                    row_list = [datetime.now().strftime("%H:%M:%S.%f")[:-3]]
                    for name in names_in_order:
                        row_list.append(device_dict[name].get_value())
                    writer.writerow(row_list)
                    new_data_to_record = False  # Reset the flag after writing
                else:
                    time.sleep(IDLE_WAIT_DELAY) # Sleep for a short time to avoid busy waiting
        
        except Exception as e:
            logging.error(f"Error while recording data: {e}")

def _start_record_thread(filename: str):
    """Starts a _record_data_to_csv thread and updates recording flag.
    """
    global thread_record_data, recording

    # Check if called when thread already exists
    if thread_record_data and thread_record_data.is_alive():
        logging.error("Cannot start recording: already recording data.")
        raise Exception("Cannot start recording: already recording data. Please stop recording first.")

    # Clear the stop event to ensure the thread can start
    stop_record_event.clear()

    thread_record_data = threading.Thread(target=_record_data_to_csv, args=(filename,), daemon=True)
    thread_record_data.start()

    recording = True

def _stop_record_thread():
    """ Stops current _record_data_to_csv thread if running.
    """  
    # Internal function to stop the thread that records data to a CSV file.

    global recording, thread_record_data

    stop_record_event.set()

    recording = False

    if thread_record_data and thread_record_data.is_alive():
        thread_record_data.join(timeout=1)  # give it a second to clean up
        logging.info("Recording stopped.")
    else:
        logging.info("Recording thread was not running or already stopped.")
    thread_record_data = None