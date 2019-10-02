import time
import subprocess
import os
import math
from datetime import datetime

import RPi.GPIO as GPIO
import smbus2                    # I2C Bus
import bme280 as bme             # Bosch Temperatur/Feuchtesensor
from Adafruit_GPIO import I2C
from tsl2561 import TSL2561      # Luxsensor
import Adafruit_ADS1x15

# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------


class Bme280:
    """Klasse für den Zugriff auf den BME280 Temp/Feuchtigkeitssensor
    """

    def __init__(self, params):
        """Konstruktor

        Args:
            params (dict): {
                i2c_address: Adresse als Hexstring. Standardwert ist 0x76.
                bus: Nummer des I²C Busses. Standardwert ist 1.
            }
        """
        self.__address = int(params.get('i2c_address', '0x76'), 16)
        self.__bus = params.get('bus', 1)

    def __enter__(self):
        self.__smbus = smbus2.SMBus(self.__bus)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__smbus.close()

    def do_work(self, current_values={}):
        """Liest die Werte des BME280 Temperatursensors aus.

        Args:
            current_values (dict, optional): Die vom Cronmodul übergebenen aktuellen Werte aller Sensoren. Defaults to {}.

        Returns:
            dict: Ein Dictionary mit den Keys HUM (RF in %), TEMP (in °C) und PRES (in hPa)
        """
        cal_params = bme.load_calibration_params(self.__smbus, self.__address)
        data = bme.sample(self.__smbus, self.__address, cal_params)
        return {
            'HUM': round(data.humidity, 1),
            'TEMP': round(data.temperature, 1),
            'PRES': round(data.pressure, 1)
        }

    @staticmethod
    def calc_dewp(temp, hum):
        """Berechnet den Taupunkt nach der Formel von http://old.wetterzentrale.de/cgi-bin/webbbs/wzarchive2004_2.pl?noframes;read=506422

        Args:
            temp (float): Die Temperatur in °C.
            hum (float): Die relative Feuchte in %.

        Returns:
            float: Der Taupunkt in °C.
        """
        a = 17.08085
        b = 234.175
        E0 = 6.1078
        # Sättigungsdampfdruck E(t)
        e_saett = E0 * math.exp(a*temp/(b+temp))
        # Dampfdruck
        e = hum/100 * e_saett
        # Taupunkt
        return b * math.log(e/E0) / (a-math.log(e/E0))

# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------


class Tsl2561:
    """Klasse für den Zugriff auf den TSL2581 Luxsensor. 
    """

    def __init__(self, params):
        """Konstruktor

        Args:
            params (dict): {
                i2c_address: Adresse als Hexstring. Standardwert ist 0x39.
                bus: Nummer des I²C Busses. Standardwert ist 1.
            }
        """
        self.__address = int(params.get('i2c_address', "0x39"), 16)
        self.__bus = params.get('bus', 1)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def do_work(self, current_values={}):
        tsl = TSL2561(address=self.__address, busnum=self.__bus)
        value = tsl.lux()
        return None if not isinstance(value, int) else value


# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
class Relais:
    """Setzt ein oder mehrere Relaiskanäle auf den in params übergebenen Wert oder schaltet den
    PIN zwischen den Zeiten onFrom und onTo auf 1 bzw. zwischen offFrom und offTo auf 1.
    Es wird kein cleanup durchgeführt, damit bei einem Neustart nicht kurz aus- und eingeschalten wird.
    """

    def __init__(self, params):
        """Konstruktor: Setzt den PIN Mode auf OUT, initialisiert jedoch nicht mit einem Wert.

        Args:
            params (dict): {
                pin (list): Array mit den Broadcom (BCM) Nummern der GPIO Pins.
                state (int, optional): Der Zustand, auf den der PIN gesetzt werden soll.
                onFrom (string, optional): Zeitangabe in HH:MM, ab wann der PIN auf 1 gesetzt werrden soll.
                onTo (string, optional): Zeitangabe in HH:MM, bis wann der PIN auf 1 gesetzt werrden soll.
                offFrom (string, optional): Zeitangabe in HH:MM, ab wann der PIN auf 0 gesetzt werrden soll.
                offTo (string, optional): Zeitangabe in HH:MM, bis wann der PIN auf 0 gesetzt werrden soll.            }
        """
        self.__channels = params['pin']
        self.__state = params.get('state', None)
        self.__onFrom  = datetime.strptime(params['onFrom'],  "%H:%M").time() if 'onFrom'  in params else None
        self.__onTo    = datetime.strptime(params['onTo'],    "%H:%M").time() if 'onTo'    in params else None
        self.__offFrom = datetime.strptime(params['offFrom'], "%H:%M").time() if 'offFrom' in params else None
        self.__offTo   = datetime.strptime(params['offTo'],   "%H:%M").time() if 'offTo'   in params else None

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.__channels, GPIO.OUT)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def do_work(self, current_values={}):
        """Setzt den PIN mit folgender Priorität:
        1. Ist ein onFrom und onTo Wert gesetzt, wird der PIN innerhalb dieser Zeitspanne auf 1 gesetzt.
        2. Ist ein offFrom und offTo Wert gesetzt, wird der PIN innerhalb dieser Zeitspanne auf 0 gesetzt.
        3. Ist state angegeben, wird der PIN auf diesen state gesetzt.
        Ist nichts angegeben, wird der Zustand nicht verändert.
        
        Args:
            current_values (dict, optional): [description]. Defaults to {}.
        
        Returns:
            int: Der gesetzte Zustand der PINs (1, 0 oder None).
        """
        time_now = datetime.now().time()
        if self.__onFrom is not None and self.__onTo is not None:
            self.__state = 1 if self.__onFrom <= time_now and self.__onTo >= time_now else 0
        elif self.__offFrom is not None and self.__offTo is not None:
            self.__state = 0 if self.__offFrom <= time_now and self.__offTo >= time_now else 1

        if self.__state is not None:
            GPIO.output(self.__channels, self.__state)
        return self.__state

    def __del__(self):
        pass


# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
class Fan:
    """Klasse für die sensorgesteuerte Regelung des Lüfters
    """

    def __init__(self, params):
        """Konstruktor

        Args:
            params (dict): {
                pin: BCM Nummer des GPIO Pins, der auf 1 (EIN) oder 0 (AUS) gesetzt wird.
                boxsensor: Name des Sensors in cronjobs.json, der den Wert der Temperatur und Feuchte der Box liefert.
                roomsensor: Name des Sensors in cronjobs.json, der den Wert der Temperatur und Feuchte des Raumes liefert.
                lightstate: Name der Klasse, die den Zustand der Beleuchtung angibt.
            }
        """
        self.__pin = params['pin']
        self.__boxsensor = params['boxsensor']
        self.__roomsensor = params['roomsensor']
        self.__lightstate = params['lightstate']
        self.__state = False
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.__pin, GPIO.OUT)
        GPIO.output(self.__pin, self.__state)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def do_work(self, current_values):
        """Steuert den Lüfter an. Es wird nur eingeschalten, wenn das Klima außerhalb der Normwerte
        (18-25°C und 40-70° RH) ist und ein Ansaugen der Luft die Normwerte herstellen kann.

        Args:
            current_values (dict): {
                self.__boxsensor:
                    VALUE:
                        HUM: Wert der Luftfeuchtigkeit der Box in %.
                        TEMP: Wert der Temperatur in der Box in °C.
                self.__roomsensor:
                    VALUE:
                        HUM: Wert der Luftfeuchtigkeit der Box in %.
                        TEMP: Wert der Temperatur in der Box in °C.
            }
        """
        box_values = current_values[self.__boxsensor]['VALUE']
        room_values = current_values[self.__roomsensor]['VALUE']
        box_dewp = Bme280.calc_dewp(box_values['TEMP'], box_values['HUM'])
        room_dewp = Bme280.calc_dewp(room_values['TEMP'], room_values['HUM'])
        light_on = current_values[self.__lightstate]['VALUE']
        new_state = True

        # Normklima erreicht? Den Ventilator ausschalten
        if box_values['TEMP'] >= 18 and box_values['TEMP'] <= 25 and \
           box_values['HUM'] >= 40 and box_values['HUM'] <= 70:
           new_state = False

        # Bei Abweichungen einschalten, wenn das Sinn machen würde.
        if box_values['TEMP'] > 25:
            new_state = new_state and room_values['TEMP'] < 25
        if box_values['TEMP'] < 18:
            new_state = new_state and room_values['TEMP'] > 18
        if box_values['HUM'] > 70:
            new_state = new_state and (room_dewp < box_dewp - 0.5)
        if box_values['HUM'] < 40:
            new_state = new_state and (room_dewp > box_dewp)
        if light_on == True:
            new_state = True

        self.__state = new_state
        GPIO.output(self.__pin, self.__state)

    def __del__(self):
        pass


# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
class Cam:
    """Klasse für das Aufnehmen eines Bilder der Webcam
    """

    def __init__(self, params):
        """Konstruktor. Initialisiert den Dateinamen der Bilddatei und setzt das Timeout.

        Args:
            params (dict): {
                timeout: Timeout in Sekunden für den Video4Linux Prozess. Standardwert ist 5.
            }
        """
        self.__filename = '/home/alarm/webserver/static/webcam.jpg'
        self.__timeout = int(params.get('timeout', "5"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def do_work(self, current_values={}):
        """Nimmt durch das externe Programm /usr/bin/v4lctl ein Bild auf. Dabei wird das erste
        Gerät verwendet, das in /dev/video* gefunden wird. Es wird der Befehl
        /usr/bin/v4lctl -c (video_device) snap jpeg full (filename)
        abgesetzt. Konnte kein Bild aufgenommen werden (Prozess lieferte Timeout oder ungleich 0), 
        wird das alte Bild - wenn es mehr als 1 Stunde alt ist - gelöscht. 

        Args:
            current_values (dict, optional): Die vom Cronmodul übergebenen aktuellen Werte aller Sensoren. Defaults to {}.
        """
        try:
            video_device = sorted([x.path for x in os.scandir(path='/dev') if 'video' in x.name])[0]
            command = ['/usr/bin/v4lctl', '-c', video_device,
                       'snap', 'jpeg', 'full', self.__filename]
            subprocess.run(command, timeout=self.__timeout, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except Exception:
            try:
                if time.time() - os.path.getmtime(self.__filename) > 3600:
                    os.remove(self.__filename)
            except Exception:
                pass
            raise

    def __del__(self):
        pass


# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
class Relaymonitor:
    """Ermittelt den Status des Relais, indem die GPIO PINs gelesen werden. Die Zuordnung zu den BCM
    GPIO Nummern ist CH1: PIN 25, CH2: PIN 24, CH3: PIN 23, CH4: PIN 18.
    Da in der Datenbank für jeden Wert eine Spalte angelegt wird, müssen die Namen generisch sein.
    """

    def __init__(self, params):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def do_work(self, current_values={}):
        """Ermittelt den Status der PINs

        Args:
            current_values (dict, optional): Die vom Cronmodul übergebenen aktuellen Werte aller Sensoren. Defaults to {}.

        Returns:
            [dict]: {
                CH1: Wert des PINs 25. 1: HIGH, 0: LOW oder nicht als OUT definiert.
                CH2: Wert des PINs 24. 1: HIGH, 0: LOW oder nicht als OUT definiert.
                CH3: Wert des PINs 23. 1: HIGH, 0: LOW oder nicht als OUT definiert.
                CH4: Wert des PINs 18. 1: HIGH, 0: LOW oder nicht als OUT definiert.
            }
        """
        states = []           
        for channel in [25, 24, 23, 18]:
            try:
                states.append(int(GPIO.input(channel)))
            except:
                states.append(-1)
        return dict(zip(['CH1', 'CH2', 'CH3', 'CH4'], states))

    def __del__(self):
        pass

# --------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------
class Adc:
    """Liest die 4 Kanäle des ADS1115 AD Wandlers ein.
    """

    def __init__(self, params):
        """Konstruktor

        Args:
            params (dict): {
                i2c_address: Adresse als Hexstring. Standardwert ist 0x48.
                bus: Nummer des I²C Busses. Standardwert ist 1.
                gain: Verstärkung des AD Wandlers. Standardwert ist 1. Gültige Werte und Spannungsbereiche sind
                    2/3 = +/-6.144V 
                      1 = +/-4.096V
                      2 = +/-2.048V
                      4 = +/-1.024V
                      8 = +/-0.512V
                     16 = +/-0.256V
            }
        """
        self.__address = int(params.get('i2c_address', "0x48"), 16)
        self.__bus = params.get('bus', 1)
        self.__gain = params.get('gain', 1)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def do_work(self, current_values={}):
        """Liest einmalig alle 4 Kanäle des AD Wandlers.
        
        Args:
            current_values (dict, optional): Die vom Cronmodul übergebenen aktuellen Werte aller Sensoren. Defaults to {}.
        
        Returns:
            dict: {
                CH1: Wert des Kanals 1 (16 bit signed int), 
                CH2: Wert des Kanals 2 (16 bit signed int), 
                CH3: Wert des Kanals 3 (16 bit signed int), 
                CH4: Wert des Kanals 4 (16 bit signed int)
            }
        """
        
        adc = Adafruit_ADS1x15.ADS1115(address=self.__address, busnum=self.__bus)
        values = [0] * 4
        for i in range(4):
            values[i] = adc.read_adc(i, gain=self.__gain)

        return {
            'CH1': values[0],
            'CH2': values[1],
            'CH3': values[2],
            'CH4': values[3]
        }

    def __del__(self):
        pass
