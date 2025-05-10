from machine import I2C,Pin,Timer
import dht,struct

# ENS160 Register address
## This 2-byte register contains the part number in little endian of the ENS160.
ENS160_PART_ID_REG = 0x00
## This 1-byte register sets the Operating Mode of the ENS160.
ENS160_OPMODE_REG = 0x10
## This 1-byte register configures the action of the INTn pin.
ENS160_CONFIG_REG = 0x11
## This 1-byte register allows some additional commands to be executed on the ENS160.
ENS160_COMMAND_REG = 0x12
## This 2-byte register allows the host system to write ambient temperature data to ENS160 for compensation.
ENS160_TEMP_IN_REG = 0x13
## This 2-byte register allows the host system to write relative humidity data to ENS160 for compensation.
ENS160_RH_IN_REG = 0x15
## This 1-byte register indicates the current STATUS of the ENS160.
ENS160_DATA_STATUS_REG = 0x20
## This 1-byte register reports the calculated Air Quality Index according to the UBA.
ENS160_DATA_AQI_REG = 0x21
## This 2-byte register reports the calculated TVOC concentration in ppb.
ENS160_DATA_TVOC_REG = 0x22
## This 2-byte register reports the calculated equivalent CO2-concentration in ppm, based on the detected VOCs and hydrogen.
ENS160_DATA_ECO2_REG = 0x24
## This 2-byte register reports the calculated ethanol concentration in ppb.
ENS160_DATA_ETOH_REG = 0x22
## This 2-byte register reports the temperature used in its calculations (taken from TEMP_IN, if supplied).
ENS160_DATA_T_REG = 0x30
## This 2-byte register reports the relative humidity used in its calculations (taken from RH_IN if supplied).
ENS160_DATA_RH_REG = 0x32
## This 1-byte register reports the calculated checksum of the previous DATA_ read transaction (of n-bytes).
ENS160_DATA_MISR_REG = 0x38
## This 8-byte register is used by several functions for the Host System to pass data to the ENS160.
ENS160_GPR_WRITE_REG = 0x40
## This 8-byte register is used by several functions for the ENS160 to pass data to the Host System.
ENS160_GPR_READ_REG = 0x48

# OPMODE(Address 0x10) register mode
## DEEP SLEEP mode (low power standby).
ENS160_SLEEP_MODE  = 0x00
## IDLE mode (low-power).
ENS160_IDLE_MODE = 0x01
## STANDARD Gas Sensing Modes.
ENS160_STANDARD_MODE = 0x02

# CMD(0x12) register command
## reserved. No command.
ENS160_COMMAND_NOP = 0x00
## Get FW Version Command.
ENS160_COMMAND_GET_APPVER = 0x0E
## Clears GPR Read Registers Command.
ENS160_COMMAND_CLRGPR = 0xCC

SAMPLE_RATE=1

class ENS160:
    @staticmethod
    def _crc8(sequence, polynomial: int, init_value: int):
        crc = init_value & 0xFF
        for item in sequence:
            tmp = 0xFF & ((crc << 1) ^ item)
            if 0 == crc & 0x80:
                crc = tmp
            else:
                crc = tmp ^ polynomial
        return crc
    def __init__(self,i2c_bus,dev_addr=0x53,dht_pin=None,sda=None,scl=None,dht_vers=11):
        if sda==None:
            if i2c_bus==0:
                sda=0
                scl=1
            else:
                sda=2
                scl=3
        self._bus=I2C(i2c_bus,scl=Pin(scl),sda=Pin(sda),freq=400_000)
        self.dev=dev_addr
        if dht_pin:
            if dht_vers in (2,22):
                self.dht=dht.DHT22(Pin(dht_pin))
            else:
                self.dht=dht.DHT11(Pin(dht_pin))
            self.dht.measure()
            self._curr_humidity=self.dht.humidity()
            self._curr_temp=self.dht.temperature()
            self._th_update=False
            self._dht_timer=Timer(period=30_000,mode=Timer.PERIODIC,callback=self.updateTH)
        else:
            self.dht=None
        self._bus.writeto_mem(self.dev,ENS160_OPMODE_REG,b'\x02')
    def updateTH(self,timer):
        '''update temp and humidity from dht on a schedule'''
        if timer==self._dht_timer:
            self.dht.measure()
            t=self.dht.temperature()
            if self._curr_temp!=t:
                self._curr_temp=t
                self._th_update=True
            h=self.dht.humidity()
            if self._curr_humidity!=h:
                self._curr_humidity=h
                self._th_update=True
    def getReading(self):
        if self._th_update:
            self._bus.writeto_mem(self.dev,ENS160_TEMP_IN_REG,struct.pack('<H',int((self._curr_temp+273.15)*64)))
            self._bus.writeto_mem(self.dev,ENS160_RH_IN_REG,struct.pack('<H',int(self._curr_humidity*512)))
            self._th_update=False
        aqi=self._bus.readfrom_mem(self.dev,ENS160_DATA_AQI_REG,1)
        tvoc=self._bus.readfrom_mem(self.dev,ENS160_DATA_TVOC_REG,2)
        co2=self._bus.readfrom_mem(self.dev,ENS160_DATA_ECO2_REG,2)
        eth=self._bus.readfrom_mem(self.dev,ENS160_DATA_ETOH_REG,2)
        return (self._curr_temp,self._curr_humidity,aqi[0],struct.unpack('<H',tvoc)[0],struct.unpack('<H',co2)[0],struct.unpack('<H',eth)[0])

class DC:
    def __init__(self,config,name):
        self.config=config
        self.r_id=name
        if len(self.config['bus'])>1:
            scl=self.config['bus'][1]
            sda=self.config['bus'][2]
        else:
            if self.config['bus'][0]==0:
                scl=1
                sda=0
            else:
                scl=3
                sda=2
        if 'dht_pin' in self.config:
            dht_dat=self.config['dht_pin']
            dht_type=self.config['dht_vers']
        else:
            dht_dat=None
        self.dev=ENS160(config['bus'][0],dht_pin=dht_dat,scl=scl,sda=sda,dht_vers=dht_type)
    def getReading(self):
        t_c,h_c,aqi,tvoc,co2,eth=self.dev.getReading()
        return (self.r_id,'airquality',{'temp':t_c,'humidity':h_c,'aqi':aqi,'TVOC':tvoc,'CO2':co2,'ethanol':eth,'sensor':self.r_id,'AlertVal':0,'Threshold':100,'ThresholdHigh':100,'ThresholdLow':100})

if __name__=='__main__':
    import time
    dev=ENS160(0,dht_pin=14)
    while True:
        print(dev.getReading())
        time.sleep(5)
