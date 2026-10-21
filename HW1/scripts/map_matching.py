"""HMM map matching (Newson & Krumm, ACM SIGSPATIAL GIS 2009) on the OSM drive network
(kaohsiung_drive; the denser kaohsiung_bus network made paths less accurate, see EXPERIMENT_LOG.md),
plus route-based interpolation between matched points.

Hidden states  : candidate positions = projections of a GPS fix onto road edges within RADIUS_M
                 (at most K_CAND nearest edges; both directions of a two-way road are separate
                 directed edges, so the transition model decides the direction of travel).
Emission       : log p(z_t | c) = -0.5 * (d(z_t, c) / sigma_z)^2      (Gaussian GPS noise)
Transition     : log p(c_t -> c_t+1) = -| ||z_t - z_t+1|| - route(c_t, c_t+1) | / beta
                 route = driving distance on the directed graph (one-way streets respected);
                 transitions faster than V_MAX_MS or not reachable within the search cutoff = -inf
Decoding       : Viterbi in log space. Up to MAX_SKIP consecutive fixes without candidates
                 (outliers) are skipped and the chain continues across them. If no transition is
                 possible, or the run without candidates is longer, the chain is broken and decoding
                 restarts at the next fix (breaks are reported).
Interpolation  : between two matched fixes the bus is assumed to drive the shortest route at a
                 constant speed, so a time t maps to the point at fraction (t - t_i) / (t_i+1 - t_i)
                 of the route length.

All geometry is in EPSG:3826 (TWD97 / TM2, metres).
"""
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.ops import substring

HW1 = Path(__file__).resolve().parents[1]
GRAPHML = HW1 / "data" / "static" / "osm" / "kaohsiung_drive.graphml"  # routing network (see build_osm_network.py)
BUS_EDGES = HW1 / "data" / "static" / "osm" / "kaohsiung_bus_edges.parquet"  # drive + service + bus-only roads, labels only
METRIC_CRS = "EPSG:3826"
RADIUS_M = 50.0
K_CAND = 5
V_MAX_MS = 40.0  # 144 km/h
MAX_SKIP = 0     # outlier fixes (no road within RADIUS_M) skipped inside a chain; 0 = end the chain (v1/v2 runs)


@dataclass
class Candidate:
    edge: int          # index into RoadNetwork.edges
    offset: float      # metres from the edge start along its geometry
    x: float
    y: float
    dist: float        # metres from the GPS fix


class RoadNetwork:
    def __init__(self, graphml=GRAPHML):
        G = ox.project_graph(ox.load_graphml(graphml), to_crs=METRIC_CRS)
        _, edges = ox.graph_to_gdfs(G, nodes=True, edges=True, fill_edge_geometry=True)
        edges = edges.reset_index()
        self.u = edges["u"].to_numpy()
        self.v = edges["v"].to_numpy()
        self.geom = edges.geometry.to_numpy()
        self.length = np.array([g.length for g in self.geom])
        self.tree = STRtree(self.geom)
        # routing graph: one directed edge per (u, v), the shortest parallel edge
        self.D = nx.DiGraph()
        self.best_edge = {}
        for i, (a, b, L) in enumerate(zip(self.u, self.v, self.length)):
            if (a, b) not in self.best_edge or L < self.length[self.best_edge[(a, b)]]:
                self.best_edge[(a, b)] = i
                self.D.add_edge(a, b, w=L)
        self._sp_cache = {}

    def candidates(self, x, y, radius=RADIUS_M, k=K_CAND):
        p = Point(x, y)
        idx = self.tree.query(p, predicate="dwithin", distance=radius)
        out = []
        for i in idx:
            g = self.geom[i]
            s = g.project(p)
            q = g.interpolate(s)
            out.append(Candidate(int(i), s, q.x, q.y, p.distance(q)))
        out.sort(key=lambda c: c.dist)
        return out[:k]

    def node_dist(self, a, b, cutoff):
        """Shortest driving distance from node a to node b (inf if beyond cutoff)."""
        if a == b:
            return 0.0
        key = (a, round(cutoff, -2))
        if key not in self._sp_cache:
            if len(self._sp_cache) > 2000:  # entries can hold thousands of nodes for long gaps
                self._sp_cache.clear()
            self._sp_cache[key] = nx.single_source_dijkstra_path_length(self.D, a, cutoff=cutoff, weight="w")
        return self._sp_cache[key].get(b, np.inf)

    def route_dist(self, c1, c2, cutoff):
        """Driving distance from candidate c1 to candidate c2."""
        if c1.edge == c2.edge and c2.offset >= c1.offset - 1.0:
            return max(c2.offset - c1.offset, 0.0)
        rest = self.length[c1.edge] - c1.offset
        mid = self.node_dist(self.v[c1.edge], self.u[c2.edge], cutoff)
        return rest + mid + c2.offset

    def route_line(self, c1, c2):
        """Polyline of the shortest drive from c1 to c2 (None if unreachable)."""
        if c1.edge == c2.edge and c2.offset >= c1.offset - 1.0:
            seg = substring(self.geom[c1.edge], c1.offset, max(c2.offset, c1.offset))
            return seg if seg.length > 0 else LineString([(c1.x, c1.y), (c2.x, c2.y)])
        try:
            nodes = nx.shortest_path(self.D, self.v[c1.edge], self.u[c2.edge], weight="w")
        except nx.NetworkXNoPath:
            return None
        coords = list(substring(self.geom[c1.edge], c1.offset, self.length[c1.edge]).coords)
        for a, b in zip(nodes, nodes[1:]):
            coords += list(self.geom[self.best_edge[(a, b)]].coords)[1:]
        coords += list(substring(self.geom[c2.edge], 0, c2.offset).coords)[1:]
        if len(coords) < 2:
            coords = [(c1.x, c1.y), (c2.x, c2.y)]
        return LineString(coords)


def match(net, xs, ys, ts, sigma_z, beta, max_skip=MAX_SKIP):
    """Viterbi map matching of one trajectory.

    xs, ys: metres (EPSG:3826); ts: seconds. Returns a list with, per fix, the chosen
    Candidate or None (no candidate within reach), and the number of chain breaks.
    A run of at most max_skip fixes without candidates (outliers) is skipped and the chain
    continues across it (transition from the last fix before to the first fix after), as in
    Newson & Krumm; a longer run ends the chain. max_skip=0 ends the chain at every such fix.
    """
    cands = [net.candidates(x, y) for x, y in zip(xs, ys)]
    n = len(xs)
    chosen = [None] * n
    breaks = 0
    t = 0
    while t < n:
        while t < n and not cands[t]:
            t += 1
        if t >= n:
            break
        idx = [t]  # fixes decoded in this chain
        score = [np.array([-0.5 * (c.dist / sigma_z) ** 2 for c in cands[t]])]
        back = [None]
        t += 1
        while t < n:
            if not cands[t]:
                j = t
                while j < n and not cands[j]:
                    j += 1
                if j >= n or j - t > max_skip:
                    break
                t = j
            p = idx[-1]
            prev, cur = cands[p], cands[t]
            d_gc = float(np.hypot(xs[t] - xs[p], ys[t] - ys[p]))
            dt = max(ts[t] - ts[p], 1.0)
            cutoff = min(3 * d_gc + 1000.0, V_MAX_MS * dt + 2 * RADIUS_M)
            trans = np.full((len(prev), len(cur)), -np.inf)
            for i, a in enumerate(prev):
                for j, b in enumerate(cur):
                    r = net.route_dist(a, b, cutoff)
                    if np.isfinite(r) and r <= V_MAX_MS * dt + 2 * RADIUS_M:
                        trans[i, j] = -abs(d_gc - r) / beta
            total = score[-1][:, None] + trans
            best_prev = total.argmax(axis=0)
            best = total[best_prev, np.arange(len(cur))]
            if not np.isfinite(best).any():  # chain break: restart decoding here
                breaks += 1
                break
            emis = np.array([-0.5 * (c.dist / sigma_z) ** 2 for c in cur])
            score.append(best + emis)
            back.append(best_prev)
            idx.append(t)
            t += 1
        # backtrack this chain
        j = int(np.argmax(score[-1]))
        for k in range(len(score) - 1, -1, -1):
            chosen[idx[k]] = cands[idx[k]][j]
            if back[k] is not None:
                j = int(back[k][j])
    return chosen, breaks


def interpolate_route(net, c1, t1, c2, t2, t):
    """Position at time t (t1 <= t <= t2) driving the shortest route from c1 to c2."""
    line = net.route_line(c1, c2)
    f = (t - t1) / (t2 - t1) if t2 > t1 else 0.0
    if line is None:
        return c1.x + f * (c2.x - c1.x), c1.y + f * (c2.y - c1.y)
    p = line.interpolate(f * line.length)
    return p.x, p.y
