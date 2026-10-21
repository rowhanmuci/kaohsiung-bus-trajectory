"""HW1 Part 3: validate the repaired paths against an independent reference, the official route shapes.

The masking test (repair_eval.py) checks WHERE the bus is at a masked time, against noisy GPS; it does
not check whether the matched road is the road the bus actually drove. TDX publishes the shape of every
route and direction (/v2/Bus/Shape, data/static/tdx_bus_shape_kaohsiung.json, version 2026-10-01). The
HMM never sees it, so it serves as the reference for the path:

  1. points   distance from raw GPS / matched / corrected / imputed points to the trip's own route shape
  2. paths    for a sample of trips, the HMM path between consecutive fixes (route_line) vs the straight
              line between the raw fixes: share of path length within TOL_M of the route shape
  3. masking  reconstructed masked points per method (repair_eval_errors.parquet) vs the route shape

Only the study area (OSM network) is used. Caveat: the shape is the planned route; a bus that leaves it
(deadhead run to a depot, detour, terminal loop) also counts as "off route" here, so the numbers are a
lower bound. Rows where the raw GPS itself is far from the shape show how often that happens.

Outputs: report/route_shape_check.csv (summary), report/route_shape_paths.csv (one row per path segment),
         report/route_shape_points.parquet, report/route_shape_masking.parquet (per-point distances)
"""
import json
from multiprocessing import Pool
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import wkt

import map_matching as mm
from gps_clean import EXPRESS
from repair_eval import STUDY_BBOX

HW1 = Path(__file__).resolve().parents[1]
GPS = HW1 / "data" / "processed" / "gps"
REPORT = HW1 / "report"
TOLS = (15, 30, 50)
TOL_M = 30           # headline tolerance: a wide arterial is ~30-40 m across, shapes are drawn on one side
STEP_M = 10          # path sampling step
N_PATH_TRIPS = 2000
SEED = 7
_net = _shapes = _params = None


def load_shapes():
    d = pd.DataFrame(json.loads((HW1 / "data" / "static" / "tdx_bus_shape_kaohsiung.json").read_text(encoding="utf-8")))
    g = gpd.GeoSeries([wkt.loads(s) for s in d.Geometry], crs="EPSG:4326").to_crs(mm.METRIC_CRS)
    return {(u, int(k)): geom for u, k, geom in zip(d.RouteUID, d.Direction, g)}


def project(lon, lat):
    p = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs="EPSG:4326").to_crs(mm.METRIC_CRS)
    return p.x.to_numpy(), p.y.to_numpy()


def dist_to_shape(x, y, keys, shapes):
    """Element-wise distance from points (x, y) to the shape of their (route_uid, direction) key."""
    geoms = np.array([shapes[k] for k in keys], dtype=object)
    return shapely.distance(shapely.points(x, y), geoms)


def shares(d):
    d = pd.Series(d).dropna()
    out = {"n": len(d), "median_m": round(float(d.median()), 1), "P90_m": round(float(d.quantile(.9)), 1)}
    out.update({f"within_{t}m": round(float((d <= t).mean()), 4) for t in TOLS})
    return out


# ---------------------------------------------------------------- 1. points
def check_points(rep, trip_key, shapes):
    w, s, e, n = STUDY_BBOX
    rep = rep[rep.lon.between(w, e) & rep.lat.between(s, n)].copy()
    keys = rep.trip_id.map(trip_key).to_numpy()
    rep["x"], rep["y"] = project(rep.lon, rep.lat)
    rep["d_repaired"] = dist_to_shape(rep.x, rep.y, keys, shapes)
    has_raw = rep.raw_lon.notna().to_numpy()
    rx, ry = project(rep.raw_lon.fillna(0), rep.raw_lat.fillna(0))
    rep["d_raw"] = np.where(has_raw, dist_to_shape(rx, ry, keys, shapes), np.nan)
    rows = [{"check": "points", "set": "raw GPS (all fixes)", **shares(rep.d_raw)}]
    for kind in ("matched", "offnet", "unmatched", "imputed"):
        k = rep[rep.kind == kind]
        if kind != "imputed":
            rows.append({"check": "points", "set": f"{kind}: raw GPS", **shares(k.d_raw)})
        if kind in ("matched", "imputed"):  # offnet / unmatched keep the raw position
            rows.append({"check": "points", "set": f"{kind}: repaired", **shares(k.d_repaired)})
    # matched fixes whose raw GPS is on the planned route: isolates matching errors from route deviations
    on = rep[(rep.kind == "matched") & (rep.d_raw <= TOL_M)]
    rows.append({"check": "points", "set": f"matched, raw within {TOL_M} m of route: repaired", **shares(on.d_repaired)})
    # trips whose raw GPS does not follow the labelled route at all (special runs, wrong route label)
    per_trip = rep.groupby("trip_id").d_raw.median()
    rows.append({"check": "trips", "set": "trips in study area", "n": len(per_trip)})
    rows.append({"check": "trips", "set": "trips with median raw distance to route > 100 m", "n": int((per_trip > 100).sum()),
                 "share": round(float((per_trip > 100).mean()), 4)})
    return rows, rep


# ---------------------------------------------------------------- 2. paths
def init_worker(params):
    global _net, _shapes, _params
    _net, _shapes, _params = mm.RoadNetwork(), load_shapes(), params


def sample_line(line):
    if line is None or line.length == 0:
        return np.empty(0, dtype=object)
    return shapely.line_interpolate_point(line, np.arange(0, line.length, STEP_M))


def path_trip(trip):
    trip = trip.sort_values("gps_time")
    t = (trip.gps_time - trip.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    xs, ys = trip.x.to_numpy(), trip.y.to_numpy()
    shape = _shapes[(trip.route_uid.iloc[0], int(trip.direction.iloc[0]))]
    chosen, _ = mm.match(_net, xs, ys, t, _params["sigma_z_m"], _params["beta_m"])
    hmm_pts, chord_pts, raw_d = [], [], []
    for i in range(len(chosen) - 1):
        a, b = chosen[i], chosen[i + 1]
        if a is None or b is None:
            continue
        hmm_pts.append(sample_line(_net.route_line(a, b)))
        chord_pts.append(sample_line(shapely.LineString([(xs[i], ys[i]), (xs[i + 1], ys[i + 1])])))
        raw_d.append(max(shapely.distance(shapely.Point(xs[i], ys[i]), shape),
                         shapely.distance(shapely.Point(xs[i + 1], ys[i + 1]), shape)))
    out = []
    for name, pts in (("hmm", hmm_pts), ("chord", chord_pts)):
        for seg, rd in zip(pts, raw_d):
            if len(seg):
                d = shapely.distance(seg, shape)
                out.append((int(trip.trip_id.iloc[0]), name, rd, len(seg) * STEP_M, *[float((d <= tol).mean()) for tol in TOLS]))
    return out


def check_paths(clean, params):
    w, s, e, n = STUDY_BBOX
    g = clean.groupby("trip_id")
    ok = pd.DataFrame({"inside": g.lon.min().ge(w) & g.lon.max().le(e) & g.lat.min().ge(s) & g.lat.max().le(n),
                       "n": g.size(), "express": g.express.first()})
    ids = ok[ok.inside & ~ok.express & (ok.n >= 10)].sample(n=N_PATH_TRIPS, random_state=SEED).index
    trips = [d for _, d in clean[clean.trip_id.isin(ids)].groupby("trip_id")]
    rows = []
    with Pool(processes=14, initializer=init_worker, initargs=(params,)) as pool:
        for r in pool.imap_unordered(path_trip, trips, chunksize=10):
            rows.extend(r)
    seg = pd.DataFrame(rows, columns=["trip_id", "path", "raw_end_dist_m", "length_m"] + [f"within_{t}m" for t in TOLS])
    seg.to_csv(REPORT / "route_shape_paths.csv", index=False)
    out = []
    for subset, m in (("all segments", seg.raw_end_dist_m >= 0),
                      (f"both raw ends within {TOL_M} m of route", seg.raw_end_dist_m <= TOL_M)):
        for path, d in seg[m].groupby("path"):
            # length-weighted share of the path lying within each tolerance of the route shape
            row = {"check": "paths", "set": f"{path} ({subset})", "n": int(d.trip_id.nunique()),
                   "length_km": round(float(d.length_m.sum()) / 1000, 1)}
            row.update({f"within_{t}m": round(float(np.average(d[f"within_{t}m"], weights=d.length_m)), 4) for t in TOLS})
            out.append(row)
    return out, seg


# ---------------------------------------------------------------- 3. masking
def check_masking(clean, trip_key, shapes):
    errs = pd.read_parquet(REPORT / "repair_eval_errors.parquet")
    keys = errs.trip_id.map(trip_key).to_numpy()
    errs["d_route"] = dist_to_shape(errs.x.to_numpy(), errs.y.to_numpy(), keys, shapes)
    # truth: the masked fix itself (idx = position in the trip sorted by time)
    tr = clean[clean.trip_id.isin(errs.trip_id.unique())].sort_values(["trip_id", "gps_time"])
    tr["idx"] = tr.groupby("trip_id").cumcount()
    errs = errs.merge(tr[["trip_id", "idx", "x", "y"]].rename(columns={"x": "tx", "y": "ty"}), on=["trip_id", "idx"])
    errs["d_truth"] = dist_to_shape(errs.tx.to_numpy(), errs.ty.to_numpy(), errs.trip_id.map(trip_key).to_numpy(), shapes)
    rows = []
    for k, d in errs.groupby("k"):
        truth = d[d.method == "hmm"]
        rows.append({"check": f"masking k={k}", "set": "truth (masked GPS fix)", **shares(truth.d_truth)})
        for m, dm in d.groupby("method"):
            rows.append({"check": f"masking k={k}", "set": m, **shares(dm.d_route)})
    return rows, errs


def main():
    params = json.loads((REPORT / "repair_params.json").read_text(encoding="utf-8"))
    shapes = load_shapes()
    clean = pd.read_parquet(GPS / "gps_clean.parquet")
    first = clean.groupby("trip_id")[["route_uid", "direction"]].first()
    trip_key = {t: (u, int(d)) for t, u, d in zip(first.index, first.route_uid, first.direction)}

    rows, pts = check_points(pd.read_parquet(GPS / "gps_repaired.parquet"), trip_key, shapes)
    print(pd.DataFrame(rows).to_string(index=False), flush=True)
    r2, seg = check_paths(clean, params)
    print(pd.DataFrame(r2).to_string(index=False), flush=True)
    r3, errs = check_masking(clean, trip_key, shapes)
    print(pd.DataFrame(r3).to_string(index=False), flush=True)
    pd.DataFrame(rows + r2 + r3).to_csv(REPORT / "route_shape_check.csv", index=False)
    pts[["trip_id", "kind", "d_raw", "d_repaired"]].to_parquet(REPORT / "route_shape_points.parquet", index=False)
    errs[["trip_id", "k", "method", "idx", "d_route", "d_truth"]].to_parquet(REPORT / "route_shape_masking.parquet", index=False)


if __name__ == "__main__":
    main()
