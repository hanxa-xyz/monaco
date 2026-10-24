"""Defensive loader for the Medal data packet.

Accepts a folder of per-tab CSVs (Google Sheets "Download → CSV" names them "<doc> - <tab>.csv"), a
single .xlsx, or a single CSV. It never assumes a layout: every tab is scanned as a raw grid for header
rows (runs of cells that match Legend column names), each header's block runs down until a blank row,
and blocks are classified by their column signature. Stacked blocks, side-by-side blocks, title rows,
offset columns, commas, %, and odd date formats all work. A block whose header matches Legend columns
but can't be classified is kept in P.unknown and reported; free-text regions with no Legend header
(notes, banners) are skipped.

    from medal_parse import load_packet
    P = load_packet("path/to/packet_dir_or.xlsx")
    P.report()                 # what was found — read this out loud first
    P.get("rl", "daily")       # DataFrame or None
    P.ext("gj")                # external CCU/copies/wishlists/DAU merged on date
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Every column name the Legend defines (normalized), plus the obvious keys.
KNOWN = {
    "date", "day", "ds", "week", "game", "game_name", "title",
    "players", "clips_total", "clips_autoclip_native", "clips_autoclip_steam_achievement", "clippers_total",
    "clippers_autoclip", "clips_deleted_distinct", "users_deleting", "clips_shared_distinct", "users_sharing",
    "public_posts_total", "public_posts_autoclip_native", "users_posting",
    "trigger_class", "clips_captured", "deleted_within_14d", "shared_within_14d", "public_posts",
    "trigger_name", "got_autoclip", "returned_wk2", "returned_wk5",
    "clips_autoclip", "delete_events", "share_events", "players_monthly_avg", "clippers_monthly_avg",
    "average_players", "copies_sold", "copies_sold_change", "wishlists", "wishlists_change", "dau", "ccu",
}

# Game registry: aliases matched against tab names / game-column values. Extend live if needed.
# events = known calendar confounds (start, end, label) from public research; add more live with --event.
GAMES = {
    "rl": dict(name="Rocket League", aliases=["rocket"], launch="2026-05-07", model="f2p",
               events=[("2026-05-20", "2026-05-26", "RLCS Paris Major")]),
    "gj": dict(name="Ghost Janitors", aliases=["ghost", "janitor"], launch="2026-05-21", model="paid",
               events=[]),
}

EXTERNAL_KINDS = ("ccu", "copies_sold", "wishlists", "dau", "external")


def norm(s):
    s = str(s).strip().lower()
    s = re.sub(r"[^0-9a-z]+", "_", s).strip("_")
    return {"returned_wk_2": "returned_wk2", "returned_wk_5": "returned_wk5",
            "returned_wk2_returned_wk5": "returned_wk2"}.get(s, s)


def game_of(text):
    t = str(text).lower()
    tokens = set(re.split(r"[^0-9a-z]+", t))
    for key, g in GAMES.items():
        if key in tokens or any(a in t for a in g["aliases"]):
            return key
    return None


# ---------------------------------------------------------------- grid readers
def _pad(rows):
    w = max((len(r) for r in rows), default=0)
    return [[(c or "").strip() for c in r] + [""] * (w - len(r)) for r in rows]


def _read_csv_grid(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return _pad(list(csv.reader(f)))


def _tab_name(path):
    stem = Path(path).stem
    return stem.split(" - ")[-1].strip() if " - " in stem else stem


def read_grids(src):
    """{tab_name: grid(list of list of str)} from a folder, an xlsx, or a csv."""
    src = Path(src)
    if src.is_dir():
        files = sorted([p for p in src.iterdir() if p.suffix.lower() in (".csv", ".tsv", ".xlsx", ".xls")])
        out = {}
        for p in files:
            out.update(read_grids(p))
        return out
    if src.suffix.lower() in (".xlsx", ".xls"):
        sheets = pd.read_excel(src, sheet_name=None, header=None, dtype=str)
        return {name: _pad(df.fillna("").astype(str).values.tolist()) for name, df in sheets.items()}
    return {_tab_name(src): _read_csv_grid(src)}


# ---------------------------------------------------------------- block detection
def _is_number(s):
    return bool(re.fullmatch(r"[-+$]?[\d,]*\.?\d+%?", s.replace(" ", ""))) if s else False


def _runs(row):
    """Contiguous runs of non-empty cells: [(start, end_inclusive)]."""
    runs, start = [], None
    for j, c in enumerate(row + [""]):
        if c and start is None:
            start = j
        elif not c and start is not None:
            runs.append((start, j - 1))
            start = None
    return runs


def _header_score(cells):
    names = [norm(c) for c in cells]
    if any(_is_number(c) for c in cells):
        return 0
    return sum(n in KNOWN for n in names)


def find_blocks(grid):
    """Yield (title, header_row, col_start, col_end, DataFrame of strings)."""
    claimed = set()
    blocks = []
    for i, row in enumerate(grid):
        for a, b in _runs(row):
            cells = row[a:b + 1]
            if (i, a) in claimed or len(cells) < 2 or _header_score(cells) < 2:
                continue
            data, j = [], i + 1
            while j < len(grid) and any(grid[j][a:b + 1]):
                if _header_score(grid[j][a:b + 1]) >= 2:   # next block's header directly below
                    break
                data.append(grid[j][a:b + 1])
                claimed.add((j, a))
                j += 1
            title = ""
            if i > 0 and grid[i - 1][a] and not any(grid[i - 1][a + 1:b + 1]):
                title = grid[i - 1][a]
            df = pd.DataFrame(data, columns=_dedupe([norm(c) or f"col{k}" for k, c in enumerate(cells)]))
            blocks.append((title, i, a, b, df))
    return blocks


def _dedupe(cols):
    seen, out = {}, []
    for c in cols:
        seen[c] = seen.get(c, 0) + 1
        out.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
    return out


# ---------------------------------------------------------------- typing
DATE_COLS = {"date", "day", "ds", "week"}


def _to_num(s):
    s = s.astype(str).str.strip().str.replace(r"[,$\s]", "", regex=True)
    pct = s.str.endswith("%")
    s = s.str.rstrip("%").replace({"": None, "-": None, "—": None, "n/a": None, "NA": None, "nan": None})
    v = pd.to_numeric(s, errors="coerce")
    return v.where(~pct, v / 100)


def coerce(df):
    df = df.copy()
    df = df[df.apply(lambda r: any(str(x).strip() for x in r), axis=1)]
    for c in df.columns:
        col = df[c].astype(str).str.strip()
        nonblank = col[col != ""]
        if c == "got_autoclip":
            df[c] = col.str.lower().map({"true": True, "1": True, "yes": True, "y": True,
                                         "false": False, "0": False, "no": False, "n": False})
            continue
        num = _to_num(col)
        if c in DATE_COLS or (num.notna().mean() < 0.5 and len(nonblank)):
            dt = pd.to_datetime(col, errors="coerce", format="mixed") if c in DATE_COLS or \
                nonblank.str.match(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}").mean() > 0.8 else None
            if dt is not None and dt.notna().mean() > 0.8:
                df[c] = dt.dt.normalize()
                continue
        if len(nonblank) and num[col != ""].notna().mean() > 0.9:
            df[c] = num
        else:
            df[c] = col
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- classification
def classify(cols, title="", tab=""):
    c = set(cols)
    if "trigger_class" in c:
        return "outcomes_14d"
    if "trigger_name" in c:
        return "trigger_breakdown"
    if "got_autoclip" in c:
        return "return_rate"
    if "players_monthly_avg" in c or ("clips_autoclip" in c and ("game" in c or "title" in c)):
        return "platform"
    if "clips_total" in c and "players" in c:
        return "daily"
    ext = [k for k in ("copies_sold", "wishlists", "dau") if k in c]
    has_ccu = "average_players" in c or "ccu" in c or ("players" in c and "clips_total" not in c)
    if len(ext) + has_ccu >= 2:
        return "external"
    if ext:
        return ext[0]
    if has_ccu:
        return "ccu"
    t = norm(title)
    for k in ("daily", "platform", "ccu", "copies_sold", "wishlists", "dau", "return_rate", "trigger"):
        if k in t:
            return k
    return "unknown"


EXT_RENAME = {"players": "ccu_peak", "ccu": "ccu_peak", "average_players": "ccu_avg"}


@dataclass
class Packet:
    tables: dict = field(default_factory=dict)   # (game, kind) -> DataFrame
    log: list = field(default_factory=list)
    unknown: list = field(default_factory=list)

    def get(self, game, kind):
        return self.tables.get((game, kind))

    def ext(self, game):
        """External tables for a game merged on date (outer)."""
        parts = [df for (g, k), df in self.tables.items() if g == game and k in EXTERNAL_KINDS]
        if not parts:
            return None
        out = None
        for df in parts:
            df = df.rename(columns=EXT_RENAME)
            out = df if out is None else out.merge(df, on="date", how="outer", suffixes=("", "_dup"))
        out = out[[c for c in out.columns if not c.endswith("_dup")]]
        return out.sort_values("date").reset_index(drop=True)

    def games(self):
        return sorted({g for g, k in self.tables if g in GAMES and k == "daily"})

    def report(self):
        print("PARSE REPORT")
        for line in self.log:
            print("  " + line)
        if self.unknown:
            print("UNCLASSIFIED blocks (inspect P.unknown):")
            for tab, title, df in self.unknown:
                print(f"  [{tab}] '{title}' cols={list(df.columns)[:8]} rows={len(df)}")
        expected = [(g, "daily") for g in GAMES] + [(g, "outcomes_14d") for g in GAMES] + \
            [(g, "trigger_breakdown") for g in GAMES] + [(g, "return_rate") for g in GAMES] + [("platform", "platform")]
        missing = [f"{g}/{k}" for g, k in expected if (g, k) not in self.tables]
        if missing:
            print("MISSING (views that need these will skip): " + ", ".join(missing))
        for g in GAMES:
            if self.ext(g) is not None:
                e = self.ext(g)
                print(f"  external[{g}] merged: cols={list(e.columns)} {e['date'].min().date()}→{e['date'].max().date()}")


def _add(P, key, df, where):
    if key in P.tables:                       # same table split across blocks → append rows
        df = pd.concat([P.tables[key], df], ignore_index=True).drop_duplicates()
        where += " (appended)"
    P.tables[key] = df
    rng = ""
    dcol = next((c for c in ("date", "week") if c in df.columns and pd.api.types.is_datetime64_any_dtype(df[c])), None)
    if dcol:
        rng = f" {df[dcol].min().date()}→{df[dcol].max().date()}"
    P.log.append(f"{key[0]}/{key[1]:<18} {df.shape[0]:>5} rows × {df.shape[1]:<2} cols{rng}  ← {where}")


def load_packet(src):
    P = Packet()
    for tab, grid in read_grids(src).items():
        if norm(tab) in ("legend", "top_sheet"):
            continue
        tab_game = game_of(tab)
        is_platform_tab = "platform" in tab.lower()
        is_external_tab = "external" in tab.lower()
        for title, i, a, b, raw in find_blocks(grid):
            df = coerce(raw)
            kind = classify(df.columns, title, tab)
            where = f"[{tab}] row {i + 1} col {a + 1}" + (f" '{title}'" if title else "")
            if kind == "unknown":
                P.unknown.append((tab, title, df))
                continue
            if kind == "daily" and is_external_tab:
                kind = "external"
            if kind == "players_only":
                kind = "ccu"
            gcol = next((c for c in ("game", "game_name", "title") if c in df.columns), None)
            if kind == "platform":
                if gcol and gcol != "game":
                    df = df.rename(columns={gcol: "game"})
                _add(P, ("platform", "platform"), df, where)
                continue
            if gcol and kind not in EXTERNAL_KINDS:  # long table with a game column → split per game
                for val, sub in df.groupby(gcol):
                    g = game_of(val)
                    if g:
                        _add(P, (g, kind), sub.drop(columns=gcol).reset_index(drop=True), where + f" game={val}")
                continue
            g = tab_game or game_of(title) or ("platform" if is_platform_tab else None)
            if g is None:
                P.unknown.append((tab, title, df))
                continue
            _add(P, (g, kind), df, where)
    return P


if __name__ == "__main__":
    import sys
    load_packet(sys.argv[1]).report()
