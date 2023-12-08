import machine,micropython,time

dc_name='current_dc'

class dc:
    def __init__(self,conf):
        self.conf=conf
        self.timer=machine.Timer()
        self._reading=0
        self._buf=array.array('H',b'\x00\x00'*10)
        self._read_idx=0
        self._totalizer=sum(self._buf)
        self.adc=machine.ADC(machine.Pin(conf['adc_pin']))
        self.adc_mult=3.3/65535
    def run(self,run_flag):
        self._run=run_flag
        self.timer.init(mode=machine.Timer.PERIODIC,freq=int(conf['mains_freq'])*10,callback=self.reading)
    def reading(self,timer):
        # do the reading here
        #print('reading timer')
        inst_v=self.adc.read_u16()*self.adc_mult
        inst_i=inst_i*(20/3.3)
        self._totalizer-=self._buf[self._read_idx]
        self._buf[self._read_idx]=inst_i
        self._totalizer+=inst_i
        self._read_idx+=1
        if self._read_idx>=10:
            self._read_idx=0
        self._reading=(self._totalizer/10)*1.1107
        #print('done')
        if not self._run:
            self.timer.deinit()
    def getReading(self):
        irq_state=machine.disable_irq()
        r=self._reading
        machine.enable_irq(irq_state)
        return r
