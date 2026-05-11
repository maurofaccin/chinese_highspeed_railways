from pathlib import Path

import geopandas as gpd
import osm_nets as osm
import pandas as pd

from chsr import CN_RAILS, DATAPATH


def load_trains() -> pd.DataFrame:
    """Delays per station/day in minutes."""
    data = pd.read_csv(DATAPATH, nrows=None)[["date", "station_name", "departure_delay"]]
    data["departure_delay"] = data["departure_delay"].clip(lower=0)
    data = data.groupby(["date", "station_name"]).sum()["departure_delay"].unstack(fill_value=0.0)
    return data


def load_nodes(stationlist=pd.Index) -> osm.Nodes:
    nodes = gpd.read_file(CN_RAILS, columns=["id", "name:en", "geometry"])
    lnodes = nodes.drop_duplicates(subset="name:en")

    mtch = lnodes["name:en"].isin(stationlist)
    exact = lnodes.loc[mtch]
    exact["real_name"] = exact["name:en"]
    lnodes = lnodes.loc[~mtch]
    stationlist = stationlist.difference(exact["name:en"])
    print(len(exact), len(lnodes), len(stationlist))

    mtch = lnodes["name:en"].isin(stationlist.str.replace(" Railway", ""))
    fuzz = lnodes.loc[mtch]
    fuzz["real_name"] = fuzz["name:en"]  # TODO
    lnodes = lnodes.loc[~mtch]
    stationlist = stationlist.str.replace(" Railway", "").difference(fuzz["name:en"])
    print(len(fuzz), len(lnodes), len(stationlist))
    print(fuzz)

    mtch = lnodes["name:en"].isin(stationlist.str.replace(" Station", ""))
    fuzz2 = lnodes.loc[mtch]
    fuzz2["real_name"] = fuzz2["name:en"]  # TODO
    lnodes = lnodes.loc[~mtch]
    stationlist = stationlist.str.replace(" Station", "").difference(fuzz2["name:en"])
    print(len(fuzz2), len(lnodes), len(stationlist))
    print(fuzz2)

    print(stationlist)
    exit()

    return osm.Nodes(exact)


def load_graph() -> osm.Graph:
    g = osm.retrieve_edges(CN_RAILS, split_when_touching=False)
    print(g)
    pass


def main() -> None:
    """Do the main."""
    delay_at_station = load_trains()
    print(delay_at_station)
    print(delay_at_station.sum(axis=0).sort_values())
    # n = load_nodes(d.columns)
    # g = load_graph()


if __name__ == "__main__":
    main()
