"""HW1 Part 3, step 1-2: rule-based cleaning of the raw bus-GPS reports and trip segmentation.

Steps (each removed/flagged fix is counted in the summary):
  1. de-duplicate: keep one row per (plate, gps_time); the repeats are the same record served
     again by the platform (same coordinates, speed, azimuth)                  [issue B]
  2. invalid coordinates: placeholder (120.111109, 22.11111) or outside a box around Kaohsiung City
     (KAOHSIUNG, incl. mountain districts; NOT the study area, whose fixes are all kept)  [issue D]
  3. clock skew: gps_time later than the poll that delivered it (> 5 s) -> flagged, kept
  4. trips: a bus's fixes are split into trips at a gap > GAP_S, or when route or direction
     changes                                                                    [issue A]
  5. speed spikes: a fix whose implied speed (straight line / time) from the previous fix AND to
     the next fix both exceed V_MAX (city 100 km/h, freeway express 130 km/h) is a GPS jump. A bus
     with FREQUENT_SPIKES or more spikes over the 4 days (about 100x the fleet's spike rate; the
     cause is unknown) is treated as speed-anomaly data: all its fixes are dropped; for the other
     buses only the trip that contains the spike is dropped                      [issue D / C]
  6. layovers: buses report while they stand at a terminal or in a depot. A run of fixes that
     stays within DWELL_R of its first fix is a stop (DWELL_R = 30 m: with sigma_z = 5.6 m, two fixes
     of a standing bus are within ~24 m of each other 99% of the time); at the start of a trip only the departure
     fix is kept, at the end only the arrival fix, and a stop of LAYOVER_S or longer inside a
     trip (terminal rest without a gap) is cut out and the trip split there        [issue A]
  7. trips with fewer than MIN_FIXES fixes, or that never leave a MIN_EXTENT radius (parked
     buses), are dropped

Input:  data/processed/gps/gps_reports_raw.parquet   (gps_flatten.py)
Output: data/processed/gps/gps_clean.parquet         one row per kept fix, with trip_id
        data/processed/gps/gps_trips.csv             one row per trip
        report/clean_summary.csv                     how many fixes each rule removed
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

HW1 = Path(__file__).resolve().parents[1]
GPS = HW1 / "data" / "processed" / "gps"
METRIC_CRS = "EPSG:3826"
PLACEHOLDER = (120.111109, 22.11111)
KAOHSIUNG = (120.1, 22.4, 121.1, 23.5)  # w, s, e, n incl. mountain districts
EXPRESS = r"^E\d|快線|快捷|國道"
V_MAX_CITY, V_MAX_EXPRESS = 100.0, 130.0  # km/h
GAP_S = 300
FREQUENT_SPIKES = 5  # a bus with this many speed spikes or more: all its data treated as speed-anomaly data
DWELL_R = 30.0      # m: a bus within this distance of where it stopped is still standing there
LAYOVER_S = 600     # s: a stop this long inside a trip is a layover (terminal rest), not traffic
MIN_FIXES = 5
MIN_EXTENT = 300.0  # m: a "trip" that never leaves this radius is a parked bus


def implied_speeds(f):
    """km/h from the previous fix and to the next fix of the same plate (NaN at edges)."""
    same_prev = f.plate.eq(f.plate.shift())
    same_next = f.plate.eq(f.plate.shift(-1))
    dt_prev = f.gps_time.diff().dt.total_seconds()
    d_prev = np.hypot(f.x.diff(), f.y.diff())
    v_in = np.where(same_prev & (dt_prev > 0), d_prev / dt_prev * 3.6, np.nan)
    v_out = np.where(same_next, pd.Series(v_in, index=f.index).shift(-1), np.nan)
    return v_in, v_out


def stops(x, y):
    """Partition a trip into runs [i, j): fixes i..j-1 all lie within DWELL_R of fix i."""
    runs, i, n = [], 0, len(x)
    while i < n:
        j = i + 1
        while j < n and np.hypot(x[j] - x[i], y[j] - y[i]) <= DWELL_R:
            j += 1
        runs.append((i, j))
        i = j
    return runs


def drop_layovers(x, y, t):
    """keep mask and piece number per fix: terminal waits trimmed, long stops inside cut out."""
    n = len(x)
    keep, cut = np.ones(n, bool), np.zeros(n, bool)
    runs = stops(x, y)
    for k, (i, j) in enumerate(runs):
        if j - i < 2:
            continue
        if k == 0:
            keep[i:j - 1] = False          # waiting before departure: keep the departure fix
        elif k == len(runs) - 1:
            keep[i + 1:j] = False          # waiting after arrival: keep the arrival fix
        elif t[j - 1] - t[i] >= LAYOVER_S:
            keep[i + 1:j - 1] = False      # rest in the middle: keep arrival and departure,
            cut[j - 1] = True              # and start a new trip at the departure
    return keep, np.cumsum(cut)


def main():
    raw = pd.read_parquet(GPS / "gps_reports_raw.parquet")
    steps = [("raw reports", len(raw))]

    f = raw.sort_values("poll_time").drop_duplicates(["plate", "gps_time"]).copy()
    steps.append(("1. after de-duplication (plate, gps_time)", len(f)))

    w, s, e, n = KAOHSIUNG
    bad = (np.isclose(f.lon, PLACEHOLDER[0]) & np.isclose(f.lat, PLACEHOLDER[1])) | \
          ~f.lon.between(w, e) | ~f.lat.between(s, n) | f.lon.isna() | f.lat.isna()
    f = f[~bad]
    steps.append(("2. after removing placeholder / out-of-area coordinates", len(f)))

    f["clock_skew"] = (f.gps_time - f.poll_time).dt.total_seconds() > 5
    steps.append(("3. clock-skew fixes (flagged, kept)", int(f.clock_skew.sum())))

    pts = gpd.GeoSeries(gpd.points_from_xy(f.lon, f.lat), crs="EPSG:4326").to_crs(METRIC_CRS)
    f["x"], f["y"] = pts.x.to_numpy(), pts.y.to_numpy()
    f["express"] = f.route_name.fillna("").str.contains(EXPRESS)
    f = f.sort_values(["plate", "gps_time"]).reset_index(drop=True)

    dt = f.gps_time.diff().dt.total_seconds()
    new_trip = ~f.plate.eq(f.plate.shift()) | (dt > GAP_S) | ~f.route_uid.eq(f.route_uid.shift()) | \
               ~f.direction.eq(f.direction.shift())
    f["trip_id"] = new_trip.cumsum()
    steps.append(("4. trips after splitting at gaps > 300 s / route or direction changes", int(f.trip_id.nunique())))

    v_in, v_out = implied_speeds(f)
    v_max = np.where(f.express, V_MAX_EXPRESS, V_MAX_CITY)
    spike = (v_in > v_max) & (v_out > v_max)
    per_bus = f.loc[spike].groupby("plate").size()
    bad_buses = per_bus[per_bus >= FREQUENT_SPIKES].index
    bad_trips = f.loc[spike & ~f.plate.isin(bad_buses), "trip_id"].unique()
    steps.append(("5. speed-spike fixes (in & out > V_MAX)", int(spike.sum())))
    steps.append((f"5. buses with >= {FREQUENT_SPIKES} spikes (all their fixes dropped)", len(bad_buses)))
    steps.append(("5. other trips containing a spike (dropped)", len(bad_trips)))
    f = f[~(f.plate.isin(bad_buses) | f.trip_id.isin(bad_trips))].reset_index(drop=True)
    steps.append(("5. fixes after dropping those buses and trips", len(f)))

    keep = np.ones(len(f), bool)
    piece = np.zeros(len(f), np.int64)
    for _, idx in f.groupby("trip_id").indices.items():
        k, p = drop_layovers(f.x.to_numpy()[idx], f.y.to_numpy()[idx], f.gps_time.to_numpy()[idx].astype("int64") / 1e9)
        keep[idx], piece[idx] = k, p
    n_layover_trips = int(pd.Series(piece).groupby(f.trip_id.to_numpy()).max().sum())
    f = f[keep].copy()
    f["trip_id"] = f.groupby(["trip_id", piece[keep]], sort=False).ngroup()
    steps.append(("6. fixes after removing terminal waits / layovers", len(f)))
    steps.append(("6. trips split at a layover inside the trip", n_layover_trips))

    g = f.groupby("trip_id")
    extent = np.hypot(g.x.transform("max") - g.x.transform("min"), g.y.transform("max") - g.y.transform("min"))
    ok = (g.trip_id.transform("size") >= MIN_FIXES) & (extent >= MIN_EXTENT)
    f = f[ok].copy()
    f["trip_id"] = f.trip_id.rank(method="dense").astype(int)
    steps.append((f"7. fixes after dropping trips with < {MIN_FIXES} fixes or < {MIN_EXTENT:.0f} m extent", len(f)))
    steps.append(("7. trips", int(f.trip_id.nunique())))

    f["dt_s"] = f.groupby("trip_id").gps_time.diff().dt.total_seconds()
    cols = ["trip_id", "plate", "route_uid", "route_name", "direction", "express", "gps_time", "poll_time",
            "lon", "lat", "x", "y", "speed", "azimuth", "duty_status", "bus_status", "dt_s", "clock_skew"]
    f[cols].to_parquet(GPS / "gps_clean.parquet", index=False)

    trips = f.groupby("trip_id").agg(plate=("plate", "first"), route_name=("route_name", "first"),
                                     direction=("direction", "first"), express=("express", "first"),
                                     start=("gps_time", "min"), end=("gps_time", "max"), n_fixes=("x", "size"),
                                     max_gap_s=("dt_s", "max"))
    trips["minutes"] = (trips.end - trips.start).dt.total_seconds() / 60
    trips.to_csv(GPS / "gps_trips.csv", encoding="utf-8-sig")

    summary = pd.DataFrame(steps, columns=["step", "count"])
    (HW1 / "report").mkdir(exist_ok=True)
    summary.to_csv(HW1 / "report" / "clean_summary.csv", index=False, encoding="utf-8-sig")
    print(summary.to_string(index=False))
    print(f"trips: {len(trips):,} | fixes/trip median {trips.n_fixes.median():.0f} | "
          f"minutes/trip median {trips.minutes.median():.0f} | trips with a gap > 90 s: {(trips.max_gap_s > 90).mean():.1%}")


if __name__ == "__main__":
    main()
