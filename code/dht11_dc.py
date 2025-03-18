import dht
from machine import Pin

SAMPLE_FREQ=1  # 10 hz sample freq....
DATA_TYPE='humidity'

class DC:
    def __init__(self,conf,name):
        self.conf=conf
        self.r_id=name
        if 'version' in self.conf:
            vers=self.conf['version']
        if vers in (2,22):
            self.dht=dht.DHT22(Pin(self.conf['pin']))
        else:
            self.dht=dht.DHT11(Pin(self.conf['pin']))
        self.dht.measure()
    def getReading(self):
        self.dht.measure()
        return (self.r_id,DATA_TYPE,{'temp':self.dht.temperature(),'humidity':self.dht.humidity(),'AlertVal':0,'Threshold':40,'sensor':'%s-DHT' % self.r_id})
