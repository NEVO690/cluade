"""Player-facing product names in one place.

The social tab follows the original brief ("TIKTOK"). TikTok is a trademark of
its owner: set XGUN_SOCIAL_NAME (or edit SOCIAL_NAME) before distributing Xgun,
e.g. "CLIPS" or "XTOK".
"""
import os

GAME_NAME = "XGUN"
SOCIAL_NAME = os.environ.get("XGUN_SOCIAL_NAME", "TIKTOK").strip().upper() or "TIKTOK"
