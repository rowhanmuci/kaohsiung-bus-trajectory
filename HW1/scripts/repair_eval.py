"""HW1 Part 3: evaluate GPS gap repair by masking observed fixes and reconstructing them.

Evaluation trips: trips fully inside the study area, city routes (no freeway express), at least
MIN_FIXES fixes, no internal gap > 90 s. Drawn evenly from the four collection days, then split
into a tuning set (parameter search) and a test set (reported numbers).

Masking: keep every k-th fix (k = 2, 4, 8, i.e. one fix per 2 / 4 / 8 minutes) plus the last one;
the dropped fixes are the ground truth to reconstruct.

Methods
  linear   straight-line interpolation in x(t), y(t) between kept fixes
  spline   natural cubic spline of x(t), y(t) through the kept fixes
  kalman   constant-velocity Kalman filter + RTS smoother over the kept fixes, read at the
           dropped times (process noise = white acceleration sigma_a)
  hmm      HMM map matching of the kept fixes (map_matching.py), then route-based
           interpolation along the matched shortest path (ours)

Metrics per method and k: MAE, RMSE, median, P90 of the distance (m) between the reconstructed
and the true fix, and the share of reconstructed points within 15 m of a road.

Outputs: report/repair_eval_summary.csv, report/repair_eval_errors.parquet,
         report/repair_params.json, report/figures/repair_*.png
"""
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

import map_matching as mm

HW1 = Path(__file__).resolve().parents[1]
GPS = HW1 / "data" / "processed" / "gps" / "gps_clean.parquet"
REPORT = HW1 / "report"
STUDY_BBOX = (120.25, 22.53, 120.43, 22.80)
MIN_FIXES = 30
PER_DAY = 70             # trips drawn per collection day
TUNE_SHARE = 0.2
KS = (2, 4, 8)
BETAS = (25, 50, 100, 200, 400)
SIGMA_AS = (0.05, 0.1, 0.3, 1.0)
SEED = 7
_net = None


def init_worker():
    global _net
    _net = mm.RoadNetwork()


def select_trips(f):
    w, s, e, n = STUDY_BBOX
    g = f.groupby("trip_id")
    ok = pd.DataFrame({
        "inside": g.apply(lambda d: (d.lon.between(w, e) & d.lat.between(s, n)).all(), include_groups=False),
        "n": g.size(), "max_gap": g.dt_s.max(), "express": g.express.first(), "day": g.gps_time.first().dt.date})
    ok = ok[ok.inside & (ok.n >= MIN_FIXES) & (ok.max_gap <= 90) & ~ok.express]
    picked = ok.groupby("day").sample(n=PER_DAY, random_state=SEED)
    picked = picked.sample(frac=1, random_state=SEED)
    n_tune = int(len(picked) * TUNE_SHARE)
    return picked.index[:n_tune].tolist(), picked.index[n_tune:].tolist(), len(ok)


def keep_mask(n, k):
    keep = np.zeros(n, bool)
    keep[::k] = True
    keep[-1] = True
    return keep


def kalman_rts(t, z, obs, sigma_a, sigma_z):
    """Constant-velocity Kalman filter + Rauch-Tung-Striebel smoother; z is (n, 2), obs marks observed rows."""
    n = len(t)
    H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)
    R = np.eye(2) * sigma_z ** 2
    xf, Pf, xp, Pp, Fs = np.zeros((n, 4)), np.zeros((n, 4, 4)), np.zeros((n, 4)), np.zeros((n, 4, 4)), np.zeros((n, 4, 4))
    first = int(np.argmax(obs))
    x, P = np.array([z[first, 0], z[first, 1], 0, 0]), np.diag([sigma_z ** 2, sigma_z ** 2, 100.0, 100.0])
    for i in range(n):
        if i > 0:
            dt = t[i] - t[i - 1]
            F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], float)
            q = sigma_a ** 2
            Q = q * np.array([[dt ** 4 / 4, 0, dt ** 3 / 2, 0], [0, dt ** 4 / 4, 0, dt ** 3 / 2],
                              [dt ** 3 / 2, 0, dt ** 2, 0], [0, dt ** 3 / 2, 0, dt ** 2]])
            x, P = F @ x, F @ P @ F.T + Q
            Fs[i] = F
        xp[i], Pp[i] = x, P
        if obs[i]:
            S = H @ P @ H.T + R
            K = P @ H.T @ np.linalg.inv(S)
            x = x + K @ (z[i] - H @ x)
            P = (np.eye(4) - K @ H) @ P
        xf[i], Pf[i] = x, P
    xs = xf.copy()
    for i in range(n - 2, -1, -1):
        C = Pf[i] @ Fs[i + 1].T @ np.linalg.inv(Pp[i + 1])
        xs[i] = xf[i] + C @ (xs[i + 1] - xp[i + 1])
    return xs[:, :2]


def reconstruct(trip, k, beta, sigma_z, sigma_a, methods=("linear", "spline", "kalman", "hmm")):
    """Reconstruct the dropped fixes of one trip at sparsity k; returns one row per (method, dropped fix)."""
    t = (trip.gps_time - trip.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    xy = trip[["x", "y"]].to_numpy()
    keep = keep_mask(len(t), k)
    tk, xk = t[keep], xy[keep]
    drop = np.flatnonzero(~keep)
    est = {}
    if "linear" in methods:
        est["linear"] = np.column_stack([np.interp(t[drop], tk, xk[:, 0]), np.interp(t[drop], tk, xk[:, 1])])
    if "spline" in methods:
        est["spline"] = np.column_stack([CubicSpline(tk, xk[:, 0], bc_type="natural")(t[drop]),
                                         CubicSpline(tk, xk[:, 1], bc_type="natural")(t[drop])])
    if "kalman" in methods:
        est["kalman"] = kalman_rts(t, xy, keep, sigma_a, sigma_z)[drop]
    if "hmm" in methods:
        chosen, _ = mm.match(_net, xk[:, 0], xk[:, 1], tk, sigma_z, beta)
        out = []
        for i in drop:
            j = np.searchsorted(tk, t[i]) - 1  # kept fixes j and j+1 bracket t[i]
            c1, c2 = chosen[j], chosen[j + 1]
            if c1 is None or c2 is None:
                out.append((np.interp(t[i], tk, xk[:, 0]), np.interp(t[i], tk, xk[:, 1])))
            else:
                out.append(mm.interpolate_route(_net, c1, tk[j], c2, tk[j + 1], t[i]))
        est["hmm"] = np.array(out)
    # split each error into along-track (wrong timing on the right road) and cross-track (off the
    # path) parts, using the true local direction of travel from the neighbouring true fixes
    u = xy[drop + 1] - xy[drop - 1]
    u = u / np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-9)
    rows = []
    for m, p in est.items():
        e = p - xy[drop]
        err = np.hypot(e[:, 0], e[:, 1])
        along = np.abs(e[:, 0] * u[:, 0] + e[:, 1] * u[:, 1])
        cross = np.abs(e[:, 0] * u[:, 1] - e[:, 1] * u[:, 0])
        for i, er, a, c, (px, py) in zip(drop, err, along, cross, p):
            rows.append((int(trip.trip_id.iloc[0]), k, m, int(i), float(er), float(a), float(c), float(px), float(py)))
    return rows


def run_trip(args):
    trip, k, beta, sigma_z, sigma_a, methods = args
    try:
        return reconstruct(trip, k, beta, sigma_z, sigma_a, methods)
    except Exception as e:  # keep the evaluation going; report the failure
        return [("error", str(e)[:200])]


def run_all(pool, trips, ks, beta, sigma_z, sigma_a, methods):
    jobs = [(t, k, beta, sigma_z, sigma_a, methods) for t in trips for k in ks]
    rows, errors = [], []
    for r in pool.imap_unordered(run_trip, jobs, chunksize=2):
        if r and r[0][0] == "error":
            errors.append(r[0][1])
        else:
            rows.extend(r)
    df = pd.DataFrame(rows, columns=["trip_id", "k", "method", "idx", "err_m", "along_m", "cross_m", "x", "y"])
    return df, errors


def main():
    f = pd.read_parquet(GPS)
    tune_ids, test_ids, n_eligible = select_trips(f)
    by_trip = {tid: g.sort_values("gps_time").reset_index(drop=True) for tid, g in f[f.trip_id.isin(tune_ids + test_ids)].groupby("trip_id")}
    tune, test = [by_trip[i] for i in tune_ids], [by_trip[i] for i in test_ids]
    print(f"eligible trips {n_eligible:,}; tuning {len(tune)}, test {len(test)}", flush=True)

    with Pool(processes=8, initializer=init_worker) as pool:
        # sigma_z from the data (Newson & Krumm): 1.4826 * median distance to the nearest road
        global _net
        _net = mm.RoadNetwork()
        d = [c[0].dist for g in tune for x, y in zip(g.x, g.y) if (c := _net.candidates(x, y))]
        sigma_z = float(1.4826 * np.median(d))
        print(f"sigma_z = {sigma_z:.1f} m (from {len(d):,} tuning fixes)", flush=True)

        # tune beta (HMM) and sigma_a (Kalman) on the tuning set at k = 4
        grid = []
        for beta in BETAS:
            df, _ = run_all(pool, tune, (4,), beta, sigma_z, 0.3, ("hmm",))
            grid.append(("hmm", "beta", beta, df.err_m.mean()))
            print(f"  tune hmm beta={beta}: MAE {df.err_m.mean():.1f} m", flush=True)
        for sa in SIGMA_AS:
            df, _ = run_all(pool, tune, (4,), 50, sigma_z, sa, ("kalman",))
            grid.append(("kalman", "sigma_a", sa, df.err_m.mean()))
            print(f"  tune kalman sigma_a={sa}: MAE {df.err_m.mean():.1f} m", flush=True)
        g = pd.DataFrame(grid, columns=["method", "param", "value", "mae"])
        beta = float(g[g.method == "hmm"].sort_values("mae").value.iloc[0])
        sigma_a = float(g[g.method == "kalman"].sort_values("mae").value.iloc[0])
        params = {"sigma_z_m": round(sigma_z, 2), "beta_m": beta, "sigma_a_ms2": sigma_a, "radius_m": mm.RADIUS_M,
                  "k_candidates": mm.K_CAND, "v_max_kmh": mm.V_MAX_MS * 3.6, "tuning_trips": len(tune),
                  "test_trips": len(test), "grid": g.to_dict("records")}
        (REPORT / "repair_params.json").write_text(json.dumps(params, indent=2), encoding="utf-8")
        print(f"chosen beta={beta}, sigma_a={sigma_a}", flush=True)

        # test set, all methods and sparsity levels
        errs, failures = run_all(pool, test, KS, beta, sigma_z, sigma_a, ("linear", "spline", "kalman", "hmm"))

    # on-road share of reconstructed points
    from shapely import STRtree
    import geopandas as gpd
    tree = STRtree(_net.geom)
    _, dist = tree.query_nearest(gpd.points_from_xy(errs.x, errs.y), return_distance=True, all_matches=False)
    errs["road_dist_m"] = dist
    errs.to_parquet(REPORT / "repair_eval_errors.parquet", index=False)
    summ = errs.groupby(["k", "method"]).agg(n=("err_m", "size"), MAE=("err_m", "mean"),
                                             RMSE=("err_m", lambda e: float(np.sqrt(np.mean(e ** 2)))),
                                             median=("err_m", "median"), P90=("err_m", lambda e: e.quantile(.9)),
                                             along_MAE=("along_m", "mean"), cross_MAE=("cross_m", "mean"),
                                             on_road_15m=("road_dist_m", lambda d: (d <= 15).mean())).round(3).reset_index()
    summ.to_csv(REPORT / "repair_eval_summary.csv", index=False)
    print(summ.to_string(index=False))
    if failures:
        print(f"{len(failures)} trip-runs failed, e.g. {failures[:2]}")


if __name__ == "__main__":
    main()
