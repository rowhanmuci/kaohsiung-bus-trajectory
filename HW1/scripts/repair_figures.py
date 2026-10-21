"""Figures for HW1 Part 3 (repair & evaluation).

Colours follow the method everywhere (fixed categorical order, validated reference palette):
  hmm (ours) blue, linear orange, spline aqua, kalman yellow; raw / truth in neutral greys.

Outputs (report/figures/):
  repair_error_by_k.png       MAE / P90 per method and sparsity, along- vs cross-track split
  repair_cdf_k4.png           error CDF per method at k = 4 (one kept fix per 4 minutes)
  repair_example_k4.png       one test trip: truth, kept fixes, linear / spline / HMM reconstruction
  repair_before_after.png     before / after for (1) a single-fix drift spike, (2) a transmission gap filled along the network
  repair_example_k4_panels.png  the example trip, one panel per method, each reconstruction joined to its true fix
  repair_route_validation.png share of reconstructed points / repaired paths on the official route shape
  network_drive_vs_bus_{1,2}.png  one place, two networks: OSM drive vs drive + service + bus-only roads
  route_vs_repair.png         official route shape vs a repaired trip, and a k = 8 reconstruction that leaves the route
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

import map_matching as mm  # noqa: E402
from gps_clean import EXPRESS  # noqa: E402
from repair_eval import STUDY_BBOX, keep_mask  # noqa: E402

HW1 = Path(__file__).resolve().parents[1]
REPORT, FIG = HW1 / "report", HW1 / "report" / "figures"
GPS = HW1 / "data" / "processed" / "gps"
METHODS = ["hmm", "linear", "spline", "kalman"]
LABEL = {"hmm": "HMM map matching + 沿路網補值（本研究）", "linear": "直線內插", "spline": "Cubic spline", "kalman": "Kalman + RTS"}
SHORT = {"hmm": "HMM + 路網", "linear": "直線內插", "spline": "Spline", "kalman": "Kalman"}
COLOR = {"hmm": "#2a78d6", "linear": "#eb6834", "spline": "#1baf7a", "kalman": "#eda100"}
INK, INK2, MUTED, ROAD = "#0b0b0b", "#52514e", "#8a8984", "#d9d8d4"
ROUTE_SHAPE = "#1BAF7A"  # TDX official route shape, a translucent green band so it stands apart from the grey OSM roads
K_LABEL = {2: "每 2 分鐘留 1 點", 4: "每 4 分鐘留 1 點", 8: "每 8 分鐘留 1 點"}

font_manager.fontManager.addfont("C:/Windows/Fonts/msjh.ttc")
plt.rcParams.update({"font.family": "Microsoft JhengHei", "axes.unicode_minus": False, "figure.dpi": 130,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.grid": True, "grid.color": "#ececea", "grid.linewidth": 0.8, "axes.axisbelow": True,
                     "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2})


def error_by_k(summ):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1.3, 1.3, 1]})
    ks = sorted(summ.k.unique())
    width = 0.19

    def grouped(ax, groups, value):
        for j, m in enumerate(METHODS):
            vals = [value(g, m) for g in groups]
            xs = np.arange(len(groups)) + (j - 1.5) * (width + 0.02)
            ax.bar(xs, vals, width, color=COLOR[m], label=SHORT[m], edgecolor="white", linewidth=1)
            if m in ("hmm", "linear"):  # selective direct labels: ours vs the simplest baseline
                for x, v in zip(xs, vals):
                    ax.text(x, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)

    for ax, metric, title in ((axes[0], "MAE", "平均誤差 MAE（公尺）"), (axes[1], "P90", "第 90 百分位誤差（公尺）")):
        grouped(ax, ks, lambda k, m: summ[(summ.k == k) & (summ.method == m)][metric].iloc[0])
        ax.set_xticks(range(len(ks)), [K_LABEL[k] for k in ks])
        ax.set_title(title, fontsize=11, color=INK)
    axes[0].legend(frameon=False, fontsize=9)
    # along- and cross-track parts are |projections| of the error vector, so they are shown side by
    # side (their sum is not the MAE)
    k4 = summ[summ.k == 4].set_index("method")
    grouped(axes[2], ["along_MAE", "cross_MAE"], lambda c, m: k4.loc[m, c])
    axes[2].set_xticks([0, 1], ["沿行進方向\n（時間估錯）", "垂直行進方向\n（偏離道路）"])
    axes[2].set_title("誤差拆解（每 4 分鐘留 1 點，MAE 公尺）", fontsize=11, color=INK)
    fig.suptitle("遮點還原實驗：被遮掉的 GPS 點與還原位置的距離（測試集）", color=INK)
    fig.savefig(FIG / "repair_error_by_k.png", bbox_inches="tight"); plt.close(fig)


def cdf_k4(errs):
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for m in METHODS:
        e = np.sort(errs[(errs.k == 4) & (errs.method == m)].err_m.to_numpy())
        ax.plot(e, np.arange(1, len(e) + 1) / len(e), color=COLOR[m], label=LABEL[m])
    ax.set_xlim(0, 600); ax.set_ylim(0, 1)
    ax.set_xlabel("還原位置與真實 GPS 點的距離（公尺）"); ax.set_ylabel("累積比例")
    ax.set_title("誤差的累積分布（每 4 分鐘留 1 點）", color=INK)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.savefig(FIG / "repair_cdf_k4.png", bbox_inches="tight"); plt.close(fig)


def draw_roads(ax, net, xs, ys, pad=250, color=ROAD, lw=0.8):
    x0, x1, y0, y1 = xs.min() - pad, xs.max() + pad, ys.min() - pad, ys.max() + pad
    idx = net.tree.query(__import__("shapely").box(x0, y0, x1, y1))
    for i in idx:
        gx, gy = net.geom[i].xy
        ax.plot(gx, gy, color=color, lw=lw, zorder=1)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)


def _example_trip(errs, clean):
    """The test trip where HMM beats linear by the largest margin at k = 4 (25-70 fixes), taller than wide
    so that four panels side by side stay readable."""
    m = errs[errs.k == 4].groupby(["trip_id", "method"]).err_m.mean().unstack()
    m = m[(m.linear - m.hmm) > 0].assign(gain=lambda d: d.linear - d.hmm).sort_values("gain", ascending=False)
    for tid in m.index:
        cand = clean[clean.trip_id == tid].sort_values("gps_time").reset_index(drop=True)
        if 25 <= len(cand) <= 70 and 0.4 <= np.ptp(cand.x) / max(np.ptp(cand.y), 1) <= 1.0:
            return cand


def example_k4(errs, clean, net, params):
    trip = _example_trip(errs, clean)
    t = (trip.gps_time - trip.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    xy = trip[["x", "y"]].to_numpy()
    keep = keep_mask(len(t), 4)
    chosen, _ = mm.match(net, xy[keep, 0], xy[keep, 1], t[keep], params["sigma_z_m"], params["beta_m"])
    e = errs[(errs.k == 4) & (errs.trip_id == trip.trip_id.iloc[0])]
    fig, ax = plt.subplots(figsize=(8, 8))
    draw_roads(ax, net, xy[:, 0], xy[:, 1])
    for a, b in zip(chosen, chosen[1:]):
        if a is not None and b is not None:
            line = net.route_line(a, b)
            if line is not None:
                ax.plot(*line.xy, color=COLOR["hmm"], lw=2, alpha=0.6, zorder=2)
    ax.plot(xy[:, 0], xy[:, 1], "o", ms=5, color=MUTED, zorder=3, label="真實 GPS（每 60 秒，被遮掉的當答案）")
    for meth, mk in (("linear", "s"), ("spline", "^"), ("hmm", "o")):
        p = e[e.method == meth]
        ax.plot(p.x, p.y, mk, ms=8, mfc=COLOR[meth], mec="white", mew=1.5, zorder=5,
                label=f"{LABEL[meth]}（MAE {p.err_m.mean():.0f} m）")
    ax.plot(xy[keep, 0], xy[keep, 1], "D", ms=9, color=INK, mec="white", mew=1.5, zorder=6, label="保留的點（每 4 分鐘）")
    ax.set_title(f"還原範例：{trip.route_name.iloc[0]}（{trip.plate.iloc[0]}）{trip.gps_time.iloc[0]:%m/%d %H:%M}，"
                 f"藍線為 HMM 找出的道路路徑", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.01))
    fig.savefig(FIG / "repair_example_k4.png", bbox_inches="tight"); plt.close(fig)


def example_k4_panels(errs, clean, net, params):
    """The same example trip, one panel per method: each reconstructed point joined to its true fix."""
    from matplotlib.lines import Line2D
    trip = _example_trip(errs, clean)
    t = (trip.gps_time - trip.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    xy = trip[["x", "y"]].to_numpy()
    keep = keep_mask(len(t), 4)
    chosen, _ = mm.match(net, xy[keep, 0], xy[keep, 1], t[keep], params["sigma_z_m"], params["beta_m"])
    e = errs[(errs.k == 4) & (errs.trip_id == trip.trip_id.iloc[0])]
    aspect = (np.ptp(xy[:, 0]) + 300) / (np.ptp(xy[:, 1]) + 300)  # map width / height incl. the 150 m pad
    fig, axes = plt.subplots(1, 4, figsize=(16, 4 / aspect + 1.7), gridspec_kw={"wspace": 0.04})
    for ax, m in zip(axes, ["linear", "spline", "kalman", "hmm"]):
        draw_roads(ax, net, xy[:, 0], xy[:, 1], pad=150)
        if m == "hmm":
            for a, b in zip(chosen, chosen[1:]):
                line = net.route_line(a, b) if a is not None and b is not None else None
                if line is not None:
                    ax.plot(*line.xy, color=COLOR["hmm"], lw=2, alpha=0.45, zorder=2)
        p = e[e.method == m].sort_values("idx")
        truth = xy[p.idx.to_numpy()]
        for (tx, ty), (px, py) in zip(truth, p[["x", "y"]].to_numpy()):
            ax.plot([tx, px], [ty, py], color=COLOR[m], lw=1.3, alpha=0.9, zorder=3)
        ax.plot(truth[:, 0], truth[:, 1], "o", ms=5, color=MUTED, zorder=4)
        ax.plot(p.x, p.y, "o", ms=6.5, mfc=COLOR[m], mec="white", mew=1, zorder=5)
        ax.plot(xy[keep, 0], xy[keep, 1], "D", ms=7, color=INK, mec="white", mew=1.2, zorder=6)
        ax.set_title(f"{LABEL[m] if m != 'hmm' else 'HMM + 沿路網補值'}\nMAE {p.err_m.mean():.0f} m", fontsize=12, color=INK)
    handles = [Line2D([], [], ls="", marker="D", ms=7, color=INK, label="保留的點（每 4 分鐘）"),
               Line2D([], [], ls="", marker="o", ms=5, color=MUTED, label="被遮掉的真實 GPS（答案）"),
               Line2D([], [], color=COLOR["hmm"], lw=2, alpha=0.45, label="HMM 找出的道路路徑"),
               Line2D([], [], color=INK2, lw=1.3, label="還原點到答案的誤差（線）")] +               [Line2D([], [], ls="", marker="o", ms=7, mfc=COLOR[m], mec="white", label=f"{SHORT[m]} 還原的點")
               for m in ["linear", "spline", "kalman", "hmm"]]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=11, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle(f"還原範例分開比較：{trip.route_name.iloc[0]}（{trip.plate.iloc[0]}）{trip.gps_time.iloc[0]:%m/%d %H:%M}，"
                 f"每 4 分鐘留 1 點", color=INK, fontsize=13)
    fig.savefig(FIG / "repair_example_k4_panels.png", bbox_inches="tight"); plt.close(fig)


def network_compare(repaired):
    """Same place, two networks: the OSM drive network vs drive + service and bus-only roads (bus network).
    Roads are drawn alike in both panels, so the difference is which roads exist. One figure per place."""
    from matplotlib.lines import Line2D
    import shapely
    drive = gpd.read_parquet(HW1 / "data" / "static" / "osm" / "kaohsiung_drive_edges.parquet").to_crs(mm.METRIC_CRS)
    bus = gpd.read_parquet(mm.BUS_EDGES).to_crs(mm.METRIC_CRS)
    spots = [("中正路、捷西路一帶（橘 20、21、23 路）", 120.3925, 22.622), ("岡燕路、岡山路一帶（紅 69、8506 路）", 120.300, 22.7925)]
    kind_style = {"matched": (COLOR["hmm"], "o", "對到一般道路（matched）"),
                  "offnet": (COLOR["linear"], "o", "附近只有總站／轉運站道路（offnet）"),
                  "unmatched": (INK, "x", "50 m 內沒有任何道路（unmatched）")}
    R = 420
    for n, (name, lon, lat) in enumerate(spots, 1):
        cx, cy = (v[0] for v in _project([lon], [lat]))
        box = shapely.box(cx - R, cy - R, cx + R, cy + R)
        near = repaired[repaired.raw_lon.between(lon - 0.006, lon + 0.006) & repaired.raw_lat.between(lat - 0.006, lat + 0.006)]
        px, py = _project(near.raw_lon, near.raw_lat)
        inside = (abs(px - cx) < R) & (abs(py - cy) < R)
        near, px, py = near[inside], px[inside], py[inside]
        counts = near.kind.value_counts()
        fig, axes = plt.subplots(1, 2, figsize=(13, 7.0), gridspec_kw={"wspace": 0.04})
        for ax, (edges, title) in zip(axes, ((drive, f"一般道路網 drive（{len(drive[drive.intersects(box)])} 條路段）"),
                                             (bus, f"加上總站道路、公車專用道 bus（{len(bus[bus.intersects(box)])} 條路段）"))):
            for g in edges[edges.intersects(box)].geometry:
                ax.plot(*g.xy, color="#6F6E69", lw=1.5, zorder=1, solid_capstyle="round")
            for kind, (col, mk, _) in kind_style.items():
                sel = (near.kind == kind).to_numpy()
                ax.plot(px[sel], py[sel], mk, ms=3.2, color=col, alpha=0.6, zorder=3 if kind == "matched" else 4)
            ax.set_xlim(cx - R, cx + R); ax.set_ylim(cy - R, cy + R); ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
            ax.set_title(title, fontsize=12, color=INK)
        handles = [Line2D([], [], ls="", marker=mk, ms=6, color=col, label=f"{lab} {counts.get(k, 0):,}")
                   for k, (col, mk, lab) in kind_style.items()]
        fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=11, bbox_to_anchor=(0.5, 0.02))
        fig.suptitle(f"{name}：同一個地點，兩種路網", color=INK, fontsize=13, y=0.97)
        fig.savefig(FIG / f"network_drive_vs_bus_{n}.png", bbox_inches="tight"); plt.close(fig)


def route_vs_repair(clean, net, params):
    """Official route shape vs (left) a fully repaired trip and (right) a k = 8 reconstruction leaving the route."""
    from matplotlib.lines import Line2D
    import shapely
    from shapely import Point
    from shapely.ops import substring
    from route_shape_check import load_shapes
    shapes = load_shapes()
    SHAPE, ROADS = ROUTE_SHAPE, "#C9C7C0"

    def own_shape(trip):
        """The part of the trip's own route shape between its first and last fix (no stubs beyond)."""
        shp = shapes[(trip.route_uid.iloc[0], int(trip.direction.iloc[0]))]
        a = shp.project(Point(trip.x.iloc[0], trip.y.iloc[0]))
        b = shp.project(Point(trip.x.iloc[-1], trip.y.iloc[-1]))
        return substring(shp, min(a, b), max(a, b)), abs(b - a) / shp.length

    def draw_shape(ax, shp):
        ax.plot(*shp.xy, color=SHAPE, lw=8, alpha=0.35, zorder=1.5, solid_capstyle="round")

    def path(ax, chosen):
        for a, b in zip(chosen, chosen[1:]):
            line = net.route_line(a, b) if a is not None and b is not None else None
            if line is not None:
                ax.plot(*line.xy, color=COLOR["hmm"], lw=2.2, zorder=3)

    # left: a trip that covers most of one route, whose HMM path follows it while straight chords cut corners
    seg = pd.read_csv(REPORT / "route_shape_paths.csv")
    on_route = (seg.raw_end_dist_m <= 30).groupby(seg.trip_id).mean()
    seg = seg[seg.raw_end_dist_m <= 30]
    agg = seg.assign(w=seg.within_30m * seg.length_m).groupby(["trip_id", "path"]).agg(w=("w", "sum"), L=("length_m", "sum"))
    share = (agg.w / agg.L).unstack()
    L = agg.L.unstack()["hmm"]
    good = share[(share.hmm >= 0.99) & L.between(5000, 14000) & (on_route.reindex(share.index) >= 0.99)]
    good = good.assign(gap=lambda d: d.hmm - d.chord).sort_values("gap", ascending=False)
    def revisits(trip):
        """Does the bus come back to where it was (an out-and-back spur)? Fixes 3+ apart within 40 m."""
        xy = trip[["x", "y"]].to_numpy()
        d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        far_in_time = np.abs(np.arange(len(xy))[:, None] - np.arange(len(xy))[None, :]) >= 3
        return bool((far_in_time & (d < 40)).any())

    for tid in good.index:  # a regular route, covering most of it, compact, never driving the same road twice
        trip_a = clean[clean.trip_id == tid].sort_values("gps_time").reset_index(drop=True)
        if "小黃" in str(trip_a.route_name.iloc[0]) or revisits(trip_a):
            continue
        shp_a, cover = own_shape(trip_a)
        if cover >= 0.8 and 0.6 <= np.ptp(trip_a.x) / max(np.ptp(trip_a.y), 1) <= 1.6:
            break
    sa = share.loc[tid]
    # right: a k = 8 test trip whose reconstructed points leave the route while the true fixes stay on it
    rm = pd.read_parquet(REPORT / "route_shape_masking.parquet")
    off = rm[(rm.k == 8) & (rm.method == "hmm") & (rm.d_truth <= 30) & (rm.d_route > 150)]
    tid_b = off.trip_id.value_counts().index[0]
    trip_b = clean[clean.trip_id == tid_b].sort_values("gps_time").reset_index(drop=True)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.6), gridspec_kw={"wspace": 0.05})
    ax = axes[0]
    ta = (trip_a.gps_time - trip_a.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    chosen, _ = mm.match(net, trip_a.x.to_numpy(), trip_a.y.to_numpy(), ta, params["sigma_z_m"], params["beta_m"])
    draw_roads(ax, net, trip_a.x.to_numpy(), trip_a.y.to_numpy(), pad=200, color=ROADS, lw=0.9)
    draw_shape(ax, shp_a)
    ax.plot(trip_a.x, trip_a.y, "--", color=COLOR["linear"], lw=1.4, zorder=2.5)
    path(ax, chosen)
    miss = np.array([c is None for c in chosen])  # no candidate road within RADIUS_M: kept at the raw position, no path
    ax.plot(trip_a.x[~miss], trip_a.y[~miss], "o", ms=4.5, color=INK2, mec="white", mew=0.8, zorder=4)
    ax.plot(trip_a.x[miss], trip_a.y[miss], "o", ms=7, mfc="white", mec=MUTED, mew=2, zorder=4)
    if miss.any():
        mx, my = trip_a.x[miss].to_numpy(), trip_a.y[miss].to_numpy()
        d = shapely.distance(shapely.points(mx, my), shp_a)
        why = ("這段路（大學橋一帶）在 OSM 標成\nservice / driveway，drive 路網沒有"  # checked on OSM: ways 799115377, 603570581, 799115388
               if (trip_a.route_name.iloc[0], trip_a.plate.iloc[0]) == ("97", "883-V2") else "這段路不在 drive 路網")
        ax.annotate(f"這 {miss.sum()} 點沒有 HMM 路徑：點在官方路線上\n（{d.min():.0f}–{d.max():.0f} m），但{why}\n"
                    f"→ 50 m 內沒有候選道路，保留原位",
                    xy=(mx.mean(), my.mean()), xycoords="data", xytext=(0.36, 0.62), textcoords="axes fraction",
                    fontsize=10.5, color=INK, va="center",
                    bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=MUTED, lw=0.8),
                    arrowprops=dict(arrowstyle="->", color=INK2, lw=1.2, shrinkB=8), zorder=7)
    ax.plot(trip_a.x.iloc[0], trip_a.y.iloc[0], "^", ms=13, color=INK, mec="white", mew=1.5, zorder=6)
    ax.plot(trip_a.x.iloc[-1], trip_a.y.iloc[-1], "s", ms=11, color=INK, mec="white", mew=1.5, zorder=6)
    ax.set_title(f"全量修復：{trip_a.route_name.iloc[0]}（{trip_a.plate.iloc[0]}）{trip_a.gps_time.iloc[0]:%m/%d %H:%M}\n"
                 f"路徑在官方路線 30 m 內（兩端都對到道路的路段）：HMM {sa.hmm:.0%}、直線相連 {sa.chord:.0%}",
                 fontsize=11, color=INK)
    ax = axes[1]
    tb = (trip_b.gps_time - trip_b.gps_time.iloc[0]).dt.total_seconds().to_numpy()
    xy = trip_b[["x", "y"]].to_numpy()
    keep = keep_mask(len(tb), 8)
    chosen, _ = mm.match(net, xy[keep, 0], xy[keep, 1], tb[keep], params["sigma_z_m"], params["beta_m"])
    errs = pd.read_parquet(REPORT / "repair_eval_errors.parquet")
    rec = errs[(errs.k == 8) & (errs.method == "hmm") & (errs.trip_id == tid_b)]
    bad = off[off.trip_id == tid_b].idx.to_numpy()
    cx, cy = xy[bad, 0].mean(), xy[bad, 1].mean()
    span = max(np.ptp(xy[bad, 0]), np.ptp(xy[bad, 1]), 500) / 2 + 350
    draw_roads(ax, net, np.array([cx - span, cx + span]), np.array([cy - span, cy + span]), pad=0, color=ROADS, lw=1.1)
    draw_shape(ax, own_shape(trip_b)[0])
    path(ax, chosen)
    ax.plot(xy[:, 0], xy[:, 1], "o", ms=4.5, color=MUTED, zorder=4)
    ax.plot(rec.x, rec.y, "o", ms=6, mfc=COLOR["hmm"], mec="white", mew=1, zorder=5)
    ax.plot(xy[keep, 0], xy[keep, 1], "D", ms=8, color=INK, mec="white", mew=1.2, zorder=6)
    on_road = float((rec.road_dist_m <= 1).mean()) if "road_dist_m" in rec else float("nan")
    ax.set_title(f"每 8 分鐘留 1 點：{trip_b.route_name.iloc[0]}（{trip_b.plate.iloc[0]}）{trip_b.gps_time.iloc[0]:%m/%d %H:%M}\n"
                 f"HMM 還原的點都在道路上（{on_road:.0%}），但走了最短路徑，不是公車的路線", fontsize=11, color=INK)
    handles = [Line2D([], [], color=SHAPE, lw=8, alpha=0.35, label="TDX 官方路線線形（這趟走過的那段）"),
               Line2D([], [], ls="", marker="^", ms=10, color=INK, label="起點（左）"),
               Line2D([], [], ls="", marker="s", ms=9, color=INK, label="終點（左）"),
               Line2D([], [], color=COLOR["hmm"], lw=2.2, label="HMM 修復的路徑"),
               Line2D([], [], color=COLOR["linear"], lw=1.4, ls="--", label="原始點直線相連（左）"),
               Line2D([], [], ls="", marker="o", ms=5, color=INK2, label="原始 GPS（左）／被遮掉的真實 GPS（右）"),
               Line2D([], [], ls="", marker="o", ms=7, mfc="white", mec=MUTED, mew=2, label="路網外，保留原位（左）"),
               Line2D([], [], ls="", marker="D", ms=7, color=INK, label="保留的點（右）"),
               Line2D([], [], ls="", marker="o", ms=6, color=COLOR["hmm"], label="HMM 還原的點（右）")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=11, bbox_to_anchor=(0.5, -0.07))
    fig.savefig(FIG / "route_vs_repair.png", bbox_inches="tight"); plt.close(fig)


def _project(lon, lat):
    p = gpd.GeoSeries(gpd.points_from_xy(lon, lat), crs="EPSG:4326").to_crs(mm.METRIC_CRS)
    return p.x.to_numpy(), p.y.to_numpy()


def _pair(axes, tr, net, mark, label, tunnels, shape):
    """Before (raw fixes joined by straight lines) / after (repaired points on the network) for one trip window,
    over the trip's TDX official route shape (independent check: HMM never sees it)."""
    import shapely
    from shapely.ops import substring
    tr = tr.sort_values("time")
    raw = tr[tr.raw_lon.notna()]
    rx, ry = _project(raw.raw_lon, raw.raw_lat)
    fx, fy = _project(tr.lon, tr.lat)
    a, b = shape.project(shapely.Point(fx[0], fy[0])), shape.project(shapely.Point(fx[-1], fy[-1]))
    own = substring(shape, min(a, b), max(a, b))  # the part of the route this window covers
    shown = tunnels[tunnels.distance(shapely.MultiPoint(np.c_[fx, fy])) < 60]  # tunnels this trip passes through
    for ax in axes:
        draw_roads(ax, net, np.r_[rx, fx], np.r_[ry, fy], pad=150)
        ax.plot(*own.xy, color=ROUTE_SHAPE, lw=8, alpha=0.35, zorder=1.4, solid_capstyle="round",
                label="TDX 官方路線（HMM 沒用到）")
        for j, g in enumerate(shown.geometry):
            ax.plot(*g.xy, color=INK2, lw=1.6, ls=(0, (3, 2)), zorder=1.5,
                    label=f"隧道（{shown.name.iloc[0]}）" if j == 0 else None)
    axes[0].plot(rx, ry, "-", color=MUTED, lw=1.2, zorder=2)
    axes[0].plot(rx, ry, "o", ms=7, color=INK2, mec="white", mew=1.2, zorder=3, label="原始 GPS（每 60 秒）")
    mark(axes[0], raw, rx, ry)
    axes[0].legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.01))
    axes[0].set_title(f"{label}｜修復前\n{tr.route_name.iloc[0]}（{tr.plate.iloc[0]}）{tr.time.min():%m/%d %H:%M}",
                      fontsize=11, color=INK)
    kinds = tr.kind.to_numpy()
    axes[1].plot(rx, ry, "-", color=MUTED, lw=1, alpha=0.5, zorder=2, label="原始 GPS 軌跡（參考）")
    # the repaired path along the network between consecutive matched fixes (filled points lie on it)
    real = tr[tr.kind != "imputed"]
    rxy = np.c_[_project(real.lon, real.lat)]
    for (a, b), (pa, pb) in zip(zip(real.iloc[:-1].itertuples(), real.iloc[1:].itertuples()), zip(rxy[:-1], rxy[1:])):
        if a.kind != "matched" or b.kind != "matched":
            continue
        ca, cb = _candidate(net, a.edge_u, a.edge_v, *pa), _candidate(net, b.edge_u, b.edge_v, *pb)
        line = net.route_line(ca, cb) if ca and cb else None
        if line is not None:
            axes[1].plot(*line.xy, "-", color=COLOR["hmm"], lw=2, alpha=0.6, zorder=2,
                         label="HMM 路徑（沿路網）" if "HMM 路徑（沿路網）" not in axes[1].get_legend_handles_labels()[1] else None)
    axes[1].plot(fx[kinds == "matched"], fy[kinds == "matched"], "o", ms=7, color=COLOR["hmm"], mec="white", mew=1.2,
                 zorder=3, label="map matching 後的位置")
    kept = np.isin(kinds, ["offnet", "unmatched"])
    if kept.any():
        axes[1].plot(fx[kept], fy[kept], "o", ms=7, mfc="white", mec=MUTED, mew=2, zorder=4,
                     label="路網外，保留原始位置")
    if (kinds == "imputed").any():
        axes[1].plot(fx[kinds == "imputed"], fy[kinds == "imputed"], "o", ms=7, mfc="white", mec=COLOR["hmm"], mew=2,
                     zorder=4, label="沿路網補的點（每 60 秒）")
    axes[1].legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.01))
    imp = kinds == "imputed"
    d = shapely.distance(shapely.points(fx[imp], fy[imp]), shape) if imp.any() else []
    axes[1].set_title(f"{label}｜修復後\n" + ("對到道路上" if kept.any() else "每個點都對到道路上")
                      + (f"；補的 {imp.sum()} 點都在官方路線 {max(max(d), 1):.0f} m 內" if imp.any() else ""),
                      fontsize=11, color=INK)


def _candidate(net, u, v, x, y):
    """Rebuild a map-matching candidate from a repaired fix (its edge u -> v and snapped position)."""
    if pd.isna(u) or (int(u), int(v)) not in net.best_edge:
        return None
    from shapely import Point
    i = net.best_edge[(int(u), int(v))]
    s = net.geom[i].project(Point(x, y))
    q = net.geom[i].interpolate(s)
    return mm.Candidate(i, s, q.x, q.y, 0.0)


def _spike_window(rep):
    """The largest single-fix drift spike that map matching pulls back (30-50 m off road, neighbours on road),
    with a clean +-8 min window (every point matched or imputed)."""
    eda = pd.read_parquet(GPS / "gps_fixes_eda.parquet", columns=["plate", "gps_time", "drift_spike", "road_dist_m"])
    spikes = eda[eda.drift_spike & eda.road_dist_m.between(30, 50)].sort_values("road_dist_m", ascending=False)
    for _, s in spikes.iterrows():
        tr = rep[(rep.plate == s.plate) & rep.time.between(s.gps_time - pd.Timedelta("8min"), s.gps_time + pd.Timedelta("8min"))]
        if len(tr) >= 10 and tr.trip_id.nunique() == 1 and tr.kind.isin(["matched", "imputed"]).all():
            return tr, s


def _gap_window(rep, avoid_xy):
    """A filled gap inside the study area, both ends matched, where the route bends away from the straight chord
    (at least 2 km from avoid_xy, so the two examples show different places)."""
    w, s, e, n = STUDY_BBOX
    city = ~rep.route_name.fillna("").str.contains(EXPRESS)
    tids = rep.loc[(rep.kind == "imputed") & city, "trip_id"].unique()
    sub = rep[rep.trip_id.isin(tids)].sort_values(["trip_id", "time"]).reset_index(drop=True)
    sub["x"], sub["y"] = _project(sub.lon, sub.lat)
    sub["run"] = ((sub.kind != sub.kind.shift()) | (sub.trip_id != sub.trip_id.shift())).cumsum()
    best = None
    for _, g in sub[sub.kind == "imputed"].groupby("run"):
        if len(g) < 2:  # gaps of >= 150 s: at least two filled points
            continue
        i0, i1 = g.index[0] - 1, g.index[-1] + 1
        if i0 < 0 or i1 >= len(sub) or sub.trip_id[i0] != g.trip_id.iloc[0] or sub.trip_id[i1] != g.trip_id.iloc[0]:
            continue
        a, b = sub.loc[i0], sub.loc[i1]
        if a.kind != "matched" or b.kind != "matched" or not (w <= a.lon <= e and s <= a.lat <= n):
            continue
        if np.hypot(a.x - avoid_xy[0], a.y - avoid_xy[1]) < 2000:
            continue
        cx, cy = b.x - a.x, b.y - a.y
        L = np.hypot(cx, cy)
        if L < 400:
            continue
        dev = float(np.max(np.abs(cx * (g.y - a.y) - cy * (g.x - a.x)) / L))  # distance from the straight chord
        if dev <= 400 and (best is None or dev > best[0]):
            best = (dev, a.trip_id, a.time, b.time)
    _, tid, t0, t1 = best
    tr = rep[(rep.trip_id == tid) & rep.time.between(t0 - pd.Timedelta("4min"), t1 + pd.Timedelta("4min"))]
    return tr, (t0, t1)


def before_after(repaired, net, clean):
    from route_shape_check import load_shapes
    shapes = load_shapes()
    uid = clean.drop_duplicates("trip_id").set_index("trip_id").route_uid
    shape_of = lambda tr: shapes[(uid[tr.trip_id.iloc[0]], int(tr.direction.iloc[0]))]
    edges = gpd.read_parquet(HW1 / "data" / "static" / "osm" / "kaohsiung_bus_edges.parquet").to_crs(mm.METRIC_CRS)
    tunnels = edges[edges.tunnel.astype(str).str.contains("yes", na=False)]
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), gridspec_kw={"hspace": 0.5, "wspace": 0.08})
    tr, s = _spike_window(repaired)

    def mark_spike(ax, raw, rx, ry):
        sp = (raw.time == s.gps_time).to_numpy()
        ax.plot(rx[sp], ry[sp], "o", ms=18, mfc="none", mec="#d03b3b", mew=2, zorder=4,
                label=f"單點飄移（離路 {s.road_dist_m:.0f} m）")

    _pair(axes[0], tr, net, mark_spike, "① GPS 飄移", tunnels, shape_of(tr))
    sx, sy = _project(tr.raw_lon.dropna(), tr.raw_lat.dropna())
    tr, (t0, t1) = _gap_window(repaired, (sx.mean(), sy.mean()))

    def mark_gap(ax, raw, rx, ry):
        i = np.flatnonzero((raw.time == t0).to_numpy())[0]
        ax.plot(rx[i:i + 2], ry[i:i + 2], "--", color="#d03b3b", lw=2.5, zorder=4,
                label=f"斷訊 {(t1 - t0).total_seconds():.0f} 秒（只能直線相連）")

    _pair(axes[1], tr, net, mark_gap, "② 傳輸斷訊", tunnels, shape_of(tr))
    fig.suptitle("修復前後比較（HMM map matching + 沿路網補點）", color=INK, y=0.99)
    fig.savefig(FIG / "repair_before_after.png", bbox_inches="tight"); plt.close(fig)


def route_validation(chk):
    """Share within 30 m of the official route shape: masked-point reconstructions per k, and matched paths."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1.6, 1]})
    ks = (2, 4, 8)
    width = 0.15
    get = lambda check, s: float(chk[(chk.check == check) & (chk.set == s)].within_30m.iloc[0]) * 100
    series = [("truth (masked GPS fix)", "被遮掉的真實 GPS（參考上限）", MUTED)] + [(m, SHORT[m], COLOR[m]) for m in METHODS]
    for j, (key, lab, col) in enumerate(series):
        vals = [get(f"masking k={k}", key) for k in ks]
        xs = np.arange(len(ks)) + (j - 2) * (width + 0.02)
        axes[0].bar(xs, vals, width, color=col, label=lab, edgecolor="white", linewidth=1)
        if key in ("hmm", "linear"):
            for x, v in zip(xs, vals):
                axes[0].text(x, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)
    axes[0].set_xticks(range(len(ks)), [K_LABEL[k] for k in ks]); axes[0].set_ylim(0, 122); axes[0].set_yticks(range(0, 101, 20))
    axes[0].set_ylabel("在官方路線 30 m 內的比例（%）")
    axes[0].set_title("遮點實驗：還原點是否落在公車自己的路線上", fontsize=11, color=INK)
    axes[0].legend(frameon=False, fontsize=8.5, ncol=3, loc="upper center")
    groups = [("全部路段", "all segments"), ("兩端點都在路線上", "both raw ends within 30 m of route")]
    for j, (path, lab, col) in enumerate((("chord", "原始點直線相連", COLOR["linear"]), ("hmm", "HMM 路徑", COLOR["hmm"]))):
        vals = [get("paths", f"{path} ({g})") for _, g in groups]
        xs = np.arange(len(groups)) + (j - 0.5) * 0.36
        axes[1].bar(xs, vals, 0.34, color=col, label=lab, edgecolor="white", linewidth=1)
        for x, v in zip(xs, vals):
            axes[1].text(x, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8, color=INK2)
    axes[1].set_xticks(range(len(groups)), [g for g, _ in groups]); axes[1].set_ylim(0, 118)
    axes[1].set_yticks(range(0, 101, 20))
    axes[1].set_ylabel("路徑長度在官方路線 30 m 內的比例（%）")
    axes[1].set_title("全量修復：兩點之間的路徑（抽 2,000 趟；只算兩端都對到道路的 98.8%）", fontsize=11, color=INK)
    axes[1].legend(frameon=False, fontsize=9, loc="upper center", ncol=2)
    fig.suptitle("用 TDX 官方路線線形驗證（HMM 沒有使用這份資料）", color=INK)
    fig.savefig(FIG / "repair_route_validation.png", bbox_inches="tight"); plt.close(fig)


def main():
    params = json.loads((REPORT / "repair_params.json").read_text(encoding="utf-8"))
    summ = pd.read_csv(REPORT / "repair_eval_summary.csv")
    errs = pd.read_parquet(REPORT / "repair_eval_errors.parquet")
    error_by_k(summ)
    cdf_k4(errs)
    if (REPORT / "route_shape_check.csv").exists():
        route_validation(pd.read_csv(REPORT / "route_shape_check.csv"))
    net = mm.RoadNetwork()
    clean = pd.read_parquet(GPS / "gps_clean.parquet")
    example_k4(errs, clean, net, params)
    example_k4_panels(errs, clean, net, params)
    if (GPS / "gps_repaired.parquet").exists():
        repaired = pd.read_parquet(GPS / "gps_repaired.parquet")
        before_after(repaired, net, clean)
        network_compare(repaired)
    if (REPORT / "route_shape_masking.parquet").exists():
        route_vs_repair(clean, net, params)
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
