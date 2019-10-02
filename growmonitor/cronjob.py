import rasp as rasp
import time
import os
import json
import logging
from croniter import croniter

class Cronjob:
    __cron_infos = []
    __last_values = {}
    __configfile = 'cronjobs.json'
    __config_timestamp = 0

    def __init__(self, configfile):
        self.__configfile = configfile

    def start_working(self, disable_cron = False, on_job_ready = lambda val: None, on_all_jobs_ready = lambda: None):
        while True:
            self.__read_config()
            current_time = int(time.time())
            for id, job in self.__cron_infos.items():
                iter = croniter(job['run_at'], current_time)
                next_run = int(iter.get_next()) if disable_cron == False else current_time + 1
                if 'next_run' not in job:
                    job['next_run'] = next_run
                if job['next_run'] <= current_time:
                    try:
                        with job['instance'] as instance:
                            value = instance.do_work(self.__last_values)
                        if (value is not None):
                            data = {
                                'TIMESTAMP': job['next_run'],
                                'OFFSET': round(time.time()-job['next_run'], 1),
                                'SENSOR': id,
                                'VALUE': value
                            }
                            self.__last_values[id] = data
                            on_job_ready(data)
                    except Exception:
                        logging.exception('Fehler beim Durchführen des Jobs %s', id)
                    job['next_run'] = next_run
            on_all_jobs_ready()                        
            time.sleep(1)          

    def __read_config(self):
        def prepare_element(elem):
            for required in ['run_at', 'class']:
                if required not in elem.keys():
                    raise Exception('Key {} nicht gefunden.'.format(required))
            if not croniter.is_valid(elem['run_at']):
                raise Exception('Ungültiger Cron eintrag: {}'.format(elem['run_at']))
            elem['instance'] = getattr(rasp, elem['class'])(elem.get('params', {}))
            return elem

        try:
            config_timestamp = os.path.getmtime(self.__configfile)
            if self.__config_timestamp < config_timestamp:
                with open(self.__configfile, "r") as json_file:
                    actors = json.load(json_file)
                cron_infos = dict(zip(actors, map(prepare_element, actors.values())))
                self.__cron_infos = cron_infos
                self.__config_timestamp = config_timestamp
                logging.info("Konfiguration neu gelesen.")
        except Exception:
            logging.exception('Fehler beim Lesen der Konfiguration aus %s.', self.__configfile)

    def __str__(self):
        return json.dumps(self.__cron_infos, indent = 2, default = lambda val: '<internal>')            