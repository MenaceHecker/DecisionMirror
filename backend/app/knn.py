from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors


LABELS = ("W", "D", "L")  # from the TEAM's perspective in our API output


@dataclass
class KNNModel:
    nn: NearestNeighbors
    X: np.ndarray
    y: np.ndarray
    match_ids: np.ndarray


def _softmax_inv_dist(d: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    # weights = 1/(d+eps), normalized
    w = 1.0 / (d + eps)
    s = w.sum()
    if s <= 0:
        return np.ones_like(w) / len(w)
    return w / s


def _probs_from_neighbors(labels: np.ndarray, weights: np.ndarray) -> np.ndarray:
    # labels are 0/1/2
    p = np.zeros(3, dtype=float)
    for lab, w in zip(labels, weights):
        p[int(lab)] += float(w)
    s = p.sum()
    if s <= 0:
        return np.array([1 / 3, 1 / 3, 1 / 3], dtype=float)
    return p / s


def _confidence(distances: np.ndarray, weights: np.ndarray) -> Tuple[float, str]:
    # Heuristic confidence:
    # - closer neighbors => higher confidence
    # - effective sample size higher => higher confidence
    d_mean = float(np.mean(distances))
    ess = 1.0 / float(np.sum(np.square(weights)))  # effective sample size

    # map distance scale to score in [0,1] (tuned for our simple features)
    # lower d_mean better
    dist_score = 1.0 / (1.0 + d_mean)

    ess_score = min(1.0, ess / 15.0)  # saturate ~15 neighbors
    score = 0.6 * dist_score + 0.4 * ess_score

    if score >= 0.70:
        level = "HIGH"
    elif score >= 0.45:
        level = "MED"
    else:
        level = "LOW"

    return float(score), level


def fit_knn(states: pd.DataFrame, k: int = 25) -> KNNModel:
    X = states.to_numpy(dtype=float)
    nn = NearestNeighbors(n_neighbors=k, metric="euclidean")
    nn.fit(X)
    return KNNModel(nn=nn, X=X, y=None, match_ids=None)  # y/match_ids set elsewhere


def build_model(df: pd.DataFrame, k: int = 25) -> KNNModel:
    # df contains features + label_home + match_id
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

    X = df[feature_cols].to_numpy(dtype=float)
    y = df["label_home"].to_numpy(dtype=int)
    match_ids = df["match_id"].to_numpy(dtype=int)

    nn = NearestNeighbors(n_neighbors=k, metric="euclidean")
    nn.fit(X)

    return KNNModel(nn=nn, X=X, y=y, match_ids=match_ids)


def predict_probs(
    model: KNNModel,
    x_query: np.ndarray,
    exclude_match_id: int | None = None,
) -> Dict[str, float]:
    # Get neighbors
    distances, indices = model.nn.kneighbors(x_query.reshape(1, -1), return_distance=True)
    distances = distances[0]
    indices = indices[0]

    # Optionally exclude same match neighbors (prevents leakage)
    if exclude_match_id is not None:
        keep = model.match_ids[indices] != exclude_match_id
        indices = indices[keep]
        distances = distances[keep]

        # if we excluded too many, fall back to original neighbors
        if len(indices) < 5:
            distances, indices = model.nn.kneighbors(x_query.reshape(1, -1), return_distance=True)
            distances = distances[0]
            indices = indices[0]

    labels = model.y[indices]
    w = _softmax_inv_dist(distances)
    p_home = _probs_from_neighbors(labels, w)  # probs in HOME perspective

    score, level = _confidence(distances, w)

    # Return as dict for HOME perspective initially; conversion to team perspective is handled outside.
    return {
        "pW_home": float(p_home[0]),
        "pD_home": float(p_home[1]),
        "pL_home": float(p_home[2]),
        "confidence_score": score,
        "confidence_level": level,
        "avg_distance": float(np.mean(distances)),
    }
