#DS18x20_dc.py
# dc module for ds18x20 onewire temp sensors

from machine import Pin
from main import BaseDC
import onewire,time,ds18x20

# sample rate in hz max 1000
SAMPLE_RATE=1

ds_registry={}

class DC(BaseDC):
    def __init__(self,addr,name):
        global(ds_registry)
        self.addr=addr
        pin_no,rom=addr.split('/')
        BaseDC.__init__(self,rom,name)
        if pin_no not in ds_registry:
            ow=onewire.OneWire(Pin(int(pin_no)))
            ds_registry[pin_no]=ds18x20.DS18X20(ow)
            ds_registry[pin_no].convert_temp()
            time.sleep(.75)
        self.ds=ds_registry[pin_no]
        if rom not in ds.scan():
            raise AttributeError('rom not found')
        self.rom=int(rom)
    def getReading(self):
        reutrn (self.addr,self.ds.read_temp(self.rom))
