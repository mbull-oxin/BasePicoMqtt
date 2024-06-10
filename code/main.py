# main.py
from _thread import allocate_lock,start_new_thread
import umqttsimple as mqtt
import pyb,array,sys
USE_DC=[]

DISCON=0
CONN=1
ERR=2

class MqttClient:
    def __init__(self,queue,conf):
        self._queue=queue
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],conf['port'])
        self.run=True
        self.con_stat=DISCON
        self.machine_id=conf['id']
    def run(self,d_s):
        while self.run:
            msg=self._queue.get(timeout=20)
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
        if len(self):
            with self._mutex:
                evt=this.pop(0)
            return evt
        else:
            gotit=self._event.acquire(True,timeout)
            if gotit:
                with self._mutex:
                    evt=this.pop(0)
                self._event.release()
                #self._event.acquire()
                return evt
            else:
                return None

class Scheduler:
    def __init__(self,queue):
        self._queue=queue
        self.dc_inst={}
        self.samp_freq=0
        self.req_samp_rates={}
        self._multipliers={}
        self.readings=array.array('H')
        self._count=0
    def add(self,dc):
        module=sys.modules[dc.__module__]
        if module.SAMPLE_RATE!=self.sample_freq and module.__name__ not in self.req_samp_rates:
            self.req_sample_rates[module.__name__]=module.SAMPLE_RATE
            self.samp_freq=max(self.samp_freq,module.SAMPLE_RATE)
            self.recalc_mults()
        if module.__name__ in self.dc_inst:
            self.dc_inst[module.__name__].append(dc)
        else:
            self.dc_inst[module.__name__]=[dc]
    def recalc_mults(self):
        self._multipliers={}
        for mod in self.req_samp_rates:
            n_mult=self.req_samp_rates[mod]/self.samp_freq
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
                    self._queue.push(self.readings.pop(0))
                pyb.enable_interrupts(int_state)
            else:
                time.sleep(.1)
    def isr(self):
        self._count=self._count+1
        for mult in self._multipliers.keys():
            if self._count%mult==0:
                for mod in self._multipliers[mult]:
                    for dc in self.dc_inst[mod.__name__]:
                        self.readings.append(dc.getReading())

class BaseDC:
    def __init__(self,addr,name):
        self.addr=addr
        self.r_id=name
        # override to setup hardware ready for reading
    def getReading(self):
        # override to do the actual reading and return in tuple with self.r_id
        return (self.r_id,1)            

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
                config[_curr_section][key]=val
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
        if 'module' in config[key] and config[key]['module'] not in sys.modules:
            exec('import '+config[key]['module'])
        ds_m=sys.modules[config[key]['module']]
        if not ('dc' in dir(ds_m) and 'SAMPLE_RATE' in dir(ds_m)):
            raise AttributeError('not a dc module')
        sched.add(ds_m.DC(config[key]['addr'],key))
    start_new_thread(cli.run,(),{})
    sched.run()
    
