import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

RAW = Path("data/raw/statsbomb")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

MINUTES = 91  # 0..90


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _match_score_from_match_obj(m: Dict[str, Any]) -> Tuple[int, int]:
    return int(m.get("home_score", 0)), int(m.get("away_score", 0))


def _final_label_home(home_score: int, away_score: int) -> int:
    # 0=W, 1=D, 2=L from HOME perspective
    if home_score > away_score:
        return 0
    if home_score == away_score:
        return 1
    return 2


def _is_second_half(e: Dict[str, Any]) -> bool:
    period = e.get("period")
    return period in (2, 3, 4)  # StatsBomb: 1=1H,2=2H


def _minute_bucket(e: Dict[str, Any]) -> int:
    m = int(e.get("minute", 0))
    if m < 0:
        return 0
    if m > 90:
        return 90
    return m


def build_states_for_match(match_obj: Dict[str, Any]) -> pd.DataFrame:
    match_id = int(match_obj["match_id"])
    home_team = match_obj["home_team"]["home_team_name"]
    away_team = match_obj["away_team"]["away_team_name"]

    home_final, away_final = _match_score_from_match_obj(match_obj)
    label_home = _final_label_home(home_final, away_final)

    events_path = RAW / "events" / f"{match_id}.json"
    events: List[Dict[str, Any]] = _load_json(events_path)

    # arrays indexed by minute
    home_goals = np.zeros(MINUTES, dtype=np.int32)
    away_goals = np.zeros(MINUTES, dtype=np.int32)

    home_shots = np.zeros(MINUTES, dtype=np.int32)
    away_shots = np.zeros(MINUTES, dtype=np.int32)

    home_passes = np.zeros(MINUTES, dtype=np.int32)
    away_passes = np.zeros(MINUTES, dtype=np.int32)

    home_yellow = np.zeros(MINUTES, dtype=np.int32)
    away_yellow = np.zeros(MINUTES, dtype=np.int32)

    home_red = np.zeros(MINUTES, dtype=np.int32)
    away_red = np.zeros(MINUTES, dtype=np.int32)

    home_subs = np.zeros(MINUTES, dtype=np.int32)
    away_subs = np.zeros(MINUTES, dtype=np.int32)

    # Walk events, bucket by minute
    for e in events:
        team = (e.get("team") or {}).get("name")
        typ = (e.get("type") or {}).get("name")
        minute = _minute_bucket(e)

        is_home_team = team == home_team
        is_away_team = team == away_team

        if typ == "Shot":
            if is_home_team:
                home_shots[minute] += 1
            elif is_away_team:
                away_shots[minute] += 1

            shot = e.get("shot") or {}
            outcome = (shot.get("outcome") or {}).get("name")
            if outcome == "Goal":
                if is_home_team:
                    home_goals[minute] += 1
                elif is_away_team:
                    away_goals[minute] += 1

        elif typ == "Pass":
            if is_home_team:
                home_passes[minute] += 1
            elif is_away_team:
                away_passes[minute] += 1

        elif typ == "Substitution":
            if is_home_team:
                home_subs[minute] += 1
            elif is_away_team:
                away_subs[minute] += 1

        elif typ == "Foul Committed":
            # Cards live under foul_committed.card
            fc = e.get("foul_committed") or {}
            card = (fc.get("card") or {}).get("name")
            if card:
                if "Yellow" in card:
                    if is_home_team:
                        home_yellow[minute] += 1
                    elif is_away_team:
                        away_yellow[minute] += 1
                if "Red" in card:
                    if is_home_team:
                        home_red[minute] += 1
                    elif is_away_team:
                        away_red[minute] += 1

        elif typ == "Card":
            # Some feeds include explicit Card events (defensive handling)
            card = (e.get("card") or {}).get("name")
            if card:
                if "Yellow" in card:
                    if is_home_team:
                        home_yellow[minute] += 1
                    elif is_away_team:
                        away_yellow[minute] += 1
                if "Red" in card:
                    if is_home_team:
                        home_red[minute] += 1
                    elif is_away_team:
                        away_red[minute] += 1

    # cumulative score & subs/cards
    home_score_by_min = np.cumsum(home_goals)
    away_score_by_min = np.cumsum(away_goals)

    home_subs_used = np.cumsum(home_subs)
    away_subs_used = np.cumsum(away_subs)

    home_y = np.cumsum(home_yellow)
    away_y = np.cumsum(away_yellow)
    home_r = np.cumsum(home_red)
    away_r = np.cumsum(away_red)

    def roll5(x: np.ndarray) -> np.ndarray:
        # rolling sum over last 5 minutes inclusive (t-4..t)
        out = np.zeros_like(x)
        for t in range(MINUTES):
            lo = max(0, t - 4)
            out[t] = int(x[lo : t + 1].sum())
        return out

    home_shots_5 = roll5(home_shots)
    away_shots_5 = roll5(away_shots)
    home_passes_5 = roll5(home_passes)
    away_passes_5 = roll5(away_passes)

        # momentum home perspective, then normalize per match for nicer visuals
    shots5_diff = home_shots_5 - away_shots_5
    passes5_diff = home_passes_5 - away_passes_5
    cards_home = home_y + 3 * home_r
    cards_away = away_y + 3 * away_r
    cards_diff = cards_home - cards_away

    m_raw = (
        2.0 * (home_score_by_min - away_score_by_min)
        + 0.6 * shots5_diff
        + 0.2 * passes5_diff
        - 0.8 * cards_diff
    ).astype(float)

    mu = float(m_raw.mean())
    sd = float(m_raw.std()) if float(m_raw.std()) > 1e-6 else 1.0
    m_z = (m_raw - mu) / sd
    m_clamped = np.clip(m_z, -3.0, 3.0) / 3.0  # [-1, 1]


    rows = []
    for t in range(MINUTES):
        rows.append(
            {
                "match_id": match_id,
                "minute": t,
                "home_team": home_team,
                "away_team": away_team,
                "goal_diff_home": int(home_score_by_min[t] - away_score_by_min[t]),
                "shots5_home": int(home_shots_5[t]),
                "shots5_away": int(away_shots_5[t]),
                "passes5_home": int(home_passes_5[t]),
                "passes5_away": int(away_passes_5[t]),
                "yellow_home": int(home_y[t]),
                "yellow_away": int(away_y[t]),
                "red_home": int(home_r[t]),
                "red_away": int(away_r[t]),
                "subs_used_home": int(home_subs_used[t]),
                "subs_used_away": int(away_subs_used[t]),
                "label_home": int(label_home),
                "momentum_home": float(m_clamped[t]),
                "momentum_away": float(-m_clamped[t]),

            }
        )

    return pd.DataFrame(rows)


def main():
    sample_matches_path = RAW / "sample_matches.json"
    matches = _load_json(sample_matches_path)

    frames = []
    for m in matches:
        frames.append(build_states_for_match(m))

    df = pd.concat(frames, ignore_index=True)

    out_path = OUT / "states.parquet"
    df.to_parquet(out_path, index=False)
    print("Wrote", out_path, "rows:", len(df))


if __name__ == "__main__":
    main()
