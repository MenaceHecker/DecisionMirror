from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from app.knn import KNNModel, build_model

_MODEL: Optional[KNNModel] = None
_DF: Optional[pd.DataFrame] = None


def load_states_df() -> pd.DataFrame:
    global _DF
    if _DF is not None:
        return _DF

    p = Path(__file__).resolve().parents[1] / "data" / "processed" / "states.parquet"
    if not p.exists():
        raise FileNotFoundError(f"states.parquet not found at {p}. Run: python scripts/build_states.py")

    _DF = pd.read_parquet(p)
    return _DF


def get_model(k: int = 25) -> Tuple[KNNModel, pd.DataFrame]:
    global _MODEL
    df = load_states_df()
    if _MODEL is None:
        _MODEL = build_model(df, k=k)
    return _MODEL, df
