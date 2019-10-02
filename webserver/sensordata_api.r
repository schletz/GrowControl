rm(list=ls())
for(package in c("tidyverse", "skimr", "lubridate", "gridExtra", "scales", "DBI")) {
	if (!require(package, character.only = TRUE)) { 
		install.packages(package, repos = "https://cran.wu.ac.at"); 
		library(package, character.only = TRUE); 
	}	
}

database <- "../data/sensordata.db"
#database <- "C:/Users/Michael/Desktop/sensordata.db"

calc_dewpoint <- function(temp = NA, hum = NA) {
	# http://old.wetterzentrale.de/cgi-bin/webbbs/wzarchive2004_2.pl?noframes;read=506422
	const <- list(a = 17.08085, b = 234.175, E0 = 6.1078)
	# Sättigungsdampfdruck E(t)
	e_saett <- const$E0 * exp(const$a*temp/(const$b+temp))
	# Dampfdruck
	e <- hum/100 * e_saett
	# Taupunkt
	const$b * log(e/const$E0) / (const$a-log(e/const$E0))
}

get_data <- function(starttime = NA, endtime = NA, interval = NA, sensor = ".") {
	# Liefert die Daten aller Tabellen in der Datenbank normalisiert im Format
	# TIMESTAMP      SENSOR VALUETYPE  VAL
	# 1563870000 BME280_BOX    OFFSET  1.3
	# 1563870600 BME280_BOX    OFFSET  1.3
	# 1563882600 BME280_BOX       HUM 37.9
	# 1563883200 BME280_BOX       HUM 65.1
	# 1563883800 BME280_BOX       HUM 39.3
	
	starttime <- replace_na(starttime, 0)
	endtime <- replace_na(endtime, as.double(Sys.time()))
	interval <- replace_na(interval, 1)
	
	conn <- dbConnect(RSQLite::SQLite(), database)
	tables <- dbListTables(conn)
	
	data <- tables[str_detect(str_to_lower(tables), str_to_lower(sensor))] %>%
		map_dfr(function(table) {
			result <- dbGetQuery(conn, str_c("SELECT * FROM ", table, " WHERE TIMESTAMP >= ", starttime, " AND TIMESTAMP <= ", endtime, " AND TIMESTAMP % ", interval, "= 0")) %>%
				mutate(SENSOR = str_trim(SENSOR))				
			sensor <- str_to_lower(result$SENSOR[1])
			if (str_starts(sensor, "bme280")) {
				result <- mutate(result, DEWP = round(calc_dewpoint(TEMP, HUM), 1))
			}
			if (str_starts(sensor, "tsl2561")) {
				result <- rename(result, LUX = VALUE)
			}
			result %>%
				gather("VALUETYPE", "VALUE", -TIMESTAMP, -SENSOR)
		})
	dbDisconnect(conn)
	data
}

#* @json
#* @get /QutaqIyomi297FaxisUbaza575/getStats
getStats <- function(hours = NA) {
	# Liefert die Daten für den Startbildschirm: Aktueller Wert, MIN, MAX und AVG.
	# Dabei werden die Daten zuerst in 10min Blöcken aggregiert, um unterschiedliche Intervalle
	# zu beseitigen.
	hours <- replace_na(as.integer(hours), 1*24)
	now <- trunc(as.double(Sys.time()))
	endtime <- trunc(now / 600) * 600
	starttime <- endtime - hours * 3600
	
	# Werden über 7 Tage abgefragt, dann fragen wir nur die vollen 10 Minuten Werte aus der DB ab.
	# Davor verwenden wir die Minutenwerte und bilden MAX/MIN/AVG lokal (exakter bei MAX/MIN).
	interval <- ifelse(hours <= 7*24, 60, 600)
	data10min <-  get_data(starttime, endtime, interval = interval) %>%
		mutate(TIMESTAMP = trunc(TIMESTAMP / 600) * 600) %>%
		group_by(SENSOR, VALUETYPE, TIMESTAMP) %>%
		summarize(AVG = mean(VALUE, na.rm = TRUE),
				  MIN = min(VALUE, na.rm = TRUE), 
				  MAX = max(VALUE, na.rm = TRUE))		

	# Den letzten Wert nur aus der letzten Stunde berücksichtigen. Sonst ist er nicht mehr aktuell.
	last_values <- get_data(now - 3600, now) %>%
		group_by(SENSOR, VALUETYPE) %>%
		summarize(LAST_TIMESTAMP = last(TIMESTAMP, order_by = TIMESTAMP),		  
				  LAST_VALUE     = last(VALUE, order_by = TIMESTAMP))
	
	# Von den 10min Werten dürfen nur 10% fehlen. Dafür erstellen wir eine Sequence mit allen
	# möglichen 10min Werten und erstellen alle Kombinationen aus 10min Wert, Sensor und Valuetype.
	max_missing <- 0.1
	tibble(TIMESTAMP = seq(starttime, endtime, by=600)) %>%
	crossing(data10min %>% distinct(SENSOR, VALUETYPE)) %>%
		left_join(data10min, by = c("TIMESTAMP", "SENSOR", "VALUETYPE")) %>%
		group_by(SENSOR, VALUETYPE) %>%
		summarize(MISSING = sum(is.na(AVG)) / n(),
				  AVG = ifelse(MISSING <= max_missing, round(mean(AVG, na.rm = TRUE), 1), NA),
				  MIN = ifelse(MISSING <= max_missing, min(MIN, na.rm = TRUE), NA),
				  MAX = ifelse(MISSING <= max_missing, max(MAX, na.rm = TRUE), NA)) %>%
		left_join(last_values, by = c("SENSOR", "VALUETYPE")) %>%
		mutate(AGE_SEC = now - LAST_TIMESTAMP)
}

#* @json
#* @get /QutaqIyomi297FaxisUbaza575/getActiveSensors
getActiveSensors <- function() {
	endtime <- trunc(as.double(Sys.time()))
	starttime <- starttime <- endtime - 24 * 3600
	get_data(starttime, endtime) %>% distinct(SENSOR, VALUETYPE)
}

#* @json
#* @get /QutaqIyomi297FaxisUbaza575/getPlotValues
getPlotValues <- function(sensor = ".", valuetype = ".", endtime = NA, hours = NA, avg_over = NA) {
	hours <- replace_na(as.integer(hours), 24)
	avg_over <- replace_na(as.integer(avg_over), 1)
	endtime <- replace_na(trunc(as.double(endtime)), trunc(as.double(Sys.time())))
	starttime <- endtime - hours * 3600
	
	data <-  get_data(starttime, endtime, sensor = sensor) %>%
		filter(SENSOR == sensor & VALUETYPE == valuetype) %>%
		mutate(TIMESTAMP = trunc(TIMESTAMP / avg_over) * avg_over) %>%
		group_by(TIMESTAMP) %>%
		summarize(y = mean(VALUE, na.rm = TRUE)) %>%
		mutate(x = TIMESTAMP * 1000) %>%
		select(x, y)
	data
}	


#* @assets ./static /QutaqIyomi297FaxisUbaza575
list()


getStats(1) %>% print(n = 3)
getStats(30*24) %>% print(n = 3)

sensors <- getActiveSensors() %>% print()
getPlotValues(sensors$SENSOR[1], sensors$VALUETYPE[1]) %>% print(n = 3)

