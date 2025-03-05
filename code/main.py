# main.py
from _thread import allocate_lock,start_new_thread
from _thread import exit as t_exit
import umqtt.robust as mqtt
from machine import Pin
import machine,array,time,micropython,sys,json,datetime,network,ntptime,gc

micropython.alloc_emergency_exception_buf(200)
gc.enable()
gc.threshold(6400)
print(gc.mem_free())
DISCON=0
CONN=1
ERR=2

def setupLED(pin):                              # convenience function to setup pin for led, return machine.Pin object
    led_pin=Pin(pin,Pin.OUT)
    led_pin.off()
    return led_pin

class NetStatusLED:
    def __init__(self,grn_pin,red_pin=None,blue_pin=None):
        self._led=machine.PWM(Pin(grn_pin,Pin.OUT),freq=500,duty_ns=0) # single color may or may not be green actual led
        if red_pin and blue_pin:
            # rgb led use it...
            self._red=machine.PWM(Pin(red_pin,Pin.OUT),freq=500,duty_ns=0)
            self._blue=machine.PWM(Pin(blue_pin,Pin.OUT),freq=500,duty_ns=0)
        else:
            self._red=None
    def setStatus(self,status):
        # TODO: sensibly indicate status (one the the status constants above) using one or more leds....
        pass


# board constants...
CODE_INHIBIT=Pin(22,machine.Pin.IN,machine.Pin.PULL_UP)
NET_STATUS=NetStatusLED(18,red_pin=19,blue_pin=20)
ACT_LED=None # change to LED object from setup_led above for activity indication



class MqttClient:
    # wrap umqttsimple client and handle connection state / send all msg's from queue
    def __init__(self,conf,queue,log):
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],int(conf['port']))
        self._run=None
        self.con_stat=DISCON
        self.machine_id=conf['id']
        self.log=log
        try:
            self.client.connect(clean_session=True)
            self.con_stat=CONN
            self.log('[MqttClient] connected')
        except Exception as exc:
            self.log('[MqttClient] error connecting to broker',exc)
            self.con_stat=ERR
            #continue
        self.queue=queue
        self.act_led=setupLED(21)
    def run(self):
        self._run=True
        while self._run:
            #print('[MqttClient] wait...')
            try:
                msg=queue.get(timeout=20)
            except StopIteration:
                print('MqttClient] timeout')
                continue
            self.log('[MqttClient] got',msg)
            payload=msg[1]
            payload['machine']=self.machine_id
            t=time.localtime()
            payload['timestamp']=datetime.datetime(t[0],t[1],t[2],hour=t[3],minute=t[4],second=t[5]).isoformat()+'+00:00'
            if msg and self.con_stat!=CONN:
                try:
                    self.log(self.client.port)
                    self.client.connect(clean_session=True)
                    self.con_stat=CONN
                    self.log('[MqttClient] connected')
                except Exception as exc:
                    self.log('[MqttClient] error connecting to broker',exc)
                    self.log('[MqttClient] dropped msg -\n\tTopic - %s\n\tPayload - %s' % msg)
                    self.con_stat=ERR
                    continue
            if msg:
                self.log('[MqttClient] publish to %s/%s' % (self.machine_id,msg[0]),msg)
                self.act_led.on()
                try:
                    topic='airquality_monitoring/%s-%s' % (self.machine_id,msg[0])
                    topic=topic.encode('UTF-8')
                    self.client.publish(topic,json.dumps(msg[1]))
                    self.log('[MqttClient] publish done')
                except Exception as exc:
                    self.log('[MqttClient] error publishing to broker',exc)
                    self.con_stat=ERR
                    continue
                self.act_led.off()
        self._run=None
    def stop(self):
        self._run=False
        self.queue.put(None)
        time.sleep(2)
        t_exit()

class Queue:
    def __init__(self,q_len):
        self._q_len=q_len
        self._queue=[]
        self._mutex=allocate_lock()
        self._evt=allocate_lock()
        self._evt.acquire()
        self._timer=machine.Timer()
    def put(self,msg):
        with self._mutex:
            self._queue.append(msg)
            if len(self._queue)>=self._q_len:
                print('[Queue.put] dropping',self._queue.pop(0))
        try:
            self._evt.release()
        except RuntimeError:
            print('ERR - releasing lock')
    def wait(self,timeout=60):
        if self._queue:
            return True
        if timeout:
            self._timer.init(mode=machine.Timer.ONE_SHOT,period=timeout*1000,callback=self._timeout)
        while not self._evt.acquire(0):
            time.sleep_ms(5)
        return len(self._queue)
    def get(self,timeout=0):
        print(self._queue)
        if self.wait(timeout=timeout):
            with self._mutex:
                return self._queue.pop(0)
        else:
            raise(StopIteration())
    def _release(self,timer):
        timer.deinit()
        try:
            self._evt.release()
        except Exception as exc:
            print(exc)
    def _timeout(self,timer):
        micropython.schedule(self._release,timer)

class Scheduler:
    def __init__(self,queue):
        self._queue=queue
        self.dc_inst={}
        self.samp_freq=0
        self.req_samp_rates={}
        self._multipliers={}
        self.readings=[]
        self._count=0
        self._timer=None
        self.req_sample_rates={}
        self._read_flag=False
        self._run=1
    def add(self,module,dc):
        mod_name=module.__name__
        #print(mod_name,dc,self.req_samp_rates)
        freq_change=False
        if mod_name not in self.req_samp_rates:
            self.req_samp_rates[mod_name]=module.SAMPLE_RATE
            #print(self.req_samp_rates)
            if module.SAMPLE_RATE!=self.samp_freq:
                freq_change=True
                self.samp_freq=max(self.samp_freq,module.SAMPLE_RATE)
            #print('calling recalc',self.samp_freq,self.req_samp_rates)
            self.recalc_mults()
            if freq_change:
                if self._timer:
                    self._timer.deinit()
                else:
                    self._timer=machine.Timer()
                self._timer.init(freq=self.samp_freq,mode=machine.Timer.PERIODIC,callback=self.isr)
        if mod_name in self.dc_inst:
            self.dc_inst[mod_name].append(dc)
        else:
            self.dc_inst[mod_name]=[dc]
    def recalc_mults(self):
        self._multipliers={}
        #print('[Scheduler.recalcMults]',self.req_samp_rates)
        for mod in self.req_samp_rates:
            n_mult=int(self.samp_freq/self.req_samp_rates[mod])
            if n_mult in self._multipliers:
                self._multipliers[n_mult].append(mod)
            else:
                self._multipliers[n_mult]=[mod]
        #print('[Scheduler.recalcMults]',self._multipliers)
    def run(self):
        if not self._timer:
            self._timer=machine.Timer()
            self._timer.init(freq=self.samp_freq,mode=machine.Timer.PERIODIC,callback=self.isr)
        while self._run:
            try:
                time.sleep(1)
                gc.collect()
                #print('[Scheduler] mem free %s' % gc.mem_free())
            except KeyboardInterrupt:
                break
        self._run=-1
        self._timer.deinit()
    def _run_mult(self,mult):
        for mod in self._multipliers[mult]:
            for dc in self.dc_inst[mod]:
                print('[Scheduler._run_mult]',dc)
                self._queue.put(dc.getReading())
    def isr(self,timer):
        self._count=self._count+1
        #print('[Scheduler.isr] count',self._count)
        for mult in self._multipliers.keys():
            #print('[Scheduler.isr] mult',mult)
            if self._count%mult==0:
                micropython.schedule(self._run_mult,mult)
    def stop(self):
        self._run=0
        while self._run==0:
            time.sleep(0.2)

def parseValue(val_str):
    val_str=val_str.strip("'")
    val_str=val_str.strip('"')
    if val_str.isdigit():
        return int(val_str)
    elif val_str.startswith('(') and val_str.endswith(')'):
        # tuple break it down
        l=[]
        for val in val_str[1:-1].split(','):
            l.append(parseValue(val))
        return tuple(l)
    else:
        try:
            return float(val_str)
        except:
            return val_str

def readConf(fname):
    config={}
    _curr_section=None
    c_f=open(fname,'r')
    for c_l in c_f.readlines():
        if '#' in c_l:
            c_l,comment=c_l.split('#',1)
        if '[' in c_l:
            _curr_section=c_l[c_l.index('[')+1:c_l.index(']')]
            config[_curr_section]={}
        elif '=' in c_l:
            key,val=c_l.strip().split('=',1)
            val=parseValue(val)
            if _curr_section:
                config[_curr_section][key]=val
            else:
                config[key]=val
    c_f.close()
    return config

# main network thread.....
class NetworkChannel:
    def __init__(self,conf):
        self.net_status=DISCON
        if 'network' in conf:
            self.wlan=network.WLAN(network.STA_IF)
            self.wlan.active(True)
            if self.matchNetwork(config['ssid'],self.wlan.scan()):
                self.connect(wlan)
    def matchNetwork(self,ssid,sc_res):
        for net in sc_res:
            net_err_led.off()
            print(ssid,net[0])
            if ssid==net[0]:
                net_conn_led.on()
                return True
            net_err_led.on()
        return False




net_conn_led=setupLED(17)
net_err_led=setupLED(16)

# TODO: wrap these two in a class for network control to be integrated into mqtt client thread (or maybe make this main thread and launch / monitor mqtt client from here)
def matchNetwork(ssid,sc_res):
    for net in sc_res:
        net_err_led.off()
        print(ssid,net[0])
        if ssid==net[0]:
            net_conn_led.on()
            return True
        net_err_led.on()
    return False

def connectNetwork(ssid='digitao',key='pass'):
    wlan=network.WLAN(network.STA_IF)
    wlan.active(True)
    b_ssid=bytes(ssid,'UTF-8')
    while not matchNetwork(b_ssid,wlan.scan()):
        print('[ERR] network %s not found' % ssid)
        time.sleep(3)
    while not wlan.isconnected():
        net_conn_led.on()
        wlan.connect(ssid,key)
        time.sleep_ms(50)
        net_conn_led.off()
        time.sleep(3)
        if not wlan.isconnected():
            print('No connection - retry')
    print('network confg',wlan.ifconfig())
    net_conn_led.off()
    ntptime.settime()
    net_conn_led.on()
    time.sleep(3)
    net_conn_led.off()
    return wlan

def flashNetLED():
    net_conn_led()

def fakelog(*args):
    pass    

inhibit=Pin(22,machine.Pin.IN,machine.Pin.PULL_UP)
#print(inhibit.value())
if __name__=='__main__' and inhibit.value():
    import network,tomli
    #config=readConf('node.conf')
    c_f=open('node.toml','rb')
    config=tomli.load(c_f)
    c_f.close()
    print(config)
    net_conf=config.pop('network',None)
    if net_conf:
        net_err_led.on()
        wlan=connectNetwork(ssid=net_conf['ssid'],key=net_conf['key'])
    queue=Queue(20)
    cli=MqttClient(net_conf.pop('mqtt'),queue,print)
    sched=Scheduler(queue)
    for key in config:
        # configure _dc module in scheduler
        if 'module' in config[key] and config[key]['module'] not in sys.modules:
            exec('import '+config[key]['module'])
        ds_m=sys.modules[config[key]['module']]
        if not ('DC' in dir(ds_m) and 'SAMPLE_RATE' in dir(ds_m)):
            raise AttributeError('not a dc module')
        dc_inst=ds_m.DC(config[key],key)
        sched.add(ds_m,dc_inst)
    start_new_thread(sched.run,(),{})
    try:
        cli.run()
    except Exception as exc:
        sched.stop()
        print('scheduler stopped')
        raise(exc)
    
