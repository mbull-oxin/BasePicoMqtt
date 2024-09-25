#DS18x20_dc.py
# dc module for ds18x20 onewire temp sensors

from machine import Pin
import onewire,time,ds18x20

# sample rate in hz max 1000
SAMPLE_FREQ=1

ds_registry={}

class DsBus:
    def __init__(self,pin):
        self.ow=onewire.OneWire(Pin(int(pin_no)))
        self.ds=ds18x20.DS18X20(ow)
        self._timer=machine.Timer('ds18x20_dc')
        self.timer.init(mode=machine.Timer.PERIODIC,freq=1.25,callback=self.convert)    # frequency of 1.25Hz = period of 800ms
    def scan(self):
        return self.ds.scan()
    def convert(self,timer):
        self.ds.convert_temp()
    def read_temp(self,rom):
        return self.ds.read_temp(rom)

class DC:
    def __init__(self,conf,name):
        global ds_registry
        self.conf=conf
        pin_no,rom=self.conf['addr'].split('/')
        if pin_no not in ds_registry:
            ds_registry[pin_no]=DsBus(pin_no)
        self.ds=ds_registry[pin_no]
        if rom not in self.ds.scan():
            raise AttributeError('rom not found')
        self.rom=int(rom)
    def getReading(self):
        return (self.addr,{'temperature':self.ds.read_temp(self.rom)})

