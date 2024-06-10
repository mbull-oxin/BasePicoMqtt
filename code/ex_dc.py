import machine,micropython,time

dc_name='example_dc'

class dc:
    def __init__(self,conf):
        self.timer=machine.Timer()
        self.conf=conf
        self._reading=0
    def run(self,run_flag):
        self._run=run_flag
        self.timer.init(mode=machine.Timer.PERIODIC,freq=int(self.conf['freq']),callback=self.reading)
    def reading(self,timer):
        # do the reading here
        print('reading timer')
        self._reading=time.time()
        if not self._run:
            timer.deinit()
        #print('done')
    def getReading(self):
        irq_state=machine.disable_irq()
        r=self._reading
        machine.enable_irq(irq_state)
        return r
