# Xgun

An original third-person battle royale for Windows, written in Python with
**Panda3D**, with every 3D asset generated in **Blender** by script. It ships
with a persistent **XON** economy, a cosmetics shop and locker, a free battle
pass, quests, friends and local profiles, and an in-lobby **TIKTOK**
short-video network.

> **Offline build.** Matches are solo against **AI bots** (always labelled
> `BOT`). All accounts, purchases, videos, likes, comments and follows are
> stored on this PC. Nothing is published online. The code is structured so an
> authoritative server and an online social backend can be added later (see
> *Architecture*).

## Quick start (Windows)

1. Install 64-bit **Python 3.10–3.13** from python.org and tick "Add to PATH".
2. Double-click **`install.bat`**. It creates `.venv` and installs `requirements.txt`.
3. Double-click **`run_xgun.bat`**.

Manual setup:

```bat
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Save data, logs, uploaded videos and screenshots go to `userdata\`. Delete
that folder to reset everything. Set `XGUN_USER_DIR` to use another folder.

## Controls

| Action | Key |
|---|---|
| Move / sprint / jump | `W A S D` / `Shift` / `Space` |
| Crouch | `C` (toggle) or hold `Ctrl` |
| Fire / aim down sights | Left mouse / right mouse |
| Reload / interact (hold for chests) | `R` / `E` |
| Pickaxe, slots 1–5 | `1`–`6`, mouse wheel |
| Leave the drop ship / open glider | `Space` |
| Build mode on / off | `Q` |
| In build mode: wall / floor / ramp / next material | `1` / `2` / `3` / `4` (wheel cycles pieces), left mouse places |
| Emote / map / pause | `B` / `M` / `Esc` |
| FPS counter / screenshot | `F3` / `F12` |

## What's in the game

* **Battle royale.** A 1 km procedural island with 7 named locations (Neon
  Plaza, Harbor Point, Pinewood Lodge, Sunset Dunes, Maple Row, Ridge Watch,
  Rustyard) and roads, forests, rocks and enterable buildings with stairs.
  A match runs: drop ship → skydive → glider → loot → fight → a shrinking
  storm over 7 phases → victory or defeat screen.
  * 6 weapons (AR, SMG, shotgun, sniper, pistol, Ion Lance) in 5 rarities,
    with bloom, ADS, falloff, headshots and a sniper scope. 5 ammo types.
  * Health and shield, plus 4 healing/shield items with caps and use times.
  * Glowing loot chests (hold `E`), ammo boxes, breakable supply crates
    (pickaxe), and floor loot.
  * 5–40 players. Bots drop, loot through doorways, pick weapons by range,
    strafe, heal, flee the storm and get unstuck. Easy / Normal / Hard.
  * HUD: vitals, hotbar with rarity colours, ammo, crosshair with bloom,
    hit markers, damage numbers, kill feed, minimap with storm circles,
    full map, prompts and storm timer.
* **Economy.** XON wallet with a transaction ledger. There's a 1,000 XON welcome
  gift, and XON is earned from matches, eliminations, survival time, placement,
  quests, milestones and battle pass tiers. The daily shop rotation (2 featured
  + 6 daily) is deterministic by date, purchases need confirmation, and nothing
  costs real money.
* **Cosmetics** (no gameplay effect, which a test enforces):
  * 7 outfits, 6 back blings, 6 pickaxes, 5 gliders and 5 emotes (one with a
    boombox prop).
  * 6 weapon wraps and 5 profile banners.
  * 5 rarity tiers.
* **Progression.** A free 20-tier Season 1 battle pass, 4 daily quests chosen
  from 10, and 6 milestones with item rewards.
* **TIKTOK tab.**
  * **Feed:** vertical video player with For You, Following, Saved and Liked
    feeds, and wheel / arrow-key scrolling.
  * **Interactions:** likes, comments (delete or report), saves, follows,
    view counts and profile galleries.
  * **Discovery:** search and trending hashtags.
  * **Uploads:** native file picker, validation of format, size, duration and
    real decoding, plus visibility (everyone / followers / only me) and a
    comments on/off setting.
  * **Safety:** reporting with auto-hide after 3 reports, blocking, private
    accounts and a word filter.
  * Six original sample clips are bundled, posted by clearly marked DEMO
    accounts.
* **Friends and profiles.** Friend requests (accept, decline, cancel), friend
  list, player search, and multiple local accounts. Profiles show stats, the
  equipped cosmetics and the **TikTok follower count**, with an **Open TikTok
  profile** button.

## Project layout

```
main.py                 entry point             requirements.txt / *.bat   setup & launchers
config/                 paths, settings         save_system/database.py    SQLite + migrations
game/                   app shell, match sim, match view, avatars, effects, services, assets
player/ combat/         (combat/weapons.py: weapon defs, ballistics)   bots/brain.py  AI
world/                  terrain, island layout, collision, storm, renderer (+ GLSL terrain/water)
inventory/ economy/ progression/   catalog, locker, wallet, shop, battle pass, quests, rewards
social/                 accounts, friends, moderation, social backend (local + remote stub), demo seed
video/                  upload validation, decode probe, in-lobby player
ui/                     theme, widgets, HUD, loading screen, lobby/ (one module per tab)
audio/                  sound + music manager
assets/blender/         editable .blend source for every asset
assets/models/          game-ready .glb + manifest.json (sockets, colliders, animations)
assets/ui/thumbs/       Cycles-rendered previews   assets/ui/icons/   generated icons
assets/textures/        procedural textures, wraps, terrain splats   assets/audio/ synthesized sfx & music
assets/videos/samples/  bundled sample clips      data/   cosmetics, weapons, loot, quests, battle pass
tools/                  blender_generation/, asset_validation/, asset_export/, audio_generation/,
                        video_generation/, screenshots/
tests/                  pytest suite (economy, social, progression, match, assets, videos, UI smoke)
```

## Rebuilding assets

Every model, texture and thumbnail comes from code. You need Blender 4.2 or
newer (built and tested with Blender 5.0.1):

```bat
build_assets.bat                       :: everything
build_assets.bat characters weapons    :: selected categories
```

Or, without Blender installed, use the PyPI module (Python 3.11):
`pip install -r requirements-blender.txt`, then
`python3.11 tools/blender_generation/build_all.py`.

Categories: `textures characters pickaxes backpacks gliders props weapons items
environment`. Add `--no-render` to skip the Cycles thumbnails, or
`--only=<asset_id>` to build one asset. Afterwards, run
`python tools/asset_validation/validate_assets.py`.

Other generators:
* `tools/audio_generation/generate_audio.py`: all sound effects and music.
* `tools/asset_export/make_icons.py`: UI icons.
* `tools/video_generation/make_sample_clips.py`: sample clips (needs ffmpeg
  and an OpenGL context).

**Character pipeline.** There's one shared 22-bone skeleton. 25 animations are
authored with a direction- and IK-based pose solver, and garments are built
on the body's Skin-modifier graph and auto-skinned. A weapon socket bone is
solved so weapons sit level in the rifle hold, with per-hold corrections in
the manifest. A back socket carries back blings. **Weapons** pivot at the
grip, with `socket_muzzle`, `socket_grip_l` and `socket_sight`. Materials
tagged `_wrap` take weapon wraps. **Buildings** export collision boxes,
loot spots and chest spots, so gameplay always matches the art.

## Tests

```bat
run_tests.bat        :: or: .venv\Scripts\python -m pytest -q tests
```

32 tests cover:
* Purchases and persistence across restarts.
* Wallet integrity and the shop rotation.
* Rewards, the battle pass and quests.
* Uploads: real decoding, plus rejection of broken, renamed, truncated and
  mismatched files.
* Likes, comments, saves, views, follows, privacy, blocking and reports.
* Friends and the follower count on profiles.
* Movement, collision, hitscan damage (shield, headshots, eliminations) and
  looting/healing caps.
* Storm, inventory and full bot-only matches.
* That cosmetics don't affect gameplay.
* That every GLB loads with its skeleton, animations and sockets.
* Sample clips.
* An end-to-end UI smoke test that boots the game offscreen, opens every tab,
  plays a match and checks that rewards were saved.

`tools/screenshots/drive.py` drives the real game and captures screenshots.

## Architecture notes

* `game/match.py` is an **authoritative simulation**. Each tick takes one
  `ControlInput` per combatant, and everything observable comes out as an
  event stream. The renderer, audio and tests only consume those events.
  A future server can run the same class and stream events to clients.
* `social/backend.py` defines the `SocialBackend` interface. The game uses
  `LocalSocialBackend` (SQLite plus copied files). `RemoteSocialBackend` is
  a documented placeholder that refuses to construct, so nothing can pretend
  to be online.
* Bots use the same input path as the player, and server-side rules apply
  equally to both.

## Notes

* The "TIKTOK" tab name follows the brief. TikTok is a trademark of its owner, so
  before distributing Xgun set the `XGUN_SOCIAL_NAME` environment variable (for example
  `CLIPS`) or edit `config/branding.py`; every visible label follows it.
* All 3D models, textures, sounds, music, icons and sample videos are original
  and generated by this repository's tools. Fonts are Inter (SIL OFL 1.1, see
  `assets/fonts/OFL-Inter.txt`).
