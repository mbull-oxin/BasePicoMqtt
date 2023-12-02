# main.py
from _thread import allocate_lock,start_new_thread
import umqttsimple as mqtt

DISCON=0
CONN=1
ERR=2

class MqttClient:
    def __init__(self,conf):
        self.client=mqtt.MQTTClient(conf['id'],conf['server'],conf['port'])
        self.run=True
        self.con_stat=DISCON
    def run(self,d_s):
        while self.run:
        	try:
        		self.client

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
                return this.pop(0)
        else:
            return None

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
	nic=network.WLAN(network.STA_IF)
	nic.active(True)
	nic.connect(config['network']['ssid'],config['network']['key'])
    queue=Queue()
    cli=MqttClient(config['mqtt'])
    data_source=DataSource(config['data_source'])
    data_source.run()
    cli.run()
    
