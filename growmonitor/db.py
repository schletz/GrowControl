import logging
import threading
import sqlite3
import pymssql                     # pacman -S freetds && pip install cython &&  pip install pymssql 
import os

# "h2815404.stratoserver.net", "SensorDb", "h5dv4e3RzLDQ", "SensorDb"
class Database:
    __db_queue = []
    __db_queue_lock = threading.Lock()
    __write_thread = threading.Thread()
    __table_prefix = 'data'

    @staticmethod
    def sqlite(filename, table_prefix = "data"):
        """Erstellt ein Database Objekt für den Zugriff auf eine SQLite Datenbank.
        
        filename -- Dateiname der zu verwendenden Datenbank. Wird erstellt, wenn nicht vorhanden.
        """
        db = Database()
        db.__connect_func = lambda: sqlite3.connect(filename)
        db.__get_tables_stmt = "SELECT name FROM sqlite_master WHERE type = 'table';"
        db.__generate_create_func = lambda tablename, record: \
            'CREATE TABLE {} (TIMESTAMP INTEGER, OFFSET REAL, SENSOR TEXT, {}, PRIMARY KEY (TIMESTAMP))' \
                .format(tablename, ', '.join([str(k) + ' REAL' for k in record['VALUE'].keys()]))
        db.__generate_insert_func = lambda tablename, record: \
            'INSERT INTO {} (TIMESTAMP, OFFSET, SENSOR, {}) VALUES (?, ?, ?, {})' \
                .format(tablename, ', '.join(record['VALUE'].keys()), ', '.join(['?'] * len(record['VALUE'])))
        db.__table_prefix = table_prefix
        return db

    @staticmethod
    def mssql(host, user, passwd, dbname, table_prefix = "data"):
        """Erstellt ein Database Objekt für den Zugriff auf eine SQL Server Datenbank.
        
        host    --  Hostname oder IP Adresse des Datenbankservers
        user    --  Benutzername am SQL Server
        passwd  --  Passwort
        db      --  Name der zu verwendenden Datenbank
        """        
        db = Database()
        db.__connect_func =  lambda: pymssql.connect(host, user, passwd, dbname)
        db.__get_tables_stmt = "SELECT name FROM sys.objects WHERE TYPE = 'U'"
        db.__generate_create_func = lambda tablename, record: \
            'CREATE TABLE {} (TIMESTAMP BIGINT, OFFSET REAL, SENSOR CHAR(16), {}, PRIMARY KEY (TIMESTAMP))' \
                .format(tablename, ', '.join([str(k) + ' FLOAT' for k in record['VALUE'].keys()]))
        db.__generate_insert_func = lambda tablename, record: \
            'INSERT INTO {} (TIMESTAMP, OFFSET, SENSOR, {}) VALUES (%d, %d, %s, {})' \
                .format(tablename, ', '.join(record['VALUE'].keys()), ', '.join(['%d'] * len(record['VALUE'])))
        db.__table_prefix = table_prefix
        return db

    def enqueue(self, record):
        """Stellt einen Datensatz zum Schreiben in die Datenbank in die Warteschlange."""
        with self.__db_queue_lock:
            self.__db_queue.append(_prepare_record(record, self.__table_prefix))

    def write_queue(self):
        def write_thread_func():
            """Schreibt die Warteschlange in die Datenbank und leert die Warteschlange."""
            with self.__db_queue_lock:
                to_write = self.__db_queue
                self.__db_queue = []
            if len(to_write) == 0:
                return
            failed = []                
            try:
                with self.__connect_func() as conn:            
                    cursor = conn.cursor()
                    cursor.execute(self.__get_tables_stmt)
                    tables = [val[0].lower() for val in cursor.fetchall()]
                    # Der einzelne Datensatz wird in die entsprechende Sensortabelle geschrieben.
                    for record in to_write:
                        try:
                            tablename, tabledata = record
                            # Tupel mit den einzelnen Werten pro Zeile erzeugen
                            values = (tabledata['TIMESTAMP'], tabledata['OFFSET'], tabledata['SENSOR']) + tuple(v for v in tabledata['VALUE'].values())
                            # Existiert die Tabelle noch nicht, wird sie erzeugt. Dabei wird für jedes Attribut
                            # in value eine eigene Spalte vom Typ double angelegt.
                            if tablename not in tables:
                                cursor.execute(self.__generate_create_func(tablename, tabledata))
                            cursor.execute(self.__generate_insert_func(tablename, tabledata), values)
                            conn.commit()
                        except Exception:
                            failed.append(record)
                            logging.exception("Fehler beim Einfügen eines Datensatzes: %s", to_write)
            # Im Fehlerfall die Daten noch einmal versuchen zu schreiben. Bei einem Puffer von 1000
            # wird dieser geleert, offensichtlich ist die DB länger ausgefallen und muss über das log
            # befüllt werden.        
            except Exception:
                failed = to_write
                logging.exception("Fehler beim Verbinden zur Datenbank.")
            # Maximal die neuesten 10 000 in der Queue lassen, damit sie bei länger 
            # ausgefallener DB nicht überläuft.
            with self.__db_queue_lock:
                self.__db_queue = (failed + self.__db_queue)[-10000:]

        if not self.__write_thread.is_alive():
            self.__write_thread = threading.Thread(target = write_thread_func) 
            self.__write_thread.start()

    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        if self.__write_thread.is_alive():
            self.__write_thread.join()        

def _prepare_record(record, prefix = "data"):
    """Erstellt einen neuen Record, der die verwendeten Felder für das INSERT sicher beinhaltet.
    Außerdem wird - wenn VALUE nur eine Zahl ist - auch ein dictionary dafür erstellt.
    """
    for required in ['TIMESTAMP', 'OFFSET', 'SENSOR', 'VALUE']:
        if required not in record.keys():
            raise Exception('{} nicht vorhanden.'.format(required))

    new_record = dict(record)
    if not isinstance(new_record['VALUE'], dict):
        new_record['VALUE']  = {'VALUE': new_record['VALUE']}
    tablename = '{}_{}'.format(prefix, new_record['SENSOR']).lower()

    return (tablename, new_record)

def write_line(data):
    """Schreibt den Datensatz in 2 Textdateien:
        1. In die Datei data_sensorname.txt (wird angehängt)
        2. In die Datei data_sensorname_latest.txt (wird überschrieben)
    """
    try:
        filename, record = _prepare_record(data)
        write_header = not os.path.isfile(filename + '.txt')
        header = ['TIMESTAMP', 'OFFSET', 'SENSOR'] + \
                 [v for v in record['VALUE'].keys()]
        values = [str(record['TIMESTAMP']), str(record['OFFSET']), str(record['SENSOR'])] + \
                 [str(v) for v in record['VALUE'].values()]

        with open(filename + '.txt', 'a') as logfile:
            if write_header == True: 
                logfile.write('\t'.join(header) + '\r\n')
            logfile.write('\t'.join(values) + '\r\n')

        with open(filename + '_latest.txt', 'w') as logfile:
            logfile.write('\t'.join(header) + '\r\n')
            logfile.write('\t'.join(values) + '\r\n')
    except Exception:
        logging.exception('Fehler beim Schreiben in die Textdatei.')
