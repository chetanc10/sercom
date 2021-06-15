#!/bin/env python

######################### Import required python modules/submodules
import os
import sys
import serial
import time
import re
import platform
import datetime

# Making this script version-agnostic, we need version number to abstract
# and call version-specific Serial/File IO and other API functions
pyver = platform.python_version()

from serial import Serial
from datetime import datetime

# Uncomment/Comment out the following to debug/run-normally the python script
#import pdb; pdb.set_trace ()

# Actual script execution starts at SOPS. Find SOPS
######################### Serial-Port-Handler-Environment (SPHE)

# cmd_src_types
CmdFromScript = 0
CmdFromStdIn = 1

DevicePortNumber = "undefined"
BaudRate = 115200

# Log file handle
logfile = "undefined"
# Flag to control logging of Serial IN/OUT data into a logfile
LogSerialDataTimestamp = 1

# List of allowed baud rates
AllowedBaudRates = [110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

######################### Serial communication and logging helper functions

# Function to get current date & time in format: Feb  9 22:38:33
# Usage  : GetTimestamp
# Return : Stringized current date and time
def GetTimestamp () :
    if LogSerialDataTimestamp == 1 :
        timestamp = datetime.now ()
        return timestamp.strftime ("%b %d %H:%M:%S")
    else :
        return ""

# Function to receive data over Serial port in python-version independent way
# Usage  : RecvSerialData (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String containing the data received on serial port
def RecvSerialData (SerialPort) :
    if pyver.startswith("3.") :
        Data = SerialPort.read (100).decode ()
    else :
        Data = SerialPort.read (100)
    return Data

# Function to send data over Serial port in python-version independent way
# Usage  : SendSerialData (SerialPort, buf)
#          SerialPort - Serial Port Interface handle
#          buf        - buffer containing data to be send over serial port
# Return : number of data bytes sent over the serial port
def SendSerialData (SerialPort, buf) :
    if pyver.startswith("3.") :
        numTxBytes = SerialPort.write (buf.encode ())
    else :
        numTxBytes = SerialPort.write (buf)
    SerialPort.flush ()
    return numTxBytes

# Function to read console (stdin) input from use bring python-version-agnostic
# Usage  : ReadConsoleInput ()
# Return : Console input data given by user from stdin console
def ReadConsoleInput () :
    if pyver.startswith("3.") :
        return input ("")
    else :
        return raw_input ("")

# Function to strip the Command from the Response
# Usage  : StripStartOfString (buf)
#          buf        - buffer containing data to be processed
# Return : Stripped string
def StripStartOfString (buf) :
    _rule = re.compile (r'([^\n]+)')
    stripStr = re.search(_rule, buf).group(1) + "\n"
    buf = buf[len (stripStr):]
    return buf


# Function to recv complete response with OK/ERROR with 10 second timeout
# Usage  : RecvFullResponse (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String buffer containing Serial data received
def RecvFullResponse (SerialPort) :
    Resp = ""
    numRetries = 10
    while 1:
        RxChunk = RecvSerialData (SerialPort)
        if (len (RxChunk) == 0) :
            numRetries -= 1
            if numRetries == 0 :
                break
            else :
                time.sleep (1)
                continue
        else :
            numRetries = 10
        Resp += RxChunk
        if "ERROR" in RxChunk or "OK" in RxChunk :
            break
    return Resp

# Function to handle a Command-Response session
# Usage  : HandleCmdAndGetResp (SerialPort, Cmd, CmdSrc)
#          SerialPort - Serial Port Interface handle
#          Cmd        - Command string
#          CmdSrc     - refer cmd_src_types
# Return : String buffer containing Serial data received
def HandleCmdAndGetResp (SerialPort, Cmd, CmdSrc) :
    Cmd = Cmd + "\r"
    logfile.write (GetTimestamp () + " [O] " + repr (Cmd) + "\n")
    SendSerialData (SerialPort, Cmd)
    Resp = RecvFullResponse (SerialPort)
    if not "ERROR" in Resp and not "OK" in Resp :
        errStr = "***SERROR: " + Cmd + " Timed-out with no/incomplete response\n"
        print (errStr)
        logfile.write (errStr)
    if len (Resp) != 0 :
        logfile.write (GetTimestamp () + " [I] " + repr (Resp) + "\n")
        if CmdSrc == CmdFromStdIn :
            Resp = StripStartOfString (Resp)
        print (Resp)
    logfile.flush ()
    sys.stdout.flush ()
    # This print statement is to separate console prints per command
    print ("-----------------")
    return Resp

######################### Start-Of-Python-Script (SOPS)

# Validate argument count
if len(sys.argv) < 3 :
    Usage = "Usage: " + sys.argv[0] + " <Device#> <BaudRate>\nDevice# : Linux - /dev/ttyx for the detected serial port (known using dmesg|tail)\n          Windows - COMx for the detected serial port (known using device manager)\n"
    sys.exit (Usage)

DevicePortNumber = sys.argv[1]
BaudRate = int (sys.argv[2])

# Validate given BaudRate value
if BaudRate not in AllowedBaudRates:
    sys.exit ("ERROR: Invalid BaudRate " + str (BaudRate))

# Configure and open Serial Port
if pyver.startswith("3.") :
    SerialPort = serial.Serial(port=DevicePortNumber, baudrate=BaudRate, inter_byte_timeout=0.2, timeout=0.01)
else :
    SerialPort = serial.Serial(port=DevicePortNumber, baudrate=BaudRate, interCharTimeout=0.01, timeout=0.01)

logfile = open("logFile.txt", "w")

# Validate basic command before actual serial communication
Resp = HandleCmdAndGetResp (SerialPort, "AT", CmdFromScript)
if "OK" not in Resp :
    SerialPort.close ()
    logfile.close ()
    sys.exit ("***SERROR: Basic AT-OK session failed .. Aborting!")

# Controlled loop to enable manual command entry from stdin
while 1 :
    Cmd = ReadConsoleInput ()
    if len (Cmd) == 0 :
        continue
    if Cmd == "exit" :
        SerialPort.close ()
        logfile.close ()
        quit ()
    if Cmd == "break" :
        break
    HandleCmdAndGetResp (SerialPort, Cmd, CmdFromStdIn)

SerialPort.close ()
logfile.close ()
quit ()

