from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import app.model_store as model_store
from typing import Dict, Any, Optional
from app.statsbomb import load_sample_matches, extract_subs, load_events


from app.statsbomb import load_sample_matches, extract_subs

app = FastAPI(title="DecisionMirror API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulateRequest(BaseModel):
    match_id: int
    sub_event_id: str
    alt_minute: int


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/matches")
def matches():
    ms = load_sample_matches()
    return {"matches": ms}


@app.get("/matches/{match_id}/subs")
def subs(match_id: int):
    s = extract_subs(match_id)
    return {"match_id": match_id, "subs": s}

@app.get("/matches/{match_id}/turning_points")
def turning_points(match_id: int, top_n: int = 5):
    model, df = model_store.get_model(k=25)

    # build minute -> momentum (home perspective)
    rows = df[df["match_id"] == match_id][["minute", "momentum_home"]]
    if rows.empty:
        return {"match_id": match_id, "turning_points": []}

    mom = {int(r["minute"]): float(r["momentum_home"]) for _, r in rows.iterrows()}

    # tag candidate minutes where something “happened”
    events = load_events(match_id)
    tags_by_min = {}
    for e in events:
        typ = (e.get("type") or {}).get("name")
        minute = max(0, min(90, int(e.get("minute", 0))))

        tag = None
        if typ == "Shot":
            shot = e.get("shot") or {}
            outcome = (shot.get("outcome") or {}).get("name")
            if outcome == "Goal":
                tag = "GOAL"
        elif typ == "Substitution":
            tag = "SUB"
        elif typ in ("Foul Committed", "Card"):
            card = None
            if typ == "Foul Committed":
                fc = e.get("foul_committed") or {}
                card = (fc.get("card") or {}).get("name")
            else:
                card = (e.get("card") or {}).get("name")
            if card:
                if "Red" in card:
                    tag = "RED"
                elif "Yellow" in card:
                    tag = "YELLOW"

        if tag:
            tags_by_min.setdefault(minute, set()).add(tag)

    candidates = []
    for t, tags in tags_by_min.items():
        t0 = max(0, t - 2)
        t1 = min(90, t + 5)
        swing = float(mom.get(t1, 0.0) - mom.get(t0, 0.0))

        # choose primary tag for UI label
        primary = "GOAL" if "GOAL" in tags else "RED" if "RED" in tags else "SUB" if "SUB" in tags else "YELLOW"

        one = (
            "Goal triggered a major momentum swing." if primary == "GOAL" else
            "Red card created a major momentum shock." if primary == "RED" else
            "Substitution aligned with a tactical swing." if primary == "SUB" else
            "Yellow card preceded a momentum change."
        )

        candidates.append({
            "minute": int(t),
            "event_type": primary,
            "swing_home": swing,
            "impact": abs(swing),
            "one_liner": one,
        })

    candidates.sort(key=lambda x: x["impact"], reverse=True)
    picks = candidates[: max(1, min(15, int(top_n)))]

    return {"match_id": match_id, "turning_points": picks}



def _team_perspective_from_home_probs(pW_home: float, pD_home: float, pL_home: float, team_is_home: bool):
    # If team is home: W/D/L = home W/D/L
    # If team is away: away win = home loss, away loss = home win
    if team_is_home:
        return {"W": pW_home, "D": pD_home, "L": pL_home}
    return {"W": pL_home, "D": pD_home, "L": pW_home}

def _feature_row_for_minute(df, match_id: int, minute: int):
    minute = max(0, min(90, int(minute)))
    row = df[(df["match_id"] == match_id) & (df["minute"] == minute)]
    if row.empty:
        return None
    return row.iloc[0]

def _event_minutes(match_id: int):
    # minute -> list of event tags
    events = load_events(match_id)  # from statsbomb.py (add import)
    out = {}
    for e in events:
        typ = (e.get("type") or {}).get("name")
        minute = int(e.get("minute", 0))
        minute = max(0, min(90, minute))

        tag = None
        if typ == "Shot":
            shot = e.get("shot") or {}
            outcome = (shot.get("outcome") or {}).get("name")
            if outcome == "Goal":
                tag = "GOAL"
        elif typ == "Substitution":
            tag = "SUB"
        elif typ in ("Foul Committed", "Card"):
            # try to detect card presence
            card = None
            if typ == "Foul Committed":
                fc = e.get("foul_committed") or {}
                card = (fc.get("card") or {}).get("name")
            else:
                card = (e.get("card") or {}).get("name")
            if card:
                if "Red" in card:
                    tag = "RED"
                elif "Yellow" in card:
                    tag = "YELLOW"

        if tag:
            out.setdefault(minute, []).append(tag)
    return out


def _apply_sub_effect(x: np.ndarray, team_is_home: bool, minutes_shift: int) -> np.ndarray:
    # x columns follow feature_cols in simulate()
    IDX_SH5_H, IDX_SH5_A = 2, 3
    IDX_PA5_H, IDX_PA5_A = 4, 5

    x2 = x.copy()
    m = max(-30, min(30, int(minutes_shift)))  # cap
    if m == 0:
        return x2

    # earlier shift (negative) => positive effect
    strength = min(1.0, abs(m) / 12.0)   # 12 min shift ~= full effect
    direction = -1 if m < 0 else 1       # earlier=-1, later=+1

    pass_boost = 2.0 * strength * (-direction)
    shot_boost = 0.6 * strength * (-direction)

    if team_is_home:
        x2[IDX_PA5_H] += pass_boost
        x2[IDX_SH5_H] += shot_boost
        x2[IDX_PA5_A] -= 0.5 * pass_boost
        x2[IDX_SH5_A] -= 0.5 * shot_boost
    else:
        x2[IDX_PA5_A] += pass_boost
        x2[IDX_SH5_A] += shot_boost
        x2[IDX_PA5_H] -= 0.5 * pass_boost
        x2[IDX_SH5_H] -= 0.5 * shot_boost

    # keep rolling features non-negative
    x2[IDX_PA5_H] = max(0.0, x2[IDX_PA5_H])
    x2[IDX_PA5_A] = max(0.0, x2[IDX_PA5_A])
    x2[IDX_SH5_H] = max(0.0, x2[IDX_SH5_H])
    x2[IDX_SH5_A] = max(0.0, x2[IDX_SH5_A])
    return x2


def _build_wp_curve(df, model, match_id: int, team_is_home: bool, feature_cols, cf_from_minute: int | None = None, minutes_shift: int = 0):
    wp = []
    for minute in range(0, 91):
        r = _feature_row_for_minute(df, match_id, minute)
        if r is None:
            continue

        x = r[feature_cols].to_numpy(dtype=float)

        if cf_from_minute is not None and minute >= cf_from_minute and minutes_shift != 0:
            x = _apply_sub_effect(x, team_is_home, minutes_shift)

        from app.knn import predict_probs
        p = predict_probs(model, x, exclude_match_id=match_id)
        probs = _team_perspective_from_home_probs(p["pW_home"], p["pD_home"], p["pL_home"], team_is_home)
        wp.append({"minute": minute, **probs})
    return wp

@app.get("/matches/{match_id}/momentum")
def momentum(match_id: int):
    model, df = model_store.get_model(k=25)
    rows = df[df["match_id"] == match_id][["minute", "momentum_home"]]
    out = [{"minute": int(r["minute"]), "momentum": float(r["momentum_home"])} for _, r in rows.iterrows()]
    return {"match_id": match_id, "momentum": out}


def _build_momentum_curve(df, match_id: int, team_is_home: bool):
    out = []
    col = "momentum_home" if team_is_home else "momentum_away"
    for minute in range(0, 91):
        r = _feature_row_for_minute(df, match_id, minute)
        if r is None:
            continue
        out.append({"minute": minute, "momentum": float(r[col])})
    return out


@app.post("/simulate")
def simulate(req: SimulateRequest) -> Dict[str, Any]:
    model, df = model_store.get_model(k=25)

    subs = extract_subs(req.match_id)
    sub = next((s for s in subs if s["event_id"] == req.sub_event_id), None)
    if not sub:
        return {"error": "sub_event_id not found for match", "match_id": req.match_id, "sub_event_id": req.sub_event_id}

    # determine if team is home
    matches = load_sample_matches()
    m = next((x for x in matches if int(x["match_id"]) == int(req.match_id)), None)
    if not m:
        return {"error": "match_id not found in sample_matches.json", "match_id": req.match_id}

    home_team = m["home_team"]["home_team_name"]
    team_is_home = (sub["team"] == home_team)

    actual_minute = int(sub["minute"])
    alt_minute = int(req.alt_minute)

    r_actual = _feature_row_for_minute(df, req.match_id, actual_minute)
    r_alt = _feature_row_for_minute(df, req.match_id, alt_minute)
    if r_actual is None or r_alt is None:
        return {"error": "state vector missing", "match_id": req.match_id}

    feature_cols = [
        "minute",
        "goal_diff_home",
        "shots5_home",
        "shots5_away",
        "passes5_home",
        "passes5_away",
        "yellow_home",
        "yellow_away",
        "red_home",
        "red_away",
        "subs_used_home",
        "subs_used_away",
    ]

    x_actual = r_actual[feature_cols].to_numpy(dtype=float)
    x_alt = r_alt[feature_cols].to_numpy(dtype=float)

    from app.knn import predict_probs

    pa = predict_probs(model, x_actual, exclude_match_id=req.match_id)
    pb = predict_probs(model, x_alt, exclude_match_id=req.match_id)

    probs_actual = _team_perspective_from_home_probs(pa["pW_home"], pa["pD_home"], pa["pL_home"], team_is_home)
    probs_alt = _team_perspective_from_home_probs(pb["pW_home"], pb["pD_home"], pb["pL_home"], team_is_home)

    delta = {k: float(probs_alt[k] - probs_actual[k]) for k in ("W", "D", "L")}

    # confidence: average the two
    conf_score = float((pa["confidence_score"] + pb["confidence_score"]) / 2.0)
    conf_level = "HIGH" if conf_score >= 0.70 else "MED" if conf_score >= 0.45 else "LOW"

    return {
        "match_id": req.match_id,
        "sub_event_id": req.sub_event_id,
        "team": sub["team"],
        "actual_minute": actual_minute,
        "alt_minute": max(0, min(90, alt_minute)),
        "probs_actual": probs_actual,
        "probs_alt": probs_alt,
        "delta": delta,
        "confidence": {
            "level": conf_level,
            "score": conf_score,
            "why": f"Based on {len(df)} historical minute-states with similar scoreline, tempo, and game phase.",
        },
    }
