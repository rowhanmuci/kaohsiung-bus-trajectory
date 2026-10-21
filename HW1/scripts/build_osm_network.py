"""Download the OSM road network buses can use in the study area (via osmnx) and save it.

Study area = the Kaohsiung urban plain box STUDY_BBOX (about 18 x 30 km). It holds ~88% of
the bus GPS fixes collected on 2026-10-16..18; the rest are long-haul express lines
(E25/E32/E01B... into the mountains, 8042 to Tainan airport). Covering every fix would need a
~6,000 km^2 box, larger than the city itself, so those stretches are left out of map matching.
Networks (--network):
  drive  osmnx network_type="drive": public roads open to cars. It leaves out highway=service and
         roads tagged motorcar=no, i.e. the roads inside bus terminals, MRT transfer stations and
         campuses, and bus-only roads; buses on their official route there were > 50 m from any
         edge (route_shape_check.py), so this network is kept only for comparison.
  bus    (default) "drive" + service roads (without driveways, drive-throughs, parking aisles,
         private and emergency access) + ways open to buses (bus / psv = yes | designated) +
         highway=busway.
The graph is simplified (one edge per road segment between intersections, curvature kept in
`geometry`), and only the largest weakly connected component is kept.

Outputs (HW1/data/static/osm/), <net> = kaohsiung_bus or kaohsiung_drive:
  <net>.graphml           directed MultiDiGraph (u, v, key), for routing / map matching
  <net>_nodes.parquet     GeoParquet, EPSG:4326: osmid, x, y, street_count, geometry
  <net>_edges.parquet     GeoParquet, EPSG:4326: u, v, key, osmid, highway, name, oneway, service,
                          lanes, maxspeed, tunnel, bridge, length (m), geometry
  <net>_summary.json      counts, lengths, share of GPS fixes inside the box
  study_area.geojson      the box used

Road data (c) OpenStreetMap contributors, ODbL.
Usage: python build_osm_network.py [--network bus|drive] [--bbox 120.25 22.53 120.43 22.80]
"""
import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import box

HW1 = Path(__file__).resolve().parents[1]
OUT = HW1 / "data" / "static" / "osm"
GPS = HW1 / "data" / "processed" / "gps" / "gps_reports_raw.parquet"
STUDY_BBOX = (120.25, 22.53, 120.43, 22.80)  # west, south, east, north (WGS84)
_NOT_ROADS = ("abandoned|bridleway|bus_guideway|construction|corridor|cycleway|elevator|escalator|footway|no|path|"
              "pedestrian|planned|platform|proposed|raceway|razed|rest_area|services|steps|track")
BUS_FILTERS = [  # union of Overpass filters (osmnx custom_filter list)
    f'["highway"]["area"!~"yes"]["access"!~"private"]["highway"!~"{_NOT_ROADS}"]["motor_vehicle"!~"no"]'
    f'["motorcar"!~"no"]["service"!~"driveway|drive-through|emergency_access|parking|parking_aisle|private"]',
    *[f'["highway"]["area"!~"yes"]["highway"!~"{_NOT_ROADS}"]["service"!~"parking_aisle"]["{t}"~"yes|designated"]'
      for t in ("bus", "psv")],
    '["highway"="busway"]',
]
OVERPASS = ["https://overpass-api.de/api", "https://overpass.kumi.systems/api", "https://maps.mail.ru/osm/tools/overpass/api"]


def download(bbox, network):
    """graph_from_bbox with retries over several Overpass endpoints (the public ones are often at capacity)."""
    kw = {"network_type": "drive"} if network == "drive" else {"custom_filter": BUS_FILTERS}
    for attempt in range(8):
        ox.settings.overpass_url = OVERPASS[attempt % len(OVERPASS)]
        try:
            return ox.graph_from_bbox(bbox, simplify=True, retain_all=False, **kw)
        except Exception as e:  # noqa: BLE001  server busy / gateway timeout
            wait = 30 * 2 ** (attempt // len(OVERPASS))
            print(f"  {ox.settings.overpass_url}: {str(e)[:80]} -> retry in {wait} s", flush=True)
            time.sleep(wait)
    raise RuntimeError("Overpass unavailable")


def flatten_lists(gdf):
    """osmnx keeps merged attributes as lists (and mixes ints with lists, e.g. osmid);
    store every object column as a string ("a;b" for lists) so Parquet gets one type."""
    for col in gdf.columns:
        if col != "geometry" and gdf[col].dtype == object:
            gdf[col] = gdf[col].apply(lambda v: ";".join(map(str, v)) if isinstance(v, list)
                                      else (None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)))
    return gdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", choices=("bus", "drive"), default="bus")
    parser.add_argument("--bbox", type=float, nargs=4, default=STUDY_BBOX, metavar=("W", "S", "E", "N"))
    args = parser.parse_args()
    west, south, east, north = args.bbox
    name = f"kaohsiung_{args.network}"
    OUT.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OUT / "cache")
    ox.settings.log_console = False

    area = gpd.GeoDataFrame({"name": ["study area"]}, geometry=[box(west, south, east, north)], crs="EPSG:4326")
    area.to_file(OUT / "study_area.geojson", driver="GeoJSON")
    G = download((west, south, east, north), args.network)
    ox.save_graphml(G, OUT / f"{name}.graphml")

    nodes, edges = ox.graph_to_gdfs(G)
    flatten_lists(nodes.reset_index()).to_parquet(OUT / f"{name}_nodes.parquet")
    flatten_lists(edges.reset_index()).to_parquet(OUT / f"{name}_edges.parquet")

    hw = edges["highway"].apply(lambda v: v[0] if isinstance(v, list) else v)
    summary = {
        "network": args.network,
        "bbox_wsen": [west, south, east, north],
        "area_km2": round(area.to_crs("EPSG:3826").area.iloc[0] / 1e6, 1),
        "nodes": len(nodes),
        "edges_directed": len(edges),
        "edge_length_km": round(edges["length"].sum() / 1000, 1),
        "km_by_highway": (edges.assign(hw=hw).groupby("hw")["length"].sum() / 1000).round(1)
                          .sort_values(ascending=False).head(10).to_dict(),
        "oneway_share": round(float(edges["oneway"].astype(bool).mean()), 3),
    }
    if GPS.exists():
        fx = pd.read_parquet(GPS, columns=["plate", "gps_time", "lon", "lat"]).drop_duplicates(["plate", "gps_time"])
        summary["gps_fixes_inside_share"] = round(float((fx.lon.between(west, east) & fx.lat.between(south, north)).mean()), 3)
    (OUT / f"{name}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
