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
| Online matches | `net/match_server.py` is an authoritative 30 Hz server; clients mirror state from diffs. Host/Join in the PLAY tab, dedicated server via `run_match_server.bat`, and bots replace players who leave. Tested with real TCP on localhost: two clients, a full match to the end, version mismatch and late joins. |
| Online social | `net/social_server.py` (HTTP/JSON, PBKDF2 passwords, tokens) plus `RemoteSocialBackend`. Tested over real HTTP: two accounts see each other's uploads, likes, comments and follows. Privacy and ownership are enforced server-side, and the UI falls back to local when the server disappears. |

## Known limitations

* **Online was tested on localhost only**, not across real routers or the
  internet. Internet play needs TCP port forwarding (47800 matches, 47801
  social).
* **No client-side prediction** in online matches. Movement lags by the round
  trip, which is fine on a LAN but noticeable at high ping.
* **The social server speaks plain HTTP.** Put it behind an HTTPS reverse
  proxy before using it on the internet.
* **Economy, cosmetics, progression and friends are local per PC**, even
  online. No real money is involved.
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
3. Online: add client-side prediction for the local player, and move
   friends and the XON economy to the server if they should be shared.
