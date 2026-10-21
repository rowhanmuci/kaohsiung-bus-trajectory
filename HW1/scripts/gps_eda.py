"""Exploratory data analysis of the raw bus-GPS reports (HW1 Part 2).

Reads the flattened raw table (gps_flatten.py) and the OSM network (build_osm_network.py),
measures the data issues below, and writes one figure per issue plus a summary table.

Definitions
  report        one bus entry in one poll (the raw table has one row per report)
  fix           a distinct (plate, gps_time): the same fix is often repeated in later polls
  window        a collection period; gaps are only measured between fixes in the same window
  age           poll_time - gps_time   (how old a position is when we receive it)
  latency       update_time - gps_time (GPS fix -> TDX platform)
  implied speed distance / time between consecutive fixes of the same bus

Issues
  A  transmission gaps: intervals between consecutive fixes vs the nominal 60 s
  B  duplicates and stale positions kept by TDX (up to 2 h)
  C  GPS noise / drift: distance from each fix to the nearest OSM road; jitter while stopped
  D  physical outliers: implied speed jumps, reported vs implied speed, placeholder coordinates
  E  latency of the feed

Outputs: HW1/report/figures/eda_*.png, HW1/report/eda_summary.csv,
         HW1/data/processed/gps/gps_fixes_eda.parquet (fixes with dt, implied speed, road distance)
"""
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from shapely import STRtree  # noqa: E402

HW1 = Path(__file__).resolve().parents[1]
GPS = HW1 / "data" / "processed" / "gps" / "gps_reports_raw.parquet"
OSM = HW1 / "data" / "static" / "osm"
FIG = HW1 / "report" / "figures"
METRIC_CRS = "EPSG:3826"
NOMINAL_S = 60
WINDOWS = [("10/16 Fri", "2026-10-16 10:30", "2026-10-16 16:00"), ("10/17 Sat", "2026-10-17 09:00", "2026-10-17 16:00"),
           ("10/18 Sun", "2026-10-18 06:00", "2026-10-18 21:00"), ("10/19 Mon", "2026-10-19 06:00", "2026-10-19 21:00")]
EXPRESS = r"^E\d|快線|快捷|國道"  # freeway express routes: >90 km/h is real there
PLACEHOLDER = (120.111109, 22.111110)

font_manager.fontManager.addfont("C:/Windows/Fonts/msjh.ttc")
plt.rcParams.update({"font.family": "Microsoft JhengHei", "axes.unicode_minus": False, "figure.dpi": 130, "axes.grid": True, "grid.alpha": 0.3})
summary = []


def note(issue, metric, value, detail=""):
    summary.append({"issue": issue, "metric": metric, "value": value, "detail": detail})
    print(f"[{issue}] {metric}: {value} {detail}")


def window_of(t):
    out = pd.Series(pd.NA, index=t.index, dtype="object")
    for name, a, b in WINDOWS:
        out[(t >= pd.Timestamp(a)) & (t < pd.Timestamp(b))] = name
    return out


def build_fixes(df):
    fixes = df.sort_values("poll_time").drop_duplicates(["plate", "gps_time"]).copy()
    fixes["window"] = window_of(fixes["gps_time"])
    fixes = fixes.dropna(subset=["window"]).sort_values(["plate", "gps_time"])
    pts = gpd.GeoSeries(gpd.points_from_xy(fixes.lon, fixes.lat), crs="EPSG:4326").to_crs(METRIC_CRS)
    fixes["x"], fixes["y"] = pts.x.to_numpy(), pts.y.to_numpy()
    same = fixes.plate.eq(fixes.plate.shift()) & fixes.window.eq(fixes.window.shift())
    fixes["dt_s"] = np.where(same, fixes.gps_time.diff().dt.total_seconds(), np.nan)
    fixes["step_m"] = np.where(same, np.hypot(fixes.x.diff(), fixes.y.diff()), np.nan)
    fixes["implied_kmh"] = np.where(fixes.dt_s > 0, fixes.step_m / fixes.dt_s * 3.6, np.nan)
    fixes["prev_speed"] = np.where(same, fixes.speed.shift(), np.nan)
    fixes["express"] = fixes.route_name.fillna("").str.contains(EXPRESS)
    return fixes


def overview(df, fixes, edges, area):
    # spatial coverage: all fixes (left) and the study area with the OSM network (right)
    area_m = area.to_crs(METRIC_CRS)
    w, s, e, n = area_m.total_bounds
    fig, axes = plt.subplots(1, 2, figsize=(13, 7.5), gridspec_kw={"width_ratios": [1, 1.05]})
    valid = fixes[fixes.lon.between(120.1, 121.1) & fixes.lat.between(22.4, 23.5)]  # drop placeholder / bad coords
    axes[0].scatter(valid.x, valid.y, s=0.05, alpha=0.15, color="#08519c", rasterized=True)
    area_m.boundary.plot(ax=axes[0], color="red", lw=1.2)
    share_in = (fixes.x.between(w, e) & fixes.y.between(s, n)).mean()
    axes[0].set_title(f"全部 {len(fixes):,} 個定位點（紅框：研究範圍，含 {share_in:.0%}）", fontsize=10)
    edges.plot(ax=axes[1], color="#d0d0d0", lw=0.25)
    inside = fixes[(fixes.x.between(w, e)) & (fixes.y.between(s, n))]
    hb = axes[1].hexbin(inside.x, inside.y, gridsize=110, bins="log", cmap="inferno_r", mincnt=1, extent=(w, e, s, n))
    fig.colorbar(hb, ax=axes[1], shrink=0.7, label="定位點數（log）")
    axes[1].set_xlim(w, e); axes[1].set_ylim(s, n)
    axes[1].set_title("研究範圍內的密度（灰線：OSM 路網）", fontsize=10)
    for ax in axes:
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("公車 GPS 的空間涵蓋")
    fig.savefig(FIG / "eda_00_coverage_map.png", bbox_inches="tight"); plt.close(fig)

    # active buses over the day, per collection day
    df = df.assign(age_s=(df.poll_time - df.gps_time).dt.total_seconds(), window=window_of(df.poll_time))
    active = df[df.age_s <= 120].groupby(["window", "poll_time"]).plate.nunique().reset_index()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for name, g in active.groupby("window"):
        tod = g.poll_time.dt.hour + g.poll_time.dt.minute / 60
        ax.plot(tod, g.plate.rolling(5, center=True, min_periods=1).mean(), label=name, lw=1.4)
    ax.set_xlabel("時刻"); ax.set_ylabel("在線公車數（定位在 2 分鐘內）"); ax.set_xticks(range(6, 22))
    ax.set_title("各時段在線公車數：平日與週末、尖峰與離峰"); ax.legend()
    fig.savefig(FIG / "eda_01_active_buses.png", bbox_inches="tight"); plt.close(fig)
    note("overview", "reports / fixes / buses / routes", f"{len(df):,} / {len(fixes):,} / {fixes.plate.nunique()} / {fixes.route_name.nunique()}")
    for name, g in active.groupby("window"):
        note("overview", f"active buses per poll, {name}", f"median {g.plate.median():.0f}, max {g.plate.max()}")


def issue_a_gaps(fixes):
    dt = fixes.dt_s.dropna()
    bins = pd.cut(dt, [0, 45, 90, 150, 900, np.inf], labels=["<45 s（過密）", "45–90 s（正常）", "90–150 s（漏 1 筆）",
                                                         "150 s–15 min（斷訊或停站）", ">15 min（多為休息、收班）"])
    share = bins.value_counts(normalize=True).sort_index()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.3), gridspec_kw={"width_ratios": [1.4, 1], "wspace": 0.45})
    axes[0].hist(dt.clip(upper=600), bins=120, color="#3182bd")
    axes[0].set_yscale("log"); axes[0].axvline(NOMINAL_S, color="r", ls="--", label="標稱 60 s")
    axes[0].set_xlabel("同一台公車相鄰兩次定位的時間差（秒，>600 歸為 600）"); axes[0].set_ylabel("次數（log）"); axes[0].legend()
    axes[1].barh(share.index.astype(str), share.values * 100, color=["#9ecae1", "#31a354", "#fdae6b", "#e6550d", "#a50f15"])
    axes[1].set_xlabel("%"); axes[1].set_xlim(0, 118); axes[1].invert_yaxis()
    counts = bins.value_counts().sort_index()
    for i, (v, c) in enumerate(zip(share.values, counts.values)):
        axes[1].text(v * 100 + 0.8, i, f"{v:.2%}（{c:,}）", va="center", fontsize=9)
    fig.suptitle("問題 A：取樣間隔不規則與傳輸中斷"); fig.savefig(FIG / "eda_A_sampling_gaps.png", bbox_inches="tight"); plt.close(fig)
    note("A gaps", "fix intervals measured", f"{len(dt):,}", f"median {dt.median():.0f}s")
    for k, v in share.items():
        note("A gaps", f"interval {k}", f"{v:.2%}")
    long = fixes[fixes.dt_s > 150]
    note("A gaps", "intervals > 150 s", f"{len(long):,}", f"on {long.plate.nunique()} / {fixes.plate.nunique()} buses")
    # a long interval is only a transmission gap if the bus kept driving the same route: most long ones are
    # layovers at a terminal or the end of a duty (bus did not move, or changed route / direction)
    same_route = fixes.route_uid.eq(fixes.route_uid.shift()) & fixes.direction.eq(fixes.direction.shift())
    moving = long[(long.step_m > 300) & same_route.loc[long.index]]
    note("A gaps", "of which the bus moved > 300 m on the same route (real transmission gaps)", f"{len(moving):,}",
         f"on {moving.plate.nunique()} buses")
    note("A gaps", "intervals > 15 min where the bus did not move > 300 m or changed route (layover / off duty)",
         f"{((fixes.dt_s > 900) & ~((fixes.step_m > 300) & same_route)).sum():,}", f"of {(fixes.dt_s > 900).sum():,}")


def issue_b_duplicates_stale(df, fixes):
    df = df.assign(age_s=(df.poll_time - df.gps_time).dt.total_seconds())
    dup = df.duplicated(["plate", "gps_time"])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3))
    axes[0].hist(df.age_s.clip(lower=1, upper=7200), bins=np.logspace(0, np.log10(7200), 80), color="#756bb1")
    axes[0].set_xscale("log"); axes[0].set_yscale("log")
    for s, lab in [(60, "1 min"), (600, "10 min"), (3600, "1 h"), (7200, "2 h")]:
        axes[0].axvline(s, color="#555", ls=":", lw=0.8); axes[0].text(s, axes[0].get_ylim()[1] * 0.3, lab, rotation=90, fontsize=8)
    axes[0].set_xlabel("收到時，這筆位置已經多舊（poll_time - GPSTime，秒）"); axes[0].set_ylabel("回報數（log）")
    per_poll = df.assign(dup=dup, stale=df.age_s > 600).groupby("poll_time")[["dup", "stale"]].mean() * 100
    per_poll["window"] = window_of(per_poll.index.to_series())
    for i, (name, g) in enumerate(per_poll.groupby("window")):  # one segment per collection day: no lines across nights
        tod = g.index.hour + g.index.minute / 60
        axes[1].plot(tod, g.dup.rolling(15, min_periods=1).mean(), color=f"C{i}", lw=1, label=f"{name} 重複回報 %")
        axes[1].plot(tod, g.stale.rolling(15, min_periods=1).mean(), color=f"C{i}", lw=1, ls=":")
    axes[1].set_xlabel("時刻（實線：重複回報 %；點線：超過 10 分鐘的舊位置 %）")
    axes[1].set_ylabel("%"); axes[1].legend(fontsize=8)
    fig.suptitle("問題 B：重複回報與 TDX 保留的過期位置（最長 2 小時）")
    fig.savefig(FIG / "eda_B_duplicates_stale.png", bbox_inches="tight"); plt.close(fig)
    note("B duplicates/stale", "reports that repeat an earlier fix", f"{dup.mean():.2%}", f"({dup.sum():,})")
    for s in (300, 1800, 3600):
        note("B duplicates/stale", f"reports older than {s // 60} min", f"{(df.age_s > s).mean():.2%}", f"({(df.age_s > s).sum():,})")
    note("B duplicates/stale", "reports with GPSTime after poll time (clock skew)", f"{(df.age_s < -5).sum():,}")


def issue_c_drift(fixes, edges, area):
    # the road network only covers the study area, so road distance is measured inside it only
    w, s, e, n = area.total_bounds
    inside = fixes.lon.between(w, e) & fixes.lat.between(s, n)
    tree = STRtree(edges.geometry.to_numpy())
    pts = gpd.points_from_xy(fixes.x[inside], fixes.y[inside])
    _, dist = tree.query_nearest(pts, return_distance=True, all_matches=False)
    fixes["in_study_area"] = inside
    fixes["road_dist_m"] = np.nan
    fixes.loc[inside, "road_dist_m"] = dist
    note("C drift", "fixes inside the study area (OSM network)", f"{inside.mean():.1%}", f"({inside.sum():,})")
    # Note: "jitter while stopped" cannot be measured from the Speed field: it is the instantaneous speed
    # at the sampling moment, so a bus can report 0 at three samples in a row while driving between
    # red lights and stops (see issue D).
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5), gridspec_kw={"width_ratios": [1.2, 1]})
    axes[0].hist(fixes.road_dist_m.clip(upper=200), bins=100, color="#2ca25f")
    axes[0].set_yscale("log"); axes[0].set_xlabel("定位點到最近 OSM 道路的距離（公尺，>200 歸為 200）"); axes[0].set_ylabel("定位點數（log）")
    for d in (20, 50):
        axes[0].axvline(d, color="r", ls=":"); axes[0].text(d, axes[0].get_ylim()[1] * 0.3, f"{d} m", color="r")
    # Off-road fixes are of two kinds: buses parked in depots/terminals (real positions, just not on the
    # drivable network) and single fixes that jump off the road while the bus is driving (GPS drift).
    same_prev = fixes.plate.eq(fixes.plate.shift()) & fixes.window.eq(fixes.window.shift())
    same_next = fixes.plate.eq(fixes.plate.shift(-1)) & fixes.window.eq(fixes.window.shift(-1))
    spike = (fixes.road_dist_m > 30) & same_prev & same_next & (fixes.road_dist_m.shift() < 10) & \
            (fixes.road_dist_m.shift(-1) < 10) & (fixes.implied_kmh > 5)
    fixes["drift_spike"] = spike
    moving = fixes.implied_kmh > 5
    # example: the 15-minute stretch of one bus with the most such spikes
    # example: around the clearest spike (60-150 m off while both neighbours are on the road)
    sp = fixes[spike]
    pick = sp[sp.road_dist_m.between(60, 150)].sort_values("road_dist_m", ascending=False).iloc[0]
    key = (pick.plate, pick.gps_time)
    seg = fixes[(fixes.plate == key[0]) & fixes.gps_time.between(key[1] - pd.Timedelta("6min"), key[1] + pd.Timedelta("6min"))]
    pad = 300
    win = edges.cx[seg.x.min() - pad:seg.x.max() + pad, seg.y.min() - pad:seg.y.max() + pad]
    win.plot(ax=axes[1], color="#bbb", lw=0.8)
    axes[1].plot(seg.x, seg.y, "-", color="#555", lw=0.8)
    sc = axes[1].scatter(seg.x, seg.y, c=seg.road_dist_m.clip(upper=150), cmap="RdYlGn_r", vmin=0, vmax=150, s=28, zorder=3)
    fig.colorbar(sc, ax=axes[1], shrink=0.8, label="離道路距離（m）")
    axes[1].set_title(f"範例：{seg.route_name.iloc[0]}（{key[0]}）{key[1]:%m/%d %H:%M}，單一點偏離 {pick.road_dist_m:.0f} m", fontsize=10)
    axes[1].set_aspect("equal"); axes[1].set_xticks([]); axes[1].set_yticks([])
    fig.suptitle("問題 C：GPS 雜訊與漂移（定位點偏離道路）")
    fig.savefig(FIG / "eda_C_drift.png", bbox_inches="tight"); plt.close(fig)
    rd = fixes.road_dist_m.dropna()
    for d in (20, 50, 100):
        note("C drift", f"in-area fixes > {d} m from any road", f"{(rd > d).mean():.2%}", f"({(rd > d).sum():,})")
    note("C drift", "median distance to road (in-area fixes)", f"{rd.median():.1f} m")
    far = fixes.road_dist_m > 50
    note("C drift", "fixes > 50 m off-road: share taken while moving (> 5 km/h)", f"{(far & moving).sum() / max(1, far.sum()):.1%}",
         "the rest are mostly buses parked in depots/terminals off the drivable network")
    note("C drift", "single-fix jumps off the road while driving (> 30 m, neighbours < 10 m)", f"{spike.sum():,}",
         f"on {sp.plate.nunique()} buses")


def issue_d_outliers(fixes, df):
    v = fixes.dropna(subset=["implied_kmh"])
    city, expr = v[~v.express], v[v.express]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    axes[0].hist([city.implied_kmh.clip(upper=200), expr.implied_kmh.clip(upper=200)], bins=100, stacked=True,
                 color=["#3182bd", "#fd8d3c"], label=["市區路線", "國道快線（E 線等）"])
    axes[0].set_yscale("log"); axes[0].axvline(100, color="r", ls="--"); axes[0].legend()
    axes[0].set_xlabel("相鄰定位換算出的車速（km/h，>200 歸為 200）"); axes[0].set_ylabel("次數（log）")
    hb = axes[1].hexbin(v.speed, v.implied_kmh.clip(upper=150), gridsize=60, bins="log", cmap="viridis", mincnt=1)
    axes[1].plot([0, 120], [0, 120], "r--", lw=1); fig.colorbar(hb, ax=axes[1], label="log 次數")
    axes[1].set_xlabel("回報的 Speed 欄位（km/h）"); axes[1].set_ylabel("位置換算出的車速（km/h）")
    fig.suptitle("問題 D：物理上不合理的數值（瞬間跳點、回報車速與位置不一致）")
    fig.savefig(FIG / "eda_D_speed_outliers.png", bbox_inches="tight"); plt.close(fig)
    note("D outliers", "city-route fix pairs with implied speed > 100 km/h", f"{(city.implied_kmh > 100).mean():.3%}", f"({(city.implied_kmh > 100).sum():,})")
    note("D outliers", "express-route pairs > 100 km/h (mostly real freeway speed)", f"{(expr.implied_kmh > 100).mean():.2%}", f"({(expr.implied_kmh > 100).sum():,})")
    note("D outliers", "reported Speed > 90 km/h on city routes", f"{(fixes[~fixes.express].speed > 90).sum():,}")
    mismatch = v[(v.dt_s <= 90) & ((v.speed - v.implied_kmh).abs() > 30)]
    note("D outliers", "|reported - implied speed| > 30 km/h (dt <= 90 s)", f"{len(mismatch) / max(1, (v.dt_s <= 90).sum()):.2%}")
    # Speed is the instantaneous speed at the sampling moment, not the average since the last fix
    z = v[v.speed == 0]
    note("D outliers", "fix pairs reporting Speed = 0", f"{len(z) / len(v):.1%}",
         f"of those {(z.implied_kmh > 20).mean():.1%} moved > 20 km/h on average")
    per_bus = v.groupby("plate").agg(n=("speed", "size"), zero=("speed", lambda s: (s == 0).mean()),
                                     moving=("implied_kmh", lambda s: (s > 10).mean()))
    stuck = per_bus[(per_bus.zero > 0.95) & (per_bus.moving > 0.3) & (per_bus.n > 60)]
    note("D outliers", "buses whose Speed is stuck at 0 while moving", f"{len(stuck)}", f"plates {list(stuck.index)}")
    ph = df[np.isclose(df.lon, PLACEHOLDER[0]) & np.isclose(df.lat, PLACEHOLDER[1])]
    note("D outliers", f"placeholder coordinates {PLACEHOLDER}", f"{len(ph):,} reports", f"buses {ph.plate.nunique()}")
    outside = df[~df.lon.between(120.1, 121.1) | ~df.lat.between(22.4, 23.5)]
    note("D outliers", "reports outside Kaohsiung", f"{len(outside):,}")


def issue_e_latency(df):
    lat = (df.update_time - df.gps_time).dt.total_seconds()
    fresh = lat[(df.poll_time - df.gps_time).dt.total_seconds() <= 120]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(fresh.clip(-10, 180), bins=95, color="#636363"); ax.set_yscale("log")
    ax.set_xlabel("UpdateTime - GPSTime（秒）"); ax.set_ylabel("回報數（log）")
    ax.set_title("問題 E：資料延遲（車機定位 → TDX 平台）")
    fig.savefig(FIG / "eda_E_latency.png", bbox_inches="tight"); plt.close(fig)
    note("E latency", "median / p95 latency (fresh reports)", f"{fresh.median():.0f} s / {fresh.quantile(.95):.0f} s")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(GPS)
    edges = gpd.read_parquet(OSM / "kaohsiung_bus_edges.parquet").to_crs(METRIC_CRS)
    area = gpd.read_file(OSM / "study_area.geojson")
    fixes = build_fixes(df)
    overview(df, fixes, edges, area)
    issue_a_gaps(fixes)
    issue_b_duplicates_stale(df, fixes)
    issue_c_drift(fixes, edges, area)
    issue_d_outliers(fixes, df)
    issue_e_latency(df)
    fixes.drop(columns=["x", "y"]).to_parquet(HW1 / "data" / "processed" / "gps" / "gps_fixes_eda.parquet", index=False)
    pd.DataFrame(summary).to_csv(HW1 / "report" / "eda_summary.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
