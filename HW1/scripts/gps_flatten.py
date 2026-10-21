"""Flatten the raw bus-GPS snapshots into one table, without any cleaning.

Every report of every poll is kept, including the same report seen in several polls
(the EDA studies those duplicates). Times are local (Asia/Taipei), timezone-naive.

Input:  HW1/data/raw/bus_gps_kaohsiung/<YYYYMMDD>/<HHMMSS>.json.gz
Output: HW1/data/processed/gps/gps_reports_raw.parquet   (one row per report per poll)
        HW1/data/processed/gps/gps_polls.csv              (one row per poll: time, n_reports)

Columns: poll_time, plate, operator_id, route_uid, route_name, subroute_uid, subroute_name,
         direction, lon, lat, geohash, speed, azimuth, duty_status, bus_status,
         gps_time, src_update_time, update_time

Usage: python gps_flatten.py [--start "2026-10-16 10:30"] [--end "2026-10-19 21:00"]
"""
import argparse
import gzip
import json
from pathlib import Path

import pandas as pd

HW1 = Path(__file__).resolve().parents[1]
RAW = HW1 / "data" / "raw" / "bus_gps_kaohsiung"
OUT = HW1 / "data" / "processed" / "gps"


def local_naive(s):
    """ISO strings with +08:00 -> timezone-naive local timestamps."""
    return pd.to_datetime(s, utc=True).dt.tz_convert("Asia/Taipei").dt.tz_localize(None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-10-16 10:30")
    parser.add_argument("--end", default="2026-10-19 21:00")
    args = parser.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)

    rows, polls = [], []
    for day in sorted(p for p in RAW.iterdir() if p.is_dir() and p.name.isdigit()):
        for f in sorted(day.glob("*.json.gz")):
            poll_time = pd.Timestamp(f"{day.name} {f.name[:6]}")
            if not (start <= poll_time < end):
                continue
            payload = json.load(gzip.open(f, "rt", encoding="utf-8"))
            polls.append({"poll_time": poll_time, "n_reports": len(payload)})
            for b in payload:
                pos = b.get("BusPosition") or {}
                rows.append({
                    "poll_time": poll_time, "plate": b.get("PlateNumb"), "operator_id": b.get("OperatorID"),
                    "route_uid": b.get("RouteUID"), "route_name": (b.get("RouteName") or {}).get("Zh_tw"),
                    "subroute_uid": b.get("SubRouteUID"), "subroute_name": (b.get("SubRouteName") or {}).get("Zh_tw"),
                    "direction": b.get("Direction"), "lon": pos.get("PositionLon"), "lat": pos.get("PositionLat"),
                    "geohash": pos.get("GeoHash"), "speed": b.get("Speed"), "azimuth": b.get("Azimuth"),
                    "duty_status": b.get("DutyStatus"), "bus_status": b.get("BusStatus"),
                    "gps_time": b.get("GPSTime"), "src_update_time": b.get("SrcUpdateTime"),
                    "update_time": b.get("UpdateTime"),
                })
    df = pd.DataFrame(rows)
    for col in ("gps_time", "src_update_time", "update_time"):
        df[col] = local_naive(df[col])
    df["bus_status"] = df["bus_status"].astype("Int64")  # missing in some reports
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "gps_reports_raw.parquet", index=False)
    pd.DataFrame(polls).to_csv(OUT / "gps_polls.csv", index=False)
    print(f"{len(polls)} polls {start:%m-%d %H:%M} -> {end:%m-%d %H:%M}, {len(df):,} reports, "
          f"{df.plate.nunique()} buses, {df.route_name.nunique()} routes -> {OUT / 'gps_reports_raw.parquet'}")
    print("polls per day:", pd.DataFrame(polls).poll_time.dt.date.value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
