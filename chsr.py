"""Base function and data."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio as rio
import shapely
from rasterio import mask
from scipy.spatial import KDTree

DATAPATH = Path("chinese_high-speed_railways/high-speed trains operation data.csv.gz")
CN_RAILS = Path("data/CN_railways.gpkg")
CN_STATION_LOC = Path("data/stations.gpkg")
OUTPUT = Path("stats")
OUTPUT.mkdir(exist_ok=True)


def load_transitions() -> pd.DataFrame:
    cachefile = Path("/tmp/full_transitions.csv.gz")
    if cachefile.is_file():
        transitions = pd.read_csv(cachefile)
        return transitions

    delays = pd.read_csv(DATAPATH, parse_dates=["date"])

    # set of stations to be merged
    rename_name = CN_STATION_LOC.name.removesuffix(".gpkg") + "_dups.json"
    with (CN_STATION_LOC.parent / rename_name).open("r") as fin:
        rename = json.load(fin)
    delays["station_name"] = (
        delays["station_name"].str.removesuffix(" Railway Station").replace(rename)
    )
    delays = delays[
        ["date", "station_name", "station_order", "scheduled_departure_time", "departure_delay"]
    ]
    delays["departure_delay"] = delays["departure_delay"].clip(lower=0)

    transitions = (
        delays.iloc[:-1]
        .reset_index()
        .join(delays.iloc[1:].reset_index(), lsuffix="_source", rsuffix="_target")
    )
    transitions = transitions[
        (transitions["station_order_target"] - transitions["station_order_source"]) == 1
    ]
    transitions = transitions.rename(
        columns={
            "station_name_source": "source",
            "station_name_target": "target",
            "scheduled_departure_time_source": "departure_source",
            "scheduled_departure_time_target": "departure_target",
            "date_source": "date",
        }
    )

    # Fix with geographic corrections
    lines = gpd.read_file(CN_STATION_LOC, layer="lines")

    # Look for neighbors
    # WARN: same stations have the same name,
    #       the only way to distinguish them is through their neighbors
    neigs = pd.concat([lines, lines.rename(columns={"target": "source", "source": "target"})])
    neigs = (
        neigs.loc[neigs["source"].str.contains("_"), ["source", "target"]]
        .drop_duplicates()
        .groupby("source")
        .agg(list)["target"]
        .to_dict()
    )
    neigs = {(str(k).split("_")[0], ng): (k, ng) for k, ngs in neigs.items() for ng in ngs}
    neigs = neigs | {(k[1], k[0]): (v[1], v[0]) for k, v in neigs.items()}

    def rename_on_neigs(data: pd.Series):
        s = data["source"]
        t = data["target"]
        if (s, t) in neigs:
            s, t = neigs[(s, t)]
        return [s, t]

    transitions[["source", "target"]] = transitions[["source", "target"]].apply(
        rename_on_neigs, axis=1, result_type="expand"
    )

    # keep only relevant info
    transitions["hour"] = transitions["departure_source"].apply(lambda x: int(x[:2]))
    transitions = transitions.drop(
        columns=[
            "station_order_target",
            "station_order_source",
            "index_source",
            "index_target",
            "date_target",
        ]
    )
    transitions.to_csv(cachefile, index=False)
    return transitions


def compute_voronois(points: gpd.GeoDataFrame, **kwargs) -> gpd.GeoDataFrame:
    """Compute the voronoi polygons of each point.

    Parameters
    ----------
    points : geopd.GeoDataFrame
        a geodataframe of points (shapely.geometry.Point)
    kwargs :
        arguments to be passed to shapely.voronoi_polygons()

    Returns
    -------
    voronois : geopd.GeoDataFrame
        the same geodataframe as input with an additional column named `voronoi`
        (shapely.geometry.Polygon)

    """
    # Just put all voronoi polygons in a GeoSeries
    polys = gpd.GeoDataFrame(
        {
            "voronoi": shapely.voronoi_polygons(
                shapely.MultiPoint(points["geometry"].tolist()), **kwargs
            ).geoms
        },
        crs="4326",
        geometry="voronoi",
    )
    # pick representative points
    # polys["repr"] = polys["repr"]

    # find the closer withing the representative points
    nearest = ckdnearest_points(
        points, gpd.GeoSeries([p.point_on_surface() for p in polys.geometry])
    )

    # check if the closer representative point fall within the voronoi cell
    # otherwise search for the right one.
    real_containing_poly = []
    polygon_taken = set()
    for point_indx, point in nearest.iterrows():
        poly = polys.loc[point["_orig_indx_"]]
        if poly["voronoi"].contains(point.geometry):
            # it's OK: the point fall within the polygon
            polygon_taken.add(poly.name)
            real_containing_poly.append({"indx": point_indx, "voronoi": poly["voronoi"]})
            continue

        # find the containing polygon the hard way
        for pl_indx, pl in polys.iterrows():
            if pl_indx not in polygon_taken and pl["voronoi"].contains(point.geometry):
                polygon_taken.add(pl_indx)
                real_containing_poly.append({"indx": point_indx, "voronoi": pl["voronoi"]})
                break

    assert len(polygon_taken) == len(polys)
    assert len(real_containing_poly) == len(nearest)

    real_containing_poly_df = pd.DataFrame(real_containing_poly).set_index("indx", drop=True)
    nearest.loc[real_containing_poly_df.index, "voronoi"] = real_containing_poly_df["voronoi"]
    return nearest.drop(columns=["_dist_", "_orig_indx_"])


def ckdnearest_points(gda: gpd.GeoDataFrame, gdb: gpd.GeoSeries) -> gpd.GeoDataFrame:
    """Find points in the second GeoDataFrame that are closer to those in the first.

    Will append a few columns to `gda`:
    - `_orig_indx_`: its index
    - `_dist_`: the distance between the points
    """
    na = np.array(list(gda.geometry.apply(lambda x: (x.x, x.y))))
    nb = np.array(list(gdb.geometry.apply(lambda x: (x.x, x.y))))
    btree = KDTree(nb)
    dist, idx = btree.query(na, k=1, workers=-1)
    return gpd.GeoDataFrame(
        pd.concat(
            [
                gda.reset_index(drop=True),
                pd.Series(idx, name="_orig_indx_"),
                pd.Series(dist, name="_dist_"),
            ],
            axis=1,
        ).set_index(gda.index, drop=True)
    )


def integrate_raster(polygons: gpd.GeoSeries, raster_file: str | Path) -> pd.Series:
    """Integrate the given raster in each polygon.

    Parameters
    ----------
    polygons : geopd.GeoSeries
        a Series of polygons (e.g. voronoi cells)
    raster_file : str | Path
        the path to a raster file (GeoTiff format).

    Returns
    -------
    integral : pd.Series
        A series with the raster integrated within polygons with the same index as `polygons`.

    """
    pop = []
    with rio.open(raster_file) as raster:
        for poly in polygons:
            # load population in that window
            try:
                win_pop, win_transform = mask.mask(
                    raster, [shapely.geometry.mapping(poly)], nodata=0.0, filled=True, crop=True
                )
            except ValueError:
                pop.append(0)
                continue

            # compute the population inside the polygon
            pop.append(np.nansum(win_pop))

    return pd.Series(pop, index=polygons.index, name="population")
