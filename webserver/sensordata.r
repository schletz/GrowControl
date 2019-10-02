library("plumber")

r <- plumb("sensordata_api.r") 
r$run(host="0.0.0.0", port=80) 
