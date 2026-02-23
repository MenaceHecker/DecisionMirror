import json
from pathlib import Path
from typing import Any, Dict, List

def statsbomb_root() -> Path:
    # backend/app/statsbomb.py -> backend/
    return Path(__file__).resolve().parents[1] / "data" / "raw" / "statsbomb"

def load_sample_matches() -> List[Dict[str, Any]]:
    p = statsbomb_root() / "sample_matches.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))

def load_events(match_id: int) -> List[Dict[str, Any]]:
    p = statsbomb_root() / "events" / f"{match_id}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))

def extract_subs(match_id: int) -> List[Dict[str, Any]]:
    events = load_events(match_id)
    subs: List[Dict[str, Any]] = []

    for e in events:
        t = (e.get("type") or {}).get("name")
        if t != "Substitution":
            continue

        # StatsBomb schema:
        # - player (the player being subbed OFF)
        # - substitution.replacement (player coming ON)
        player_off = (e.get("player") or {}).get("name")
        replacement = (((e.get("substitution") or {}).get("replacement")) or {}).get("name")

        subs.append({
            "event_id": e.get("id"),              # UUID string
            "minute": int(e.get("minute", 0)),
            "second": int(e.get("second", 0)),
            "team": (e.get("team") or {}).get("name"),
            "player_off": player_off,
            "player_on": replacement,
            "reason": (e.get("substitution") or {}).get("outcome", {}).get("name")
                      or (e.get("substitution") or {}).get("reason"),
        })

    subs.sort(key=lambda s: (s["minute"], s["second"]))
    return subs
