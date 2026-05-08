"""This script will check all the station in `./chinese_high-speed_railways/high-speed trains operation data.csv.gz`
and find the relevant geographic position and corresponding OSM representation.
"""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
from shapely import LineString, Point

import chsr

dictionary = {"Zhongqing": "Chongqing"}
suffixes = {
    "qing": "?",
    "xian": "county",
    "qu": "district",
    "bei": "north",
    "nan": "south",
    "dong": "east",
    "xi": "west",
}

MANUAL = pd.DataFrame(
    [
        {"name": "Afanggong", "osmid": 5762027860},
        {"name": "Binzhou", "osmid": 5697139255},
        {"name": "Boyuquan", "osmid": 4391476630},
        {"name": "Changlinhe", "osmid": 9524540935},
        {"name": "Changzhou", "osmid": 8453216523},
        {"name": "Dongkou", "osmid": 5559277119},
        {"name": "Futian", "osmid": 2310688619},
        {"name": "Guigang", "osmid": 3909327374},
        {"name": "Hanjiang", "osmid": 7792857871},
        {"name": "Huaqiao", "osmid": 4249835303},
        {"name": "Hukou", "osmid": 2381264576},
        {"name": "Jiaxian", "osmid": 5575721523},
        {"name": "Jingxian", "osmid": 9524548104},
        {"name": "Lanshanxi", "osmid": 9549447314},
        {"name": "Luanhe", "osmid": 7781338009},
        {"name": "Lufeng", "osmid": 1732278092},
        {"name": "Lushan", "osmid": 1769587482},
        {"name": "Minchinan", "osmid": 3006156365},
        {"name": "Nanfeng", "osmid": 2501345649},
        {"name": "Nanpingbei", "osmid": 7014731878},
        {"name": "Nixi", "osmid": 5774489263},
        {"name": "Pingshan", "osmid": 5507309248},
        {"name": "Puanxian", "osmid": 3328330804},
        {"name": "Puwan", "osmid": 2832751253},
        {"name": "Qianjiang", "osmid": 3053778847},
        {"name": "Qidong", "osmid": 5141988543},
        {"name": "Qihe", "osmid": 6184600989},
        {"name": "Quanzhounan", "osmid": 8154570904},
        {"name": "Shenfang", "osmid": 7714110152},
        {"name": "Songjiangnan", "osmid": 7160140850},
        {"name": "Suining", "osmid": 7127162182},
        {"name": "Tahexi", "osmid": 8401357510},
        {"name": "Taihe", "osmid": 2314116851},
        {"name": "Wananxian", "osmid": 2941969186},
        {"name": "Weihexi", "osmid": 1603990260},
        {"name": "Wulongbeidong", "osmid": 9179735854},
        {"name": "Wuyishandong", "osmid": 7252546318},
        {"name": "Wuyuan", "osmid": 2517241085},
        {"name": "Xianyangqindu", "osmid": 1532510499},
        {"name": "Xidu", "osmid": 5559297478},
        {"name": "Xifeng", "osmid": 1763164530},
        {"name": "Xinganbei", "osmid": 7830203476},
        {"name": "Xinjinan", "osmid": 2329491735},
        {"name": "Xiuwenxian", "osmid": 8211935366},
        {"name": "Xixianbei", "osmid": 10666136336},
        {"name": "Yanling", "osmid": 4732069359},
        {"name": "Yanping", "osmid": 7014731878},
        {"name": "Yijiang", "osmid": 7791053789},
        {"name": "Yiyang", "osmid": 655354700},
        {"name": "Yongjia", "osmid": 7714110150},
        {"name": "Yongtai", "osmid": 2451353649},
        {"name": "Yuhang", "osmid": 9850732096},
        {"name": "Yujiangbei", "osmid": 13061379939},
        {"name": "Zaozhuang", "osmid": 3163707180},
        {"name": "Zhaodong", "osmid": 3701360574},
        {"name": "Zhaotian", "osmid": 7332499345},
        {"name": "Zhaoyang", "osmid": 4507851963},
        {"name": "Zunyinan", "osmid": 3695320136},
        {"name": "Taishan", "osmid": 5485730430},
        {"name": "Lijiazhai", "osmid": 9255881282},
        {"name": "Fangcheng", "osmid": 9526166087},
        {"name": "Sanmenxian", "osmid": 7714110158},
        {"name": "Jiangshan", "osmid": 9527101298},
        {"name": "Nanling", "osmid": 9521935585},
        {"name": "Yancheng", "osmid": 7682857921},
        {"name": "Guilin", "osmid": 626322669},
        {"name": "Jinjiang", "osmid": 7778190320},
        {"name": "Yixing", "osmid": 7260208795},
    ],
    columns=["osmid", "name", "zh_name"],
).set_index("name")
MANUAL["zh_name"] = MANUAL["zh_name"].astype("str")

ADDITIONAL = pd.DataFrame(
    [
        {
            "name:en": "Shuangchengbei",
            "name": "双城北",
            "osmid": 1488712226,
            "geometry": Point(126.2645857, 45.4238746),
        }
    ]
)


SPLIT = {
    "Jingzhou": [5555291485, 2492404007],
    "Fengchengdong": [9179735855, 2940767972],
    "Taian": [8431451879, 6844103016],
}


def strip_suffix(name: str) -> list[str]:
    short = name.replace(" Railway Station", "")
    names = [name, name.replace(" Railway", ""), short]
    return names


def main():
    """Do the main."""
    # First guess
    stations = pd.read_csv("./chinese_high-speed_railways/stations_lucrezia.csv")
    stations["names"] = [
        strip_suffix(n["english_name"]) + strip_suffix(n["station_name_original"])
        for _, n in stations.iterrows()
    ]
    # Manual adjustments
    stations["station_name_original"] = stations["station_name_original"].str.replace(
        " Railway Station", ""
    )
    stations = stations.set_index("station_name_original")
    for k in MANUAL.columns:
        # Add additional columns
        stations.loc[MANUAL.index, k] = MANUAL[k]

    # Data from OpenStreetMap
    osm_stations = gpd.read_file(chsr.CN_RAILS, layer="points", crs=4326).set_index(
        "id", drop=True
    )[["name", "name:en", "geometry"]]
    # Manual adjustments
    osm_stations = pd.concat([osm_stations, ADDITIONAL.set_index("osmid")])

    # Get a mapping from names, to osm indx
    osm_names = dict(zip(osm_stations["name:en"], osm_stations.index))
    osm_znnames = dict(zip(osm_stations["name"], osm_stations.index))
    for osm in [osm_names, osm_znnames]:
        if pd.NA in osm.keys():
            del osm[pd.NA]
        if "" in osm.keys():
            del osm[""]
    # clean up
    osm_znnames.pop(pd.NA, "XXX")
    osm_znnames.pop("", "XXX")
    osm_names.pop(pd.NA, "XXX")
    osm_names.pop("", "XXX")

    ids = []
    for _, st in stations.iterrows():
        _lids = st["osmid"]

        if not pd.isna(st["osmid"]):
            _lids = st["osmid"]

        if pd.isna(_lids):
            for stn in st["names"]:
                if stn in osm_names:
                    _lids = osm_names[stn]
                    break

        if pd.isna(_lids) and st["zh_name"] in osm_znnames:
            _lids = osm_znnames[st["zh_name"]]

        ids.append(_lids)

    stations["osmid"] = ids

    # deal with OSM IDs duplicates.
    dups = stations["osmid"].value_counts()
    dups = dups[dups > 1]
    dups = stations[stations["osmid"].isin(dups.index)]
    print("Test if there are stations assigned to the same point.")
    print(stations["osmid"].value_counts())
    print("WARNING: The following are mappend to the same station:")
    print(dups)

    # %%

    rename_dups = {
        sn: snames[0]
        for _, snames in dups.reset_index()[["station_name_original", "osmid"]]
        .groupby("osmid")
        .agg(list)["station_name_original"]
        .items()
        for sn in snames[1:]
    }
    # %%
    stations = stations.drop_duplicates(subset=["osmid"], keep="first", inplace=False)

    not_found = stations[stations["osmid"].isna()]
    if len(not_found) > 0:
        print(not_found)
        first = not_found.index[0]
        pairs = pd.read_csv(
            "./chinese_high-speed_railways/adjacent railway stations mileage data.csv.gz"
        )
        print(first)
        print(pairs[pairs["from_station"] == first])
        locs = pd.read_csv("./chinese_high-speed_railways/railway stations delay data.csv.gz")[
            ["station_name", "province", "city"]
        ].drop_duplicates()
        print(locs[locs["station_name"] == first])
        return

    split_stations = pd.DataFrame(
        [
            stations.loc[station].to_dict()
            | {
                "station_name_original": f"{station}_{stnum}",
                "splitted": station,
                "osmid": osmids[stnum],
            }
            for station, osmids in SPLIT.items()
            for stnum in range(len(osmids))
        ]
    ).set_index("station_name_original", drop=True)
    split_stations["zh_name"] = np.nan
    split_stations.index.name = "station_name_original"
    stations = stations.drop(list(SPLIT.keys()))

    # Merge info
    stations = (
        gpd.GeoDataFrame(
            pd.concat(
                [stations.reset_index().set_index("osmid"), osm_stations.loc[stations["osmid"]]],
                axis=1,
            ),
            crs=4326,
        )
        .reset_index()
        .set_index("station_name_original", drop=True)
        .rename(columns={"index": "osmid"})
    )
    split_stations = (
        gpd.GeoDataFrame(
            pd.concat(
                [
                    split_stations.reset_index().set_index("osmid"),
                    osm_stations.loc[split_stations["osmid"]],
                ],
                axis=1,
            ),
            crs=4326,
        )
        .reset_index()
        .set_index("station_name_original", drop=True)
        .rename(columns={"index": "osmid"})
    )

    # Deal with connections
    geod = pyproj.Geod(ellps="WGS84")
    adj = pd.read_csv("./chinese_high-speed_railways/adj.csv")
    adj = adj.map(lambda x: rename_dups.get(x, x)).groupby(["source", "target"]).sum().reset_index()
    for splitted, new_stations in split_stations.groupby("splitted"):
        closest = [
            min(
                new_stations.index,
                key=lambda x: geod.geometry_length(
                    LineString([new_stations.loc[x, "geometry"], g])
                ),
            )
            for g in stations.loc[adj[adj["source"] == splitted]["target"], "geometry"]
        ]
        adj.loc[adj["source"] == splitted, "source"] = closest
        print(adj[adj["source"] == splitted])
        closest = [
            min(
                new_stations.index,
                key=lambda x: geod.geometry_length(
                    LineString([new_stations.loc[x, "geometry"], g])
                ),
            )
            for g in stations.loc[adj[adj["target"] == splitted]["source"], "geometry"]
        ]
        adj.loc[adj["target"] == splitted, "target"] = closest
        print(adj[adj["target"] == splitted])

    stations = pd.concat([stations, split_stations])
    adj["geometry"] = [
        LineString(
            [stations.loc[link["source"], "geometry"], stations.loc[link["target"], "geometry"]]
        )
        for _, link in adj.iterrows()
    ]
    adj["real"] = [geod.geometry_length(g) / 1000 for g in adj.geometry]
    adj = adj.sort_values("real", ascending=False)
    print(adj.drop(columns="geometry"))
    adj = gpd.GeoDataFrame(adj, crs=4326)
    stations = gpd.GeoDataFrame(stations, crs=4326)
    stations["degree"] = adj["source"].value_counts()

    # write to file
    stations["osmid"] = stations["osmid"].astype("int")
    stations.drop(columns=["names", "longitude", "latitude"], errors="ignore").to_file(
        Path("data/stations.gpkg"), layer="points", mode="w"
    )
    adj.to_file(Path("data/stations.gpkg"), layer="lines", mode="w")
    with Path("data/stations_dups.json").open("w") as fout:
        json.dump(rename_dups, fout)


if __name__ == "__main__":
    main()
