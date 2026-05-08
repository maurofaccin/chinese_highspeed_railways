import pandas as pd

import chsr


def main() -> None:
    """Do the main."""
    data = pd.read_csv(chsr.DATAPATH)
    data["station_name"] = data["station_name"].str.replace(" Railway Station", "")
    print(data)
    data = data[["station_name", "station_order"]]
    data = pd.concat(
        [data.iloc[:-1].reset_index(drop=True), data.iloc[1:].reset_index(drop=True)], axis=1
    )
    data.columns = ["source", "so", "target", "to"]
    data["diff"] = data["to"] - data["so"]
    data = data[data["diff"] == 1].drop(columns=["so", "to", "diff"]).value_counts()

    data.to_csv("./chinese_high-speed_railways/adj.csv")


if __name__ == "__main__":
    main()
