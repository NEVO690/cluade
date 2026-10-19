# VOXEL WORLD

An original first-person voxel sandbox for Windows PC, built with **Unity 6 + URP + C#**.
All textures, icons and terrain are generated procedurally by the game's own code. There
are no third-party or Minecraft assets.

> Status: **Phase 2 milestone (playable voxel prototype) + most of Phase 3 (terrain, caves,
> biomes, vegetation)**. See "What is verified" below before relying on anything.

---

## Opening the project

1. Install **Unity 6 LTS (6000.0 or newer)** with **Windows Build Support** via Unity Hub.
   No `ProjectVersion.txt` is committed, so Hub will ask you which installed editor to use.
2. Unity Hub → **Add** → **Add project from disk** → select this `VoxelWorld` folder.
3. Open it. On first import the editor script `Voxel World/Configure Project` runs
   automatically. It:
   - creates and assigns a URP asset (`Assets/Settings/VoxelWorld_URP.asset`) **only if no
     render pipeline is set**. An existing URP setup is never replaced.
   - adds `Assets/Scenes/VoxelWorld.unity` to the build list and opens it.
4. The Input System package may ask to enable its backends and restart. Either answer
   works: the game supports both the new Input System and the legacy Input Manager.
5. Press **Play**. Click in the Game view to capture the mouse.

If anything looks wrong (pink materials, missing scene), run **Voxel World → Configure
Project** from the menu bar, or **Voxel World → Rebuild Game Scene**.

## Controls

| Action | Key |
|---|---|
| Move | W A S D |
| Look | Mouse |
| Jump / swim up | Space |
| Sprint | Left Shift (or Left Ctrl) |
| Mine block (hold) | Left mouse |
| Place selected block | Right mouse (hold to repeat) |
| Select hotbar slot | 1–9 or mouse wheel |
| Pick targeted block into hand | Middle mouse (if it is in the hotbar) |
| Debug overlay | F3 |
| Pause / settings | Esc |

You start with an empty hotbar. Mine blocks to collect them, then place them.

## What exists

- **Voxel engine**: column chunks (default 16×128×16, configurable on the `Game Bootstrap`
  object), `ushort` block storage, face culling (including across chunk borders), per-vertex
  ambient occlusion, interleaved vertex buffers uploaded with the advanced Mesh API, two
  sub-meshes (solid/cutout + translucent water), and a configurable block size.
- **Streaming**: terrain generation and meshing run on worker threads. Mesh upload has a
  per-frame time budget. Chunks outside the view distance are unloaded. Edits are kept in
  `WorldEdits` and re-applied when a chunk reloads.
- **Terrain**: seeded Perlin noise for continents, hills and ridged mountains. Biomes:
  Open Water, Shoreline, Sunlit Meadow, Old Woodland, Amber Dunes, Frostpine Taiga and
  Stone Highlands, with smooth biome-tinted grass and foliage. Also lakes and seas,
  spaghetti caves and caverns, coal and iron, oak, pine and cactus generation that is
  seamless across chunk borders, and grass, Emberbloom and Skybell flowers, and shrubs.
- **Original feature (first one)**: glowing **Lumen Crystals** grow on deep cave ceilings.
- **Player**: kinematic box-vs-voxel collision (sub-stepped, so it cannot tunnel through
  blocks), acceleration and friction, sprint with FOV kick, coyote time and jump buffering,
  swimming, head bob, and mouse sensitivity, FOV and invert-Y settings.
- **Interaction**: DDA voxel raycast, selection outline, data-driven mining times (block
  hardness), drops into the inventory, placement validation (no placing inside yourself,
  plants need support, replaceable blocks), and plants breaking when their support goes.
- **Inventory**: 36 slots (9 hotbar), stacking with limits, isometric block icons.
- **UI**: HUD (crosshair, hotbar, item name, mining progress, target name), loading screen,
  F3 debug overlay, and a pause menu with working Resume, sensitivity, FOV, view distance,
  invert Y and Quit.
- **Rendering (URP)**: custom shaders in `Assets/Resources/Shaders` (lit blocks with
  shadows, fog, AO and emission; animated translucent water; selection lines) and
  distance fog matched to the view distance.

## Project layout

```
Assets/
  Resources/Shaders/   VoxelLit, VoxelWater, VoxelLine (URP HLSL)
  Scenes/              VoxelWorld.unity (contains only the Game Bootstrap object)
  Scripts/
    Core/              bootstrap, input abstraction, settings, game state
    Voxel/             blocks, chunk data, mesher, raycast, physics, procedural textures (no UnityEngine)
    World/             WorldManager (streaming), WorldEdits
    World/Generation/  noise, biomes, terrain generator (no UnityEngine)
    Player/            controller, interaction
    Inventory/         items, inventory (no UnityEngine)
    Rendering/         materials, chunk renderer, outline, icons, atmosphere
    UI/                UI factory, HUD, pause menu
    Editor/            project setup utility
  Tests/EditMode/      NUnit tests (run in Unity's Test Runner)
Tools~/                verification without Unity (ignored by Unity)
```

The `Voxel`, `World/Generation` and `Inventory` code does not depend on UnityEngine, so it
can be unit-tested and run on worker threads.

**Adding a block**: add an id in `Blocks.cs`, a definition in `DefaultBlocks.cs`, and if it
needs new art, a layer in `BlockTextureLayers.cs` and a painter in
`BlockTextureGenerator.cs`. It gets an inventory item automatically.

## What is verified

| Check | Result |
|---|---|
| Runtime scripts compile (legacy input and Input System paths) against Unity 2021.3 reference assemblies + uGUI/Input System stubs | ✅ 0 errors, 0 warnings |
| Editor setup script compiles (URP API stubbed) | ✅ |
| 27 NUnit tests (meshing, culling, AO, raycast, physics, terrain determinism, inventory, edits, icons), run with .NET 8 | ✅ all pass |
| Software render of meshed terrain (winding, UVs, AO, culling) | ✅ 0 winding mismatches across 264k triangles |
| Compiled **inside Unity 6** | ❌ not done: no Unity Editor was available |
| URP shaders compiled by Unity | ❌ not verified |
| Play mode / gameplay feel / performance on real hardware | ❌ not verified |

When you first open the project, please check the Console for errors and tell me about any,
including shader errors. These are the most likely places for first-run issues.

Re-run the checks outside Unity (needs the .NET 8 SDK):

```
dotnet test Tools~/CoreTests                                 # unit tests
dotnet test Tools~/CoreTests --filter TerrainPreview          # writes terrain_preview.ppm
dotnet build Tools~/CompileCheck                              # compile check (legacy input)
dotnet build Tools~/CompileCheck -p:InputSystem=true          # compile check (Input System)
```

## Roadmap

- Phase 4: inventory screen, resource items, crafting
- Phase 5: health, hunger, tools, original creatures, day–night cycle
- Phase 6: saving and loading (seed + `WorldEdits` + player state)
- Phase 7: voxel sky and block light, particles, audio, main menu
- Phase 8: testing and fixes
