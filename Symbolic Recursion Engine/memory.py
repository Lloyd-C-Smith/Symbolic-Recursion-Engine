# memory.py
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class MemEvent:
    ts: float
    kind: str
    text: str
    meta: dict


class Memory:
    """
    Disk-friendly, crash-resistant memory store.
    - events: JSONL
    - graph: JSON (plain dict-of-dicts)
    """

    def __init__(self, events_path: str, graph_path: str, max_events: int = 5000):
        self.events_path = events_path
        self.graph_path = graph_path
        self.max_events = max_events

        self.events: List[MemEvent] = []
        self.graph = defaultdict(Counter)

        self._ensure_parent(self.events_path)
        self._ensure_parent(self.graph_path)

        self._load_events()
        self._load_graph()

    def _ensure_parent(self, path: str) -> None:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _load_events(self) -> None:
        if not os.path.exists(self.events_path):
            return

        try:
            with open(self.events_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    self.events.append(MemEvent(**obj))
        except Exception:
            self.events = []

        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def _load_graph(self) -> None:
        if not os.path.exists(self.graph_path):
            return

        try:
            with open(self.graph_path, "r", encoding="utf-8", errors="ignore") as f:
                obj = json.load(f) or {}

            for a, neighbors in obj.items():
                if not isinstance(neighbors, dict):
                    continue
                for b, weight in neighbors.items():
                    try:
                        self.graph[a][b] = int(weight)
                    except Exception:
                        continue
        except Exception:
            self.graph = defaultdict(Counter)

    def append(self, ev: MemEvent) -> None:
        self.events.append(ev)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

        for symbol in ev.meta.get("symbols", []):
            _ = self.graph[symbol]

    def link(self, a: str, b: str, w: int = 1) -> None:
        if not a or not b or a == b:
            return

        try:
            w = int(w)
        except Exception:
            w = 1

        if w <= 0:
            w = 1

        self.graph[a][b] += w
        self.graph[b][a] += w

    def top_symbols(self, n: int) -> List[Tuple[str, int]]:
        counts = Counter()
        for ev in self.events:
            for symbol in ev.meta.get("symbols", []):
                counts[symbol] += 1
        return counts.most_common(n)

    def top_pairs(self, n: int) -> List[Tuple[Tuple[str, str], int]]:
        pairs = Counter()
        for a, neighbors in self.graph.items():
            for b, weight in neighbors.items():
                if a < b:
                    pairs[(a, b)] += int(weight)
        return pairs.most_common(n)

    def _graph_as_plain_dict(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for a, neighbors in self.graph.items():
            out[a] = {b: int(weight) for b, weight in neighbors.items()}
        return out

    def save(self) -> None:
        with open(self.events_path, "w", encoding="utf-8") as f:
            for event in self.events:
                f.write(json.dumps(event.__dict__, ensure_ascii=False) + "\n")

        with open(self.graph_path, "w", encoding="utf-8") as f:
            json.dump(self._graph_as_plain_dict(), f, indent=2, ensure_ascii=False)