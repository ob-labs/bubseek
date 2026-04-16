from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LANGCHAIN_SRC = REPO_ROOT / "contrib" / "bubseek-langchain" / "src"

if str(LANGCHAIN_SRC) not in sys.path:
    sys.path.insert(0, str(LANGCHAIN_SRC))
