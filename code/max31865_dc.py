######################################################################################
#Title   :  MAXIM Integrated MAX31865 Library for Raspberry pi Pico
#Author  :  Bardia Alikhan Afshar <bardia.a.afshar@gmail.com>
#Language:  Python
#Hardware:  Raspberry pi pico
#######################################################################################
# Extended to pico shoestring dc by Matthew Bull <mbull@oxin.co.uk>
#######################################################################################
import math
from max31865 import Max31865
SAMPLE_RATE=1
DATA_TYPE='temperature'

class DC:
    def __init__(self,config,name):
        spi_ck,spi_cs=config['addr']
        if spi_ck in (2,6,18):
            spi_bus=0
        elif spi_ck in (10,14):
            spi_bus=1
        else:
            raise ValueError('please use hardware spi: invalid serial clock pin for spi')
        #self.dev=MAX31865(spi_bus,cs=spi_cs,miso=spi_ck-2,mosi=spi_ck+1,sck=spi_ck)
        self.dev=Max31865(spi_bus,spi_cs,sck=spi_ck,mosi=spi_ck+1,miso=spi_ck-2,wires=3,filter_frequency=50,ref_resistor=430)
        self.r_id=name
        self.config=config
        if 'threshold' in self.config:
            self.thrsh=config['threshold']
        else:
            self.thrsh=250
    def getReading(self):
        if True in self.dev.fault:
            print('[ERROR] temp sensor error')
        else:
            t_c=self.dev.temperature
            print('Temp %s -> %s' % (self.r_id,t_c))
            if t_c>self.thrsh:
                alert=1
            else:
                alert=0
            return (self.r_id,DATA_TYPE,{'temp':t_c,'sensor':'%s-MAX31865' % self.r_id,'AlertVal':alert,'Threshold':self.thrsh})

if __name__=='__main__':
    mx=Max31865(0,5,wires=3,sck=6,mosi=7,miso=4,filter_frequency=50,ref_resistor=430)
    if True in mx.fault:
        print(mx.fault)
    else:
        print(mx.temperature)


