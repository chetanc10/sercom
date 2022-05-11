import os,sys
from cser import *

gPort = PycomSer ('/dev/ttyS7', 115200, 8, 'N', 1, 0.01, 0.01, 'N')

gPort.write ("at\r")
buf = gPort.read (20)
print (buf)

gPort.close ()
