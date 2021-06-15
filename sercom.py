#!/bin/env python

SercomUsageStr = "\n\
Usage: sercom.py <args> [optionals]\n\
args:\n\
     -d <Device#>   : Linux - /dev/ttyx of serial port (check dmesg|tail)\n\
                      Windows - COMx of serial port (check Device Manager)\n\
optionals: If an optional is not given, respective Default is applied\n\
     -s <ScomFile>  : .scom type file containing automatic command sequence\n\
                      SCOM - Serial Communication via text-syntactical file\n\
                      Default - No Scom commands are applicable\n\
                      NOTE: .scom file has a syntax - refer example.scom\n\
                            It can enable Manual command entry with 'enman'.\n\
     -m             : Enable Manual entry of commands from stdin console\n\
                      Default - Disabled if -s Scom is used\n\
                              - Enabled if -s Scom is not used\n\
                      NOTE: It can enable Scom with 'enscom' stdin input.\n\
     -b <BaudRate>  : Baud rate of serial port device\n\
                      Default - 115200\n\
     -c <ConfFile>  : Serial port configuration file other than Baud rate\n\
                      Expected parameters in file (refer sample.conf) - \n\
                          bytesz=[5|6|7|8]\n\
                          parity=[N|E|O|M|S]\n\
                          stpbit=[1|1.5|2]\n\
                          rdtout=[float-value]\n\
                          flowct=[N|X|R|D]\n\
                          wrtout=[float-value]\n\
     -l             : Enables logging of serial IO into a new logfile in PWD\n\
                      Default - Disabled\n\
                      If enabled, the log file name will be as follows:\n\
                      <MonthName-Date-Year_Hour-Minute-Second>_sercom.log\n\
                      e.g. May-28-2021_10-48-37_sercom.log\n\
                      Logging format per line is as follows -\n\
                      <Date> <Time> [{A}uto|{M}anual {I}|{O}] 'Data' \n\
                      e.g. May 27 14:24:50 [AO] 'AT\\r' \n\
NOTE:\n\
1. To (re-)enable Scom mode from Manual/Scom mode (one Scom run disables scom mode), use following cmd in Manual command line and at End of AutCmdFile : enscom <path-to-Scom-File>\n\
2. To (re-)enable ManualCmd mode from Scom mode, use following cmd at End of ScomFile: enman\n\
3. If both scom and manual modes are requested, manual mode runs first and then scom\n\
4. Any script specific error-messages are tagged as '***SERCOM'\n\
"

######################### Import required python modules/submodules
import os
import sys
import math
import serial
import time
import datetime
import re
import platform
import getopt
import os.path
import logging
import functools
from functools import partial
from serial import Serial

# Making this script version-agnostic, we need version number to abstract
# and call version-specific Serial/File IO and other API functions
gPyVer = platform.python_version()

# Uncomment/Comment out the following to debug/run-normally the python script
#import pdb; pdb.set_trace ()

# Actual script execution starts at SOPS. Find SOPS
######################### Serial-Port-Handler-Environment (SENV)

### Environment setup/control
# refer -d option in SercomUsageStr
gSerPortID = "undefined"
# refer -a option in SercomUsageStr
gScomEn = False
# Current Scom filename being executed
gScomFile = "undefined"
# Scom filename stack for old Scom files (used to handle Scom Chains)
gOldScoms = []
# refer -m option in SercomUsageStr
gManualEn = "on"
# refer -b option in SercomUsageStr
gSerBaud = 115200
# refer -c option in SercomUsageStr
gSerPortCfgFile = "undefined"
# refer -c option in SercomUsageStr
gSerByteSize = 8
# refer -c option in SercomUsageStr
gSerParity = 'N'
# refer -c option in SercomUsageStr
gSerStopBits = 1
# refer -c option in SercomUsageStr
gSerRdTimeout = 0.001
# refer -c option in SercomUsageStr
gSerFlowCtrl = None
# refer -c option in SercomUsageStr
gSerWrTimeout = 0.01
# Logging control
gLoggingEnabled = False
# Timeout for full response reception with OK/ERROR
gFullRespTout = 20
# Response timeout indication flag set/unset for every fresh CmdResp session
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
gLogFileName = datetime.datetime.now().strftime('%b-%d-%Y_%H-%M-%S') + \
        "_sercom.log"
# List of allowed baud rates
gAllowedBaudRates = [110, 300, 600, 1200, 2400, 4800, 9600, \
        14400, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

######################### Helper/Handler Functions for Serial IO and logging

# Function to log IO data or any debug/error messages to a log file
# Usage  : logmsg (msg)
#          msg - message to be stored in log file
# Return : None
def logmsg (msg) :
    if gLoggingEnabled : gLogger.debug (msg)

# Function to receive data over Serial port in python-version independent way
# Usage  : RecvSerialData (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String containing the data received on serial port
def RecvSerialData (SerialPort) :
    Data = SerialPort.read (100)
    if gPyVer.startswith("3.") : Data = Data.decode ()
    return Data

# Function to send data over Serial port in python-version independent way
# Usage  : SendSerialData (SerialPort, buf)
#          SerialPort - Serial Port Interface handle
#          buf        - buffer containing data to be send over serial port
# Return : number of data bytes sent over the serial port
def SendSerialData (SerialPort, buf) :
    if gPyVer.startswith("3.") : buf = buf.encode ()
    numTxBytes = SerialPort.write (buf)
    SerialPort.flush ()
    return numTxBytes

# Function to read console (stdin) input from use bring python-version-agnostic
# Usage  : ReadConsoleInput (prompt)
#          prompt     - prompt string (optional)
# Return : Console input data given by user from stdin console
if gPyVer.startswith("3.") : ReadConsoleInput = input
else : ReadConsoleInput = raw_input

# Function to strip the Command from the Response
# Usage  : StripStartOfString (buf)
#          buf        - buffer containing data to be processed
# Return : Stripped string
def StripStartOfString (buf) :
    _rule = re.compile (r'([^\n]+)')
    stripStr = re.search(_rule, buf).group(1) + "\n"
    buf = buf[len (stripStr):]
    return buf

# Function to recv full response with OK/ERROR within gFullRespTout seconds
# Usage  : RecvFullResponse (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String buffer containing Serial data received
def RecvFullResponse (SerialPort) :
    global gRespTimedOut
    Resp = ""
    retryDelay = 0.01
    numRetries = gFullRespTout * (1 / retryDelay)
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
            time.sleep (retryDelay)
            continue
        numRetries = gFullRespTout
        Resp += RxChunk
        if "\r\nERROR\r\n" in Resp or \
                "\r\nOK\r\n" in Resp or "\r\n+CME ERROR:" in Resp :
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
    if CmdSrc == CmdFromScript : print (Cmd)
    CmdSrcID = ["A", "M"][CmdSrc]
    logmsg ("[" + CmdSrcID +  "O] " + repr (Cmd))
    SendSerialData (SerialPort, Cmd)
    Resp = RecvFullResponse (SerialPort)
    if gRespTimedOut == True :
        errStr = "***SERCOM: Cmd \"" + _cmd + \
        "\" Timed-out with no/incomplete response\n"
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

######################### Application Functions for Serial IO handling

# Function to have a controlled loop for handling manual command from stdin
# Usage  : HandleManualCmds ()
# Return : None
def HandleManualCmds () :
    global gManualEn
    global gScomEn
    global gScomFile

    while 1 :
        Cmd = ReadConsoleInput ("")
        if len (Cmd) == 0 : continue
        if Cmd[0:2].lower () == "at" :
            HandleCmdAndGetResp (gSerPort, Cmd, CmdFromStdIn)
        elif Cmd[0:5] == "break" :
            print ("-----------------")
            break
        elif Cmd[0:6] == "enscom" :
            arg = Cmd.split(" ")[1:][0]
            if len (arg) == 0 or \
                    os.path.isfile (arg) == False or arg[-5:] != ".scom" :
                print ("\n***SERCOM: Scom file not found or invalid - " \
                        + arg + "\n")
                print ("Continuing in Manual Cmd mode..")
                continue
            gScomEn = True
            gScomFile = arg
            break
    # Disable ManualCmd mode, it may be set again when required
    gManualEn = False

###  Functions ACL_xyz(*args) are specific to (A)uto (C)ommand (L)oop ACL ###
### They take argument list (*args) as input and return a string to caller ###

# Function to find a substring in a main string and return status
# args = (pattern, main_string)
def ACL_FindInString (*args) :
    if args[0] in args[1] : return "1"
    else : return "0"

# Function to call HandleCmdAndGetResp function from a Scom loop
# args = (SerialPort, Cmd)
def ACL_HandleSerCmd (*args) :
    SerialPort = args[0]
    Cmd = args[1]
    return HandleCmdAndGetResp (SerialPort, Cmd, CmdFromScript)

# Dummy function doing nothing
# args - don't care
def ACL_DummyFunction (*args) :
    return "dummy"

# Function to run a scom-configured loop for looped commands from an scom file
# Usage  : DoAutoLoopScomCmds (Cmd, ScomFH)
#          Cmd        - line read from AutCmd file starting with loopbegin
#          ScomFH     - File handle to read commands and execute in the loop
# Return : None
def DoAutoLoopScomCmds (Cmd, ScomFH) :
    # Serial response to a ScomCmd
    Resp = ""
    # Iteration count of the loop
    ACLKeepLoopAlive = -1 # If no iteration count specified, loop indefinitely
    # ACL functions list using 'partial' module to call with relevant arguments
    ACLFlist = []
    # Local return value holder
    RetVal = 0

    # If this is not a loopbegin, assume something wrong / no loop to run
    if Cmd[0:9] != "loopbegin" : return

    # Remove all extra spaces from 'loopbegin' command
    Cmd = str (re.sub(' +', ' ', Cmd))
    # Line read from ScomCmd .scom file is stored in Cmd
    Cmd = Cmd.split (' ', 1)[1]
    # Parse and get the number of iterations
    if Cmd[0:4] == "iter" : ACLKeepLoopAlive = int (re.findall ('\d+', Cmd)[0])

    # Read lines continuously, parse and get either - 
    # 1. Target command
    # 2. other scom commands
    # and update the ACLFlist accordingly till we get - 
    #     . EOF (means a bad scom file) : LOOP won't run
    #     . loopend (end of the loop) : LOOP will run
    #     . bad syntax line before EOF/loopend (bad scom file) : LOOP won't run
    for Cmd in ScomFH :
        # Remove newline character in Cmd read (line)
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
            ACLFlist.append (partial (ACL_HandleSerCmd, *args))
        elif Cmd[0:5] == "sleep" :
            # Remove all extra spaces
            Cmd = str (re.sub(' +', ' ', Cmd))
            Cmd = Cmd[6:]
            # A delay to be added in loop
            args = []
            args.append (float (Cmd))
            ACLFlist.append (partial (time.sleep, *args))
        elif Cmd[0:7] == "loopend" : break # End indication of the loop
        else : Cmd = "" # Just discard.. It's an invalid command

    # There may be multiple causes of failure above. Check and act accordingly
    if RetVal != 0 :
        ACLFlist = []
        return RetVal

    # Let the loop begin! Crowd cheering Yaaaaaay
    while ACLKeepLoopAlive :
        # Take ACLFlist and execute function by function
        for i in ACLFlist :
            Resp = i ()
        ACLKeepLoopAlive -= 1

# Function to try switch to previous (mother) scom in chained scom test cases
# Usage  : SwitchToMotherScom (ScomFH)
#          ScomFH     - File handle to current (child) scom file
#          reason     - reason of the switch
# Return : ScomFH     - Handle to scom file if mother scom is found
#                       'None' if mother not found
def SwitchToMotherScom (ScomFH, reason) :
    global gScomEn
    global gOldScoms
    print ("\n***SERCOM: " + reason)
    ScomFH.close ()
    # If an Scom Chain is setup and if we're in child Scom, go back to mother
    if gOldScoms == [] :
        print ("\n***SERCOM: No scom chain.. Exiting scom mode.")
        gScomEn = False
        return
    ScomFH = gOldScoms.pop ()
    print ("\n***SERCOM: Continuing mother scom: " + ScomFH.name)
    return ScomFH

# Function to run a loop to read and handle Cmds from scom file sequenitally
# Usage  : HandleScomCmds ()
# Return : None
def HandleScomCmds () :
    global gScomEn
    global gScomFile
    global gOldScoms
    global gManualEn
    NewScomFileAvl = False

    ScomFH = open (gScomFile, 'r')
    while 1 :
        Cmd = ScomFH.readline ()
        if not Cmd :
            ScomFH = SwitchToMotherScom (ScomFH, "EOF on " + gScomFile)
            if ScomFH == None : return
        if len (Cmd) == 0 or Cmd[0] == '#' or Cmd[0] == '\n': continue
        # Remove newline character in Cmd read
        Cmd = Cmd[:-1]
        if Cmd[0:2].lower () == "at" :
            Resp = HandleCmdAndGetResp (gSerPort, Cmd, CmdFromScript)
        elif Cmd[0:6] == "expect" :
            sys.exit ("Need to update!")
        elif Cmd[0:9] == "loopbegin" : DoAutoLoopScomCmds (Cmd, ScomFH)
        elif Cmd[0:5] == "break" :
            ScomFH = SwitchToMotherScom (ScomFH, "'break' on " + gScomFile)
            if ScomFH == None : return
        elif Cmd[0:5] == "enman" :
            gManualEn = True
            break
        elif Cmd[0:6] == "enscom" :
            # Remove all extra spaces
            Cmd = str (re.sub(' +', ' ', Cmd))
            arg = Cmd.split(" ")[1:][0]
            if len (arg) == 0 or \
                    os.path.isfile (arg) == False or arg[-5:] != ".scom" :
                print ("\n***SERCOM: Scom file not found or invalid - " \
                        + arg + ". Continuing normally")
                continue
            gOldScoms.append (ScomFH)
            print ("\n***SERCOM: Switch to child scom: " + arg)
            ScomFH = open (arg, "r")

# Function to close all open files and serial port handles
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

if len (sys.argv) == 1 : sys.exit (SercomUsageStr)

# Validate arguments 
opts, args = getopt.getopt(sys.argv[1:], 'd:s:b:c:lm')
for opt, arg in opts :
    if opt == "-d" :
        if len (arg) == 0 :
            sys.exit ("\nERROR: Need valid Device ID\n" + SercomUsageStr)
        gSerPortID = arg
    elif opt == "-s" :
        if len (arg) == 0 or \
                os.path.isfile (arg) == False or arg[-5:] != ".scom" :
            sys.exit ("\nERROR: Scom file not found or invalid - " \
                    + arg + "\n" + SercomUsageStr)
        gScomEn = True
        gScomFile = arg
    elif opt == "-m" : gManualEn = True
    elif opt == "-b" :
        if int (arg) not in gAllowedBaudRates :
            sys.exit ("\nERROR: Invalid BaudRate - " \
                    + arg + "\n" + SercomUsageStr)
        gSerBaud = int (arg)
    elif opt == "-c" :
        if len (arg) == 0 or \
                os.path.isfile (arg) == False or arg[-5:] != ".conf" :
            sys.exit ("\nERROR: PortConfig file not found or invalid - " \
                    + arg + "\n" + SercomUsageStr)
        gSerPortCfgFile = arg
    elif opt == "-l" : gLoggingEnabled = True

if gSerPortID == "undefined" :
    sys.exit ("\nERROR: Need valid Device ID\n" + SercomUsageStr)

# Set default status of Manual mode; refer -m option in SercomUsageStr
if gScomEn == False : gManualEn = True

# Check/Validate Serial Port configuration from gSerPortCfgFile
if gSerPortCfgFile != "undefined" :
    PortCfgFH = open (gSerPortCfgFile, 'r')
    BadSerParams = "none"
    _bytesz = gSerByteSize
    _parity = gSerParity
    _stpbit = gSerStopBits
    _rdtout = gSerRdTimeout
    _flowct = gSerFlowCtrl
    _wrtout = gSerWrTimeout
    while 1 :
        Cfg = PortCfgFH.readline ()
        if not Cfg : break
        if len (Cfg) == 0 : continue
        # Remove newline character in Cmd read
        Cfg = Cfg[:-1]
        # Remove all spaces in line
        Cfg = Cfg.replace (" ", "")
        if Cfg[0:6] == "bytesz" :
            if Cfg[6] != "=" or (int (Cfg[7:]) not in [5, 6, 7, 8]) :
                BadSerParams = "bytesz"; break
            _bytesz = int (Cfg[7:])
        elif Cfg[0:6] == "parity" :
            parr = ["N", "E", "O", "M", "S"]
            if Cfg[6] != "=" or (not any (i in Cfg[7:] for i in parr)) :
                BadSerParams = "parity"; break
            _parity = Cfg[7]
        elif Cfg[0:6] == "stpbit" :
            sarr = ["1", "1.5", "2"]
            if Cfg[6] != "=" or (not any (i in Cfg[7:] for i in sarr)) :
                BadSerParams = "stpbit"; break
            if Cfg[7:] == "1" or Cfg[7:] == "2" : _stpbit = int (Cfg[7:])
            else : _stpbit = float (Cfg[7:])
        elif Cfg[0:6] == "rdtout" :
            if Cfg[6] != "=" : BadSerParams = "rdtout"; break
            try : f = float (Cfg[7:])
            except ValueError : BadSerParams = "rdtout"; break
            _rdtout = f
        elif Cfg[0:6] == "flowct" :
            farr = ["N", "X", "R", "D"]
            if Cfg[6] != "=" or (not any (i in Cfg[7:] for i in farr)) :
                BadSerParams = "flowct"; break
            _flowct = Cfg[7]
        elif Cfg[0:6] == "wrtout" :
            if Cfg[6] != "=" : BadSerParams = "wrtout"; break
            try : f = float (Cfg[7:])
            except ValueError : BadSerParams = "wrtout"; break
            _wrtout = f
    if BadSerParams == "none" :
        # gSerPortCfgFile has valid parameters, update serial parameters
        gSerByteSize = _bytesz
        gSerParity = _parity
        gSerStopBits = _stpbit
        gSerRdTimeout = _rdtout
        gSerFlowCtrl = _flowct
        gSerWrTimeout = _wrtout
        print ("\n***SERCOM: Updated Serial Port Configuration from " \
                + gSerPortCfgFile + "\n")
    else :
        print ("\n***SERCOM: Bad parameter (" + BadSerParams + ") in " \
                + gSerPortCfgFile + \
                ". Using Default Serial Port Configuration.\n")

print ("Session Logging      : " + str (gLoggingEnabled))
print ("Scom tests           : " + str (gScomEn))
print ("Manual Command entry : " + str (gManualEn))
print ("Serial Port Device   : " + gSerPortID)
print ("Serial Baud Rate     : " + str (gSerBaud))
print ("Serial Byte Size     : " + str (gSerByteSize))
print ("Serial Parity        : " + gSerParity)
print ("Serial Stop Bits     : " + str (gSerStopBits))
print ("Serial Read Timeout  : " + str (gSerRdTimeout))
print ("Serial FlowCtrl      : " + str (gSerFlowCtrl))
print ("Serial Write Timeout : " + str (gSerWrTimeout))
print ("\n-----------------")

# Configure and open Serial Port
gSerPort = serial.Serial (port=gSerPortID, baudrate=gSerBaud, \
        bytesize=gSerByteSize, parity=gSerParity, stopbits=gSerStopBits, \
        timeout=gSerRdTimeout, write_timeout=gSerWrTimeout, \
        xonxoff=gSerParity=='X', rtscts=gSerParity=='R', \
        dsrdtr=gSerParity=='D')

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
    sys.exit ("***SERCOM: Basic AT-OK session failed .. Aborting!")

# We may have advanced test sequences requiring repeated
# Manual and Scom Command sequences independently
while 1 :
    #print ("[MAIN] Manual:{}, Scom:{}".format (gManualEn, gScomEn))
    if gManualEn == True : HandleManualCmds ()
    elif gScomEn == True : HandleScomCmds ()
    else : break

CloseOpenFiles ()

sys.exit ("\nThat's all folks..!\n")

