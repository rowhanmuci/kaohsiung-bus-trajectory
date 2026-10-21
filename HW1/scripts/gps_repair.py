"""HW1 Part 3: repair every cleaned trip with HMM map matching + route-based gap filling.

For each trip (gps_clean.parquet):
  1. HMM map matching of all its fixes (map_matching.py, drive network) with sigma_z and beta
     tuned in repair_eval.py (report/repair_params.json). A fix is moved onto its matched road;
     drift of up to the search radius (EDA issue C) is removed this way.
  2. Fixes with no drive road within the search radius keep their raw position. They are NOT
     treated as drift: checked against the official route shapes (route_shape_check.py), most of
     them lie on the bus's own route, on roads the drive network lacks (terminals, MRT transfer
     bays, campus roads) or just outside the study area, and re-imputing them along the network
     moved them off the route (EXPERIMENT_LOG.md). They are labelled instead:
       offnet     a road of the denser bus network (drive + service + bus-only roads) is within
                  the search radius: the bus is on a road outside the routing network
       unmatched  no road at all within the radius: outside the study area, depot, or large drift
  3. Gap filling: wherever two consecutive matched fixes are more than FILL_GAP_S apart, points
     are inserted every STEP_S seconds along the shortest driving route between them.

Output: data/processed/gps/gps_repaired.parquet, one row per point:
  trip_id, plate, route_name, direction, time, lon, lat (repaired), raw_lon, raw_lat,
  kind ("matched" | "offnet" | "unmatched" | "imputed"), snap_m (raw -> matched distance),
  edge_u, edge_v (OSM node ids of the matched drive edge)
Summary: report/repair_summary.csv
"""
import json
from multiprocessing import Pool
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

import map_matching as mm

HW1 = Path(__file__).resolve().parents[1]
GPS = HW1 / "data" / "processed" / "gps"
REPORT = HW1 / "report"
FILL_GAP_S = 90
STEP_S = 60
_net = None
_params = None


def init_worker(params):
    global _net, _params
    _net, _params = mm.RoadNetwork(), params


def repair_trip(trip):
    trip = trip.sort_values("gps_time")
    t = (trip.gps_time - trip.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    xs, ys = trip.x.to_numpy(), trip.y.to_numpy()
    chosen, breaks = mm.match(_net, xs, ys, t, _params["sigma_z_m"], _params["beta_m"])
    base = {"trip_id": int(trip.trip_id.iloc[0]), "plate": trip.plate.iloc[0], "route_name": trip.route_name.iloc[0],
            "direction": trip.direction.iloc[0]}
    t0 = trip.gps_time.iloc[0]
    rows = []
    for i, c in enumerate(chosen):
        if c is None:
            rows.append({**base, "t": t[i], "x": xs[i], "y": ys[i], "raw_x": xs[i], "raw_y": ys[i],
                         "kind": "unmatched", "snap_m": np.nan, "edge_u": None, "edge_v": None})
        else:
            rows.append({**base, "t": t[i], "x": c.x, "y": c.y, "raw_x": xs[i], "raw_y": ys[i], "kind": "matched",
                         "snap_m": c.dist, "edge_u": int(_net.u[c.edge]), "edge_v": int(_net.v[c.edge])})
        if i + 1 < len(chosen) and t[i + 1] - t[i] > FILL_GAP_S and c is not None and chosen[i + 1] is not None:
            for tt in np.arange(t[i] + STEP_S, t[i + 1] - STEP_S / 2, STEP_S):
                px, py = mm.interpolate_route(_net, c, t[i], chosen[i + 1], t[i + 1], tt)
                rows.append({**base, "t": tt, "x": px, "y": py, "raw_x": np.nan, "raw_y": np.nan, "kind": "imputed",
                             "snap_m": np.nan, "edge_u": None, "edge_v": None})
    out = pd.DataFrame(rows)
    out["time"] = t0 + pd.to_timedelta(out.pop("t"), unit="s")
    return out, breaks


def label_offnet(out):
    """Unmatched fixes with a road of the bus network (drive + service + bus-only) within the radius."""
    bus = gpd.read_parquet(mm.BUS_EDGES).to_crs(mm.METRIC_CRS)
    um = (out.kind == "unmatched").to_numpy()
    _, d = shapely.STRtree(bus.geometry.to_numpy()).query_nearest(
        shapely.points(out.raw_x[um], out.raw_y[um]), return_distance=True, all_matches=False)
    kind = out.kind.to_numpy().copy()
    kind[np.flatnonzero(um)[d <= mm.RADIUS_M]] = "offnet"
    out["kind"] = kind


def main():
    params = json.loads((REPORT / "repair_params.json").read_text(encoding="utf-8"))
    f = pd.read_parquet(GPS / "gps_clean.parquet")
    trips = [g for _, g in f.groupby("trip_id")]
    print(f"repairing {len(trips):,} trips ({len(f):,} fixes) with sigma_z={params['sigma_z_m']} m, beta={params['beta_m']} m", flush=True)
    parts, breaks = [], 0
    with Pool(processes=14, initializer=init_worker, initargs=(params,)) as pool:
        for n, (part, b) in enumerate(pool.imap_unordered(repair_trip, trips, chunksize=20), 1):
            parts.append(part)
            breaks += b
            if n % 2000 == 0:
                print(f"  {n:,}/{len(trips):,} trips", flush=True)
    out = pd.concat(parts, ignore_index=True).sort_values(["trip_id", "time"]).reset_index(drop=True)
    out[["edge_u", "edge_v"]] = out[["edge_u", "edge_v"]].astype("Int64")  # OSM node ids; empty unless matched
    label_offnet(out)
    ll = gpd.GeoSeries(gpd.points_from_xy(out.x, out.y), crs=mm.METRIC_CRS).to_crs("EPSG:4326")
    raw = gpd.GeoSeries(gpd.points_from_xy(out.raw_x.fillna(0), out.raw_y.fillna(0)), crs=mm.METRIC_CRS).to_crs("EPSG:4326")
    # positional assignment (.to_numpy()): never align a fresh GeoSeries index with the sorted frame
    out["lon"], out["lat"] = ll.x.round(7).to_numpy(), ll.y.round(7).to_numpy()
    out["raw_lon"] = np.where(out.raw_x.notna(), raw.x.round(7).to_numpy(), np.nan)
    out["raw_lat"] = np.where(out.raw_x.notna(), raw.y.round(7).to_numpy(), np.nan)
    cols = ["trip_id", "plate", "route_name", "direction", "time", "lon", "lat", "raw_lon", "raw_lat", "kind",
            "snap_m", "edge_u", "edge_v"]
    out[cols].to_parquet(GPS / "gps_repaired.parquet", index=False)
    kinds = out.kind.value_counts()
    summ = pd.DataFrame([
        ("trips", len(trips)), ("input fixes", len(f)), ("matched fixes", int(kinds.get("matched", 0))),
        (f"offnet fixes (bus-network road within {mm.RADIUS_M:.0f} m, raw position kept)", int(kinds.get("offnet", 0))),
        (f"unmatched fixes (no road within {mm.RADIUS_M:.0f} m, raw position kept)", int(kinds.get("unmatched", 0))),
        (f"imputed points (gaps > {FILL_GAP_S} s, every {STEP_S} s)", int(kinds.get("imputed", 0))),
        ("HMM chain breaks", breaks),
        ("median snap distance of matched fixes (m)", round(float(out.snap_m.median()), 2)),
        ("P95 snap distance of matched fixes (m)", round(float(out.snap_m.quantile(.95)), 2))],
        columns=["item", "value"])
    summ.to_csv(REPORT / "repair_summary.csv", index=False, encoding="utf-8-sig")
    print(summ.to_string(index=False))


if __name__ == "__main__":
    main()
