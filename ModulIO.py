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

class Device:
    def __init__ (self, char, name, pins):
        global conf_event
        global errr_event
        conf_event.clear()
        errr_event.clear()

        self.value = None
        self.index = None
        self.name = None
        self.pin = None
        
        global ser
        try:
            # Convert list of pins into string separating pins with spaces
            pin_str = " ".join(map(str, pins)) if isinstance(pins, list) else str(pins)

            ser.write(f"s {char} {name} {pin_str}\r\n".encode())

            # error check before confirming device
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()

            if not confirmed or errored:
                raise Exception(f"Device {name} failed to initialize")

            self.name = name
            self.pin = pin_str

            global num_devices
            self.index = num_devices
            num_devices += 1

            global names_in_order
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
        ser.write(f"c {self.index} {value}\r\n".encode())

    def update(self, value):
        # Internal function for the sake of updating the device with its latest value.
        self.value = value

    def set_index(self, new_idx):
        # Internal function to change the index of the device. Used when another device is deleted.
        self.index = new_idx


ser = None # Serial connection instance

device_dict = {} # Names to device instances
names_in_order = [] # Names in order of indexes
num_devices = 0  # Global counter for devices

conf_event = threading.Event() # Signifies action confirmed
errr_event = threading.Event() # Signifies error
stop_event = threading.Event() # Tells receive data thread to stop

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
    global ser
    try:
        ser = serial.Serial(port, 115200, timeout=10)
        print(f"Connected to {port}.")
        thread_receive_data.start()
    except Exception as e:
        print(f"Error connecting to {port}: {e}")

def disconnect() -> None:
    global ser
    if ser and ser.is_open:
        ser.close()
        print("Disconnected.")
        stop_event.set() # For reeive_data thread

    else:
        print("Serial port is not open or already closed.")

def create_device(device_type: str, name: str, pins: list[int]) -> Device | None:
    global device_dict

    if device_type == "Button":
        device = ButtonDevice(name, pins[0])
    elif device_type == "PressureSensor":
        device = PressureSensorDevice(name, pins[0], pins[1]) # data pin, clock pin
    elif device_type == "LED":
        device = LEDDevice(name, pins[0])
    elif device_type == "DCMotor":
        device = DCMotorDevice(name, pins[0])
    
    else:
        print(f"Unknown device type: {device_type}")
        return
    
    if device:
        device_dict[name] = device
        print(f"Added {device_type} '{name}' on pin(s) {pins}.")
        return device
    else:
        print(f"Failed to add {device_type} '{name}'.")

def remove_device(name: str) -> None:
    # Deletes a device from the available devices.
    # Removes it from both Arduino and Python.
    global ser
    global device_dict
    global num_devices
    global names_in_order
    global conf_event
    global errr_event

    if name in device_dict:

        conf_event.clear()
        errr_event.clear()
        
        idx = device_dict[name].index

        try:
            # Delete device from Arduino
            ser.write(f"r {idx}".encode())

            # Error check to see if it was actually deleted
            confirmed = conf_event.wait(timeout=2)
            errored = errr_event.is_set()

            if not confirmed or errored:
                raise Exception(f"Failed to remove device {name}.")
            
            # Delete device from Python
            del device_dict[name]
            print(f"Removed device '{name}'.")

            # Remove the name at the device's index
            names_in_order.pop(idx)

            # Update the index of all devices after the removed one
            for i in range(idx, len(names_in_order)):
                device_dict[names_in_order[i]].set_index(i)
            
        except Exception as e:
            print(e) 

    else:
        print(f"Device '{name}' not found.")


def toggle_data_stream(period=None) -> None:
    # Toggles data stream on/off. 
    # If period is specified, sets delay between messages. Default is 100ms.
    # Period will continue to be the set value until changed again.
    if period:
        ser.write(f"t {period}\r\n".encode())
    else:        
        ser.write("t\r\n".encode())

def update_data(datalist: list) -> None:
    # Internal function to update the device_dict with new status/sensor data.
    if len(datalist) % 2 == 0: 
        while datalist:
            key = datalist.pop()
            value = datalist.pop()
        
            if key in device_dict:
                device_dict[key].update(value)
            else:
                print(f"Warning: {key} not found in device_dict")  
    else:
        print("Data list must have an even number of elements")

###################################################################################################
# THREADING

def receive_data() -> None:
    global ser
    global conf_event
    global errr_event
    global stop_event

    while not stop_event.is_set():
        if ser and ser.is_open and ser.in_waiting > 0:
            try:
                data = ser.readline().decode('utf-8').strip()
                if data:

                    match data[0:5]:
                        case "Conf:":
                            print(data[5:])
                            conf_event.set()
                        case "Data:":
                            assert data.endswith(";"), "Incomplete data (missing semicolon)"
                            update_data(data[6:-1].split())
                        case "Errr:":
                            print("Error: ", data[6:])
                            errr_event.set()
                        case "Recv:":
                            pass

            except Exception as e:
                print(f"Error while receiving data: {e}")

thread_receive_data = threading.Thread(target=receive_data, daemon=True)
