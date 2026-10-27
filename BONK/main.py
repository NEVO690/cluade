"""BONK! - start the game.

    python main.py                 play
    python main.py --autoplay ...  automated run (see src/bonk/client/autoplay.py)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))


def main():
    try:
        import panda3d  # noqa: F401
        import gltf  # noqa: F401
    except ImportError as exc:
        print("Missing dependency: %s\nInstall with:  pip install -r requirements.txt" % exc)
        return 1
    from bonk.client.app import run
    run(sys.argv[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
