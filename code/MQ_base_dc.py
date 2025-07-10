''' 
Base module for MQ series gas sensors, subclass DC then implement suitable
convert method for the sensor in use.... 
Then change packet template for suitable MQTT packet

'''
from machine import Pin,ADC
import utime

CONV_FACTOR=3.3 / (65535)
DATA_TYPE='gas_concentration'
#Select ADC input 0 (GPIO26)
DEF_T_HIGH=80
DEF_T_LOW=20


class DC:
    def __init__(self,conf,name,ctrl=None):
        self.conf=conf
        self.r_id=name
        if 'adc_chan' in conf:
            ch=conf['adc_chan']
        else:
            # GPIO 26 / pin 31
            ch=0
        self.adc=ADC(ch,3000000)
        self.dio=Pin(22,Pin.IN)
        if 'threshold_high' in conf:
            self.t_high=conf['threshold_high']
        else:
            self.t_high=DEF_T_HIGH
        if 'threshold_low' in conf:
            self.t_low=conf['threshold_low']
        else:
            self.t_low=DEF_T_LOW
        self._heated=False
        self._st_timer=Timer(-1)
        self._st_timer.init(Timer.ONE_SHOT,period=20000,callback=self._startup)
    def _startup(self,tm):
        if tm==self._st_timer:
            self.heated=True
    def getReading(self):
        ''' read from the adc if gas is present'''
        if self.dio.value() and self._heated:
            _raw=self.adc.read_u16() * CONV_FACTOR
            gas,value,units=self.convert(_raw)
            return (self.r_id,DATA_TYPE,{'AlertVal': (reading>self.t_high or reading<self.t_low),'ThresholdLow':self.t_low, 'ThresholdHigh': self.t_high, 'sensor': self.r_id, 'gas': gas, 'value': value, 'units':units})
    def convert(self,raw_v):
        # override to convert to PPM, return tuple of (<gas>,<value>,<reading>)
        return ('base',raw_v,'volts')
    
        
        

