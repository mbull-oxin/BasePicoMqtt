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

STAT_ERR=0
STAT_WARN=1
STAT_OK=2

def setupLED(pin):                              # conveience function to setup pin for led, return machine.Pin object
    led_pin=Pin(pin,Pin.OUT)
    led_pin.off()
    return led_pin

class StatusDisplay:
    def __init__(self,**config):
        # override to setup display specific outputs
        self.curr_stat={}
        self.curr_msg={}
        self.last_mod=None
        self.err_stat=False
        self.warn_stat=False
    def setStatus(self,stat,mod='SYSTEM',msg=''):
        self.curr_stat[mod]=stat
        self.curr_msg[mod]=msg
        self.last_mod=mod
        if stat==STAT_ERR:
            print('[ERROR] %s - %s' % (mod,msg))
        elif stat==STAT_WARN:
            print('[WARN] %s - %s' % (mod,msg))
        else:
            print('[INFO] %s - %s' % (mod,msg))
        # update global error and warning status
        if STAT_ERR in self.curr_stat.values():
            self.err_stat=True
        else:
            self.err_stat=False
        if STAT_WARN in self.curr_stat.values():
            self.warn_stat=True
        else:
            self.warn_stat=False
        self.updateStatus()
    def updateStatus(self):
        # override to display status....
        pass

class TrafficLightStatus(StatusDisplay):
    def __init__(self,red_pin=18,amber_pin=19,green_pin=20,**config):
        super().__init__()
        self.err_led=setupLED(red_pin)
        self.warn_led=setupLED(amber_pin)
        self.ok_led=setupLED(green_pin)
        self.flash_cycle=True
        self.timer=machine.Timer(mode=machine.Timer.PERIODIC,period=1000,callback=self.setLEDs)
    def setLEDs(self,t):
        #print('[timer]',self.timer,t)
        if t==self.timer:
            #alternate flash cycle
            self.flash_cycle=not self.flash_cycle
            if self.err_stat and self.warn_stat:
                # we have warnings and errors do an alternating red / amber
                if self.flash_cycle:
                    self.err_led.on()
                    self.warn_led.off()
                else:
                    self.err_led.off()
                    self.warn_led.on()
            elif self.err_stat:
                #we have errors
                self.err_led.on()
                self.warn_led.off()
            elif self.warn_stat:
                self.err_led.off()
                if self.flash_cycle:
                    self.warn_led.on()
                else:
                    self.warn_led.off()
            else:
                # yay no errors or warnings...
                self.err_led.off()
                self.warn_led.off()
                self.ok_led.on()
    def updateStatus(self):
        if self.err_stat:
            self.err_led.on()
        if self.warn_stat:
            self.warn_led.on()
        if self.err_stat or self.warn_stat:
            self.ok_led.off()
        else:
            self.ok_led.on()

class RGBStatus(StatusDisplay):
    def __init__(self,base_pin=None,**conf):
        super().__init__()
        if base_pin:
            self.red=PWM(Pin(base_pin))
            self.red.freq(1000)
            self.green=PWM(Pin(base_pin+1))
            self.green.freq(1000)
            self.blue=PWM(Pin(base_pin+2))
            self.blue.freq(1000)
        else:
            self.red=None
            print('no base pin set bailing')
    def setColor(self,color):
        if type(color)==tuple:
            r,g,b=color
        elif color.startswith('#'):
            #TODO: decode hex string
            r=ord(binascii.unhexlify(color[1:3]))
            g=ord(binascii.unhexlify(color[3:5]))
            b=ord(binascii.unhexlify(color[5:7]))
        self.red.duty_u16(r*257)
        self.green.duty_u16(g*257)
        self.blue.duty_u16(b*257) 
    def updateStatus(self):
        if not self.red:
            return
        if self.err_stat:
            self.setColor((255,0,0))
        elif self.warn_stat:
            self.setColor((127,127,0))
        else:
            self.setColor((0,255,0))

STATUS_MAP={'trafficlight':TrafficLightStatus,'RGB':RGBStatus}

DISCON=0
CONN=1
ERR=2

class MqttClient:
    # wrap umqttsimple client and handle connection state / send all msg's from queue
    def __init__(self,conf,stat,queue,log):
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],int(conf['port']))
        self._run=None
        self.con_stat=DISCON
        self.machine_id=conf['id']
        self.log=log
        #self.log('[MqttClient] connecting to %s' % conf['server'])
        stat.setStatus(STAT_WARN,mod='MQTT',msg='connecting to %s' % conf['server'])
        try:
            self.client.connect(clean_session=True)
            self.con_stat=CONN
            #self.log('[MqttClient] connected')
            stat.setStatus(STAT_OK,mod='MQTT',msg='connected')
        except Exception as exc:
            self.log('[MqttClient] error connecting to broker',exc)
            self.con_stat=ERR
            stat.setStatus(STAT_ERR,mod='MQTT',msg='error connecting to broker')
            #continue
        self.queue=queue
        #self.act_led=setupLED(21)
        self.stat=stat
    def run(self):
        self._run=True
        while self._run:
            #print('[MqttClient] wait...')
            try:
                msg=queue.get(timeout=20)
            except StopIteration:
                #print('MqttClient] timeout')
                continue
            self.log('[MqttClient] got',msg)
            payload=msg[2]
            payload['machine']=self.machine_id
            t=time.localtime()
            payload['timestamp']=datetime.datetime(t[0],t[1],t[2],hour=t[3],minute=t[4],second=t[5]).isoformat()+'+00:00'
            if msg and self.con_stat!=CONN:
                try:
                    self.log(self.client.port)
                    self.client.connect(clean_session=True)
                    self.con_stat=CONN
                    self.log('[MqttClient] connected')
                    self.stat.setStatus(STAT_OK,mod='MQTT',msg='connected')
                except Exception as exc:
                    self.log('[MqttClient] error connecting to broker',exc)
                    self.log('[MqttClient] dropped msg -\n\tParameter - %s\n\tPayload - %s' % (msg[0],msg[2]))
                    self.stat.setStatus(STAT_ERR,mod='MQTT',msg='Mqtt client dropped msg -\n\tParameter - %s\n\tPayload - %s' % (msg[0],msg[2]))
                    self.con_stat=ERR
                    continue
            if msg:
                self.log('[MqttClient] publish to %s/%s' % (self.machine_id,msg[0]),msg)
                #self.act_led.on()
                try:
                    topic='%s_monitoring/%s-%s' % (msg[1],self.machine_id,msg[0])
                    topic=topic.encode('UTF-8')
                    self.client.publish(topic,json.dumps(payload))
                    self.log('[MqttClient] publish done')
                except Exception as exc:
                    self.log('[MqttClient] error publishing to broker',exc)
                    self.stat.setStatus(STAT_ERR,mod='MQTT',msg='error publishing to broker')
                    self.con_stat=ERR
                    continue
                #self.act_led.off()
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
    def __init__(self,stat,queue):
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
        print(mod_name,dc,self.req_samp_rates)
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

# TODO: wrap these two in a class for network control to be integrated into mqtt client thread (or maybe make this main thread and launch / monitor mqtt client from here)
def matchNetwork(ssid,sc_res):
    for net in sc_res:
        #net_err_led.off()
        print(ssid,net[0])
        if ssid==net[0]:
            #net_conn_led.on()
            return True
        #net_err_led.on()
    return False

def connectNetwork(stat,ssid='digitao',key='pass'):
    stat.setStatus(STAT_ERR,mod='NETWORK',msg='network startup')
    wlan=network.WLAN(network.STA_IF)
    wlan.active(True)
    b_ssid=bytes(ssid,'UTF-8')
    #print(b_ssid,wlan.scan())
    while not matchNetwork(b_ssid,wlan.scan()):
        #print('[ERR] network %s not found' % ssid)
        stat.setStatus(STAT_WARN,mod='NETWORK',msg='network %s not found' % ssid)
        time.sleep(3)
    while not wlan.isconnected():
        #net_conn_led.on()
        wlan.connect(ssid,key)
        time.sleep(5)
        if not wlan.isconnected():
            stat.setStatus(STAT_WARN,mod='NETWORK',msg='No connection - retry')
    #print('network confg',wlan.ifconfig())
    #net_conn_led.off()
    ntptime.settime()
    stat.setStatus(STAT_OK,mod='NETWORK',msg='network connected')
    return wlan

if __name__=='__main__':
    import network,tomli
    #config=readConf('node.conf')
    c_f=open('node.toml','rb')
    config=tomli.load(c_f)
    c_f.close()
    print(config)
    sys_conf=config.pop('system')
    if sys_conf['inhibit']:
        inhib_pin=Pin(sys_conf['inhibit'],machine.Pin.IN,machine.Pin.PULL_UP)
        if not inhib_pin.value():
            sys.exit()
    if sys_conf['status']['type']=='None':
        status_disp=StatusDisplay(**sys_conf['status'])
    else:
        status_disp=STATUS_MAP[sys_conf['status']['type']](**sys_conf['status'])
    status_disp.setStatus(STAT_WARN,mod='SYSTEM',msg='system startup')
    net_conf=config.pop('network',None)
    if net_conf:
        #net_err_led.on()
        wlan=connectNetwork(status_disp,ssid=net_conf['ssid'],key=net_conf['key'])
    queue=Queue(20)
    cli=MqttClient(net_conf.pop('mqtt'),status_disp,queue,print)
    sched=Scheduler(status_disp,queue)
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
    status_disp.setStatus(STAT_OK,mod='SYSTEM',msg='Scheduler Started')
    try:
        cli.run()
    except Exception as exc:
        sched.stop()
        print('scheduler stopped')
        raise(exc)
    
