from pathlib import Path

import geopandas as gpd
import pandas as pd
import rioxarray
import shapely
import xarray as xr
from osm_nets import osm

import chsr
from chsr import CN_RAILS, CN_STATION_LOC


def load_edges() -> osm.Edges:
    cachefile = Path("data/cache_edges.gpkg")
    if cachefile.is_file():
        return osm.Edges(gpd.read_file(cachefile))
    edges = osm.Edges(
        gpd.read_file(CN_RAILS, layer="ways")
        .set_index("id", drop=True)
        .drop(columns=["source", "target"], errors="ignore")
    )
    edges.data = edges.data.drop(index=[88617671, 894965561, 1128048289])

    edges = edges.cleanup()
    edges = edges.split_edges_when_touching(max_workers=16)
    edges = edges.drop_duplicated_edges()

    edges.data.to_file(cachefile, index=False)
    return edges


def load_nodes() -> gpd.GeoDataFrame:
    return gpd.read_file(CN_STATION_LOC, layer="points").set_index(
        "station_name_original", drop=True
    )


def prepage_base_graph(enclosing_polygon: gpd.GeoDataFrame) -> osm.Graph:
    cachefile = Path("data/basegraph.gpkg")
    if cachefile.is_file():
        return osm.Graph.read(cachefile, node_index="NODE_ID", crs=osm.PRJ_MET)
    # get all small edge parts
    edges = load_edges()

    print("nodes from edge boundaries")
    nodes = edges.nodes_from_boundaries(prefix="__tmp_")
    nodes.data["__keep__"] = False

    graph = osm.Graph(edges=edges, region=enclosing_polygon, nodes=nodes)
    print("got graph")
    graph = graph.to_meters().aggregate_nodes(10)

    graph.write(cachefile)

    return graph


def prepare_graph() -> osm.Graph:
    """Prepare the graph."""
    cachefile = Path("graph.gpkg")
    if cachefile.is_file() and False:
        return osm.Graph.read(cachefile)

    # Retrieving the enclosing polygon.
    enclosing_polygon = gpd.read_file("./data/gadm41_CHN.gpkg", layer="ADM_ADM_0").loc[[0]]

    # get all small edge parts
    graph = prepage_base_graph(enclosing_polygon=enclosing_polygon)

    # Add real stations and overwrite overlapping nodes.
    stations = load_nodes()
    stations["__keep__"] = True
    print("add_nodes")
    graph = graph.add_nodes(
        osm.Nodes(stations).to_meters(), max_distance=300, max_distance_bounds=10
    )

    # Remove nodes that do not belong to any edge
    graph = graph.drop_disconnected_nodes()

    # Load transitions
    transition = prepare_train_transitions()
    graph = graph.from_shortest_path_all(
        pairs=transition[["source", "target"]].drop_duplicates()
        # avoid_distance=300,  # do not increase too much
        # force_smooth=True,
    )

    graph.write(cachefile)
    return graph


def prepare_train_transitions() -> pd.DataFrame:
    transitions = chsr.load_transitions()
    transitions = (
        transitions[["source", "target", "date", "hour"]]
        .value_counts()
        .reset_index()
        .sort_values(by=["date", "hour"])
    )

    return transitions


def prepare_delays(aggr: str = "1h") -> pd.DataFrame:
    transitions = chsr.load_transitions()
    transitions = transitions[["date", "source", "departure_source", "departure_delay_source"]]
    transitions["time"] = pd.to_datetime(
        transitions["date"] + " " + transitions["departure_source"]
    )
    transitions = (
        transitions.drop(columns=["date", "departure_source"])
        .set_index("time")
        .groupby("source")
        .resample(aggr)
        .sum()
        .reset_index()
        .pivot(columns="source", index="time", values="departure_delay_source")
        .fillna(0.0)
    )
    return transitions


def prepare_rain_stats() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = load_nodes()

    region = shapely.buffer(
        shapely.simplify(gpd.read_file("./data/gadm41_CHN.gpkg").iloc[0].geometry, 0.1), 0.1
    )
    assert len(nodes[~nodes.within(region)]) == 0

    data = []
    node_data = []
    for f in sorted(Path("copernicus").glob("*")):
        print(f)
        a = xr.load_dataarray(f).rio.write_crs(4326).rio.clip([region]).fillna(0.0)
        data.append(a.sum(["longitude", "latitude"]).to_dataframe()[["tp"]])

        vals = a.sel(
            longitude=nodes.geometry.x.to_xarray(),
            latitude=nodes.geometry.x.to_xarray(),
            method="nearest",
        )
        node_data.append(vals.to_dataframe()[["tp"]])

    data = pd.concat(data)
    data.index.name = "time"
    node_data = pd.concat(node_data).unstack(1, fill_value=0)
    node_data.index.name = "time"
    node_data.columns = node_data.columns.droplevel(0)

    return data, node_data


def main() -> None:
    """Do the main."""
    g = prepare_graph()

    cachefile = chsr.OUTPUT / "rain_peaks.csv.gz"
    cachefile2 = chsr.OUTPUT / "rain_peaks_stations.csv.gz"
    if not cachefile.is_file():
        rain_tot, rain_stations = prepare_rain_stats()
        rain_tot.to_csv(cachefile)
        rain_stations.to_csv(cachefile2)

    cachefile = chsr.OUTPUT / "aggregate_transitions.csv.gz"
    if not cachefile.is_file():
        tr = prepare_train_transitions()
        tr.to_csv(cachefile)

    for aggr in ["1h", "1D"]:
        cachefile = chsr.OUTPUT / "delays_per_stations.csv.gz"
        if aggr == "1h":
            cachefile = chsr.OUTPUT / "delays_per_stations_h.csv.gz"

        if not cachefile.is_file():
            t = prepare_delays(aggr)
            t.to_csv(cachefile)


if __name__ == "__main__":
    main()
