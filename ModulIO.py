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
import csv

class Device:
    def __init__ (self, char, name, pins):
        global conf_event
        conf_event.clear()
        global errr_event
        errr_event.clear()

        self.value = None
        self.index = None
        self.name = None
        self.pin = None
        
        global ser
        try:
            # Convert list of pins into string separating pins with spaces
            pin_str = " ".join(map(str, pins)) if isinstance(pins, list) else str(pins)

            safe_write(f"s {char} {name} {pin_str}\r\n")

            # error check before confirming device
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()
            if not confirmed or errored:
                raise Exception(f"Device {name} failed to initialize")

            self.name = name
            self.pin = pin_str

            global names_in_order
            self.index = len(names_in_order)
            names_in_order.append(name)

            self.value = None # will be filled by thread_receive_data

        except Exception as e:
            print(f"Failed to initialize device {name}: {e}")
            raise

    def read(self):
        # Callable function to read the value of the device (both sensors & actuators).
        # Sensors display their sensed value, while actuators display their current state.
        return self.value
    
    def write(self, value):
        # Callable function to change the value of the device, if it is an actuator.
        safe_write(f"c {self.index} {value}\r\n")

    def update(self, value):
        # Internal function to update the device with its latest value.
        self.value = value

    def get_index(self):
        # Internal function to get the index of the device.
        return self.index

    def set_index(self, new_idx):
        # Internal function to change the index of the device. Used when another device is deleted.
        self.index = new_idx


# Serial setup
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

###################################################################################################  
# DEVICE CLASSES

class ButtonDevice(Device):
    def __init__ (self, name, pin):
        super().__init__("b", name, pin)

class PressureSensorDevice(Device):
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

def connect(port: str) -> None:
    # Connects to the specified serial port.
    try:
        global ser
        ser = serial.Serial(port, 115200, timeout=10)
        print(f"Connected to {port}.")
        
        start_receive_thread() # Start thread to read messages from Arduino

    except Exception as e:
        print(f"Error connecting to {port}: {e}")

def disconnect() -> None:
    # Disconnects from the currently connected serial port.

    # Recording check
    global recording
    if recording:
        print("Cannot perform this action while recording.")
        return

    stop_receive_thread()

    global ser
    if ser and ser.is_open:
        ser.close()
        print("Disconnected.")

    else:
        print("Serial port is not open or already closed.")

def safe_write(msg: str) -> None:
    # Thread-safe function to write to the serial port.
    global ser
    if ser and ser.is_open:
        global serial_lock
        with serial_lock:
            ser.write(msg.encode())

def create_device(device_char: str, name: str, pins: list[int]) -> Device | None:
    # Creates a device of the specified type and adds it to the device dictionary.

    # Recording check
    global recording
    if recording:
        print("Cannot perform this action while recording.")
        return
    
    # Name check
    global names_in_order
    if name in device_dict:
        print(f"Device '{name}' already exists. Please choose a different name.")
        return
    
    # Device number check
    global MAX_DEVICES
    if len(names_in_order) >= MAX_DEVICES:
        print(f"Maximum number of devices ({MAX_DEVICES}) reached. Cannot add more devices.")
        return

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
            print(f"Unknown device type: {device_char}")
            return
        
    type_map = {"b": "Button", "p": "PressureSensor", "l": "LED", "m": "DCMotor"} # For printed message
    
    if device: # If a device is created successfully
        global device_dict
        device_dict[name] = device

        # Print confitrmation message
        print(f"Added {type_map.get(device_char)} '{name}' on pin(s) {pins}.")

        return device
    else:
        print(f"Failed to add {type_map.get(device_char)} '{name}'.")

def remove_device(name: str) -> None:
    # Deletes a device from the available devices. Removes it from both Arduino and Python.

    # Recording check
    global recording
    if recording:
        print("Cannot perform this action while recording.")
        return

    global device_dict
    if name in device_dict:
        global conf_event
        conf_event.clear()
        global errr_event
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
            print(f"Removed device '{name}'.")

            # Remove the name at the device's index
            global names_in_order
            names_in_order.pop(idx)

            # Update the index of all devices after the removed one
            for i in range(idx, len(names_in_order)):
                device_dict[names_in_order[i]].set_index(i)
            
        except Exception as e:
            print(e) 

    else:
        print(f"Device '{name}' not found.")

def toggle_data_stream() -> None:
    # Toggles data stream on/off. 
    safe_write("t\r\n")
    
    global data_stream_active
    data_stream_active = not data_stream_active

def change_data_stream_delay(delay: int) -> None:
    # Changes the delay between data stream updates.
    # Delay is in milliseconds.
    # Default is 100ms.
    
    if not isinstance(delay, int) or delay < 1:
        print("Error: Delay must be an integer above 0.")
        return
    
    safe_write(f"u {delay}\r\n")
    print(f"Data stream delay set to {delay} ms.")

def update_data(datalist: list) -> None:
    # Internal function to update the device_dict with new status/sensor data.
    
    # Ensure device-value pairs are complete
    global names_in_order
    if len(datalist) % 2 == 0 and len(datalist) / 2 == len(names_in_order): 
        
        while datalist:
            key = datalist.pop()
            value = datalist.pop()
        
            if key in device_dict:
                device_dict[key].update(value)
            else:
                print(f"Warning: {key} not found in device_dict")  
        
        # If recording is active, set the flag to record new data
        global recording
        if recording:
            global new_data_to_record
            new_data_to_record = True

    else:
        print("Error: Received data list is not complete or does not match device count.")

def start_recording(filename:str) -> None:
    # Starts recording data to a CSV file.
    # If filename is not specified, defaults to "data.csv".

    # Data stream must be active to record data.
    global data_stream_active
    if not data_stream_active:
        print("Cannot start recording: data stream is not active.")
        return
    
    # Recording check
    global recording
    if recording:
        print("Already recording data.")
        return
    
    # Serial connection check
    global ser
    if not ser or not ser.is_open:
        print("Serial port is not open. Cannot start recording.")
        return
    
    if filename:
        start_record_thread(filename)
    else:
        start_record_thread("data.csv")

def stop_recording() -> None:
    # Stops recording data to a CSV file.
    stop_record_thread()

###################################################################################################
# THREADING

def receive_data() -> None:
    # Threaded function to receive data from the Arduino.
    # Calls appropriate actions based on received data.

    global stop_receive_event
    while not stop_receive_event.is_set():
        
        global ser
        if ser and ser.is_open and ser.in_waiting > 0:
            
            try:
                data = ser.readline().decode('utf-8').strip()
                
                if data:
                    match data[0:5]:
                        case "Conf:":
                            print(data[6:])
                            global conf_event
                            conf_event.set()

                        case "Data:":
                            # Check for complete data
                            assert data.endswith(";"), "Incomplete data (missing semicolon)"
                            # Pass data to device instances
                            update_data(data[6:-1].split())

                        case "Errr:":
                            print("Error: ", data[6:])
                            global errr_event
                            errr_event.set()

                        case "Recv:":
                            pass # No logic needed here

            except Exception as e:
                print(f"Error while receiving data: {e}")

def start_receive_thread():
    # Internal function to start a thread to receive data from the Arduino.

    # Check if called when thread already exists
    global thread_receive_data
    if thread_receive_data and thread_receive_data.is_alive():
        stop_receive_thread() # Delete thread so it can be created again

    stop_receive_event.clear()

    thread_receive_data = threading.Thread(target=receive_data, daemon=True)
    thread_receive_data.start()

def stop_receive_thread():
    # Internal function to stop the thread that receives data from the Arduino.

    stop_receive_event.set()

    global thread_receive_data
    if thread_receive_data.is_alive():
        thread_receive_data.join(timeout=1)  # give it a second to clean up

def record_data_to_csv(filename: str) -> None:
    # Threaded function to record device data stream to a CSV file.
    # While recording is active, the following is disabled:
    # - Creating or removing devices
    # - Turning off data stream

    with open(filename, mode='w', newline='') as csvfile:

        print(f"Recording data to {filename}...")

        writer = csv.writer(csvfile)

        global names_in_order
        fieldnames = ['Time'] + names_in_order # List for CSV header

        writer.writerow(fieldnames)

        try:
            global stop_record_event
            global new_data_to_record
            global device_dict
            while not stop_record_event.is_set:
                if new_data_to_record:
                    row_list = [datetime.now().strftime("%H:%M:%S.%f")[:-3]]
                    for name in names_in_order:
                        row_list.append(device_dict[name].read())
                    writer.writerow(row_list)
                    new_data_to_record = False  # Reset the flag after writing
                else:
                    # Sleep for a short time to avoid busy waiting
                    threading.Event().wait(0.010)  # 10 ms
        
        except Exception as e:
            print(f"Error while recording data: {e}")

def start_record_thread(filename: str):
    # Internal function to start a thread to record data to a CSV file.

    # Check if called when thread already exists
    global thread_record_data
    if thread_record_data and thread_record_data.is_alive():
        stop_record_thread()  # Delete thread so it can be created again

    # Clear the stop event to ensure the thread starts fresh
    global stop_record_event
    stop_record_event.clear()

    thread_record_data = threading.Thread(target=record_data_to_csv, args=(filename,), daemon=True)
    thread_record_data.start()

    global recording
    recording = True

def stop_record_thread():  
    # Internal function to stop the thread that records data to a CSV file.

    global stop_record_event
    stop_record_event.set()

    global recording
    recording = False

    global thread_record_data
    if thread_record_data.is_alive():
        thread_record_data.join(timeout=1)  # give it a second to clean up
        print("Recording stopped.")