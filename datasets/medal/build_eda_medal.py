"""/eda on the Medal clips table: one SPEC → one executed notebook (datasets/medal/out/notebooks/eda_views.ipynb).

    python3 datasets/medal/build_eda_medal.py

Entity = a clip. Anchor metric = storage_mb (data volume is Medal's goal #1). Dims = game, trigger class, trigger name.
Flag = shared within 14 days. Mix = game × trigger class. Time = clips per week by game. Saturation = clips per player.
Pareto = storage by player.
"""
import os
from pathlib import Path

from monaco.eda_build import build_from_spec

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

SPEC = dict(
    company="Medal (synthetic)",
    title="Clips captured Feb 1 – Aug 31 2026 across six games; auto-clipping launched on Rocket League May 7 and Ghost Janitors May 21.",
    setup_code=f"""
DATA = {str(OUT)!r}
clips = pd.read_csv(f'{{DATA}}/clips.csv', parse_dates=['captured_ts', 'deleted_ts', 'shared_ts'])
games = pd.read_csv(f'{{DATA}}/games.csv')
players = pd.read_csv(f'{{DATA}}/players.csv', parse_dates=['signup_date'])
sessions = pd.read_csv(f'{{DATA}}/sessions.csv', parse_dates=['session_date', 'start_ts'])
df = clips.merge(games[['game_id', 'game_name', 'business_model']], on='game_id', how='left')
TABLES = {{'clips': clips, 'sessions': sessions, 'players': players, 'games': games}}
""",
    derive_code="""
df['trigger_name'] = df['trigger_name'].fillna('(hotkey)')
df['shared_14d_flag'] = df['shared_14d'].fillna(0).astype(int)      # censored clips counted as not shared; see structure for the null count
df['kept_14d'] = (1 - df['deleted_14d'].fillna(0)).astype(int)
df['captured_week'] = df['captured_ts'].dt.to_period('W-SUN').dt.start_time
""",
    entity=None,
    entity_label="clip",
    keys={"clips": [["clip_id"]], "sessions": [["session_id"], ["player_id", "game_id", "session_date"]], "players": [["player_id"]]},
    metric="storage_mb",
    metric_label="storage (MB)",
    dims=["game_name", "trigger_class", "trigger_name"],
    flag="shared_14d_flag",
    flag_label="shared off-Medal within 14 days",
    mix=[("game_name", "trigger_class")],
    time=dict(col="captured_ts", freq="W", split="game_name"),
    saturation=[dict(entity="player_id", label="clips per player")],
    pareto=[dict(entity="player_id", value="storage_mb", label="storage by player")],
)

if __name__ == "__main__":
    nb_dir = OUT / "notebooks"
    nb_dir.mkdir(parents=True, exist_ok=True)
    build_from_spec(SPEC, str(nb_dir / "eda_views.ipynb"), workdir=str(nb_dir))
    print("wrote", os.path.relpath(nb_dir / "eda_views.ipynb", HERE))
