using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using VoxelWorld.Inventory;
using VoxelWorld.Player;
using VoxelWorld.Rendering;
using VoxelWorld.UI;
using VoxelWorld.Voxel;
using VoxelWorld.World;

namespace VoxelWorld.Core
{
    /// <summary>
    /// Entry point. Builds the whole game at runtime: block data, materials, camera, sun, world
    /// streaming, player and interface. The scene only needs this one component, which keeps
    /// the project free of fragile hand-wired references.
    /// </summary>
    [DefaultExecutionOrder(-100)]
    public sealed class GameBootstrap : MonoBehaviour
    {
        public const string SceneName = "VoxelWorld";

        [Header("World")]
        [Tooltip("World seed. 0 picks a random seed on every start.")]
        [SerializeField] private int seed = 0;
        [SerializeField, Range(8, 32)] private int chunkSizeX = 16;
        [SerializeField, Range(32, 256)] private int chunkHeight = 128;
        [SerializeField, Range(8, 32)] private int chunkSizeZ = 16;
        [Tooltip("World-space size of one block in metres. Everything, including the player, scales with it.")]
        [SerializeField, Range(0.25f, 4f)] private float blockSize = 1f;

        private BlockRegistry _blocks;
        private ItemRegistry _items;
        private BlockMaterials _materials;
        private ItemIconFactory _icons;
        private WorldManager _world;
        private AtmosphereController _atmosphere;
        private PlayerController _player;
        private PlayerInteraction _interaction;
        private PlayerInventory _inventory;
        private HudController _hud;
        private PauseMenu _pause;
        private Vector3 _spawnPoint;

        public WorldManager World => _world;
        public PlayerController Player => _player;
        public PlayerInventory Inventory => _inventory;

        private void Awake()
        {
            QualitySettings.vSyncCount = 1;
            GameState.WorldReady = false;

            _blocks = DefaultBlocks.Create();
            _items = ItemRegistry.CreateDefault(_blocks);
            _materials = BlockMaterials.Create();
            _icons = new ItemIconFactory(_blocks, _items, _materials.TilePixels);
            _inventory = new PlayerInventory(_items);

            var camera = SetUpCamera();

            var worldGo = new GameObject("World");
            worldGo.transform.localScale = Vector3.one * blockSize;
            _world = worldGo.AddComponent<WorldManager>();
            int worldSeed = seed != 0 ? seed : Random.Range(1, int.MaxValue);
            var dims = new ChunkDimensions(chunkSizeX, chunkHeight, chunkSizeZ);
            _world.Initialize(worldSeed, _blocks, _materials, dims, GameSettings.RenderDistance);

            _atmosphere = new GameObject("Atmosphere").AddComponent<AtmosphereController>();
            _atmosphere.Initialize(camera);
            UpdateViewDistance();

            var playerGo = new GameObject("Player");
            playerGo.transform.SetParent(worldGo.transform, false);
            _player = playerGo.AddComponent<PlayerController>();
            _player.Initialize(_world, camera);
            _interaction = playerGo.AddComponent<PlayerInteraction>();
            var outline = SelectionOutline.Create(worldGo.transform, _materials.Line);
            _interaction.Initialize(_world, _player, _inventory, outline);
            _player.enabled = false;
            _interaction.enabled = false;

            UIFactory.EnsureEventSystem();
            var uiRoot = new GameObject("UI");
            _hud = uiRoot.AddComponent<HudController>();
            _hud.Initialize(_inventory, _player, _interaction, _world, _icons);
            _pause = uiRoot.AddComponent<PauseMenu>();
            _pause.Initialize();
            _pause.RenderDistanceChanged += distance =>
            {
                _world.SetRenderDistance(distance);
                UpdateViewDistance();
            };

            StartCoroutine(SpawnWhenReady());
        }

        private Camera SetUpCamera()
        {
            var camera = Camera.main;
            if (camera == null)
            {
                var go = new GameObject("Main Camera") { tag = "MainCamera" };
                camera = go.AddComponent<Camera>();
                go.AddComponent<AudioListener>();
            }
            camera.nearClipPlane = 0.05f * blockSize;
            camera.allowHDR = true;
            camera.allowMSAA = true;
            return camera;
        }

        private void UpdateViewDistance()
        {
            float blocks = _world.RenderDistance * Mathf.Min(_world.Dims.SizeX, _world.Dims.SizeZ) * blockSize;
            _atmosphere.SetViewDistance(blocks);
        }

        private IEnumerator SpawnWhenReady()
        {
            _hud.SetLoading(true, "Shaping the land...");
            _world.Generator.FindSpawnColumn(out int sx, out int sz, out int surface);
            _spawnPoint = new Vector3(sx + 0.5f, surface + 1f, sz + 0.5f);
            _player.Teleport(_spawnPoint);
            _world.SetFocus(_spawnPoint);

            var center = _world.ChunkOf(sx, sz);
            const int radius = 2;
            const int total = (radius * 2 + 1) * (radius * 2 + 1);
            while (true)
            {
                int visible = 0;
                for (int dz = -radius; dz <= radius; dz++)
                for (int dx = -radius; dx <= radius; dx++)
                    if (_world.IsChunkVisible(center.Offset(dx, dz))) visible++;
                if (visible == total) break;
                _hud.SetLoading(true, $"Shaping the land...  {visible * 100 / total}%");
                yield return null;
            }

            int top = _world.GetTopSolidY(sx, sz);
            if (top >= 0) _spawnPoint.y = top + 1f;
            _player.Teleport(_spawnPoint, 0f);

            _player.enabled = true;
            _interaction.enabled = true;
            _hud.SetLoading(false);
            GameState.WorldReady = true;
            GameState.ApplyCursor();
        }

        private void Update()
        {
            if (!GameState.WorldReady) return;
            // Safety net: never let the player fall out of the world.
            if (_player.Position.y < -16f) _player.Teleport(_spawnPoint);
        }

        private void OnApplicationFocus(bool hasFocus)
        {
            if (hasFocus) GameState.ApplyCursor();
        }

        private void OnDestroy()
        {
            _icons?.Destroy();
            _materials?.Destroy();
        }

        /// <summary>
        /// If the game scene is opened without its bootstrap object (for example after a broken
        /// script reference), create one so the scene still plays.
        /// </summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureBootstrap()
        {
            if (SceneManager.GetActiveScene().name != SceneName) return;
            if (FindFirstObjectByType<GameBootstrap>() != null) return;
            new GameObject("Game Bootstrap").AddComponent<GameBootstrap>();
        }
    }
}
