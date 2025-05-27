# ModulIO
# A Python/Arduino program for managing devices over a serial connection.
# 
# This file includes callable functions to connect & disconnect serial, create & remove 
# devices, toggle data stream, and record data stream to a CSV.
# Device instances can also be read and written to, allowing for interaction with the devices.
#

###################################################################################################
# SETUP

import serial
import threading
from datetime import datetime
import time
import csv
import logging

class Device:
    def __init__ (self, char, name, pins):
        """
        Initializes a device with the given name and pins.
        @param char: Character representing the device type (e.g., 'b' for button, 'p' for pressure sensor).
        @param name: Name of the device.
        @param pins: List of pins associated with the device. For example, a button might have one pin, while a pressure sensor might have two (data and clock).
        @raises Exception: If the device fails to initialize or confirm.
        @note: This function sends a command to the Arduino to initialize the device and waits for confirmation.
        """
        global names_in_order

        conf_event.clear()
        errr_event.clear()

        self.value = None
        self.index = None
        self.name = None
        self.pin = None
        
        try:
            # Convert list of pins into string separating pins with spaces
            pin_str = " ".join(map(str, pins)) if isinstance(pins, list) else str(pins)

            safe_write(f"s {char} {name} {pin_str}")

            # error check before confirming device
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()
            if not confirmed or errored:
                raise Exception(f"Arduino did not confirm device {name} creation.")

            self.name = name
            self.pin = pin_str

            self.index = len(names_in_order)
            names_in_order.append(name)

            self.value = None # will be filled by thread_receive_data

        except Exception as e:
            logging.error(f"Failed to initialize device {name}: {e}")
            raise

    def read(self):
        """
        Callable function to read the value of the device (both sensors & actuators).
        @return: Sensors return their sensed value, while actuators return their current state.
        """
        return self.value
    
    def write(self, value: str | int):
        """
        Callable function to change the value of a device, if it is an actuator.
        @param value: The value to set the device to. For example, a motor or LED accepts a PWM value (0-255).
        """
        safe_write(f"c {self.index} {value}")

    def update(self, value):
        """
        Internal function to update the device with its latest value.
        @param value: The new value to update the device with. 
        @note: This function is typically called by the receive_data thread.
        """
        self.value = value

    def get_index(self):
        """
        Internal function to get the index of the device.
        @return: The index of the device in the Arduino's devices array.
        @note: This index is used to identify the device in serial communication.
        """
        return self.index

    def set_index(self, new_idx):
        """
        Internal function to change the index of the device. 
        @note: Used to keep indexes across Python & Arduino matching after removing a device.
        """
        self.index = new_idx


# Serial setup
SERIAL_PORT = "COM5" # Serial port to connect to (change as needed)
SERIAL_BAUD_RATE = 115200 # Baud rate for serial communication
SERIAL_TIMEOUT = 100 # Timeout for serial communication in seconds
ser = None # Connection instance
data_stream_active = False # Data stream (serial spam) status

# Device setup
device_dict = {} # Names to device instances
names_in_order = [] # Names in order of indexes
MAX_DEVICES = 10  # Maximum devices that can be created

# Recording setup
recording = False # Flag for recording data to CSV
new_data_to_record = False # Flag for new data to record in CSV

# Threading setup
thread_receive_data = None # Thread for receiving data from Arduino
stop_receive_event = threading.Event() # Tells receive data thread to stop
thread_record_data = None # Thread for recording data to CSV
stop_record_event = threading.Event() # Tells record data thread to stop
conf_event = threading.Event() # Signifies general action confirmed
errr_event = threading.Event() # Signifies general error
serial_lock = threading.Lock() # For thread-safe serial communication

# Logging setup
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] - %(message)s", 
                    handlers=[logging.FileHandler("modulio.log")])

###################################################################################################  
# DEVICE CLASSES

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

###################################################################################################
# CALLABLE FUNCTIONS

def connect() -> None:
    """
    Connects to the specified SERIAL_PORT.
    """

    global ser

    # Make sure a port is specified
    if not SERIAL_PORT:
        logging.critical("SERIAL_PORT is not set")
        raise Exception("SERIAL_PORT is not set. Please set it to a valid port.")
    
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD_RATE, timeout=SERIAL_TIMEOUT)
        logging.info(f"Connected to {SERIAL_PORT}.")
        
        time.sleep(2) # IMPORTANT! Wait for Arduino to reboot (it automatically resets when serial port is opened)

        ser.reset_input_buffer() # Empty input buffer to avoid reading startup junk
        start_receive_thread() # Start thread to read messages from Arduino

    except Exception as e:
        logging.error(f"Error connecting to {SERIAL_PORT}: {e}")
        raise

def disconnect() -> None:
    """
    Disconnects from the currently connected serial port.
    If recording is active, it will stop recording.
    """

    global ser

    # Stop all running threads
    stop_record_thread()
    time.sleep(0.1) # Give some time for the thread to stop
    stop_receive_thread()

    if ser and ser.is_open:
        ser.close()
        logging.info("Serial disconnected.")

    else:
        logging.warning("Serial port is not open or already closed.")
    
    ser = None  # Reset the serial connection

def safe_write(msg: str) -> None:
    """
    Internal Thread-safe function to write to the serial port.
    @param msg: The message to send to the Arduino.
    """

    if ser and ser.is_open:
        with serial_lock:
            ser.write(f"{msg}\n\r".encode('ascii'))
            ser.flush()  # Ensure the message is sent immediately
        logging.info(f"Python -> Sent: {msg}")

def create_device(device_char: str, name: str, pins: list[int]) -> Device | None:
    """
    Creates a device of the specified type and adds it to the device dictionary.
    @param device_char: Character representing the device type (e.g., 'b' for button, 'p' for pressure sensor).
    @param name: Name of the device.
    @param pins: List of pins associated with the device. For example, a button might have one pin, while a pressure sensor might have two (data and clock).
    @return: The created device instance, or None if the device could not be created.
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
    """
    Deletes a device from the available devices. Removes it from both Arduino and Python.
    @param name: Name of the device to remove.
    """

    global device_dict, names_in_order

    # Recording check
    if recording:
        logging.warning("Cannot delete a device while recording.")
        raise Exception("Cannot detete a device while recording. Please stop recording first.")

    if name in device_dict:
        conf_event.clear()
        errr_event.clear()
        
        idx = device_dict[name].get_index()

        try:
            # Delete device from Arduino
            safe_write(f"r {idx}")

            # Error check to see if it was actually deleted
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()
            if not confirmed or errored:
                raise Exception(f"Failed to remove device {name}.")
            
            # Delete device from Python
            del device_dict[name]
            logging.info(f"Removed device '{name}'.")

            # Remove the name at the device's index
            names_in_order.pop(idx)

            # Update the index of all devices after the removed one
            for i in range(idx, len(names_in_order)):
                device_dict[names_in_order[i]].set_index(i)
            
        except Exception as e:
            logging.error(f"Error while removing device '{name}': {e}")
            raise

    else:
        logging.warning(f"Device '{name}' not found.")
        raise Exception(f"Cannot remove device. '{name}' not found.")

def toggle_data_stream() -> None:
    """
    Toggles data stream on/off. 
    """

    global data_stream_active

    safe_write("t")
    logging.info(f"Data stream {'activated' if not data_stream_active else 'deactivated'}.")
    data_stream_active = not data_stream_active

def change_data_stream_delay(delay: int) -> None:
    """
    Changes the delay between data stream updates.
    Delay is in milliseconds.
    Default is 100ms.
    """
    
    if not isinstance(delay, int) or delay < 1:
        logging.error("Tried to set an invalid data stream delay.")
        raise Exception("Delay must be an integer above 0.")
    
    safe_write(f"u {delay}")
    logging.info(f"Data stream delay set to {delay} ms.")

def update_data(datalist: list) -> None:
    """
    Internal function to update the device_dict with new status/sensor data.
    @param datalist: List of device-value pairs received from the Arduino.
    """

    global new_data_to_record
    
    # Ensure device-value pairs are complete
    if len(datalist) % 2 == 0 and len(datalist) / 2 == len(names_in_order): 

        while datalist:
            key = datalist.pop(0) # Pop first index, which is the device name
            value = datalist.pop(0) # Pop first index again, which is now its value
        
            if key in device_dict:
                device_dict[key].update(value)
            else:
                logging.warning(f"{key} not found in device_dict")
        
        # If recording is active, set the flag to record new data
        if recording:
            new_data_to_record = True

    else:
        logging.warning("Received data list is not complete or does not match device count.")
        # Silently continue, as this can happen if the Arduino sends incomplete data.

def start_recording(filename:str) -> None:
    """ 
    Starts recording data to a CSV file.
    @param filename: Name of the CSV file to record data to.
    Data stream must be active to record data.
    """

    if not data_stream_active:
        logging.error("Cannot start recording: data stream is not active.")
        raise Exception("Cannot start recording: data stream is not active. Toggle data stream first.")
    
    # Serial connection check
    if not ser or not ser.is_open:
        logging.error("Cannot start recording: serial port is not open. ")
        raise Exception("Cannot start recording: serial port is not open. Use connect() first.")
    
    start_record_thread(filename)

def stop_recording() -> None:
    """
    Stops recording data to a CSV file.
    """
    stop_record_thread()

###################################################################################################
# THREADING

def receive_data() -> None:
    # Threaded function to receive data from the Arduino.
    # Calls appropriate actions based on received data.

    logging.info("Python can now receive data from Arduino")

    while not stop_receive_event.is_set():

        if ser and ser.is_open and ser.in_waiting > 0:

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
                            update_data(data[6:-1].split())

                        case "Errr:":
                            logging.warning("Arduino -> " + data) # only warn since usually handled by Python
                            errr_event.set()

                        case "Recv:":
                            logging.info("Arduino -> " + data) # For logging/debugging purposes only

                        case _:
                            logging.error("Received data not matched: " + data)

            except Exception as e:
                logging.error(f"Error while receiving data: {e}")

        time.sleep(0.002)  # Sleep for a short time to avoid busy waiting

def start_receive_thread():
    # Internal function to start a thread to receive data from the Arduino.

    global thread_receive_data

    # Check if called when thread already exists
    if thread_receive_data and thread_receive_data.is_alive():
        logging.info("Stopping existing receive thread before starting a new one.")
        stop_receive_thread() # Delete thread so it can be created again

    stop_receive_event.clear()

    thread_receive_data = threading.Thread(target=receive_data, daemon=True)
    thread_receive_data.start()

def stop_receive_thread():
    # Internal function to stop the thread that receives data from the Arduino.

    global thread_receive_data

    stop_receive_event.set()

    if thread_receive_data and thread_receive_data.is_alive():
        thread_receive_data.join(timeout=1)  # give it a second to clean up
        logging.info("Receive thread stopped.")
    else:
        logging.info("Receive thread was not running or already stopped.")
    thread_receive_data = None

def record_data_to_csv(filename: str) -> None:
    # Threaded function to record device data stream to a CSV file.
    # While recording is active, the following is disabled:
    # - Creating or removing devices
    # - Turning off data stream

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
                        row_list.append(device_dict[name].read())
                    writer.writerow(row_list)
                    new_data_to_record = False  # Reset the flag after writing
                else:
                    time.sleep(0.002) # Sleep for a short time to avoid busy waiting
        
        except Exception as e:
            logging.error(f"Error while recording data: {e}")
            raise

def start_record_thread(filename: str):
    # Internal function to start a thread to record data to a CSV file.

    global thread_record_data, recording

    # Check if called when thread already exists
    if thread_record_data and thread_record_data.is_alive():
        logging.error("Cannot start recording: already recording data.")
        raise Exception("Cannot start recording: already recording data. Please stop recording first.")

    # Clear the stop event to ensure the thread can start
    stop_record_event.clear()

    thread_record_data = threading.Thread(target=record_data_to_csv, args=(filename,), daemon=True)
    thread_record_data.start()

    recording = True

def stop_record_thread():  
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

    