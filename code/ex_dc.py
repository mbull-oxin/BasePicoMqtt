import machine,micropython,time

SAMPLE_FREQ=10  # 10 hz sample freq....

class DC:
    def __init__(self,conf,name):
        self.conf=conf
        self.r_id=name
    def getReading(self):
        ''' getReading should return tuple of device id and dict representing reading'''
        return (self.r_id,{})
