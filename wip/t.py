#!/usr/bin/env python

import os
import sys
import serial
import time
import re
import platform
import getopt
import os.path
import logging
import select
import threading
import functools
from functools import partial

# Set python-version identifier as:
# 2 for 2.x, 3 for 3.x, etc
gPyVer = int (platform.python_version()[0])

#import pdb; pdb.set_trace ()

# global flag controlling script continue-run/just-kill
gScriptIsAlive = True
# Modem interface type identifier
MODEM_AT = 0
MODEM_CLI = 1
gModem = MODEM_AT
# serial port identifier
gSerPort = ""
# global serial rx data buffer
gRxBuf = ""
# flag used at setup time to use threaded/non-threaded rx-loop
gSerialRxThread = True
# global/input sentries list
gWildSentries = ['\r\nOK\r\n', '\r\nERROR\r\n', '\r\n+CME ERROR:.*\r\n']
# list with string after wildcards (i.e. after .*) or else have ''
gWildCards = []
# list of sentries removed with patterns from wildcard and after
gSentries = []
# length of sentries in gSentries list
gSentryLens = []

# Function to receive data over Serial port in python-version independent way
# Usage  : RecvSerialData (SerialPort, nBytes)
#          SerialPort - Serial Port Interface handle
#          nBytes     - number of bytes to recv
# Return : String containing the data received on serial port
def RecvSerialData (SerialPort, nBytes) :
    try : Data = SerialPort.read (nBytes)
    except serial.serialutil.SerialTimeoutException : Data = ''
    if gPyVer == 3 : Data = Data.decode ()
    return Data

# Function to send data over Serial port in python-version independent way
# Usage  : SendSerialData (SerialPort, buf)
#          SerialPort - Serial Port Interface handle
#          buf        - buffer containing data to be send over serial port
# Return : number of data bytes sent over the serial port
def SendSerialData (SerialPort, buf) :
    if gPyVer == 3 : buf = buf.encode ()
    try : numTxBytes = SerialPort.write (buf)
    except serial.serialutil.SerialTimeoutException : numTxBytes = -1 
    SerialPort.flush ()
    return numTxBytes

# Function to read console (stdin) input being python-version-agnostic
# Usage  : ReadConsoleInput (prompt)
#          prompt     - prompt string (optional)
# Return : Console input data given by user from stdin console
if gPyVer == 3 : ReadConsoleInput = input
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

# Function to poll for receive data and get number of bytes to recv
# Usage  : PollSerialRx (SerialPort, timeout)
#          SerialPort - Serial Port Interface handle
#          timeout    - timeout in seconds
# Return : On Success - number of bytes to recv (0 or  more)
#          On Failure - -1
if gPyVer == 3 :
    def PollSerialRx (SerialPort, timeout) :
        ports = [SerialPort]
        try :
            re, we, erre = select.select (ports, ports, ports, timeout)
            if erre : print ("\n*******ERROR**********\n"); return -1
            if re : return SerialPort.in_waiting
        except OSError as error :
            if error.args[0] == 9 : pass # serial-port closed by now
            else : print ("\nERROR: "); print (error)
        except TypeError : pass
        return 0
else :
    def PollSerialRx (SerialPort, timeout) :
        delay = 0.01
        while (timeout > 0) and gScriptIsAlive :
            try :
                nBytes = SerialPort.inWaiting ()
                if nBytes > 0 : return nBytes
                timeout -= delay; time.sleep (delay)
            except : timeout = 0
        return 0

def SetupSentries () :
    global gWildCards
    global gSentries
    global gSentryLens
    i = 0
    # do wildcard match till '\r\n'    or  '\r'    or  '\n'
    # if a sentry ends with  '.*\r\n'  or  '.*\r'  or  '.*\n' 
    for sentry in gWildSentries :
        if ".*\r\n" in sentry :
            gWildCards.append ("\r\n")
            gSentries.append (sentry.split(".*\r\n")[0])
        elif ".*\r" in sentry :
            gWildCards.append ("\r")
            gSentries.append (sentry.split(".*\r")[0])
        elif ".*\n" in sentry :
            gWildCards.append ("\n")
            gSentries.append (sentry.split(".*\n")[0])
        else :
            gWildCards.append ("")
            gSentries.append (sentry)
        i += 1
        # length of given sentries list
        gSentryLens = [len(sentry) for sentry in gSentries]

#gSerPort = serial.Serial (port="COM6", timeout=0.01, baudrate=115200)
gSerPort = serial.Serial (port="/dev/ttyS6", timeout=0.01, baudrate=115200)

def GetResponse (cmd, timeout) :
    global gRxBuf
    # For AT-type Modems (not CLI based), it's per AT cmd
    if cmd == '' : return ''
    # Find the first cmd occurrence in gRxBuf
    delay = 0.01
    while timeout > 0 :
        SoC = gRxBuf.find (cmd)
        if SoC >= 0 : break
        timeout -= delay; time.sleep (delay)
    if timeout <= 0 or SoC < 0 : return ''
    # Found the cmd, check for full-response
    fullrsp = ''
    while timeout > 0 :
        # list with element: sentry find-indexes or -1
        sentryPos = [gRxBuf.find (i) for i in gSentries]
        # Now find first valid sentry 
        pos = len (gRxBuf)
        sentryIdx = -1
        i = 0
        while i < len (sentryPos) :
            if pos > sentryPos[i] and sentryPos[i] >= 0: 
                pos = sentryPos[i]
                sentryIdx = i
            i += 1
        if sentryIdx != -1 :
            # Found a full ATCmdResp
            EoR = pos + gSentryLens[sentryIdx]
            # If sentry's a wildcard, match it properly
            wcard = gWildCards[sentryIdx]
            if wcard : EoR += gRxBuf[EoR:].find (wcard) + len (wcard)
            fullrsp = StripStartOfString (gRxBuf)[SoC:EoR]
            # Yay..  a full ATCmdResp, handle it
            gLockRxBuf.acquire ()
            gRxBuf = gRxBuf[:SoC] + gRxBuf[EoR:]
            gLockRxBuf.release ()
            break
            #print ("now, gRxBuf: " + repr (gRxBuf))
        timeout -= delay; time.sleep (delay)
    return fullrsp

def SerialRxLoop (name) :
    global gRxBuf

    while gScriptIsAlive :
        nBytes = PollSerialRx (gSerPort, 2)
        if nBytes <= 0 : continue
        #print ("Rx-Count: " + str (nBytes))
        rxchunk = RecvSerialData (gSerPort, nBytes)
        if rxchunk == "": continue
        # append the rxchunk to global rx buffer
        gLockRxBuf.acquire ()
        gRxBuf += rxchunk
        gLockRxBuf.release ()
        # Write Serial data on console
        rxd = rxchunk
        if gModem == MODEM_AT :
            if rxd[0:2] == '\r\n' : rxd = rxd[2:]
            cmd = gSerCmd
            soc = rxd.find (cmd)
            if soc >= 0 :
                eoc = soc + len (cmd)
                if rxd[eoc:eoc+2] == '\r\n' : eoc += 2
                rxd = rxd[:soc] + rxd[eoc:]
        sys.stdout.write (rxd)
        if not gSerialRxThread : time.sleep (0.5); break

#if __name__ == "__main__":
gLockRxBuf = threading.Lock ()
SetupSentries ()

if gSerialRxThread :
    x = threading.Thread(target=SerialRxLoop, args=("SerialRxLoop",))
    x.start()

while True : 
    try :
        cmd = ReadConsoleInput ('')
        if not cmd : continue
        gSerCmd = cmd+'\r'
        SendSerialData (gSerPort, cmd+'\r')
        if not gSerialRxThread : SerialRxLoop ('rxloop')
        rsp = GetResponse (cmd+'\r', 3)
        # process rsp and/or call handlers/callbacks as required
        #sys.stdout.write (rsp)
    except IOError : pass
    except (EOFError, KeyboardInterrupt) :
        gScriptIsAlive = False
        break

if gSerialRxThread :
    try : x.join()
    except KeyboardInterrupt : pass

print ("DONE!")

gSerPort.close ()
quit ()

