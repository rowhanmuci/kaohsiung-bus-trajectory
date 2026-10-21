"""Daily quality check of the collections (bus GPS, VD, CCTV raw frames, CCTV online outputs).

GPS / VD:  polls per minute, missed minutes, logged errors, records per poll.
GPS extra: duplicate reports, stale positions, positions outside Kaohsiung, and reported
           Speed > 90 km/h compared with the speed implied by consecutive fixes.
VD extra:  detectors per poll, Status codes, lanes with speed <= 0 and whether they had traffic.
CCTV raw:  per camera frames, effective fps, gaps > 5 s, index rows vs files on disk,
           unreadable JPEGs among the last frames and a random sample, frozen streams
           (runs of byte-identical consecutive frames), resolution changes.
CCTV online: per camera processed frames, gaps > 30 s in counts.csv, bus tracks / crops,
           unreadable crops, keyframes and raw-sample minutes; dropped frames, queue length,
           reconnects and image freezes from the online log.

Usage: python qc_report.py --day 20261016 [--start 10:30 --end 16:00]
"""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

HW1 = Path(__file__).resolve().parents[1]
RAW = HW1 / "data" / "raw"


def in_window(ts, start, end):
    hm = ts.dt.strftime("%H:%M")
    keep = pd.Series(True, index=ts.index)
    if start:
        keep &= hm >= start
    if end:
        keep &= hm < end
    return keep


def poll_summary(folder, day, start, end, label):
    files = sorted((folder / day).glob("*.json.gz"))
    if not files:
        print(f"{label}: no data")
        return []
    t = pd.Series(pd.to_datetime([day + p.name[:6] for p in files], format="%Y%m%d%H%M%S"))
    files = [f for f, k in zip(files, in_window(t, start, end)) if k]
    t = t[in_window(t, start, end)].reset_index(drop=True)
    gaps = t.diff().dt.total_seconds().dropna()
    log = folder / "logs"
    errors = sum(p.read_text(encoding="utf-8").count("error:") for p in log.glob(f"*{day}.log")) if log.exists() else 0
    print(f"{label}: {len(files)} polls {t.min():%H:%M}-{t.max():%H:%M} | max gap {gaps.max():.0f}s | "
          f"missed minutes {(gaps > 90).sum()} | errors in log {errors}")
    return files


def gps_checks(files):
    rows = []
    for p in files:
        for b in json.load(gzip.open(p, "rt", encoding="utf-8")):
            pos = b.get("BusPosition") or {}
            rows.append((p.name[:6], b.get("PlateNumb"), (b.get("RouteName") or {}).get("Zh_tw"), b.get("GPSTime"),
                         pos.get("PositionLon"), pos.get("PositionLat"), b.get("Speed")))
    df = pd.DataFrame(rows, columns=["snap", "plate", "route", "gps", "lon", "lat", "speed"])
    df["gps"] = pd.to_datetime(df["gps"])
    fetched = pd.to_datetime(files[0].parent.name + df["snap"], format="%Y%m%d%H%M%S").dt.tz_localize("Asia/Taipei")
    age = (fetched - df["gps"]).dt.total_seconds()
    # Kaohsiung's full extent incl. the mountain districts (Taoyuan/Namasia reach ~121.05 E, ~23.47 N)
    outside = ~df.lon.between(120.1, 121.1) | ~df.lat.between(22.4, 23.5)
    print(f"  buses/poll {df.groupby('snap').size().min()}-{df.groupby('snap').size().max()} | unique buses {df.plate.nunique()} | "
          f"reports {len(df):,} | duplicate (plate,GPSTime) {df.duplicated(['plate', 'gps']).sum():,} | "
          f"stale >30min {int((age > 1800).sum())} | outside Kaohsiung {int(outside.sum())}")
    u = df.drop_duplicates(["plate", "gps"]).sort_values(["plate", "gps"])
    u = u[~outside.loc[u.index]]
    dx = np.hypot(u.lon.diff() * 102_000, u.lat.diff() * 111_000)
    dt = u.gps.diff().dt.total_seconds()
    same = u.plate.eq(u.plate.shift())
    u["implied_kmh"] = np.where(same & (dt > 0), dx / dt * 3.6, np.nan)
    fast = u[u.speed > 90]
    if len(fast):
        print(f"  Speed > 90 km/h: {len(fast)} reports on {fast.plate.nunique()} buses, routes "
              f"{fast.route.value_counts().head(5).to_dict()}; implied speed from GPS for those reports: "
              f"median {fast.implied_kmh.median():.0f} km/h (p90 {fast.implied_kmh.quantile(.9):.0f})")


def vd_checks(files):
    per_poll, status, lanes, zero_speed, zero_speed_no_traffic = [], {}, 0, 0, 0
    for p in files:
        recs = json.load(gzip.open(p, "rt", encoding="utf-8")).get("VDLives", [])
        per_poll.append(len(recs))
        for r in recs:
            status[r.get("Status")] = status.get(r.get("Status"), 0) + 1
            for lf in r.get("LinkFlows", []):
                for ln in lf.get("Lanes", []):
                    lanes += 1
                    if (ln.get("Speed") or 0) <= 0:
                        zero_speed += 1
                        if sum(v.get("Volume") or 0 for v in ln.get("Vehicles", [])) == 0:
                            zero_speed_no_traffic += 1
    total = sum(status.values())
    print(f"  VDs/poll {min(per_poll)}-{max(per_poll)} | Status share " +
          ", ".join(f"{k}: {v / total:.0%}" for k, v in sorted(status.items(), key=lambda kv: str(kv[0]))) +
          f" | lane-minutes with speed<=0: {zero_speed / lanes:.0%} "
          f"(of those, {zero_speed_no_traffic / max(zero_speed, 1):.0%} had zero volume)")


def online_checks(day, start, end, gap_s=30):
    base = HW1 / "data" / "processed" / "cctv_online" / day
    if not base.exists():
        return
    rows = []
    for d in sorted(base.iterdir()):
        c = pd.read_csv(d / "counts.csv", parse_dates=["fetched_at"])
        c = c[in_window(c.fetched_at, start, end)].sort_values("fetched_at")
        g = c.fetched_at.diff().dt.total_seconds()
        gaps = [(f"{c.fetched_at.iloc[i - 1]:%H:%M:%S}", round(v)) for i, v in enumerate(g) if v > gap_s]
        tr = pd.read_csv(d / "bus_tracks.csv", parse_dates=["first_seen"]) if (d / "bus_tracks.csv").exists() else pd.DataFrame()
        crops = list((d / "crops").glob("*.jpg")) if (d / "crops").exists() else []
        bad = 0
        for f in crops[:: max(1, len(crops) // 40)]:
            try:
                with Image.open(f) as im:
                    im.load()
            except Exception:
                bad += 1
        raw = RAW / "cctv_kaohsiung" / day / d.name
        n_key = len(list((raw / "keyframes").glob("*.jpg"))) if (raw / "keyframes").exists() else 0
        n_sample = 0
        if (raw / "sample" / "index.csv").exists():
            s = pd.read_csv(raw / "sample" / "index.csv", parse_dates=["fetched_at"])
            n_sample = s.fetched_at.dt.floor("min").nunique()
        rows.append({"cam": d.name[-3:], "frames": len(c), "fps": round(len(c) / max(1, (c.fetched_at.max() - c.fetched_at.min()).total_seconds()), 2),
                     "gaps>30s": len(gaps), "gap_list": "; ".join(f"{t}+{s}s" for t, s in gaps[:3]) + (" ..." if len(gaps) > 3 else ""),
                     "bus_tracks": len(tr), "crops": len(crops), "bad_crops": bad, "keyframes": n_key, "sample_min": n_sample})
    t = pd.DataFrame(rows)
    log = RAW / "cctv_kaohsiung" / "logs" / f"online_{day}.log"
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    mins = re.findall(r"processed (\d+) frames .*?queue (\d+), dropped (\d+).*?reconnects (\d+)", text)
    freezes = re.findall(r"(\d+C\d+) image frozen for (\d+)s", text)  # camera ids look like 64000C000103
    fz = pd.DataFrame(freezes, columns=["cam", "s"]).astype({"s": int}) if freezes else pd.DataFrame(columns=["cam", "s"])
    print(f"CCTV online: {len(t)} cameras | frames {t.frames.sum():,} | bus tracks {t.bus_tracks.sum():,} | crops {t.crops.sum():,} "
          f"(unreadable in sample: {int(t.bad_crops.sum())}) | log minutes {len(mins)}, dropped {sum(int(m[2]) for m in mins)}, "
          f"max queue {max((int(m[1]) for m in mins), default=0)}, reconnects {sum(int(m[3]) for m in mins)} | "
          f"freezes >=10s: {len(fz)} (" + ", ".join(f"{k[-3:]}:{v}" for k, v in fz.cam.value_counts().head(4).items()) + ")")
    print(t.to_string(index=False))


def cctv_checks(day, start, end, sample=60):
    rows = []
    for d in sorted((RAW / "cctv_kaohsiung" / day).iterdir()):
        idx = pd.read_csv(d / "index.csv", parse_dates=["fetched_at"])
        n_index, n_files = len(idx), len(list(d.glob("*.jpg")))
        idx = idx[in_window(idx.fetched_at, start, end)].reset_index(drop=True)
        g = idx.fetched_at.diff().dt.total_seconds().dropna()
        span = (idx.fetched_at.max() - idx.fetched_at.min()).total_seconds()
        check = pd.concat([idx.tail(5), idx.sample(min(sample, len(idx)), random_state=0)])
        bad, sizes = 0, set()
        for f in check.file:
            try:
                with Image.open(d / f) as im:
                    sizes.add(im.size)
                    im.load()
            except Exception:
                bad += 1
        # frozen stream: consecutive byte-identical frames, checked on a contiguous 10-minute slice
        sl = idx.iloc[len(idx) // 2: len(idx) // 2 + 2400]
        digests = [hashlib.md5((d / f).read_bytes()).hexdigest() for f in sl.file]
        identical = sum(a == b for a, b in zip(digests, digests[1:]))
        rows.append({"cam": d.name[-3:], "frames": len(idx), "fps": round(len(idx) / span, 2) if span else 0,
                     "gaps>5s": int((g > 5).sum()), "max_gap_s": round(g.max(), 1), "index_vs_files": n_index - n_files,
                     "unreadable": bad, "sizes": len(sizes), "identical_consecutive": f"{identical}/{max(len(digests) - 1, 0)}",
                     "GB": round(idx.bytes.sum() / 1e9, 2)})
    t = pd.DataFrame(rows)
    print(f"CCTV: {len(t)} cameras | frames {t.frames.sum():,} | {t.GB.sum():.1f} GB | cameras with gaps>5s: "
          f"{int((t['gaps>5s'] > 0).sum())} | index/file mismatches: {int((t.index_vs_files != 0).sum())} | "
          f"unreadable JPEGs: {int(t.unreadable.sum())} | resolution changes: {int((t.sizes > 1).sum())}")
    print(t.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--raw-cctv", action="store_true", help="also check raw CCTV frames (slow: hashes files)")
    args = parser.parse_args()
    files = poll_summary(RAW / "bus_gps_kaohsiung", args.day, args.start, args.end, "GPS")
    if files:
        gps_checks(files)
    vd_files = poll_summary(RAW / "vd_kaohsiung", args.day, args.start, args.end, "VD ")
    if vd_files:
        vd_checks(vd_files)
    if args.raw_cctv and (RAW / "cctv_kaohsiung" / args.day).exists():
        cctv_checks(args.day, args.start, args.end)
    online_checks(args.day, args.start, args.end)


if __name__ == "__main__":
    main()
