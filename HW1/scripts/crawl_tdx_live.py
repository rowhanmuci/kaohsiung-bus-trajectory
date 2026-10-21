"""Poll a TDX real-time endpoint once a minute and keep every raw response.

Datasets (--dataset):
  bus_gps  /v2/Bus/RealTimeByFrequency/City/Kaohsiung    city-bus positions, ~1 fix per bus per minute
  vd       /v2/Road/Traffic/Live/VD/City/Kaohsiung       vehicle detectors: per-lane speed, occupancy,
                                                         volume by vehicle type (S/L/T/M), every minute
Each poll is saved untouched (gzip JSON) so cleaning can be redone later:
  HW1/data/raw/<dataset>_kaohsiung/<YYYYMMDD>/<HHMMSS>.json.gz
  HW1/data/raw/<dataset>_kaohsiung/logs/crawl_<YYYYMMDD>.log

Inside --service-start..--service-end (hours) polls are every --interval seconds,
outside them every --night-interval seconds. One call per minute per dataset stays
well under the 5 calls/min limit of a basic TDX key.

Usage:
  python crawl_tdx_live.py --dataset bus_gps --minutes 45
  python crawl_tdx_live.py --dataset vd --from 05:00 --until 24:00      # daily window (Task Scheduler)
  python crawl_tdx_live.py --dataset bus_gps --stop-at "2026-12-31 23:59"
"""
import argparse
import gzip
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from keepawake import keep_awake
from tdx import TDX

HW1 = Path(__file__).resolve().parents[1]
DATASETS = {
    "bus_gps": "/v2/Bus/RealTimeByFrequency/City/Kaohsiung",
    "vd": "/v2/Road/Traffic/Live/VD/City/Kaohsiung",
}


def clock_today(hhmm):
    """Today's datetime at HH:MM; "24:00" means midnight at the end of today."""
    h, m = map(int, hhmm.split(":"))
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=h, minutes=m)


def window(args, parser):
    """(start, deadline) for this run from --minutes / --stop-at / --from + --until."""
    now = datetime.now()
    if args.minutes is not None:
        return now, now + timedelta(minutes=args.minutes)
    if args.stop_at:
        return now, datetime.strptime(args.stop_at, "%Y-%m-%d %H:%M")
    if args.until:
        return (clock_today(args.from_) if args.from_ else now), clock_today(args.until)
    parser.error("give --minutes, --stop-at or --until")


class Logger:
    def __init__(self, log_dir):
        self.log_dir = log_dir

    def __call__(self, msg):
        now = datetime.now()
        line = f"{now:%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_dir / f"crawl_{now:%Y%m%d}.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_snapshot(raw_dir, payload, fetched_at):
    day_dir = raw_dir / fetched_at.strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{fetched_at:%H%M%S}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def n_records(payload):
    if isinstance(payload, list):
        return len(payload)
    return max((len(v) for v in payload.values() if isinstance(v, list)), default=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=DATASETS, default="bus_gps")
    parser.add_argument("--minutes", type=float, help="run for this many minutes")
    parser.add_argument("--stop-at", help='stop at this local time, e.g. "2026-12-31 23:59"')
    parser.add_argument("--from", dest="from_", help="HH:MM: if started earlier, wait until then (today)")
    parser.add_argument("--until", help='HH:MM: stop at this time today ("24:00" = midnight)')
    parser.add_argument("--interval", type=float, default=60, help="seconds between polls in service hours")
    parser.add_argument("--night-interval", type=float, default=900, help="seconds between polls outside them")
    parser.add_argument("--service-start", type=int, default=5, help="service hours start (hour, local)")
    parser.add_argument("--service-end", type=int, default=24, help="service hours end (hour, local, exclusive)")
    args = parser.parse_args()
    start, deadline = window(args, parser)
    raw_dir = HW1 / "data" / "raw" / f"{args.dataset}_kaohsiung"
    log = Logger(raw_dir / "logs")
    if datetime.now() >= deadline:
        log(f"outside window (deadline {deadline:%H:%M} passed), exiting")
        return
    if datetime.now() < start:
        log(f"waiting until {start:%H:%M}")
        time.sleep((start - datetime.now()).total_seconds())

    keep_awake()
    tdx = TDX()
    polls = errors = 0
    log(f"start {args.dataset}: polling until {deadline:%Y-%m-%d %H:%M}, every {args.interval:.0f}s in "
        f"{args.service_start:02d}-{args.service_end:02d}h, every {args.night_interval:.0f}s otherwise")
    while datetime.now() < deadline:
        started = time.time()
        fetched_at = datetime.now()
        try:
            payload = tdx.get(DATASETS[args.dataset])
            path = save_snapshot(raw_dir, payload, fetched_at)
            polls += 1
            log(f"saved {n_records(payload)} records -> {path.parent.name}/{path.name}")
        except Exception as e:  # keep polling through transient network/API errors
            errors += 1
            log(f"error: {type(e).__name__}: {e}")
        service = args.service_start <= datetime.now().hour < args.service_end
        interval = args.interval if service else args.night_interval
        time.sleep(max(0.0, min(interval - (time.time() - started), (deadline - datetime.now()).total_seconds())))
    log(f"done: {polls} snapshots, {errors} errors")


if __name__ == "__main__":
    main()
