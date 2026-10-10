# Xgun — progress log and continuation checklist

## Done (each milestone run, screenshotted and tested)

| Milestone | Result |
|---|---|
| Environment | Panda3D 1.10.16 + panda3d-gltf + simplepbr. Blender 5.0.1 via `bpy` for generation. OpenGL verified (Mesa under Xvfb). |
| Foundation | SQLite with migrations; accounts, wallet + ledger, catalog, locker, shop rotation, progression, friends, social backend |
| Blender pipeline | 57 assets: 7 rigged outfits (shared skeleton, 25 animations, sockets), 6 pickaxes, 6 back blings, 5 gliders, 6 weapons, 4 consumables, 22 environment pieces. Each has a `.blend` source, a `.glb` and a Cycles thumbnail. |
| Battle royale | Authoritative sim: drop ship, skydive/glide, movement + collision, hitscan combat, loot/chests/crates, healing, 7-phase storm, bots, eliminations, placement |
| Client | Terrain splat shader, water, sky, chunked scenery, avatars with cosmetics + aim pitch, effects, HUD, minimap/map, audio |
| Lobby | All 9 tabs, results screen, wallet history, toasts, modals, transitions |
| Social | Vertical player, feeds, likes/comments/saves/follows/views, uploads with validation, search, hashtags, profiles, privacy, reports, blocks, demo seed with 6 original clips |
| Tests | 33 pytest tests including asset validation and an end-to-end offscreen UI smoke test |

## Limitations follow-up (done)

| Item | Result |
|---|---|
| Windows | `.github/workflows/xgun-windows.yml` installs like `install.bat` on `windows-latest`, runs the test suite and launches the game offscreen. It found and fixed a real Windows-only crash (numpy `uint32` memoryview format). |
| Audio | `tests/test_audio.py` checks levels, clipping, clicks, loop seams and distinct gunshot spectra, and decodes the music through Panda. It is analysed, not listened to. |
| Bots on upper floors | Buildings export walkable `nav_routes`. Bots plan up and down stairs, and tests walk every route and watch bots loot upper floors. |
| Thumbnails | Real frames extracted in-game into `userdata/thumbs/`. |
| Building | Harvest wood/stone/metal with the pickaxe, then place walls, floors and ramps on a 4 m grid. Pieces have HP by material and bullets destroy them. Bots harvest and build cover. |
| Social tab name | Label configurable via `XGUN_SOCIAL_NAME`. |

## Known limitations

* **Offline only.** Bots stand in for players, and all social data is local.
* **No edit mode** for build pieces, and no roofs or cones.
* **Not play-tested on a real Windows GPU** by a human. CI runs the software renderer.

## Next steps (suggested order)

1. Play-test on Windows with a real GPU and tune: mouse sensitivity defaults,
   weapon balance (`data/gameplay/weapons.json`), bot difficulty
   (`bots/brain.py` `SKILL`).
2. Add more outfits/weapons. Add an entry to `data/catalog/cosmetics.json`,
   a builder to `tools/blender_generation/xgb/outfits.py` (or `gear.py` /
   `weapons.py`), then run `build_assets.bat <category>` and
   `validate_assets.py`.
3. Online: implement `RemoteSocialBackend` against a real service, and run
   `MatchSim` on an authoritative server streaming `events` to clients.
