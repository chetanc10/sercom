#!/bin/env python

sercomUsageStr = "\n\
Usage: sercom.py <args> [optionals]\n\
args:\n\
     -d <Device#>   : Linux - /dev/ttyx of detected serial port (check dmesg|tail)\n\
                      Windows - COMx of detected serial port (check Device Manager)\n\
optionals: If any optional is not given, corresponsing Default setting is applied\n\
     -a <AutoCmdFile> : Automatic command sequence to be taken from a .scom type file\n\
                      Default - No Auto commands are applicable\n\
                      NOTE: .scom file has specific syntax.\n\
                            It can force enable Manual command entry with ''.\n\
                            Refer example.scom for help\n\
     -m             : Force enable Manual entry of commands from stdin console\n\
                      Default - Enabled if NO valid Auto-Command-Sequence is selected\n\
                              - Disabled if a valid Auto-Command-Sequence is selected\n\
                      NOTE: It can even enable Auto command mode with 'AutoCmd'.\n\
     -b <BaudRate>  : Baud rate of serial port device\n\
                      Default - 115200\n\
     -l             : Enables logging of commands/responses into com.log in PWD\n\
                      If not specified, logging is disabled\n\
                      Default - Disabled\n\
NOTE:\n\
1. To (re-)enable AutoCmd mode from Manual or Auto mode (one AutoCmd run disables AutoCmd mode), use following cmd in Manual command line and at End of AutCmdFile : EnableAutoCmd <path-to-AutoCmd-File>\n\
1. To (re-)enable ManualCmd mode from Auto mode, use following cmd at End of AutoCmdFile: EnableManualCmd\n\
"

######################### Import required python modules/submodules
import os
import sys
import serial
import time
import re
import platform
import getopt
import os.path
import logging
import functools

from functools import partial

# Making this script version-agnostic, we need version number to abstract
# and call version-specific Serial/File IO and other API functions
gPyVer = platform.python_version()

from serial import Serial

# Uncomment/Comment out the following to debug/run-normally the python script
#import pdb; pdb.set_trace ()

# Actual script execution starts at SOPS. Find SOPS
######################### Serial-Port-Handler-Environment (SENV)

### Environment setup/control
# refer -d option in sercomUsageStr
gSerPortID = "undefined"
# refer -a option in sercomUsageStr
gAutoCmdEnabled = False
# Auto Command container file path/name
gAutoCmdFile = "undefined"
# refer -m option in sercomUsageStr
gManualCmdEnabled = 1
# refer -b option in sercomUsageStr
gBaudRate = 115200
# Logging control
gLoggingEnabled = False
# Timeout for full response reception with OK/ERROR
gFullRespTout = 20
# Response timeout indication flag set/unset for every fresh ATCmdResp session
gRespTimedOut = False

### Other types/variables used internally 
# cmd_src_types
CmdFromScript = 0
CmdFromStdIn = 1
# Serial port IO handle
gSerPort = "undefined"
# Log file handle
gLogger = 1
# Name of Log file name
gLogFileName = "com.log"
# List of allowed baud rates
AllowedBaudRates = [110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

######################### Helper/Handler Functions for Serial communication and logging

# Function to log IO data or any debug/error messages to a log file
# Usage  : logmsg (msg)
#          msg - message to be stored in log file
# Return : None
def logmsg (msg) :
    if gLoggingEnabled :
        gLogger.debug (msg)

# Function to receive data over Serial port in python-version independent way
# Usage  : RecvSerialData (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String containing the data received on serial port
def RecvSerialData (SerialPort) :
    if gPyVer.startswith("3.") :
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
    if gPyVer.startswith("3.") :
        numTxBytes = SerialPort.write (buf.encode ())
    else :
        numTxBytes = SerialPort.write (buf)
    SerialPort.flush ()
    return numTxBytes

# Function to read console (stdin) input from use bring python-version-agnostic
# Usage  : ReadConsoleInput (prompt)
#          prompt     - prompt string (optional)
# Return : Console input data given by user from stdin console
def ReadConsoleInput (prompt) :
    if gPyVer.startswith("3.") :
        return input (prompt)
    else :
        return raw_input (prompt)

# Function to strip the Command from the Response
# Usage  : StripStartOfString (buf)
#          buf        - buffer containing data to be processed
# Return : Stripped string
def StripStartOfString (buf) :
    _rule = re.compile (r'([^\n]+)')
    stripStr = re.search(_rule, buf).group(1) + "\n"
    buf = buf[len (stripStr):]
    return buf

# Function to recv complete response with OK/ERROR with 'gFullRespTout' second timeout
# Usage  : RecvFullResponse (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String buffer containing Serial data received
def RecvFullResponse (SerialPort) :
    global gRespTimedOut
    Resp = ""
    numRetries = gFullRespTout
    gRespTimedOut = False
    while 1 :
        RxChunk = RecvSerialData (SerialPort)
        if len (RxChunk) == 0 :
            numRetries -= 1
            if numRetries == 0 :
                # Timeout with no reception! Break the loop
                gRespTimedOut = True
                break
            # Wait..! There's still time for response!
            time.sleep (1)
            continue
        numRetries = gFullRespTout
        Resp += RxChunk
        if "\r\nERROR\r\n" in Resp or "\r\nOK\r\n" in Resp or "\r\n+CME ERROR:" in Resp :
            break
    return Resp

# Function to handle a Command-Response session
# Usage  : HandleCmdAndGetResp (SerialPort, Cmd, CmdSrc)
#          SerialPort - Serial Port Interface handle
#          Cmd        - Command string
#          CmdSrc     - refer cmd_src_types
# Return : String buffer containing Serial data received
def HandleCmdAndGetResp (SerialPort, Cmd, CmdSrc) :
    _cmd = Cmd
    Cmd = Cmd + "\r"
    if CmdSrc == CmdFromScript :
        print (Cmd)
    CmdSrcIDList = ["A", "M"]
    CmdSrcID = CmdSrcIDList[CmdSrc]
    logmsg ("[" + CmdSrcID +  "O] " + repr (Cmd))
    SendSerialData (SerialPort, Cmd)
    Resp = RecvFullResponse (SerialPort)
    if gRespTimedOut == True :
        errStr = "***SERROR: Cmd \"" + _cmd + "\" Timed-out with no/incomplete response\n"
        print (errStr)
        logmsg (errStr)
    elif len (Resp) != 0 :
        Resp = StripStartOfString (Resp)
        logmsg ( "[" + CmdSrcID + "I] " + repr (Resp))
        print (Resp)
    # This print statement is to separate console prints per command
    print ("-----------------")
    sys.stdout.flush ()
    return Resp

######################### Application Functions for Modem communication handling

# Function to have a controlled loop for handling manual command from stdin
# Usage  : HandleManualCmds ()
# Return : None
def HandleManualCmds () :
    global gManualCmdEnabled
    global gAutoCmdEnabled
    global gAutoCmdFile

    while 1 :
        Cmd = ReadConsoleInput ("")
        if len (Cmd) == 0 :
            continue
        if Cmd[0:2].lower () == "at" :
            HandleCmdAndGetResp (gSerPort, Cmd, CmdFromStdIn)
        elif Cmd[0:5] == "break" :
            break
        elif Cmd[0:5] == "sleep" :
            break
        elif Cmd[0:13] == "EnableAutoCmd" :
            arg = Cmd.split(" ")[1:][0]
            if len (arg) == 0 or os.path.isfile (arg) == False or arg[-5:] != ".scom" :
                print ("\nERROR: AutoCmd file not found or invalid - " + arg + "\n")
                print ("Continuing in Manual Cmd mode")
                continue
            gAutoCmdEnabled = True
            gAutoCmdFile = arg
            break
    # Disable ManualCmd mode, it may be set again when required
    gManualCmdEnabled = False

###  Functions defined as ACL_xyz(*args) are specific to (A)uto (C)ommand (L)oop ACL ###
### They take an argument list (*args) as input and return a string to caller ###

# Function to find a substring in a main string and return status
# args = (pattern, main_string)
def ACL_FindInString (*args) :
    if args[0] in args[1] :
        return "1"
    else :
        return "0"

# Function to call HandleCmdAndGetResp function from a AutoCmd loop
# args = (SerialPort, Cmd)
def ACL_HandleAutoCmd (*args) :
    SerialPort = args[0]
    Cmd = args[1]
    return HandleCmdAndGetResp (SerialPort, Cmd, CmdFromScript)

# Dummy function doing nothing
# args - don't care
def ACL_DummyFunction (*args) :
    return "dummy"

# Function to run a scom-configured loop for looped Auto commands from an scom file
# Usage  : DoAutoLoopAutoCmds (Cmd, AutoCmdFH)
#          Cmd        - line read from AutCmd file starting with loopbegin
#          AutoCmdFH  - File handle to read commands and execute in the loop
# Return : None
def DoAutoLoopAutoCmds (Cmd, AutoCmdFH) :
    # Serial response to a AutoCmd
    Resp = ""
    # Iteration count of the loop
    ACLKeepLoopAlive = -1 # If no iteration count is specified, loop indefinitely
    # ACL functions list using 'partial' module to call with relevant arguments
    ACLFlist = []
    # Local return value holder
    RetVal = 0

    if Cmd[0:9] != "loopbegin" :
        # This is not a loopbegin!
        return

    # Line read from AutoCmd .scom file is stored in Cmd
    Cmd = Cmd.split (' ', 1)[1]
    # Parse and get the number of iterations
    if Cmd[0:4] == "iter" :
        ACLKeepLoopAlive = int (re.findall ('\d+', Cmd)[0])

    # Read lines continuously, parse and get either - 
    # 1. AT command
    # 2. other scom commands
    # and update the ACLFlist accordingly till we get - 
    #     . EOF (means a bad scom file) : LOOP won't run
    #     . loopend (end of the loop) : LOOP will run
    #     . bad syntax scom line before EOF/loopend (bad scom file) : LOOP won't run
    while 1 :
        Cmd = AutoCmdFH.readline ()
        # Remove newline character in Cmd read by readline()
        Cmd = Cmd[:-1]
        if not Cmd : 
            # EOF reached! That ain't right
            RetVal = -1
            break
        elif Cmd[0:2].lower () == "at" :
            # A command for the modem, let it be handled in loop
            args = []
            args.append (gSerPort)
            args.append (Cmd)
            ACLFlist.append (partial (ACL_HandleAutoCmd, *args))
        elif Cmd[0:5] == "sleep" :
            Cmd = Cmd[6:]
            # A delay to be added in loop
            args = []
            args.append (float (Cmd))
            ACLFlist.append (partial (time.sleep, *args))
        elif Cmd[0:7] == "loopend" :
            # End indication of the loop
            break
        else :
            # Just discard the line read as it is not having valid cmds
            Cmd = ""

    # There may be multiple causes of failure in loop-parsing. Check and act acc. to it
    if RetVal != 0 :
        ACLFlist = []
        return RetVal

    # Let the loop begin! Crowd cheering Yaaaaaay
    while ACLKeepLoopAlive :
        # Take ACLFlist and execute function by function
        i = 0
        while i < len (ACLFlist) :
            Resp = ACLFlist[i] ()
            i += 1
        ACLKeepLoopAlive -= 1

# Function to run a loop to read and handle Cmds from AutoCmd scom file sequenitally
# Usage  : HandleAutoCmds ()
# Return : None
def HandleAutoCmds () :
    global gAutoCmdEnabled
    global gAutoCmdFile
    global gManualCmdEnabled
    NewAutoCmdFileAvl = False

    AutoCmdFH = open (gAutoCmdFile, 'r')
    while 1 :
        Cmd = AutoCmdFH.readline ()
        # Check for EOF
        if not Cmd :
            AutoCmdFH.close ()
            break
        if len (Cmd) == 0 or Cmd[0] == '#' or Cmd[0] == '\n':
            continue
        # Remove newline character in Cmd read by readline()
        Cmd = Cmd[:-1]
        if Cmd[0:2].lower () == "at" :
            Resp = HandleCmdAndGetResp (gSerPort, Cmd, CmdFromScript)
        elif Cmd[0:5] == "break" :
            print ("AutoCmd encountered 'break'.. Closing file " + gAutoCmdFile)
            AutoCmdFH.close ()
            break
        elif Cmd[0:15] == "EnableManualCmd" :
            gManualCmdEnabled = True
            break
        elif Cmd[0:13] == "EnableAutoCmd" :
            arg = Cmd.split(" ")[1:][0]
            if len (arg) == 0 or os.path.isfile (arg) == False or arg[-5:] != ".scom" :
                print ("\nERROR: AutoCmd file not found or invalid - " + arg + "\n")
                print ("Continuing normally..")
                continue
            gAutoCmdFile = arg
            NewAutoCmdFileAvl = True
            break
        elif Cmd[0:9] == "loopbegin" :
            DoAutoLoopAutoCmds (Cmd, AutoCmdFH)
    # Update AutoCmd-mode-enable flag as per latest AutoCmd file
    gAutoCmdEnabled= NewAutoCmdFileAvl

# Function to close all open files, typically done on irrecoverable-error-with-exit
# Usage  : CloseOpenFiles ()
# Return : None
def CloseOpenFiles () :
    gSerPort.close ()
    if gLoggingEnabled :
        x = logging._handlers.copy()
        for i in x:
            log.removeHandler(i)
            i.flush()
            i.close()

######################### Start-Of-Python-Script (SOPS)

# Validate arguments 
argv = sys.argv[1:]
opts, args = getopt.getopt(argv, 'd:a:b:lm')
for opt, arg in opts :
    if opt == "-d" :
        if len (arg) == 0 :
            sys.exit ("\nERROR: Need valid Device ID\n" + sercomUsageStr)
        gSerPortID = arg
    elif opt == "-a" :
        if len (arg) == 0 or os.path.isfile (arg) == False or arg[-5:] != ".scom" :
            sys.exit ("\nERROR: AutoCmd file not found or invalid - " + arg + "\n" + sercomUsageStr)
        gAutoCmdEnabled = True
        gAutoCmdFile = arg
    elif opt == "-m" :
        gManualCmdEnabled = 3
    elif opt == "-b" :
        if int (arg) not in AllowedBaudRates :
            sys.exit ("\nERROR: Invalid BaudRate - " + arg + "\n" + sercomUsageStr)
        gBaudRate = int (arg)
    elif opt == "-l" :
        gLoggingEnabled = True
    else :
        sys.exit ("Unknown option: {opt}")

if gSerPortID == "undefined" :
    sys.exit ("\nERROR: Need valid Device ID\n" + sercomUsageStr)

# Disable Manual command entry if: 
# 1. '-m' is not specified in arguments
# 2. '-a' is given and valid Auto-commands file is available
if gAutoCmdEnabled and gManualCmdEnabled != 3 :
    gManualCmdEnabled = False
else :
    gManualCmdEnabled = True

print ("Serial Port Device   : " + gSerPortID)
print ("Baud Rate            : " + str (gBaudRate))
print ("Session Logging      : " + str (gLoggingEnabled))
print ("Auto Command tests   : " + str (gAutoCmdEnabled))
print ("Manual Command entry : " + str (gManualCmdEnabled))
print ("\n-----------------")

# Configure and open Serial Port
if gPyVer.startswith("3.") :
    gSerPort = serial.Serial (port=gSerPortID, baudrate=gBaudRate, inter_byte_timeout=0.01, timeout=0.001)
else :
    gSerPort = serial.Serial (port=gSerPortID, baudrate=gBaudRate, interCharTimeout=0.01, timeout=0.001)

# If logging is enabled, create a logger
if gLoggingEnabled :
    logging.basicConfig(filename=gLogFileName, level=logging.DEBUG, 
            format='%(asctime)s %(message)s', datefmt='%b %d %H:%M:%S',
            filemode='w') 
    gLogger = logging.getLogger() 

# Validate basic command before actual serial communication
Resp = HandleCmdAndGetResp (gSerPort, "AT", CmdFromScript)
if "OK" not in Resp :
    CloseOpenFiles ()
    sys.exit ("***SERROR: Basic AT-OK session failed .. Aborting!")

# We may have advanced test sequences requiring repeated
# Manual and Auto Command sequences independently
while 1 :
    #print ("Main** Manual: " + str (gManualCmdEnabled) + " Auto: " + str (gAutoCmdEnabled))
    if gManualCmdEnabled :
        HandleManualCmds ()
    elif gAutoCmdEnabled :
        HandleAutoCmds ()
    else :
        break

CloseOpenFiles ()

print ("\nThat's all folks..!\n")

quit ()

