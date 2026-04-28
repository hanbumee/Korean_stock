"""Single source of truth for windows, filter floors, and paths."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "kstock.db"

MARKETS = ("KOSPI", "KOSDAQ")

# Ordered shortest -> longest. Used for column order in the consistency view too.
WINDOWS: tuple[str, ...] = ("1d", "2d", "3d", "1w", "2w", "1m", "6m", "1y")

# Default windows for the consistency check (mixes short + long, skips noisy 1d/2d).
DEFAULT_CONSISTENCY_WINDOWS: tuple[str, ...] = ("1w", "1m", "6m", "1y")

# Filter floors for the rankings. Overridable from the dashboard sidebar.
MIN_MARKET_CAP_KRW: int = 100_000_000_000  # 100B KRW
MIN_FOREIGN_RATIO_PCT: float = 0.5         # %
