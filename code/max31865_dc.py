######################################################################################
#Title   :  MAXIM Integrated MAX31865 Library for Raspberry pi Pico
#Author  :  Bardia Alikhan Afshar <bardia.a.afshar@gmail.com>
#Language:  Python
#Hardware:  Raspberry pi pico
#######################################################################################
# Extended to pico shoestring dc by Matthew Bull <mbull@oxin.co.uk>
#######################################################################################
import math
from machine import Pin, SPI

SAMPLE_FREQ=1

MAX31865_REG_CONFIG =0x00
MAX31865_REG_RTD    =0x01
MAX31865_REG_HFT    =0x03
MAX31865_REG_LFT    =0x05
MAX31865_REG_FAULT  =0x07

# Configuration Register
MAX31865_CONFIG_50HZ_FILTER =0x01
MAX31865_CONFIG_CLEAR_FAULT =0x02
MAX31865_CONFIG_3WIRE       =0x10
MAX31865_CONFIG_ONE_SHOT    =0x20
MAX31865_CONFIG_AUTO        =0x40
MAX31865_CONFIG_BIAS_ON     =0x80

class MAX31865:
    def __init__(self,SPInum,cs=1,miso=4,mosi=7,sck=6):
        self.spi=SPI(SPInum, 100_000, polarity=0, phase=1,miso=Pin(miso),mosi=Pin(mosi),sck=Pin(sck))
        self.cs=Pin(cs, Pin.OUT)    #Chip Select Pin
        self._regWrite(MAX31865_REG_CONFIG,MAX31865_CONFIG_BIAS_ON | MAX31865_CONFIG_CLEAR_FAULT | MAX31865_CONFIG_50HZ_FILTER | MAX31865_CONFIG_AUTO | MAX31865_CONFIG_3WIRE)
        self.RefR = 430.0
        self.R0  = 100.0
    def _regWrite(self,reg,data):
        """
        Write 1 byte to the specified register.
        """
        # Construct message (set ~W bit low, MB bit low)
        msg=bytearray()
        msg.append(0x80 | reg)
        msg.append(data)
        # Send out SPI message
        self.cs.value(0)
        self.spi.write(msg)
        self.cs.value(1)
    def _regRead(self,reg,nbytes=1):
        """
        Read byte(s) from specified register. If nbytes > 1, read from consecutive
        registers.
        """
        # Determine if multiple byte (MB) bit should be set
        if nbytes < 1:
            return bytearray()
        elif nbytes==1:
            mb=0
        else:
            mb=1
        # Construct message (set ~W bit high)
        msg = bytearray()
        msg.append(0x00 | (mb << 6) | reg)
        # Send out SPI message and read
        self.cs.value(0)
        self.spi.write(msg)
        data=self.spi.read(nbytes)
        self.cs.value(1)
        val=0
        for byte in data:
            val=(val<<8)+byte
        return val
    def readTemp(self):
        """
        return current temperature in celcius or an error if there is an error condition
        """
        error=self._regRead(MAX31865_REG_FAULT)
        if(error):                   # Returns error number and Temp=0              
            return error,0
        raw_rtd=self._regRead(MAX31865_REG_RTD,nbytes=2)
        RTD=(raw_rtd * self.RefR) / (32768)
        A=3.908e-3
        B=-5.775e-7
        temp=(-A + math.sqrt(A*A - 4*B*(1-RTD/self.R0))) / (2*B)
        return error,temp        

class DC:
    def __init__(self,config,name):
        spi_ck,spi_cs=config['addr']
        if spi_ck in (2,6,18):
            spi_bus=0
        elif spi_ck in (10,14):
            spi_bus=1
        else:
            raise ValueError('please use hardware spi: invalid serial clock pin for spi')
        self.dev=MAX31865(spi_bus,cs=spi_cs,miso=spi_ck-2,mosi=spi_ck+1,sck=spi_ck)
        self.r_id=name
        self.config=config
        if 'warn_threshold' in self.config:
            self.thrsh=self.conf['warn_threshold']
        else:
            self.thrsh=250
    def getReading(self):
        err,t_c=self.dev.readTemp()
        if err:
            print('Thermocouple Error')
        else:
            if t_c>self.thrsh:
                alert=1
            else:
                alert=0
            return (self.r_id,{'temp':t_c,'sensor':'MAX31855','AlertVal':alert,'Threshold':self.thrsh})

if __name__=='__main__':
    sensor=MAX31865(0,cs=5,sck=6,mosi=7,miso=4)
    print('CONFIG:',sensor._regRead(MAX31865_REG_CONFIG))
    print('RTD:',sensor._regRead(MAX31865_REG_RTD,nbytes=2))
    print('HFT:',sensor._regRead(MAX31865_REG_HFT,nbytes=2))
    print('LFT:',sensor._regRead(MAX31865_REG_LFT,nbytes=2))
    print('FAULT:',sensor._regRead(MAX31865_REG_FAULT))
    while True:
        print('Temp:',sensor.ReadTemp()[1]['temp'])


