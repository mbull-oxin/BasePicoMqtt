#DS18x20_dc.py
# dc module for ds18x20 onewire temp sensors

from machine import Pin
import onewire,ds18x20,binascii

# sample rate in hz max 1000
SAMPLE_RATE=1
DATA_TYPE='temperature'

ds_registry={}

class DsBus:
    def __init__(self,pin):
        self.ow=onewire.OneWire(Pin(int(pin)))
        self.ds=ds18x20.DS18X20(self.ow)
        #self._timer=machine.Timer('ds18x20_dc')
        #self.timer.init(mode=machine.Timer.PERIODIC,freq=1.25,callback=self.convert)    # frequency of 1.25Hz = period of 800ms
    def scan(self):
        return self.ds.scan()
    def convert(self):
        self.ds.convert_temp()
    def read_temp(self,rom):
        return self.ds.read_temp(rom)

class DC:
    def __init__(self,conf,name):
        global ds_registry
        self.name=name
        self.conf=conf
        if 'threshold' in self.conf:
            self.threshold=self.conf['threshold']
        else:
            self.threshold=30
        pin_no=self.conf['addr'][0]
        rom_addr=binascii.unhexlify(self.conf['addr'][1])
        if pin_no not in ds_registry:
            ds_registry[pin_no]=DsBus(pin_no)
        self.ds=ds_registry[pin_no]
        if rom_addr not in self.ds.scan():
            for rom in self.ds.scan():
                print('ROM - %s' % binascii.hexlify(rom))
            raise AttributeError('rom not found')
        self.rom=rom_addr
    def getReading(self):
        self.ds.convert()
        temp=self.ds.read_temp(self.rom)
        return (self.name,DATA_TYPE,{'temp':temp,'AlertVal':temp>=self.threshold,'Threshold':self.threshold,'sensor':self.name})

