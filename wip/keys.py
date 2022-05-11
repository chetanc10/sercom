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

SysRead = 1

if SysRead :
    print ("Using sys-termios")
    fd = sys.stdin.fileno()
    if gPyVer == 3 :
        import termios
        oldterm = termios.tcgetattr(fd)
        newattr = termios.tcgetattr(fd)
        newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
        #newattr[3] = newattr[3] & ~termios.ICANON
        termios.tcsetattr(fd, termios.TCSANOW, newattr)
        import fcntl
        oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)

#import pdb; pdb.set_trace ()

UP = "\x1b[A"
DN = "\x1b[B"
RT = "\x1b[C"
LF = "\x1b[D"

def PrintOptions () :
    print ("----------------------------")
    print ("|p - Port Configuration    |")
    print ("|l - Logging options       |")
    print ("|x - Exit from this Dialog |")
    print ("Choice:                     ")
    print ("----------------------------")
    print (2*UP + RT*8, end="")
    sys.stdout.flush ()

def unPrintOptions () :
    print (4*UP + LF*8, end="")
    print (6*"                              \n")
    print (7*UP, end="")
    sys.stdout.flush ()

CTRL = 0
ARROW = 0
while True :
    try :
        if SysRead == 1 :
            c = sys.stdin.read(1)
            if c :
                if CTRL == 1 :
                    if c == 'o' : 
                        PrintOptions ()
                        CTRL = 2
                        continue
                    elif c == 'x' : 
                        print ("Breaking loop for exit..")
                        CTRL=0 
                        break
                    else :
                        CTRL = 0
                        continue
                elif CTRL == 2 :
                    if c == 'p' :
                        unPrintOptions ()
                        CTRL = 0
                        continue
                    elif c == 'l' :
                        unPrintOptions ()
                        CTRL = 0
                        continue
                    elif c == 'x' :
                        unPrintOptions ()
                        CTRL = 0
                        continue
                    continue
                elif ARROW == 1 :
                    if c == '[' :
                        ARROW = 2
                        continue
                    else :
                        ARROW = 0
                elif ARROW == 2 :
                    if c == 'A'   : sys.stdout.write (UP)
                    elif c == 'B' : sys.stdout.write (DN)
                    elif c == 'C' : sys.stdout.write (LF)
                    elif c == 'D' : sys.stdout.write (RT)
                    sys.stdout.flush ()
                    ARROW = 0
                    continue
                elif c == '\x01' :
                    CTRL = 1
                    continue
                elif c == '\x1b' :
                    ARROW = 1
                    continue
                #if c == '\n': c = '\r'
                #elif c == '\x7f' : c = '\b'
                #print (repr (c))
                sys.stdout.write (c)
                sys.stdout.flush ()
    except IOError : pass
    except (EOFError, KeyboardInterrupt) :
            break

if SysRead == 1 :
    termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)

print ("\nDone with the script!!")


