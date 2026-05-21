import bisect
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Season:
    episodes: int
    watched: int
    rating: int = 0
    label: str = ""
    p2w: bool = False   # plan-to-watch — not yet started


@dataclass
class Series:
    id: int
    name: str
    kind: str   # "tv" | "anime" | "movie" | "horror"
    seasons: Dict[str, Season]
    alt_names: List[str] = field(default_factory=list)


def _storage_path() -> Path:
    # Frozen exe: sit next to the .exe; dev: sit next to main.py
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return base / "data.json"


class Tracker:
    def __init__(self):
        self.series: List[Series] = []
        self._id_index: Dict[int, Series] = {}   # O(1) lookup by id
        self._is_sorted: bool = False
        self._dirty: bool = False

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _mark_dirty(self):
        self._dirty = True

    # ── Persistence ──────────────────────────────────────────────

    def load(self) -> str:
        path = _storage_path()
        if not path.exists():
            return "empty"
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            self.series = []
            self._id_index = {}
            for item in raw:
                seasons = {k: Season(**v) for k, v in item["seasons"].items()}
                s = Series(
                    id=item["id"], name=item["name"],
                    kind=item.get("kind", "tv"),
                    seasons=seasons,
                    alt_names=item.get("alt_names", []),
                )
                self.series.append(s)
                self._id_index[s.id] = s
            # Detect whether the saved order is already alphabetical
            keys = [s.name.lower() for s in self.series]
            self._is_sorted = all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1))
            self._dirty = False
            return "ok"
        except Exception:
            return "err"

    def save(self):
        """Write data to disk atomically: write to .tmp then rename."""
        path = _storage_path()
        tmp = path.with_suffix(".json.tmp")
        raw = [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "alt_names": s.alt_names,
                "seasons": {
                    k: {"episodes": v.episodes, "watched": v.watched,
                        "rating": v.rating, "label": v.label, "p2w": v.p2w}
                    for k, v in s.seasons.items()
                },
            }
            for s in self.series
        ]
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2)
        os.replace(tmp, path)   # atomic on all major platforms

    def flush_now(self):
        """Synchronous write if dirty. Safe to call from any thread or closeEvent."""
        if self._dirty:
            self._dirty = False   # clear before write so any mutation during write stays dirty
            self.save()

    # ── Sorting & search ─────────────────────────────────────────

    def _name_keys(self) -> List[str]:
        """Lower-cased name list used as the sort key sequence for bisect."""
        return [s.name.lower() for s in self.series]

    def sort_alphabetically(self):
        """Sort all series by name (case-insensitive) and mark dirty."""
        self.series.sort(key=lambda s: s.name.lower())
        self._is_sorted = True
        self._mark_dirty()

    def find_by_name(self, name: str, kind: Optional[str] = None) -> Optional["Series"]:
        """Locate a series by name (and optionally kind).

        Uses binary search (O(log n) comparisons) when the list is known to be
        sorted — e.g. after sort_alphabetically() or a sorted load. Falls back
        to a linear scan otherwise so correctness is never sacrificed.

        When *kind* is given, only a series matching both name and kind is
        returned, allowing same-name entries of different types to coexist.
        """
        target = name.lower()
        if self._is_sorted:
            keys = self._name_keys()
            i = bisect.bisect_left(keys, target)
            # Walk the run of same-name entries (different kinds may be adjacent)
            while i < len(self.series) and self.series[i].name.lower() == target:
                if kind is None or self.series[i].kind == kind:
                    return self.series[i]
                i += 1
            return None
        return next(
            (s for s in self.series
             if s.name.lower() == target and (kind is None or s.kind == kind)),
            None,
        )

    # ── Mutations ────────────────────────────────────────────────

    def add_series(self, name: str, season: int, episodes: int, rating: int, kind: str = "tv", p2w: bool = False, label: str = "") -> "Series":
        s = Series(
            id=int(time.time() * 1000),
            name=name,
            kind=kind,
            seasons={str(season): Season(episodes=episodes, watched=0, rating=rating, label=label, p2w=p2w)},
        )
        self._id_index[s.id] = s
        if self._is_sorted:
            # Insert at the correct alphabetical position to preserve the invariant
            keys = self._name_keys()
            idx = bisect.bisect_left(keys, name.lower())
            self.series.insert(idx, s)
        else:
            self.series.append(s)
        self._mark_dirty()
        return s

    def watch_one(self, series_id: int, season_num: int) -> bool:
        s = self._find(series_id)
        if not s:
            return False
        season = s.seasons.get(str(season_num))
        if not season or season.watched >= season.episodes:
            return False
        season.watched += 1
        self._mark_dirty()
        return season.watched == season.episodes

    def delete_series(self, series_id: int):
        self.series = [s for s in self.series if s.id != series_id]
        self._id_index.pop(series_id, None)
        self._mark_dirty()

    def apply_edit(
        self,
        series_id: int,
        name: str,
        kind: str,
        alt_names: List[str],
        season_edits: Dict[str, dict],
    ) -> Optional[str]:
        s = self._find(series_id)
        if not s:
            return None
        s.name = name
        s.kind = kind
        s.alt_names = alt_names
        for sn_str, data in season_edits.items():
            if sn_str in s.seasons:
                new_eps = data["episodes"]
                # Auto-clamp watched to [0, new_eps] — never error
                new_watched = max(0, min(data.get("watched", s.seasons[sn_str].watched), new_eps))
                s.seasons[sn_str].episodes = new_eps
                s.seasons[sn_str].watched = new_watched
                s.seasons[sn_str].rating = data["rating"]
                s.seasons[sn_str].label = data.get("label", s.seasons[sn_str].label)
        self._mark_dirty()
        return None

    def set_season_p2w(self, series_id: int, season_num: int, p2w: bool) -> bool:
        s = self._find(series_id)
        if not s:
            return False
        season = s.seasons.get(str(season_num))
        if not season:
            return False
        season.p2w = p2w
        self._mark_dirty()
        return True

    def rate_season(self, series_id: int, season_num: int, rating: int) -> bool:
        s = self._find(series_id)
        if not s:
            return False
        season = s.seasons.get(str(season_num))
        if not season:
            return False
        season.rating = rating
        self._mark_dirty()
        return True

    def delete_season(self, series_id: int, season_num: int) -> bool:
        s = self._find(series_id)
        if not s:
            return False
        key = str(season_num)
        if key not in s.seasons:
            return False
        del s.seasons[key]
        self._mark_dirty()
        return True

    def complete_season(self, series_id: int, season_num: int) -> bool:
        s = self._find(series_id)
        if not s:
            return False
        season = s.seasons.get(str(season_num))
        if not season:
            return False
        season.watched = season.episodes
        self._mark_dirty()
        return True

    def _find(self, series_id: int) -> Optional["Series"]:
        """O(1) lookup by id via the id index."""
        return self._id_index.get(series_id)
