# mirror0.py
# -*- coding: utf-8 -*-
"""
Symbolic Recursion Engine — Mirror-0
Author: Lloyd Christopher Smith
"""

from __future__ import annotations

import os
import sys
import time
import random
import re
from collections import deque
from typing import List, Optional, Tuple, Set, Dict, Any

import yaml

from memory import Memory, MemEvent
from observer import Observer
from io_handler import log, divider, show_summary

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


DEFAULT_CFG: Dict[str, Any] = {
    "engine": {
        "seed_path": "seed.txt",
        "memory_events": "memory.jsonl",
        "memory_graph": "graph.json",
        "observer_label": "Mirror-1",
        "max_events": 5000,
    },
    "runtime": {
        "recursion_delay": 0.12,
        "thoughts_min": 3,
        "thoughts_max": 7,
        "insight_chance": 0.55,
        "abstraction_every": 3,
        "max_cycles": 1,
        "autosave_every": 1,
    },
    "symbolic": {
        "max_symbol_len": 32,
        "min_pair_support": 6,
        "max_abs_depth": 2,
        "max_abs_per_100_cycles": 10,
        "repeat_window": 25,
        "explore_chance": 0.28,
        "abs_pick_chance": 0.18,
        "seed_fallback": [
            "symbolic",
            "recursion",
            "origin",
            "mirror",
            "self",
            "loop",
            "pattern",
            "context",
            "relation",
            "memory",
            "difference",
            "boundary",
            "constraint",
            "signal",
            "trace",
            "bind",
            "update",
            "state",
        ],
    },
}

BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{1,64}")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    cfg = DEFAULT_CFG
    if not os.path.exists(path):
        return cfg

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            return cfg
        return deep_merge(cfg, loaded)
    except Exception:
        return cfg


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def norm(s: str, max_symbol_len: int) -> str:
    s = (s or "").strip().lower().replace(" ", "_")
    s = re.sub(r"[^a-z0-9_\-\(\):]", "", s)
    if not s:
        return "void"
    return s[:max_symbol_len]


def bracket(s: str) -> str:
    return f"[{s}]"


def is_abs(s: str) -> bool:
    return s.startswith("abs(")


def abs_depth(s: str) -> int:
    return s.count("abs(")


def canon_pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def extract_symbols(text: str, max_symbol_len: int) -> List[str]:
    out: List[str] = []

    for item in BRACKET_RE.findall(text):
        symbol = norm(item, max_symbol_len)
        if symbol and not symbol.isdigit():
            out.append(symbol)

    if out:
        return out

    for token in TOKEN_RE.findall(text):
        if token.isdigit():
            continue
        symbol = norm(token, max_symbol_len)
        if symbol and not symbol.isdigit():
            out.append(symbol)

    return out


def load_seed(seed_path: str, max_symbol_len: int) -> List[str]:
    try:
        with open(seed_path, "r", encoding="utf-8", errors="ignore") as f:
            items = [line.strip() for line in f if line.strip()]
        items = [norm(x, max_symbol_len) for x in items]
        return [x for x in items if x and not x.isdigit()]
    except Exception:
        return []


def ensure_seed(seed_path: str, seed_fallback: List[str], max_symbol_len: int) -> None:
    if os.path.exists(seed_path):
        return

    ensure_parent(seed_path)
    with open(seed_path, "w", encoding="utf-8") as f:
        cleaned = [norm(x, max_symbol_len) for x in seed_fallback]
        cleaned = [x for x in cleaned if x and not x.isdigit()]
        f.write("\n".join(cleaned) + "\n")


class Mirror0:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

        engine_cfg = cfg["engine"]
        runtime_cfg = cfg["runtime"]
        symbolic_cfg = cfg["symbolic"]

        self.max_symbol_len = int(symbolic_cfg["max_symbol_len"])
        self.min_pair_support = int(symbolic_cfg["min_pair_support"])
        self.max_abs_depth = int(symbolic_cfg["max_abs_depth"])
        self.max_abs_per_100_cycles = int(symbolic_cfg["max_abs_per_100_cycles"])
        self.repeat_window = int(symbolic_cfg["repeat_window"])
        self.explore_chance = float(symbolic_cfg["explore_chance"])
        self.abs_pick_chance = float(symbolic_cfg["abs_pick_chance"])
        self.seed_fallback = list(symbolic_cfg["seed_fallback"])

        self.recursion_delay = float(runtime_cfg["recursion_delay"])
        self.thoughts_min = int(runtime_cfg["thoughts_min"])
        self.thoughts_max = int(runtime_cfg["thoughts_max"])
        self.insight_chance = float(runtime_cfg["insight_chance"])
        self.abstraction_every = int(runtime_cfg["abstraction_every"])

        self.seed_path = str(engine_cfg["seed_path"])
        self.memory_events = str(engine_cfg["memory_events"])
        self.memory_graph = str(engine_cfg["memory_graph"])
        self.observer_label = str(engine_cfg["observer_label"])
        self.max_events = int(engine_cfg["max_events"])

        ensure_seed(self.seed_path, self.seed_fallback, self.max_symbol_len)
        self.seed_cache: List[str] = load_seed(self.seed_path, self.max_symbol_len)

        self.memory = Memory(
            events_path=self.memory_events,
            graph_path=self.memory_graph,
            max_events=self.max_events,
        )
        self.observer = Observer(self.observer_label)

        self.recent = deque(maxlen=self.repeat_window)
        self.abstracted_pairs: Set[Tuple[str, str]] = set()
        self.abs_rate_window = deque(maxlen=100)

    def pick_symbol(self) -> str:
        tops = self.memory.top_symbols(20)
        abstractions = [s for s, _ in tops if is_abs(s) and abs_depth(s) <= self.max_abs_depth]
        primitives = [s for s, _ in tops if not is_abs(s)]

        if self.seed_cache and random.random() < self.explore_chance:
            candidates = [s for s in self.seed_cache if s not in self.recent]
            return random.choice(candidates) if candidates else random.choice(self.seed_cache)

        if abstractions and random.random() < self.abs_pick_chance:
            candidates = [a for a in abstractions if a not in self.recent]
            return random.choice(candidates) if candidates else random.choice(abstractions)

        if primitives:
            candidates = [p for p in primitives if p not in self.recent]
            return random.choice(candidates) if candidates else random.choice(primitives)

        if self.seed_cache:
            return random.choice(self.seed_cache)
        return "origin"

    def top_pairs(self, limit: int = 60) -> List[Tuple[Tuple[str, str], int]]:
        return self.memory.top_pairs(limit)

    def try_abstract(self) -> Optional[str]:
        if sum(self.abs_rate_window) >= self.max_abs_per_100_cycles:
            return None

        for (a, b), weight in self.top_pairs(80):
            a = norm(a, self.max_symbol_len)
            b = norm(b, self.max_symbol_len)
            weight = int(weight)

            if weight < self.min_pair_support:
                continue
            if a == b:
                continue
            if is_abs(a) or is_abs(b):
                continue

            key = canon_pair(a, b)
            if key in self.abstracted_pairs:
                continue

            abs_sym = norm(f"abs({a}_{b})", self.max_symbol_len)
            if abs_depth(abs_sym) > self.max_abs_depth:
                continue

            self.memory.link(abs_sym, a, max(2, weight // 2))
            self.memory.link(abs_sym, b, max(2, weight // 2))

            self.abstracted_pairs.add(key)
            self.abs_rate_window.append(1)

            return f"ABSTRACT {bracket(abs_sym)} := {bracket(a)} * {bracket(b)} (support:{weight})"

        self.abs_rate_window.append(0)
        return None

    def cycle(self, n: int) -> None:
        thoughts = random.randint(self.thoughts_min, self.thoughts_max)
        log(f"Cycle {n} | thoughts: {thoughts}")

        used: List[str] = []

        for _ in range(thoughts):
            symbol = self.pick_symbol()
            context = norm(str(self.observer.context(self.memory)), self.max_symbol_len)

            text = f"{bracket(symbol)} :: {context}"

            symbols = [norm(symbol, self.max_symbol_len)]
            if context and context != "void" and not context.isdigit():
                symbols.append(context)

            event = MemEvent(
                ts=time.time(),
                kind="reflection",
                text=text,
                meta={"symbols": symbols},
            )

            if self.observer.allow(text):
                self.memory.append(event)
                log(text)

                if len(symbols) >= 2:
                    self.memory.link(symbols[0], symbols[1], 1)

            used.append(norm(symbol, self.max_symbol_len))
            self.recent.append(norm(symbol, self.max_symbol_len))

            time.sleep(self.recursion_delay)

        for i in range(len(used) - 1):
            if used[i] != used[i + 1]:
                self.memory.link(used[i], used[i + 1], 1)

        if (n % self.abstraction_every == 0) and (random.random() < self.insight_chance):
            insight = self.try_abstract()
            if insight:
                self.memory.append(
                    MemEvent(
                        time.time(),
                        "insight",
                        insight,
                        {"symbols": extract_symbols(insight, self.max_symbol_len)},
                    )
                )
                log(f"INSIGHT: {insight}")

        show_summary(
            {
                "events": len(self.memory.events),
                "top_symbols": self.memory.top_symbols(8),
            }
        )
        divider("=")

    def save(self) -> None:
        self.memory.save()


def main() -> None:
    cfg = load_config("config.yaml")
    runtime_cfg = cfg["runtime"]

    max_cycles = int(runtime_cfg.get("max_cycles", 1))
    autosave_every = int(runtime_cfg.get("autosave_every", 1))

    engine = Mirror0(cfg)

    for i in range(1, max_cycles + 1):
        engine.cycle(i)
        if autosave_every > 0 and (i % autosave_every == 0):
            engine.save()

    if autosave_every <= 0 or (max_cycles % autosave_every != 0):
        engine.save()


if __name__ == "__main__":
    main()