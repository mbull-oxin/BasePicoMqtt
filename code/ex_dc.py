import machine,micropython,time

SAMPLE_RATE=1  # 10 hz sample freq....
DATA_TYPE='ExampleReading'

class DC:
    def __init__(self,conf,name):
        self.conf=conf
        self.r_id=name
    def getReading(self):
        ''' getReading should return tuple of device id and dict representing reading'''
        return (self.r_id,DATA_TYPE,{'AlertVal': 0, 'Threshold': 50, 'ThresholdLow': 0, 'sensor': self.r_id, 'ThresholdHigh': 50, 'temp': 21.875})
