from pathlib import Path
import pandas as pd


def read_csv(kit: str | Path, relative_path: str) -> pd.DataFrame:
    path = Path(kit) / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Required external input not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)
