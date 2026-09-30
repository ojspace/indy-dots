import sys
from pathlib import Path

# Ensure `app` package (server/) is importable regardless of pytest rootdir.
SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
