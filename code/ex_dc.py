import machine,micropython,time

SAMPLE_RATE=1  # 10 hz sample freq....
DATA_TYPE='ExampleReading'

DEF_T_HIGH=80
DEF_T_LOW=20

class DC:
    def __init__(self,conf,name,ctrl=None):
        self.conf=conf
        self.r_id=name
        if 'threshold_high' in conf:
            self.t_high=conf['threshold_high']
        else:
            self.t_high=DEF_T_HIGH
        if 'threshold_low' in conf:
            self.t_low=conf['threshold_low']
        else:
            self.t_low=DEF_T_LOW
    def getReading(self):
        ''' getReading should return tuple of device id and dict representing reading'''
        reading=21.875
        return (self.r_id,DATA_TYPE,{'AlertVal': (reading>self.t_high or reading<self.t_low),'ThresholdLow':self.t_low, 'ThresholdHigh': self.t_high, 'sensor': self.r_id, 'temp': reading})
