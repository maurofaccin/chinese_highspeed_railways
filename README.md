# Chinese Highspeed railway network.

This repo contains data and code used to build a railway network.

## Pipeline

### 1

`./osm_get_adj.py`: Create the graph from train data.

Output: `./chinese_high-speed_railways/adj.csv`

### 2.

`./osm_get_station_location.py`:
Use OSM and manual adjustments to fix multiple stations with the same names or one station with multiple names. Add geographic location.

output: `./data/stations.gpkg`, `./data/stations_dups.json`


### 3.

`./prepare_data.py`:
create the graph with transitions.
