#!/bin/env python

SercomUsageStr = "\n\
Usage: sercom.py <args> [optionals]\n\
Mandatory args:\n\
     -d <Device#>   : Linux - /dev/ttyx of serial port (check dmesg|tail)\n\
                      Windows - COMx of serial port (check Device Manager)\n\
     -c <SerConf>   : Serial port configuration file (refer sample.conf)\n\
                      Mandatory parameters - \n\
                          scvcmd=[Modem-cmd before starting Serial IO]\n\
                          scvrsp=[Modem-resp to scvcm to confirm serial IO]\n\
                      Optional parameters - \n\
                          baudrt=[Known baud rate value]\n\
                          bytesz=[5|6|7|8]\n\
                          parity=[N|E|O|M|S]\n\
                          stpbit=[1|1.5|2]\n\
                          rdtout=[float-value]\n\
                          flowct=[N|X|R|D]\n\
                          wrtout=[float-value]\n\
optionals: If an optional is not given, respective Default is applied\n\
     -s <ScomFile>  : .scom type file containing automatic command sequence\n\
                      SCOM - Serial Communication via text-syntactical file\n\
                      Default - No Scom commands are applicable\n\
                      NOTE: .scom file has a syntax - refer example.scom\n\
                            It can enable Manual commands with 'SCOM_enman'.\n\
     -m             : Enable Manual entry of commands from stdin console\n\
                      Default - Disabled if -s Scom is used\n\
                              - Enabled if -s Scom is not used\n\
                      NOTE: It can enable Scom with 'enscom'.\n\
     -l             : Enables logging of serial IO into a new logfile in PWD\n\
                      Default - Disabled\n\
                      If enabled, the log file name will be as follows:\n\
                      <MonthName-Date-Year_Hour-Minute-Second>_sercom.log\n\
                      e.g. May-28-2021_10-48-37_sercom.log\n\
                      Logging format per line is as follows -\n\
                      <Date> <Time> [{A}uto|{M}anual {I}|{O}] 'Data' \n\
                      e.g. May 27 14:24:50 [AO] 'AT\\r' \n\
NOTE:\n\
1. To (re-)enable Manual mode from Scom, cmd at ScomFile EOF: SCOM_enman\n\
2. If both scom & manual modes requested, manual runs first and then scom\n\
3. Any script specific messages are tagged as '***SERCOM'\n\
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
# Scom filename stack for old Scom files (used to handle Scom Chains)
gScomStack = []
# refer -m option in SercomUsageStr
gManualEn = "on"
# refer -c option in SercomUsageStr
gSerBaud = 115200
# refer -c option in SercomUsageStr
gSerPortCfgFile = "undefined"
# refer -c option in SercomUsageStr
gSerScvCmd = "undefined"
# refer -c option in SercomUsageStr
gSerScvRsp = "undefined"
# refer -c option in SercomUsageStr
gSerSentry = []
# refer -c option in SercomUsageStr
gSerByteSize = 8
# refer -c option in SercomUsageStr
gSerParity = 'N'
# refer -c option in SercomUsageStr
gSerStopBits = 1
# refer -c option in SercomUsageStr
gSerRdTimeout = 0.01
# refer -c option in SercomUsageStr
gSerFlowCtrl = None
# refer -c option in SercomUsageStr
gSerWrTimeout = 0.01
# Logging control
gLoggingEnabled = False

### Other types/variables used internally 
# cmd_src_types
SCmd = 0 # Modem Cmd read from scom file (Scom mode)
MCmd = 1 # Modem Cmd read from stdin (Manual mode)
# Serial port IO handle
gSerPort = "undefined"
# Log file handle
gLogger = 1
# Name of Log file name
gLogFileName = datetime.datetime.now().strftime('%b-%d-%Y_%H-%M-%S') + \
        "_sercom.log"

######################### Helper/Handler Functions for Serial IO and logging

# Function to log IO data or any debug/error messages to a log file
# Usage  : logmsg (msg)
#          msg - message to be stored in log file
# Return : None
def logmsg (msg) :
    if gLoggingEnabled : gLogger.debug (msg)

# Function to write msg to stdout and log-file (if open)
# Usage  : slogprint (msg)
#          msg - message to be written
# Return : None
def slogprint (msg) :
    logmsg ("***SERCOM: " + msg + "\n")
    print ("***SERCOM: " + msg + "\n")

# Function to write IRRECOVERABLE error msg to stdout and log-file (if open)
# and then exit the program
# Usage  : SysExit (msg)
#          msg - message to be written
# Return : None
def SysExit (msg) :
    logmsg ("\n!ERROR!: " + msg + "\n")
    print ("\n!ERROR!: " + msg + "\n")
    quit ()

# Function to receive data over Serial port in python-version independent way
# Usage  : RecvSerialData (SerialPort)
#          SerialPort - Serial Port Interface handle
# Return : String containing the data received on serial port
def RecvSerialData (SerialPort) :
    try : Data = SerialPort.read (100)
    except serial.serialutil.SerialTimeoutException : Data = ''
    if gPyVer.startswith("3.") : Data = Data.decode ()
    return Data

# Function to send data over Serial port in python-version independent way
# Usage  : SendSerialData (SerialPort, buf)
#          SerialPort - Serial Port Interface handle
#          buf        - buffer containing data to be send over serial port
# Return : number of data bytes sent over the serial port
def SendSerialData (SerialPort, buf) :
    if gPyVer.startswith("3.") : buf = buf.encode ()
    try : numTxBytes = SerialPort.write (buf)
    except serial.serialutil.SerialTimeoutException : numTxBytes = -1 
    SerialPort.flush ()
    return numTxBytes

# Function to read console (stdin) input being python-version-agnostic
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

# Function to skip first word and following spaces to point to next word
# Usage  : SkipToNextWord (line, word1len)
#          line - line to skip first word and spaces for next word
#          word1len - length of first word to skip
# Return : line with next word as start of line
def SkipToNextWord (line, word1len) :
    line = line[word1len:]
    return line[len(line) - len(line.lstrip()):]

# Function to recv full response before 'RespTout' seconds
# Usage  : RecvFullResponse (SerialPort, RespTout, SentryList)
#          SerialPort - Serial Port Interface handle
#          RespTout   - Response timeout value for this session
#          SentryList - List of sentry strings which mark Full response Rx
# Return : On Success - 0, "String buffer with Rx data"
#          On Failure - -1, "Incomplete String buffer Rx data"
def RecvFullResponse (SerialPort, RespTout, SentryList) :
    Resp = ""
    retryDelay = 0.01
    numRetries = RespTout * (1 / retryDelay)
    RxTimedOut = False
    while 1 :
        RxChunk = RecvSerialData (SerialPort)
        if len (RxChunk) == 0 :
            numRetries -= 1
            # Break the loop if reception timed-out
            if numRetries == 0 : RxTimedOut = True; break
            # At this point, there's still time for response
            time.sleep (retryDelay)
            continue
        numRetries = RespTout * (1 / retryDelay)
        Resp += RxChunk
        # Break if response has (any of) the sentry string(s)
        if [i for i in SentryList if (i in Resp)] : break
    return RxTimedOut, Resp

# Function to handle a Command-Response session
# Usage  : HandleCmdAndGetResp (SerialPort, Cmd, CmdSrc, SentryList)
#          SerialPort - Serial Port Interface handle
#          Cmd        - Command string
#          CmdSrc     - refer cmd_src_types
#          SentryList - List of sentry strings which mark Full response Rx
# Return : String buffer containing Serial data received
def HandleCmdAndGetResp (SerialPort, Cmd, CmdSrc, SentryList) :
    _cmd = Cmd
    Cmd = Cmd + "\r"
    if CmdSrc == SCmd : print (Cmd)
    CmdSrcID = ["A", "M"][CmdSrc]
    logmsg ("[" + CmdSrcID +  "O] " + repr (Cmd))
    ret = SendSerialData (SerialPort, Cmd)
    if ret < 0 :
        slogprint ("Serial Write Timeout")
        return ''
    RxTimedOut, Resp = RecvFullResponse (SerialPort, 20, SentryList)
    if RxTimedOut == True :
        slogprint ("'" + _cmd + "' Timed-out with no/incomplete response")
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
    # lScomStack is for scom enabled in manual mode
    lScomStack = []

    while 1 :
        Cmd = ReadConsoleInput ("")
        if len (Cmd) == 0 : continue
        elif Cmd[0:10] == "SCOM_break" :
            gManualEn = False
            print ("-----------------")
            break
        elif Cmd[0:11] == "SCOM_enscom" :
            arg = SkipToNextWord (Cmd, 11)
            if not os.path.isfile (arg) or arg[-5:] != ".scom" :
                slogprint ("Scom file not found or invalid - " \
                        + arg + "\nContinuing in Manual Cmd mode..")
                continue
            # Open scom file and stack it ready 
            ScomFH = open (arg, "r");
            lScomStack.append (ScomFH)
            HandleScomCmds (lScomStack)
        else :
            # Not Manual-mode control command, send to modem and get response
            Resp = HandleCmdAndGetResp (gSerPort, Cmd, MCmd, gSerSentry)

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
    return HandleCmdAndGetResp (SerialPort, Cmd, SCmd, gSerSentry)

# Dummy function doing nothing
# args - don't care
def ACL_DummyFunction (*args) :
    return "dummy"

# Function to run a scom-configured loop for looped commands from an scom file
# Usage  : DoAutoLoopScomCmds (Cmd, ScomFH)
#          Cmd        - line read from AutCmd file starting with SCOM_loopbegin
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

    # Remove all extra spaces from 'SCOM_loopbegin' command
    Cmd = str (re.sub(' +', ' ', Cmd))
    # Skip SCOM_loopbegin and point Cmd to 'iter' in line
    Cmd = Cmd.split (' ', 1)[1]
    # Parse and get the number of iterations
    if Cmd[0:4] == "iter" : ACLKeepLoopAlive = int (re.findall ('\d+', Cmd)[0])

    # Read lines continuously, parse and get either - 
    # 1. Target command
    # 2. other scom commands
    # and update the ACLFlist accordingly till we get - 
    #     . EOF (means a bad scom file) : LOOP won't run
    #     . SCOM_loopend (end of the loop) : LOOP will run
    #     . bad syntax line before EOF/SCOM_loopend (bad scom file)
    while 1 :
        Cmd = ScomFH.readline ()
        if not Cmd : RetVal = -1; break; # EOF reached! That ain't right
        if Cmd[0] == '#' or Cmd[0] == '\n': continue
        # Remove newline character in Cmd read (line)
        Cmd = Cmd[:-1]
        # Check for SCOM/Modem cmds and act accordingly
        if Cmd[0:10] == "SCOM_sleep" :
            # Remove all extra spaces
            Cmd = str (re.sub(' +', ' ', Cmd))
            Cmd = Cmd[11:]
            # A delay to be added in loop
            args = []
            args.append (float (Cmd))
            ACLFlist.append (partial (time.sleep, *args))
        elif Cmd[0:12] == "SCOM_loopend" : break # End indication of the loop
        else :
            # A command for the modem, let it be handled in loop
            args = []
            args.append (gSerPort)
            args.append (Cmd)
            ACLFlist.append (partial (ACL_HandleSerCmd, *args))

    # There may be multiple causes of failure above. Check and act accordingly
    if RetVal != 0 : return RetVal

    # Let the loop begin! Crowd cheering Yaaaaaay
    while ACLKeepLoopAlive :
        # Take ACLFlist and execute function by function
        for func in ACLFlist :
            Resp = func ()
        ACLKeepLoopAlive -= 1

# Function to try switch to previous (mother) scom in chained scom test cases
# Usage  : SwitchToMotherScom (ScomFH, ScomStack, reason)
#          ScomFH     - File handle to current (child) scom file
#          ScomStack  - Stack of Scom file handles used in this scom session
#          reason     - reason of the switch
# Return : ScomFH     - Handle to scom file if mother scom is found
#                       'None' if mother not found
def SwitchToMotherScom (ScomFH, ScomStack, reason) :
    slogprint (reason + " on " + os.path.basename(ScomFH.name))
    ScomFH.close ()
    # If an Scom Chain is setup and if we're in child Scom, go back to mother
    if ScomStack == [] : slogprint ("Exiting scom mode"); return
    ScomFH = ScomStack.pop ()
    slogprint ("Continuing mother scom: " + ScomFH.name)
    return ScomFH

# Function to run a loop to read and handle Cmds from scom file sequenitally
# Usage  : HandleScomCmds (ScomStack)
#          ScomStack  - Stack of Scom file handles used in this scom session
# Return : None
def HandleScomCmds (ScomStack) :

    ScomFH = ScomStack.pop ()
    while 1 :
        Cmd = ScomFH.readline ()
        if not Cmd :
            ScomFH = SwitchToMotherScom (ScomFH, ScomStack, "EOF")
            if ScomFH == None: return
            continue
        if Cmd[0] == '#' or Cmd[0] == '\n': continue
        # Remove newline character in Cmd read
        Cmd = Cmd[:-1]
        # Check for SCOM/Modem cmds and act accordingly
        if Cmd[0:11] == "SCOM_expect" :
            SysExit ("Need to update!")
        elif Cmd[0:14] == "SCOM_loopbegin" : DoAutoLoopScomCmds (Cmd, ScomFH)
        elif Cmd[0:10] == "SCOM_break" :
            ScomFH = SwitchToMotherScom (ScomFH, ScomStack, "SCOM_break")
            if ScomFH == None : return
        elif Cmd[0:10] == "SCOM_enman" :
            slogprint ("Switching to Manual mode")
            HandleManualCmds ()
            # At this point, Manual mode ends by 'break', continue normally
        elif Cmd[0:11] == "SCOM_enscom" :
            # Extract the filename
            arg = SkipToNextWord (Cmd, 11)
            if not os.path.isfile (arg) or arg[-5:] != ".scom" :
                slogprint ("Scom file not found or invalid - " \
                        + arg + ". Continuing normally")
                continue
            ScomStack.append (ScomFH)
            slogprint ("Switching to child scom: " + arg)
            ScomFH = open (arg, "r")
        else :
            # Not SCOM command, send to modem and get response
            Resp = HandleCmdAndGetResp (gSerPort, Cmd, SCmd, gSerSentry)

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

# Function to correct str with Esc-sequences \\r & \\n as \r & \n
# Usage  : RecodeEscSeq (s)
# Return : Updated string with correct escape sequence characters
def RecodeEscSeq (s) :
    s = s.replace ("\\r","\r")
    s = s.replace ("\\n","\n")
    return s

######################### Start-Of-Python-Script (SOPS)

if len (sys.argv) == 1 : sys.exit (SercomUsageStr)

# Validate arguments 
opts, args = getopt.getopt(sys.argv[1:], 'd:s:c:lm')
for opt, arg in opts :
    if opt == "-d" :
        if len (arg) == 0 :
            SysExit ("Need valid Device ID\n" + SercomUsageStr)
        gSerPortID = arg
    elif opt == "-s" :
        if not os.path.isfile (arg) or arg[-5:] != ".scom" :
            SysExit ("Scom file not found or invalid - " \
                    + arg + "\n" + SercomUsageStr)
        # Open scom file and stack it ready 
        ScomFH = open (arg, "r");
        gScomStack.append (ScomFH)
    elif opt == "-m" : gManualEn = True
    elif opt == "-c" :
        if not os.path.isfile (arg) or arg[-5:] != ".conf" :
            SysExit ("PortConfig file not found or invalid - " \
                    + arg + "\n" + SercomUsageStr)
        gSerPortCfgFile = arg
    elif opt == "-l" : gLoggingEnabled = True

# If logging is enabled, create a logger
if gLoggingEnabled :
    logging.basicConfig(filename=gLogFileName, level=logging.DEBUG, 
            format='%(asctime)s %(message)s', datefmt='%b %d %H:%M:%S',
            filemode='w') 
    gLogger = logging.getLogger() 

if gSerPortID == "undefined" :
    SysExit ("Need valid Device ID\n" + SercomUsageStr)

# Check/Validate Serial Port configuration from gSerPortCfgFile
if gSerPortCfgFile == "undefined" :
    SysExit ("Need Port configuration file\n" + SercomUsageStr)
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
    if Cfg[0] == '#' or Cfg[0] == '\n': continue
    # Remove newline character in Cmd read
    Cfg = Cfg[:-1]
    # Remove all spaces in line only for those not needing spaced strings
    # sentry strings may have spaces, we shouldn't remove them
    if Cfg[0:6] == "sentry" :
        if Cfg[6] != "=" : BadSerParams = "sentry"; break
        gSerSentry.append (RecodeEscSeq (Cfg[7:]))
        continue
    Cfg = Cfg.replace (" ", "")
    if Cfg[0:6] == "scvcmd" :
        if Cfg[6] != "=" : BadSerParams = "scvcmd"; break
        gSerScvCmd = Cfg[7:]
    elif Cfg[0:6] == "scvrsp" :
        if Cfg[6] != "=" : BadSerParams = "scvrsp"; break
        gSerScvRsp = Cfg[7:]
    elif Cfg[0:6] == "baudrt" :
        bauds = [110, 300, 600, 1200, 2400, 4800, 9600, \
                14400, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
        if Cfg[6] != "=" or int (Cfg[7:]) not in bauds : 
            BadSerParams = "baudrt"; break
        gSerBaud = int (Cfg[7:])
    elif Cfg[0:6] == "bytesz" :
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

if gSerScvCmd == "undefined" or gSerScvRsp == "undefined" :
    SysExit ("Need proper SCV cmd & resp strings")
if gSerSentry == [] :
    SysExit ("Need proper Sentry strings")
if BadSerParams != "none" :
    slogprint ("Bad parameter '" + BadSerParams + "' in " \
            + gSerPortCfgFile + ". Using Default Serial Port Configuration")
else :
    # gSerPortCfgFile has valid parameters, update serial parameters
    gSerByteSize = _bytesz
    gSerParity = _parity
    gSerStopBits = _stpbit
    gSerRdTimeout = _rdtout
    gSerFlowCtrl = _flowct
    gSerWrTimeout = _wrtout
    slogprint ("Updated Serial Port Configuration from " + gSerPortCfgFile)

# Configure and open Serial Port
try :
    gSerPort = serial.Serial (port=gSerPortID, baudrate=gSerBaud, \
            bytesize=gSerByteSize, parity=gSerParity, stopbits=gSerStopBits, \
            timeout=gSerRdTimeout, xonxoff=gSerParity=='X', \
            rtscts=gSerParity=='R', dsrdtr=gSerParity=='D')
    if gPyVer.startswith("3.") : gSerPort.write_timeout = gSerWrTimeout
    else : gSerPort.writeTimeout = gSerWrTimeout
except serial.serialutil.SerialException :
    SysExit ("Unable to open Serial port: " + gSerPortID)

# Set default status of Manual mode; refer -m option in SercomUsageStr
if gScomStack == [] : gManualEn = True

slogprint ("-----------------" + \
        "\nSession Logging      : " + str (gLoggingEnabled) + \
        "\nScom tests           : " + str (gScomStack == []) + \
        "\nManual Command entry : " + str (gManualEn) + \
        "\nSerial Port Device   : " + gSerPortID + \
        "\nSerial Baud Rate     : " + str (gSerBaud) + \
        "\nSerial Byte Size     : " + str (gSerByteSize) + \
        "\nSerial Parity        : " + gSerParity + \
        "\nSerial Stop Bits     : " + str (gSerStopBits) + \
        "\nSerial Read Timeout  : " + str (gSerRdTimeout) + \
        "\nSerial FlowCtrl      : " + str (gSerFlowCtrl) + \
        "\nSerial Write Timeout : " + str (gSerWrTimeout)
        )

# Validate basic command before actual serial communication
Resp = HandleCmdAndGetResp (gSerPort, gSerScvCmd, SCmd, gSerSentry)
if gSerScvRsp not in Resp :
    CloseOpenFiles ()
    SysExit ("Basic " + gSerScvCmd + "-" + gSerScvRsp + \
            " session failed. Aborting!")

# We may have advanced test sequences requiring repeated
# Manual and Scom Command sequences independently
while gManualEn == True or gScomStack != [] :
    #print ("[MAIN] Manual:{}, Scom:{}".format (gManualEn, gScomStack == []))
    if gManualEn == True : HandleManualCmds ()
    if gScomStack != [] : HandleScomCmds (gScomStack)

CloseOpenFiles ()

sys.exit ("\nThat's all folks..!\n")

