"""Start a BONK! multiplayer server.

    python run_server.py                       # 0.0.0.0:7777, full 3-round show
    python run_server.py --port 7800 --maps starter_run
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from bonk.multiplayer.server import main  # noqa: E402

if __name__ == "__main__":
    main()
