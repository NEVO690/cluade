"""Seeds a few clearly-labelled *demo* creator accounts and the bundled sample
clips so the social tab isn't empty on first launch.

Demo accounts are local, flagged ``is_demo`` and shown with a "DEMO" badge in
the UI. They are not real people and nothing is fetched from the internet.
"""
from __future__ import annotations

import json
import logging
import random

from config import paths
from social.accounts import AccountError

log = logging.getLogger(__name__)

DEMO_CREATORS = [
    ("xgun_studio", "Xgun Studio", "Official sample clips bundled with the game (offline demo account)."),
    ("dropzone_dani", "Dropzone Dani", "Demo creator. Hot drops only."),
    ("glide_guru", "Glide Guru", "Demo creator. Gliders, emotes and island tours."),
    ("loot_llama", "Loot Llama", "Demo creator. Chest goblin."),
]

DEMO_COMMENTS = ["That landing was clean!", "Which outfit is that?", "Need this emote in my locker",
                 "Ember Ronin goes hard", "Tutorial please!", "The island looks so good",
                 "Glider drip", "Victory dance supremacy"]

SEED_VERSION = "1"


def seed_demo_content(services) -> None:
    db = services.db
    sample_index = paths.SAMPLE_VIDEOS / "samples.json"
    samples = json.loads(sample_index.read_text(encoding="utf-8")) if sample_index.exists() else []
    marker = f"{SEED_VERSION}:{len(samples)}"
    if db.get_state("demo_seed") == marker:
        return
    ids = {}
    for username, display, bio in DEMO_CREATORS:
        existing = services.accounts.find_by_username(username)
        if existing:
            ids[username] = existing.id
            continue
        try:
            ids[username] = services.accounts.create(username, display, is_demo=True, bio=bio).id
        except AccountError as exc:  # pragma: no cover
            log.warning("Demo account %s skipped: %s", username, exc)

    existing_files = {r["file_path"] for r in db.all("SELECT file_path FROM videos WHERE is_sample = 1")}
    rng = random.Random(42)
    for sample in samples:
        path = paths.SAMPLE_VIDEOS / sample["file"]
        rel = str(path.relative_to(paths.ROOT)).replace("\\", "/")
        owner = ids.get(sample.get("creator", "xgun_studio"))
        if rel in existing_files or owner is None or not path.exists():
            continue
        try:
            video = services.social.upload(owner, path, sample["title"], sample.get("caption", ""),
                                           is_sample=True, copy_file=False)
        except Exception as exc:  # broken sample must never block startup
            log.warning("Sample video %s skipped: %s", path.name, exc)
            continue
        others = [i for u, i in ids.items() if i != owner]
        for liker in rng.sample(others, k=min(len(others), rng.randint(1, 3))):
            services.social.set_like(liker, video.id, True)
        commenter = rng.choice(others)
        services.social.add_comment(commenter, video.id, rng.choice(DEMO_COMMENTS))
        db.execute("UPDATE videos SET views = ? WHERE id = ?", (rng.randint(40, 900), video.id))

    for a in ids.values():  # demo creators follow each other
        for b in ids.values():
            if a != b and rng.random() < 0.6:
                services.social.set_follow(a, b, True)
    db.set_state("demo_seed", marker)
