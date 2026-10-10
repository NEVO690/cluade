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

## Known limitations

* **Offline only.** Bots stand in for players, and all social data is local.
  The interfaces for a server (`MatchSim` + events) and an online social
  backend (`SocialBackend`) are in place.
* **No building or editing mechanics.** Pickaxes are melee weapons and break
  supply crates.
* **Bots navigate by steering, not a navmesh.** Chests on upper floors are
  ignored by bots, and unreachable goals are dropped after 12 s.
* **Video thumbnails are coloured tiles** with the title; frames aren't
  extracted.
* **Not yet verified on Windows.** Development and testing happened in Linux
  CI. The Windows `.bat` files use standard venv layouts, so run
  `run_tests.bat` first on a new PC.

## Next steps (suggested order)

1. Play-test on Windows with a real GPU and tune: mouse sensitivity defaults,
   weapon balance (`data/gameplay/weapons.json`), bot difficulty
   (`bots/brain.py` `SKILL`).
2. Add a navmesh or waypoint graph through building doors and stairs so bots
   can loot upper floors.
3. Add more outfits/weapons. Add an entry to `data/catalog/cosmetics.json`,
   a builder to `tools/blender_generation/xgb/outfits.py` (or `gear.py` /
   `weapons.py`), then run `build_assets.bat <category>` and
   `validate_assets.py`.
4. Extract first-frame thumbnails for uploaded videos.
5. Online: implement `RemoteSocialBackend` against a real service, and run
   `MatchSim` on an authoritative server streaming `events` to clients.
