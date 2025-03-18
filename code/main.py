# main.py
from _thread import allocate_lock,start_new_thread
from _thread import exit as t_exit
import umqtt.robust as mqtt
from machine import Pin,PWM
import machine,time,micropython,sys,json,datetime,network,ntptime,gc,binascii

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
        self.timer=machine.Timer(mode=machine.Timer.PERIODIC,period=1,callback=self.setLEDs)
    def setLEDs(self,t):
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
            elif self.warn_stat:
                if self.flash_cycle:
                    self.err_led.on()
                else:
                    self.err_led.off()
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

CONN=1
DISCON=2
ERR=3

class MqttClient:
    # wrap umqttsimple client and handle connection state / send all msg's from queue
    def __init__(self,conf,queue,stat):
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],conf['port'])
        self._run=None
        self.con_stat=DISCON
        self.machine_id=conf['id']
        self.stat=stat
        self.stat.setStatus(STAT_WARN,mod='MQTT',msg='Mqtt client connecting to %s port %s' % (conf['server'],conf['port']))
        try:
            self.client.connect(clean_session=True)
            self.con_stat=CONN
            self.stat.setStatus(STAT_OK,mod='MQTT',msg='Mqtt client connected')
        except Exception as exc:
            self.stat.setStatus(STAT_ERR,mod='MQTT',msg='Mqtt client failed to connect to broker')
            self.con_stat=ERR
            #continue
        self.queue=queue
    def run(self):
        self._run=True
        while self._run:
            #print('[MqttClient] wait...')
            try:
                msg=queue.get(timeout=20)
            except StopIteration:
                print('MqttClient] timeout')
                continue
            self.stat.setStatus(STAT_OK,'MQTT','sending '+repr(msg))
            payload=msg[1]
            payload['machine']=self.machine_id
            t=time.localtime()
            payload['timestamp']=datetime.datetime(t[0],t[1],t[2],hour=t[3],minute=t[4],second=t[5]).isoformat()+'+00:00'
            if msg and self.con_stat!=CONN:
                try:
                    #self.log(self.client.port)
                    self.client.connect(clean_session=True)
                    self.con_stat=CONN
                    self.stat.setStatus(STAT_OK,mod='MQTT',msg='Mqtt client connected')
                    #self.log('[MqttClient] connected')
                except Exception as exc:
                    #self.log('[MqttClient] error connecting to broker',exc)
                    self.stat.setStatus(STAT_ERR,mod='MQTT',msg='Mqtt client failed to connect to broker')
                    #self.log('[MqttClient] dropped msg -\n\tTopic - %s\n\tPayload - %s' % msg)
                    self.stat.setStatus(STAT_ERR,mod='MQTT',msg='Mqtt client dropped msg -\n\tTopic - %s\n\tPayload - %s' % msg)
                    self.con_stat=ERR
                    continue
            if msg:
                #self.log('[MqttClient] ,msg)
                self.stat.setStatus(STAT_WARN,mod='MQTT',msg='publish to %s/%s' % (self.machine_id,msg[0]))
                try:
                    topic='%s_monitoring/%s-%s' % (msg[1],self.machine_id,msg[0])
                    topic=topic.encode('UTF-8')
                    self.client.publish(topic,json.dumps(msg[2]))
                    #self.log('[MqttClient] publish done')
                    self.stat.setStatus(STAT_OK,mod='MQTT',msg='Mqtt publish done')
                except Exception as exc:
                    #self.log('[MqttClient] error publishing to broker',exc)
                    self.stat.setStatus(STAT_ERR,mod='MQTT',msg='error publishing to broker')
                    self.con_stat=ERR
                    continue
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
    def __init__(self,queue,stat):
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
    wlan=network.WLAN(network.STA_IF)
    wlan.active(True)
    b_ssid=bytes(ssid,'UTF-8')
    stat.setStatus(STAT_ERR,mod='NETWORK',msg='network startup')
    while not matchNetwork(b_ssid,wlan.scan()):
        stat.setStatus(STAT_ERR,mod='NETWORK',msg='Network %s not found' % b_ssid)
        time.sleep(3)
    while not wlan.isconnected():
        wlan.connect(ssid,key)
        time.sleep_ms(50)
        stat.setStatus(STAT_WARN,mod='NETWORK',msg='Trying to connect to network')
        time.sleep(3)
        if not wlan.isconnected():
            stat.setStatus(STAT_ERR,mod='NETWORK',msg='network connection failed')
    #print('network confg',wlan.ifconfig())
    stat.setStatus(STAT_WARN,mod='NETWORK',msg='Checking for internet')
    ntptime.settime()
    stat.setStatus(STAT_OK,mod='NETWORK',msg='Network connected')

if __name__=='__main__':
    import network,tomli
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
    net_conf=config.pop('network',None)
    if net_conf:
        wlan=connectNetwork(status_disp,ssid=net_conf['ssid'],key=net_conf['key'])
    queue=Queue(20)
    cli=MqttClient(net_conf.pop('mqtt'),queue,status_disp)
    sched=Scheduler(queue,status_disp)
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
    
