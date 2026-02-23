import json
import os
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
OUT = Path("data/raw/statsbomb")
OUT.mkdir(parents=True, exist_ok=True)

def dl(url: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    print("downloading", url)
    with urllib.request.urlopen(url) as r:
        path.write_bytes(r.read())

def main():
    # 1) competitions
    dl(f"{BASE}/competitions.json", OUT / "competitions.json")

    comps = json.loads((OUT / "competitions.json").read_text(encoding="utf-8"))

    # Pick a well-known competition+season that usually exists in the repo.
    # If this ever changes, we’ll just pick the first one with matches available.
    target = None
    for c in comps:
        if c.get("competition_name") == "La Liga" and c.get("season_name") == "2015/2016":
            target = c
            break
    if target is None:
        target = comps[0]

    comp_id = target["competition_id"]
    season_id = target["season_id"]

    # 2) matches file
    matches_path = OUT / "matches" / str(comp_id) / f"{season_id}.json"
    dl(f"{BASE}/matches/{comp_id}/{season_id}.json", matches_path)

    matches = json.loads(matches_path.read_text(encoding="utf-8"))

    # 3) pick 3 matches for the sample
    sample_matches = matches[:3]
    (OUT / "sample_matches.json").write_text(json.dumps(sample_matches, indent=2), encoding="utf-8")

    # 4) download events for those matches
    for m in sample_matches:
        mid = m["match_id"]
        ev_path = OUT / "events" / f"{mid}.json"
        dl(f"{BASE}/events/{mid}.json", ev_path)

    print("Done. Sample match_ids:", [m["match_id"] for m in sample_matches])

if __name__ == "__main__":
    main()
