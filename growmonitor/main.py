# pip install croniter
# pacman -S freetds && pip install cython &&  pip install pymssql 
# pip install Adafruit_GPIO tsl2561 RPi.bme280

import datetime
import logging
import sys
from logging.handlers import RotatingFileHandler
from cronjob import Cronjob
import db

print('+------------------------------------------------------------------------------+')
print('| GROWCONTROL                                                                  |')
print('| Version 2019-08-01                                                           |')
print('+------------------------------------------------------------------------------+')

print('  Lokale Zeit: ', datetime.datetime.now())
print('  UTC:         ', datetime.datetime.utcnow())

def on_job_ready(data):
    database.enqueue(data)
    db.write_line(data)

def on_all_jobs_ready():
    database.write_queue()

logging.basicConfig(format = '%(asctime)s %(message)s', filename = 'error.log.txt', level = logging.ERROR)
logger = logging.getLogger()
handler = RotatingFileHandler('error.log.txt', maxBytes = 1048576, backupCount = 10)
logger.addHandler(handler)


#logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
try:
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'cronjobs.json'
    #with db.Database.mssql("h2815404.stratoserver.net", "SensorDb", "h5dv4e3RzLDQ", "SensorDb") as database:
    with db.Database.sqlite("../data/sensordata.db") as database:
        jobs = Cronjob(config_file)
        jobs.start_working(disable_cron = False, on_job_ready = on_job_ready, on_all_jobs_ready = on_all_jobs_ready)
except KeyboardInterrupt:
    print("Cancelled")
except Exception:
    logging.exception('Programmabbruch')

