# main.py
from _thread import allocate_lock,start_new_thread
import umqttsimple as mqtt
import pyb,array
USE_DC=[]

DISCON=0
CONN=1
ERR=2

class MqttClient:
    def __init__(self,conf):
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],conf['port'])
        self.run=True
        self.con_stat=DISCON
        self.machine_id=conf['id']
    def run(self,d_s):
        while self.run:
            msg=self.queue.get(timeout=20)
            if not msg:
                self.client.ping()
                continue
            if self.conn_stat!=CONN:
                try:
                    self.client.connect(clean_session=True)
                    self.con_stat=CONN
                except:
                    self.con_stat=ERR
            print('sending',msg)
            self.client.publish('%s/%s' % (self.machine_id,msg[0]),msg[1])

class Queue(list):
    def __init__(self):
        list.__init__(self,[])
        self._mutex=allocate_lock()
        self._event=allocate_lock()
        self._event.acquire()
    def push(self,obj):
        with self._mutex:
            self.append(obj)
            self._event.release()
        self._event.acquire()
    def get(self,timeout=None):
        gotit=self._event.acquire(True,timeout)
        if gotit:
            self._event.release()
            with self._mutex:
                evt=this.pop(0)
            self._event.acquire()
            return evt
        else:
            return None

class Scheduler:
    def __init__(self,queue):
        self._queue=queue
        self.dc_modules=[]
        self.samp_freq=0
        self.req_samp_rates={}
        self._multipliers={}
        self.readings=array.array('H')
    def add(self,module):
        if SAMPLE_RATE,dc not in module:
            raise ImportError('module is not a dc module')
        if module.SAMPLE_RATE!=self.sample_freq:
            self.req_sample_rates[module.__name__]=module.SAMPLE_RATE
            self.samp_freq=max(self.samp_freq,module.SAMPLE_RATE)
            self.recalc_mults()
        self.dc_modules.append(module)
    def recalc_mults(self):
        self._multipliers={}
        for mod in self.req_samp_rates:
            n_mult=self.samp_freq/self.req_samp_rates[mod]
            if n_mult in self._multipliers:
                self._multipliers[n_mult].append(mod)
            else:
                self._multipliers[n_mult]=[mod]
    def run(self):
        self._timer=machine.Timer(id='dc_sched')
        self._timer.init(freq=self.samp_freq,mode=machine.Timer.PERIODIC,callback=self.isr)
        while 1:
            if len(self.readings)>0:
                int_state=pyb.disable_interrupts()
                while len(self.readings):
                    self.send(self.readings[curr_reading])
                self.readings_index=0
                pyb.enable_interrupts(int_state)
            else:
                time.sleep(.1)
    def isr(self,)



if __name__=='__main__':
    import network
    config={}
    _curr_section=None
    c_f=open('node.conf','r')
    for c_l in c_f.readlines():
        if '[' in c_l:
            _curr_section=c_l[c_l.index('[')+1:c_l.index(']')]
            config[_curr_section]={}
        elif '=' in c_l:
            key,val=c_l.strip().split('=',1)
            if _curr_section:
                config[_curr_sction][key]=val
            else:
                config[key]=val
    c_f.close()
    net_conf=config.pop('network',None)
    if net_conf:
        nic=network.WLAN(network.STA_IF)
        nic.active(True)
        nic.connect(config['network']['ssid'],config['network']['key'])
    queue=Queue()
    cli=MqttClient(config.pop('mqtt'))
    sched=Scheduler(queue)
    for key in config:
        # configure _dc module in scheduler
        if 'module' in config[key]:
            exec('import '+config[key]['module'])
            ds_m=eval(config[key]['module'])
            sched.add(ds_m)
    sched.run()
    cli.run()
    
