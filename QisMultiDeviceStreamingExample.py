'''
AN-032 - Application note demonstrating automated control of multiple power devices via QIS

Automating via QIS is a lower overhead than running QPS (Quarch Power Studio) in full but still
provides easy access to data for custom processing.  This example uses Quarchpy functions to set up
multiple power devices for streaming via QIS.

There are several examples that run in series, these can be commented out if you want to simplify the actions:

simple_multi_stream_example() - This example streams each modules stream data to a unique python data structure and then
outputs the data to a csv file "{module-name}.csv"
multi_device_live_monitoring_example - This example showcases live monitoring for select stream data

QIS is distributed as part of the Quarchpy python package and does not require separate install

########### VERSION HISTORY ###########

25/03/2025 - Nabil Ghayyda  - First Version

########### REQUIREMENTS ###########

1- Python (3.x recommended)
    https://www.python.org/downloads/
2- Java 21, with JaxaFX
    https://quarch.com/support/faqs/java/
3- Quarchpy python package
    https://quarch.com/products/quarchpy-python-package/
4- Quarch USB driver (Required for USB connected devices on windows only)
    https://quarch.com/downloads/driver/
5- Check USB permissions if using Linux:
    https://quarch.com/support/faqs/usb/

########### INSTRUCTIONS ###########

1. Connect multiple Quarch power modules via USB/Ethernet.
2. Edit the script and hard-code the modules you'd like to stream with (edit myDeviceIDs list).
3. Run the script and follow any instructions on the terminal

####################################
'''
import os

# Import other libraries used in the examples
import time  # Used for sleep commands
# import logging  # Optionally used to create a log to help with debugging

from quarchpy.device import *
from quarchpy.qis import *

from io import StringIO
from threading import Thread

# Global variables to store last values and stream status
csv_data_io = []  # Store stream data in memory
last_values = {}  # Cache last values for each channel
stream_running = False

# Hardcoded list to hold all module ID's you'd like to stream with.
myDeviceIDs = [
    'TCP:QTL2789-01-001',
    'TCP:QTL2789-01-002',
    'TCP:QTL2582-01-005',
    'TCP:QTL2582-01-006',
    'TCP:QTL2843-03-002',
    'TCP:QTL2751-02-002',
    'TCP:QTL2751-01-001'
]


def main():
    # If required you can enable python logging, Quarchpy supports this and your log file
    # will show the process of scanning devices and sending the commands.  Just comment out
    # the line below.  This can be useful to send to quarch if you encounter errors
    # logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)

    print("\n\nQuarch application note example: AN-032")
    print("---------------------------------------\n\n")

    # Start QIS (if it is already running, skip this step and also avoid closing it at the end)
    print("Starting QIS...\n")
    closeQisAtEndOfTest = False
    if isQisRunning() is False:
        startLocalQis()
        closeQisAtEndOfTest = True

    # Connect to the localhost QIS instance
    myQis = QisInterface()
    print("QIS Version: " + myQis.sendAndReceiveCmd(cmd='$version'))

    # List of "quarchPPM" objects, this extends the base device class to a power device to provide additional control.
    myPowerDevices = {}

    for i in range(len(myDeviceIDs)):
        # Connect to the module
        myQuarchDevice = getQuarchDevice(myDeviceIDs[i], ConType="QIS", timeout=30)

        # Show which device you have connected to.
        print(f"Connected to Module: " + myDeviceIDs[i])

        # Convert the base device class to a power device, which provides additional controls, such as data streaming
        # The power class now also automatically sets up the default synthetic channels - to disable them simply pass skipDefaultSyntheticChannels=True
        myPowerDevice = quarchPPM(myQuarchDevice)
        # Add power device to list
        myPowerDevices[i] = myPowerDevice
        # Generate a new StringIO object for each power module
        csv_data_io.append(StringIO())

    # Select one or more example functions to run, you can comment any of these out if you do not want to run them
    simple_multi_stream_example(myPowerDevices)
    multi_device_live_monitoring_example(myPowerDevices)

    if closeQisAtEndOfTest:
        closeQis()


'''
This example streams measurement data from each module to a file for each module, by default in the same folder as the script
'''


# Setup each power module and start streaming
def simple_multi_stream_example(modules):
    global stream_running

    print("\n Simple Multi Device Streaming Example \n")

    # Loop through all set devices in hard-coded list
    for i in range(len(myDeviceIDs)):
        print(f"\nSetting QIS resampling to 1mS on module: {myDeviceIDs[i]}")
        modules[i].streamResampleMode("1mS")

        # Start the recording and set the stream duration to 30 seconds to ensure all modules stream for the same amount of time.
        print(f"Started Recording on module: {myDeviceIDs[i]}\n")
        modules[i].startStream(inMemoryData=csv_data_io[i], fileName=None, streamDuration=30)

    print("\nWait for 30 seconds...\n")
    time.sleep(30)

    for i in range(len(myDeviceIDs)):
        # Stop the stream
        print(f"\nStopping the stream on module: {myDeviceIDs[i]}")
        modules[i].stopStream()

        # Check stream status
        check_stream_status(modules[i])

        # Print & output the acquired data to a csv file "stream-date.csv"
        process_qis_data(get_device_id(myDeviceIDs[i]), csv_data_io[i])


def multi_device_live_monitoring_example(modules):
    global stream_running

    print("\n Multi Device Live Monitoring Example \n")

    for i in range(len(myDeviceIDs)):
        print(f"\nSetting QIS resampling to 500mS on module {myDeviceIDs[i]}")
        modules[i].streamResampleMode("500mS")

        # Start the recording and set the stream duration to 30 seconds to ensure all modules stream for the same amount of time.
        print(f"Started Recording on module: {myDeviceIDs[i]}\n")
        modules[i].startStream(inMemoryData=csv_data_io[i], fileName=None, streamDuration=30)

    stream_running = True
    # Start a separate thread to read and cache stream data every second
    thread = Thread(target=read_and_print_last_values, daemon=True)
    thread.start()

    print("\nWait for 30 seconds...\n")
    time.sleep(30)

    # Ensure global variable is set too false to stop the live data coming through.
    stream_running = False

    for i in range(len(myDeviceIDs)):
        # Stop the stream
        print(f"\nStopping the stream on module: {myDeviceIDs[i]}")
        modules[i].stopStream()

        # Process final stream data and update cache
        process_stream_data()

        # Check stream status
        check_stream_status(modules[i])


# Function to cache the last sample for each column
def process_stream_data():
    for i in range(len(csv_data_io)):
        csv_data_io[i].seek(0)  # Rewind to the start of the CSV data
        lines = csv_data_io[i].readlines()  # Read all lines
        if lines:
            headers = lines[0].strip().split(',')  # Extract headers from first line
            last_line = lines[-1].strip().split(',')  # Extract the last line of data
            for j, header in enumerate(headers):
                if header != "" and header is not None:  # Only process non-empty headers
                    last_values[f'{get_device_id(myDeviceIDs[i])} {header}'] = last_line[
                        j]  # Cache the last sample for each valid column


# API to request the last value by channel name
def get_last_value(channel_name):
    return last_values.get(channel_name, None)


# Continuously read and print last values during the stream every second
def read_and_print_last_values():
    while stream_running:
        # Process the latest stream data to update the cache
        process_stream_data()

        for device_id in myDeviceIDs:
            # Get and print last values for L1 RMS Voltage, Current and Power
            l1_rms_voltage = get_last_value(f"{get_device_id(device_id)} L1_RMS mV")
            l1_rms_current = get_last_value(f"{get_device_id(device_id)} L1_RMS mA")
            l1_p_app = get_last_value(f"{get_device_id(device_id)} Tot_PApp mVA")

            if l1_rms_voltage or l1_rms_current or l1_p_app:
                print(
                    f"{get_device_id(device_id)} L1 RMS Voltage: {l1_rms_voltage}, L1 RMS Current: {l1_rms_current}, Total Apparent Power: {l1_p_app}")
        print('\n')
        time.sleep(1)


# Check stream status and ensure no interruptions
def check_stream_status(module):
    print("Checking the stream is running (all data has been captured)")
    stream_status = module.streamRunningStatus()
    if "Stopped" in stream_status:
        if "Overrun" in stream_status:
            print("\tStream interrupted due to internal device buffer filling up")
        elif "User" in stream_status:
            print("\tStream Stopped")
        else:
            print("\tStopped for unknown reason")
    else:
        print("\tStream ran correctly")


def process_qis_data(device_id, csv_data_io_data):
    # Get the entire contents of the buffer as a string
    # csv_data_string = csv_data_io_data.getvalue()

    # # DEBUG - Print Header and CSV Data as a List
    # print("\nIn-Memory Data acquired from QIS: \n")
    #
    # # Print all csv data (for debugging)
    # print(csv_data_string)

    print(f"\nProcessing Stream Data for Module: {device_id}")

    # Move cursor to the beginning of the StringIO object
    csv_data_io_data.seek(0)

    # Get the current directory (where the script is located)
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the file path for the CSV file in the same directory as the script
    csv_file_path = os.path.join(current_dir, f'{device_id}.csv')

    # Output content of returned QIS data to a csv file
    with open(csv_file_path, 'w', newline='') as csv_file:
        csv_file.write(csv_data_io_data.getvalue())

    print(f"QIS Stream Data Saved to CSV File: {csv_file_path}\n")

def get_device_id(device_id):
    return device_id.replace("TCP:", "")


# Calling the main() function
if __name__ == "__main__":
    main()
