import re
import xml.etree.ElementTree as ET
from models import Season

_ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12,
}

_SEASON_RE = [
    (re.compile(r"^(.+?)\s+Season\s+(\d+)\s+Part\s+(\d+)$", re.IGNORECASE), "sp"),
    (re.compile(r"^(.+?)\s+(\d+)(?:st|nd|rd|th)\s+Season\s+Part\s+(\d+)$", re.IGNORECASE), "nsp"),
    (re.compile(r"^(.+?)\s+Season\s+(\d+)$", re.IGNORECASE), "s"),
    (re.compile(r"^(.+?)\s+(\d+)(?:st|nd|rd|th)\s+Season$", re.IGNORECASE), "ns"),
]

_TERMINAL_KEYWORDS = {"OVA", "OVAS", "OAD", "OADS", "SPECIALS", "SPECIAL", "LITE", "RECAP"}


def _strip_cdata(text: str) -> str:
    text = text.strip()
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        return text[9:-3]
    return text


def _try_season_regex(title: str):
    """Return (base, season_num, part_num, label) from Season N patterns, or None."""
    for pattern, kind in _SEASON_RE:
        m = pattern.match(title)
        if not m:
            continue
        if kind in ("sp", "nsp"):
            base, s, p = m.group(1).strip(), int(m.group(2)), int(m.group(3))
            return base, s, p, f"Season {s} Part {p}"
        base, s = m.group(1).strip(), int(m.group(2))
        return base, s, 0, ""
    return None


def _suffix_sort_and_label(raw_suffix: str) -> tuple[tuple, str]:
    """Convert raw suffix (with leading space or ': ') into (sort_key, label)."""
    if raw_suffix.startswith(": "):
        return (7, 0, 0), raw_suffix[2:]

    suffix = raw_suffix.lstrip()

    # Pure Arabic number → numeric sequel, no label
    if re.match(r"^\d+$", suffix):
        return (2, int(suffix), 0), ""

    # Roman numeral → numeric sequel, no label
    if suffix.upper() in _ROMAN_TO_INT:
        return (2, _ROMAN_TO_INT[suffix.upper()], 0), ""

    # Part N (arabic)
    m = re.match(r"^Part\s+(\d+)$", suffix, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return (3, n, 0), f"Part {n}"

    # Part I/II/...
    m = re.match(r"^Part\s+([IVXLC]+)$", suffix, re.IGNORECASE)
    if m:
        n = _ROMAN_TO_INT.get(m.group(1).upper(), 99)
        return (3, n, 0), f"Part {m.group(1)}"

    # [the] Movie [N]
    m = re.match(r"^(?:the\s+)?Movie(?:\s+(\d+))?$", suffix, re.IGNORECASE)
    if m:
        n = int(m.group(1)) if m.group(1) else 1
        label = f"Movie {n}" if m.group(1) else "Movie"
        return (4, n, 0), label

    # Known terminal keywords
    if suffix.upper() in _TERMINAL_KEYWORDS:
        return (6, 0, 0), suffix

    # Anything else (Z, GT, ∬, Lite, etc.)
    return (5, 0, 0), suffix


def _build_parent(all_titles: set[str]) -> dict[str, str]:
    """For each title, find the longest other title that is a proper prefix of it
    (matched by ' ' or ': ' separator). Returns a parent map."""
    by_len = sorted(all_titles, key=len)
    parent: dict[str, str] = {}
    for i, title in enumerate(by_len):
        best: str | None = None
        best_len = 0
        for j in range(i):
            cand = by_len[j]
            if title.startswith(cand + " ") or title.startswith(cand + ": "):
                if len(cand) > best_len:
                    best_len = len(cand)
                    best = cand
        if best:
            parent[title] = best
    return parent


def _find_root(title: str, parent: dict[str, str]) -> str:
    """Union-find root with path compression."""
    path = []
    while title in parent:
        path.append(title)
        title = parent[title]
    for t in path:
        parent[t] = title
    return title


def parse_mal_xml(path: str) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    entries = []
    for anime in root.findall("anime"):
        title = _strip_cdata(anime.findtext("series_title") or "")
        entries.append({
            "title": title,
            "episodes": int(anime.findtext("series_episodes") or 0),
            "watched": int(anime.findtext("my_watched_episodes") or 0),
            "score": int(anime.findtext("my_score") or 0),
            "p2w": (anime.findtext("my_status") or "") == "Plan to Watch",
        })
    return entries


def _make_season(entry: dict, label: str) -> Season:
    return Season(
        episodes=entry["episodes"],
        watched=entry["watched"],
        rating=entry["score"],
        label=label,
        p2w=entry["p2w"],
    )


def build_series_ungrouped(entries: list[dict]) -> list[tuple[str, dict]]:
    return [(e["title"], {"1": _make_season(e, "")}) for e in entries]


def build_series_grouped(entries: list[dict]) -> list[tuple[str, dict]]:
    all_titles = {e["title"] for e in entries}
    # Last entry wins when duplicate titles exist (MAL shouldn't produce these)
    entry_map = {e["title"]: e for e in entries}

    parent = _build_parent(all_titles)

    # buckets: lowercased root → list of (sort_key, label, entry, canonical_base)
    buckets: dict[str, list] = {}

    for title, entry in entry_map.items():
        # Structured Season N / Nth Season patterns — no prefix lookup needed
        parsed = _try_season_regex(title)
        if parsed:
            base, season_num, part_num, label = parsed
            key = base.lower()
            buckets.setdefault(key, []).append(((1, season_num, part_num), label, entry, base))
            continue

        # Resolve to root via union-find (handles transitive chains like DB→DBZ→DBZ Kai)
        root = _find_root(title, parent)
        key = root.lower()

        if root == title:
            # This title IS the root — base/standalone entry
            buckets.setdefault(key, []).append(((0, 0, 0), "", entry, title))
        else:
            raw_suffix = title[len(root):]  # includes leading " " or ": "
            sort_key, label = _suffix_sort_and_label(raw_suffix)
            buckets.setdefault(key, []).append((sort_key, label, entry, root))

    result = []
    for items in buckets.values():
        items.sort(key=lambda x: x[0])
        canonical = items[0][3]
        seasons = {str(i): _make_season(entry, label)
                   for i, (_, label, entry, _base) in enumerate(items, 1)}
        result.append((canonical, seasons))

    return result
