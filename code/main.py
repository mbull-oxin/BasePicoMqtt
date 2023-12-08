# main.py
from _thread import allocate_lock,start_new_thread
import umqttsimple as mqtt
import machine,array,time,micropython,json

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
    def run(self,d_s,run_flag):
        self._run=run_flag
        while self._run:
            #print('getting event')
            msg=d_s.get(timeout=20)
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
                time.sleep(1)
                break
            else:
                time.sleep(0.1)
        if len(self._list):
            with self._mutex:
                evt=self._list.pop(0)
            return evt
        else:
            return None

class DcManager:
    def __init__(self,queue):
        self._queue=queue
        self.dc_modules=[]
        self.dc_obj=[]
        self.output=[]
        self._run=None
    def add(self,module,conf):
        self.dc_modules.append(module)
        try:
           dc=module.dc(conf)
        except AttributeError:
            print('module is not a dc module')
            raise ImportError('module is not a dc module')
        self.dc_obj.append(dc)
        dc.run(_run)
    def run(self,run_flag):
        self._run=run_flag
        while self._run:
            try:
                for mod_idx in range(len(self.dc_modules)):
                    mod_name=self.dc_modules[mod_idx].dc_name
                    reading=self.dc_obj[mod_idx].getReading()
                    self.send(mod_name,reading)
                time.sleep(1)
            except KeyboardInterrupt:
                self._run.set(False)
                break
    def send(self,mod_name,reading):
        print(mod_name,reading)
        self._queue.put((mod_name,json.dumps({'reading':reading,'timestamp':time.time()})))

import network
config={}
_run=RunFlag()
_curr_section=None
c_f=open('node.conf','r')
for c_l in c_f.readlines():
    #print(c_l)
    if '#' in c_l:
        continue
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
print(config['network'])
net_conf=config.pop('network',None)
nic=None
if net_conf:
    nic=network.WLAN(network.STA_IF)
    nic.active(True)
    nic.connect(net_conf['ssid'],net_conf['key'])
    while nic.status()!=network.STAT_GOT_IP:
        if nic.status==network.STAT_CONNECT_FAIL:
            nic.active(False)
            print('[network] Connection failed')
        elif nic.status==network.STAT_NO_AP_FOUND:
            print('[network] No AP found')
        elif nic.status==network.STAT_WRONG_PASSWORD:
            print('[network] Incorrect password')
        else:
            print('network status',nic.status())
        time.sleep(1)
        nic.active(True)
time.sleep(1)
queue=Queue()
cli=MqttClient(config.pop('mqtt'))
mgr=DcManager(queue)
for key in config:
    # configure _dc module in scheduler
    if 'module' in config[key]:
        exec('import '+config[key]['module'])
        ds_m=eval(config[key]['module'])
        mgr.add(ds_m,config[key])
#start_new_thread(mgr.run,(),{})
start_new_thread(cli.run,(queue,_run),{})
mgr.run(_run)
    
