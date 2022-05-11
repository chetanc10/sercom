import sys
import serial
from serial import Serial

class PycomSer : #{
    """ Pycom Serial Port Console Manager Class """
    # Port Handle
    ph = None
    # Python version identifier
    pyver = int (sys.version[0])
    # Serial Port setup on class instantiation
    def __init__ (self, port, baud, bytesz, \
            parity, stpbit, rdtout, wrtout, flowct) :
        try :
            self.ph = serial.Serial (port=port, baudrate=baud, \
                    bytesize=bytesz, parity=parity, stopbits=stpbit, \
                    timeout=rdtout, xonxoff=flowct=='X', \
                    rtscts=flowct=='R', dsrdtr=flowct=='D')
            if self.pyver == 2 : self.ph.writeTimeout = wrtout
            else : self.ph.write_timeout = wrtout
            print ("Opened port: " + port)
        except serial.serialutil.SerialException :
            print ("Unable to open Serial port: " + port)
    # Serial Port Close handler
    def close (self) :
        if not self.ph : return
        port = self.ph.port
        self.ph.close ()
        print ("Closed serial port: " + port)
    # Serial Port Data Tx handler
    def write (self, buf) :
        if self.pyver != 2 : buf = buf.encode ()
        try : nbytes = self.ph.write (buf)
        except serial.serialutil.SerialTimeoutException : nbytes = -1
        self.ph.flush ()
        return nbytes
    # Serial Port Data Rx handler
    def read (self, nbytes) :
        if nbytes == 0 : nbytes = 100
        try : buf = self.ph.read (nbytes)
        except serial.serialutil.SerialTimeoutException : buf = ''
        if self.pyver != 2 : buf = buf.decode ()
        return buf
#}

