import machine,dht

SAMPLE_RATE=0.2  # 10 hz sample freq....
DATA_TYPE='DissolvedOxygen'

DEF_T_HIGH=80
DEF_T_LOW=20

CHANNEL_MAP=[26,27,28]

VREF=3300
ADC_res=1024

DO_TABLE=[    
    14460, 14220, 13820, 13440, 13090, 12740, 12420, 12110, 11810, 11530,
    11260, 11010, 10770, 10530, 10300, 10080, 9860, 9660, 9460, 9270,
    9080, 8900, 8730, 8570, 8410, 8250, 8110, 7960, 7820, 7690,
    7560, 7430, 7300, 7180, 7070, 6950, 6840, 6730, 6630, 6530, 6410
]

THRESHOLDS=(20,80)

class DC:
    def __init__(self,conf,name,ctrl=None):
        self.conf=conf
        self.r_id=name
        if 'adc_channel' in conf:
            pin=machine.Pin(CHANNEL_MAP[conf['adc_channel']])
        elif 'adc_pin' conf:
            pin=machine.Pin(conf['pin'])
        else:
            raise ValueError('grav_DO_dc configuration must have atleast one of adc_channel or adc_pin')
        if not 'calibration' in conf:
            raise KeyError('no sensor calibration found')
        if len(conf['calibration'])<2:
            self.two_point=False
        else:
            self.two_point=True
        self.cal=conf['calibration']
        self.ADC(pin,1000)
        # no good must be prcoess temp not ambient
        #if 'dht_pin' in conf:
        #    if conf['dht_vers'] in (2,22):
        #        self.dht=dht.DHT22(machine.Pin(conf['dht_pin']))
        #    else:
        #        self.dht=dht.DHT11(machine.Pin(conf['dht_pin']))
        #    self.dht.measure()
        #    self._curr_temp=self.dht.temperature()
        #    self._th_update=False
        #    self._temp_timer=Timer(period=30_000,mode=Timer.PERIODIC,callback=self.updateTH)
        #else:
        #    self.dht=None
        self.controller=ctrl
        ctrl.getLastReading('temperature')
        if 'temp_sensor_id' in conf:

        self._curr_temp=20
    def updateTH(self,timer):
        '''update temp from process temperature sensor on a schedule'''
        if timer==self._temp_timer:
            self.dht.measure()
            t=self.dht.temperature()
            if self._curr_temp!=t:
                self._curr_temp=t
                self._th_update=True
            h=self.dht.humidity()
            if self._curr_humidity!=h:
                self._curr_humidity=h
                self._th_update=True
    def getReading(self):
        ''' getReading should return tuple of device id and dict representing reading'''
        uv=self.ADC.read_uv()
        if self.th_update:
            
        if self.two_point:
            V_saturation = (self._curr_temp - self.cal[1][1]) * (self.cal[0][0] - self.cal[1][0]) / (self.cal[0][1] - self.cal[1][1]) + self.cal[1][0]
        else:
            V_saturation=self.cal[0][0]+35*self._curr_temp-self.cal[0][1]*35
        C_saturation=uv*DO_TABLE[int(self._curr_temp)]/V_saturation
        return (self.r_id,DATA_TYPE,{'AlertVal': (C_saturation>self.t_high or C_saturation<self.t_low),'ThresholdLow':self.t_low, 'ThresholdHigh': self.t_high, 'sensor': self.r_id, 'saturation': C_saturation})

