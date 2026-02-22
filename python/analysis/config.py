from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", PROJECT_ROOT / "data" / "processed"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
DEFAULT_DATA_SOURCE = os.getenv("DATA_SOURCE", "csv").strip().lower()

