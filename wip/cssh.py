
from __future__ import print_function, unicode_literals
import sys

import subprocess
import time
import fcntl, os

#import pdb; pdb.set_trace ()

#remote="venkataki@192.168.225.29"
remote="chetan@192.168.0.156"
opts="-t"
port="-p22"

ph = subprocess.Popen(['ssh', opts, remote, port],
                               stdin = subprocess.PIPE,
                               stdout = subprocess.PIPE,
                               stderr = subprocess.PIPE,
                               universal_newlines=True,
                               text=True,
                               bufsize=1)
print (ph.stdin.fileno ())
print (ph.stdout.fileno ())
print (ph.stderr.fileno ())
fcntl.fcntl(ph.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
fcntl.fcntl(ph.stderr.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

def ReadOut (cmd) :
    tmo = 2
    while tmo >= 0 :
        try :
            line = ph.stdout.readline ()
            print (line,end="")
            if not line : 
                tmo -= 1
                time.sleep (1)
        except IOError :
            break
    tmo = 2
    while tmo >= 0 :
        try :
            line = ph.stderr.readline ()
            print (line,end="")
            if not line : 
                tmo -= 1
                time.sleep (1)
        except IOError :
            break

print ("----------\n")
ph.stdin.write("ls .\n")
ReadOut ("ls .")
print ("----------\n")
ph.stdin.write("uptime\n")
ReadOut ("uptime")
print ("----------\n")
ph.stdin.write("logout\n")
ph.stdin.close()

quit ()

