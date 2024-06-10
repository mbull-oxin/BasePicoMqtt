# main.py
from _thread import allocate_lock,start_new_thread
import umqttsimple as mqtt
import machine,array,time,micropython,pyb

micropython.alloc_emergency_exception_buf(200)

USE_DC=[]

DISCON=0
CONN=1
ERR=2

class RunFlag:
    def __init__(self,flag=True):
        self._flag=flag
    def set(self,state):
        self._flag=state
    def __bool__(self):
        if self._flag:
            return True
        else:
            return False

class MqttClient:
    def __init__(self,conf):
        print(conf)
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],int(conf['port']))
        self._run=None
        self.con_stat=DISCON
        self.machine_id=conf['id']
        try:
            print(self.client.port)
            self.client.connect(clean_session=True)
            self.con_stat=CONN
            print('[MqttClient] contected')
        except Exception as exc:
            print('[MqttClient] error connecting to broker',exc)
            self.con_stat=ERR
            #continue
    def run(self,queue):
        while self._run:
            #print('getting event')
            msg=queue.get(timeout=20)
            #print('[MqttClient] got',msg)
            if not msg and self.con_stat==CONN:
                print('ping')
                self.client.ping()
                continue
            if msg and self.con_stat!=CONN:
                try:
                    print(self.client.port)
                    self.client.connect(clean_session=True)
                    self.con_stat=CONN
                    print('[MqttClient] contected')
                except Exception as exc:
                    print('[MqttClient] error connecting to broker',exc)
                    print('[MqttClient] dropped msg - %s' % msg)
                    self.con_stat=ERR
                    continue
            if msg:
                print('[MqttClient] sending',msg)
                try:
                    self.client.publish('%s/%s' % (self.machine_id,msg[0]),msg[1])
                except Exception as exc:
                    print('[MqttClient] error publishing to broker',exc)
                    self.con_stat=ERR
                    continue
        self._run.set(False)

class Queue():
    def __init__(self):
        self._list=[]
        self._mutex=allocate_lock()
        self._event=allocate_lock()
        self._event.acquire()
        self._timer=machine.Timer()
    def put(self,obj):
        with self._mutex:
            self._list.append(obj)
            self._event.release()
        time.sleep(.1)
        self._event.acquire(False)
    def _timeout(self,timer):
        print('timeout',timer,self._timer)
        if timer==self._timer:
            self._event.release()
            micropython.schedule(self._reacquire,[])
    def _reacquire(self,*args):
            while 1:
                if self._event.acquire(False):
                    break
    def get(self,timeout=None):
        if timeout:
            self._timer.init(mode=machine.Timer.ONE_SHOT,period=timeout*1000,callback=self._timeout)
        print('entering loop with timeout',timeout*1000)
        while 1:
            #print('entering loop with timeout',timeout*1000)
            gotit=self._event.acquire(False)
            #print(gotit)
            if gotit:
                self._event.release()
                time.sleep(.5) # is this really required??
                break
            else:
                time.sleep(0.1)
        if len(self._list):
            with self._mutex:
                evt=self._list.pop(0)
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
    def add(self,module,dc):
        #module=sys.modules[dc.__module__]
        mod_name=module.__name__
        if module.SAMPLE_RATE!=self.sample_freq and mod_name not in self.req_samp_rates:
            self.req_sample_rates[mod_name]=module.SAMPLE_RATE
            self.samp_freq=max(self.samp_freq,module.SAMPLE_RATE)
            self.recalc_mults()
        if mod_name in self.dc_inst:
            self.dc_inst[mod_name].append(dc)
        else:
            self.dc_inst[mod_name]=[dc]
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
        sched.add(ds_m,ds_m.DC(config[key]['addr']))
    start_new_thread(cli.run,(queue),{})
    sched.run()
    
