# backend/scripts/fetch_wc2022_pack.py
import json
from pathlib import Path
from urllib.request import urlopen, Request

# World Cup 2022 identifiers commonly used with StatsBomb open data tooling
COMP_ID = 43
SEASON_ID = 106

ROOT = Path(__file__).resolve().parents[1]  # backend/
OUT_DIR = ROOT / "data" / "raw" / "statsbomb"
EVENTS_DIR = OUT_DIR / "events"
EVENTS_DIR.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "DecisionMirror/1.0"}

def get_json(url: str):
    req = Request(url, headers=UA)
    with urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

def gh_raw(url_path: str) -> str:
    # url_path like: data/matches/43/106.json
    return f"https://raw.githubusercontent.com/statsbomb/open-data/master/{url_path}"

def matches_url() -> str:
    return gh_raw(f"data/matches/{COMP_ID}/{SEASON_ID}.json")

def events_url(match_id: int) -> str:
    return gh_raw(f"data/events/{match_id}.json")

def is_hero_match(m: dict) -> bool:
    home = (m.get("home_team") or {}).get("home_team_name", "")
    away = (m.get("away_team") or {}).get("away_team_name", "")
    stage = ((m.get("competition_stage") or {}).get("name")) or ""

    pair = {home, away}

    # Super safe picks: finals + iconic upsets + drama
    if stage == "Final":
        return True

    # Argentina-Netherlands QF (iconic)
    if pair == {"Argentina", "Netherlands"} and "Quarter" in stage:
        return True

    # Japan-Germany (upset)
    if pair == {"Japan", "Germany"}:
        return True

    # Saudi-Argentina (upset)
    if pair == {"Saudi Arabia", "Argentina"}:
        return True
    
    if pair == {"Morocco", "Spain"}:
        return True
    
    if pair == {"Croatia", "Brazil"}:
        return True

    return False

def main():
    ms = get_json(matches_url())

    heroes = [m for m in ms if is_hero_match(m)]
    if not heroes:
        raise SystemExit("No hero matches matched your filters. Adjust is_hero_match().")

    # write sample_matches.json
    out_matches = OUT_DIR / "sample_matches.json"
    out_matches.write_text(json.dumps(heroes, indent=2), encoding="utf-8")
    print("Wrote", out_matches, "matches:", len(heroes))

    # download events for each match
    for m in heroes:
        match_id = int(m["match_id"])
        ep = EVENTS_DIR / f"{match_id}.json"
        data = get_json(events_url(match_id))
        ep.write_text(json.dumps(data), encoding="utf-8")
        print("Wrote", ep)

    print("Done. Next: python scripts/build_states.py")

if __name__ == "__main__":
    main()
