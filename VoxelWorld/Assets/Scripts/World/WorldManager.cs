using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using VoxelWorld.Rendering;
using VoxelWorld.Voxel;
using VoxelWorld.World.Generation;
using Debug = UnityEngine.Debug;

namespace VoxelWorld.World
{
    /// <summary>
    /// Streams chunks around a focus point: generates block data on worker threads, builds meshes
    /// on worker threads, uploads them on the main thread within a time budget, and unloads chunks
    /// that fall out of range. Player edits are stored in <see cref="WorldEdits"/> so they survive
    /// unloading. All public methods must be called from the main thread.
    /// </summary>
    public sealed class WorldManager : MonoBehaviour, IVoxelReader
    {
        private enum ChunkState
        {
            Generating,
            Ready,
        }

        private sealed class ChunkEntry
        {
            public ChunkCoord Coord;
            public ChunkData Data;
            public ChunkState State;
            public ChunkRenderer Renderer;
            /// <summary>Bumped whenever this chunk's mesh becomes stale (own or neighbouring edits).</summary>
            public int ContentVersion;
            /// <summary>ContentVersion of the mesh currently displayed, -1 when none.</summary>
            public int AppliedVersion = -1;
            public bool MeshJobRunning;
            public bool Unloaded;
        }

        private struct MeshResult
        {
            public ChunkEntry Entry;
            public ChunkMeshData Data;
            public int Version;
        }

        [Tooltip("Main-thread milliseconds per frame that may be spent uploading chunk meshes.")]
        [SerializeField] private float meshUploadBudgetMs = 4f;

        public BlockRegistry Registry { get; private set; }
        public TerrainGenerator Generator { get; private set; }
        public ChunkDimensions Dims { get; private set; }
        public WorldEdits Edits { get; private set; }
        public int Seed { get; private set; }
        public int RenderDistance { get; private set; } = 8;
        public int LoadedChunkCount => _chunks.Count;
        public int PendingJobs => _generationJobs + _meshJobs;

        /// <summary>Raised after a block changes: (x, y, z, oldBlock, newBlock).</summary>
        public event Action<int, int, int, ushort, ushort> BlockChanged;

        private readonly Dictionary<ChunkCoord, ChunkEntry> _chunks = new Dictionary<ChunkCoord, ChunkEntry>();
        private readonly ConcurrentQueue<ChunkEntry> _generated = new ConcurrentQueue<ChunkEntry>();
        private readonly ConcurrentQueue<MeshResult> _meshed = new ConcurrentQueue<MeshResult>();
        private readonly ConcurrentBag<ChunkMesher> _mesherPool = new ConcurrentBag<ChunkMesher>();
        private readonly ConcurrentBag<ChunkMeshData> _meshDataPool = new ConcurrentBag<ChunkMeshData>();
        private readonly Stack<ChunkRenderer> _rendererPool = new Stack<ChunkRenderer>();
        private readonly List<ChunkCoord> _scratchCoords = new List<ChunkCoord>();
        private readonly ChunkData[] _neighbourScratch = new ChunkData[9];

        private BlockMaterials _materials;
        private ChunkMesher _mainThreadMesher;
        private ChunkMeshData _mainThreadMeshData;
        private (int dx, int dz)[] _spiral = Array.Empty<(int, int)>();
        private ChunkCoord _focus;
        private bool _focusValid;
        private int _generationJobs;
        private int _meshJobs;
        private int _maxJobs;
        private volatile bool _shuttingDown;
        private ChunkEntry _lastLookup;

        public void Initialize(int seed, BlockRegistry registry, BlockMaterials materials, ChunkDimensions dims, int renderDistance)
        {
            Seed = seed;
            Registry = registry;
            Dims = dims;
            _materials = materials;
            Generator = new TerrainGenerator(seed, dims);
            Edits = new WorldEdits();
            _mainThreadMesher = new ChunkMesher(registry, dims);
            _mainThreadMeshData = new ChunkMeshData();
            _maxJobs = Math.Max(1, Environment.ProcessorCount - 1);
            SetRenderDistance(renderDistance);
        }

        public void SetRenderDistance(int chunks)
        {
            RenderDistance = Mathf.Clamp(chunks, 2, 32);
            // Generation reaches one ring further than meshing so every meshed chunk has neighbours.
            int r = RenderDistance + 1;
            var list = new List<(int, int)>();
            for (int dz = -r; dz <= r; dz++)
            for (int dx = -r; dx <= r; dx++)
                list.Add((dx, dz));
            list.Sort((a, b) => (a.Item1 * a.Item1 + a.Item2 * a.Item2).CompareTo(b.Item1 * b.Item1 + b.Item2 * b.Item2));
            _spiral = list.ToArray();
        }

        public ChunkCoord ChunkOf(int wx, int wz) => new ChunkCoord(VoxelMath.FloorDiv(wx, Dims.SizeX), VoxelMath.FloorDiv(wz, Dims.SizeZ));

        /// <summary>Sets the point (block coordinates) around which chunks are kept loaded.</summary>
        public void SetFocus(Vector3 blockPosition)
        {
            _focus = ChunkOf(Mathf.FloorToInt(blockPosition.x), Mathf.FloorToInt(blockPosition.z));
            _focusValid = true;
        }

        private void Update()
        {
            if (Registry == null || !_focusValid) return;
            ProcessGenerated();
            ScheduleWork();
            UploadMeshes();
            UnloadDistant();
        }

        // ---------------------------------------------------------------- generation

        private void ProcessGenerated()
        {
            while (_generated.TryDequeue(out var entry))
            {
                _generationJobs--;
                if (entry.Unloaded) continue;
                Edits.ApplyTo(entry.Data);
                entry.State = ChunkState.Ready;
            }
        }

        private void ScheduleWork()
        {
            int generationRadius = RenderDistance + 1;
            for (int i = 0; i < _spiral.Length; i++)
            {
                var (dx, dz) = _spiral[i];
                var coord = _focus.Offset(dx, dz);
                bool inMeshRange = Math.Max(Math.Abs(dx), Math.Abs(dz)) <= RenderDistance;

                if (!_chunks.TryGetValue(coord, out var entry))
                {
                    if (Math.Max(Math.Abs(dx), Math.Abs(dz)) > generationRadius) continue;
                    if (_generationJobs >= _maxJobs * 2) continue;
                    StartGeneration(coord);
                    continue;
                }

                if (!inMeshRange || entry.State != ChunkState.Ready || entry.MeshJobRunning) continue;
                if (entry.AppliedVersion >= entry.ContentVersion) continue;
                if (_meshJobs >= _maxJobs * 2) continue;
                if (!NeighboursReady(coord)) continue;
                StartMeshJob(entry);
            }
        }

        private void StartGeneration(ChunkCoord coord)
        {
            var entry = new ChunkEntry
            {
                Coord = coord,
                Data = new ChunkData(Dims),
                State = ChunkState.Generating,
            };
            entry.Data.Reset(coord);
            _chunks.Add(coord, entry);
            _generationJobs++;
            var generator = Generator;
            Task.Run(() =>
            {
                try
                {
                    if (!_shuttingDown) generator.Generate(entry.Data);
                }
                catch (Exception e)
                {
                    Debug.LogException(e);
                }
                _generated.Enqueue(entry);
            });
        }

        private bool NeighboursReady(ChunkCoord coord)
        {
            for (int dz = -1; dz <= 1; dz++)
            for (int dx = -1; dx <= 1; dx++)
            {
                if (!_chunks.TryGetValue(coord.Offset(dx, dz), out var n) || n.State != ChunkState.Ready) return false;
            }
            return true;
        }

        private ChunkData[] CollectNeighbourhood(ChunkCoord coord, ChunkData[] target)
        {
            for (int dz = -1; dz <= 1; dz++)
            for (int dx = -1; dx <= 1; dx++)
            {
                _chunks.TryGetValue(coord.Offset(dx, dz), out var n);
                target[(dx + 1) + 3 * (dz + 1)] = n?.Data;
            }
            return target;
        }

        // ---------------------------------------------------------------- meshing

        private void StartMeshJob(ChunkEntry entry)
        {
            entry.MeshJobRunning = true;
            int version = entry.ContentVersion;
            var neighbourhood = CollectNeighbourhood(entry.Coord, new ChunkData[9]);
            _meshJobs++;
            Task.Run(() =>
            {
                ChunkMeshData data = null;
                try
                {
                    if (!_meshDataPool.TryTake(out data)) data = new ChunkMeshData();
                    if (!_shuttingDown)
                    {
                        if (!_mesherPool.TryTake(out var mesher)) mesher = new ChunkMesher(Registry, Dims);
                        mesher.Build(neighbourhood, data);
                        _mesherPool.Add(mesher);
                    }
                }
                catch (Exception e)
                {
                    Debug.LogException(e);
                    data?.Clear();
                }
                _meshed.Enqueue(new MeshResult { Entry = entry, Data = data, Version = version });
            });
        }

        private void UploadMeshes()
        {
            var timer = Stopwatch.StartNew();
            while (timer.Elapsed.TotalMilliseconds < meshUploadBudgetMs && _meshed.TryDequeue(out var result))
            {
                _meshJobs--;
                var entry = result.Entry;
                entry.MeshJobRunning = false;
                if (!entry.Unloaded && result.Data != null && result.Version > entry.AppliedVersion)
                {
                    ApplyMesh(entry, result.Data, result.Version);
                }
                if (result.Data != null)
                {
                    result.Data.Clear();
                    _meshDataPool.Add(result.Data);
                }
            }
        }

        private void ApplyMesh(ChunkEntry entry, ChunkMeshData data, int version)
        {
            if (entry.Renderer == null) entry.Renderer = AcquireRenderer(entry.Coord);
            entry.Renderer.Apply(data, Dims);
            entry.AppliedVersion = version;
        }

        /// <summary>Rebuilds a chunk's mesh immediately on the main thread (used after edits).</summary>
        private void RebuildNow(ChunkEntry entry)
        {
            if (entry.State != ChunkState.Ready || (entry.Renderer == null && entry.AppliedVersion < 0)) return;
            if (!NeighboursReady(entry.Coord)) return;
            _mainThreadMesher.Build(CollectNeighbourhood(entry.Coord, _neighbourScratch), _mainThreadMeshData);
            ApplyMesh(entry, _mainThreadMeshData, entry.ContentVersion);
            Array.Clear(_neighbourScratch, 0, _neighbourScratch.Length);
        }

        private ChunkRenderer AcquireRenderer(ChunkCoord coord)
        {
            ChunkRenderer r;
            if (_rendererPool.Count > 0)
            {
                r = _rendererPool.Pop();
                r.gameObject.SetActive(true);
            }
            else
            {
                var go = new GameObject("Chunk", typeof(MeshFilter), typeof(MeshRenderer), typeof(ChunkRenderer));
                go.transform.SetParent(transform, false);
                r = go.GetComponent<ChunkRenderer>();
                r.Initialize(_materials.Solid, _materials.Water);
            }
            r.Place(coord, Dims);
            return r;
        }

        // ---------------------------------------------------------------- unloading

        private void UnloadDistant()
        {
            int keep = RenderDistance + 2;
            _scratchCoords.Clear();
            foreach (var pair in _chunks)
            {
                if (pair.Key.ChebyshevDistance(_focus) > keep) _scratchCoords.Add(pair.Key);
            }
            foreach (var coord in _scratchCoords)
            {
                var entry = _chunks[coord];
                _chunks.Remove(coord);
                entry.Unloaded = true;
                if (_lastLookup == entry) _lastLookup = null;
                if (entry.Renderer != null)
                {
                    entry.Renderer.ClearMesh();
                    entry.Renderer.gameObject.SetActive(false);
                    _rendererPool.Push(entry.Renderer);
                    entry.Renderer = null;
                }
            }
        }

        // ---------------------------------------------------------------- block access

        private ChunkEntry ReadyEntry(int wx, int wz, out int lx, out int lz)
        {
            int cx = VoxelMath.FloorDiv(wx, Dims.SizeX), cz = VoxelMath.FloorDiv(wz, Dims.SizeZ);
            lx = wx - cx * Dims.SizeX;
            lz = wz - cz * Dims.SizeZ;
            var last = _lastLookup;
            if (last != null && last.Coord.X == cx && last.Coord.Z == cz) return last;
            if (_chunks.TryGetValue(new ChunkCoord(cx, cz), out var entry) && entry.State == ChunkState.Ready)
            {
                _lastLookup = entry;
                return entry;
            }
            return null;
        }

        public ushort GetBlock(int x, int y, int z)
        {
            if (y < 0) return Blocks.Deepstone;
            if (y >= Dims.Height) return Blocks.Air;
            var entry = ReadyEntry(x, z, out int lx, out int lz);
            return entry == null ? Blocks.Unloaded : entry.Data.Get(lx, y, lz);
        }

        public bool IsChunkReady(ChunkCoord coord) => _chunks.TryGetValue(coord, out var e) && e.State == ChunkState.Ready;

        /// <summary>True when the chunk has been meshed at least once (it is visible).</summary>
        public bool IsChunkVisible(ChunkCoord coord) => _chunks.TryGetValue(coord, out var e) && e.AppliedVersion >= 0;

        /// <summary>Topmost non-air block at a column, or -1 if the chunk is not loaded.</summary>
        public int GetTopSolidY(int x, int z)
        {
            var entry = ReadyEntry(x, z, out int lx, out int lz);
            if (entry == null) return -1;
            for (int y = Math.Min(entry.Data.MaxY, Dims.Height - 1); y >= 0; y--)
            {
                if (Registry.IsSolid(entry.Data.Get(lx, y, lz))) return y;
            }
            return 0;
        }

        /// <summary>
        /// Changes a block, records the edit and rebuilds affected meshes immediately.
        /// Returns false if the position is outside the world or its chunk is not loaded.
        /// </summary>
        public bool SetBlock(int x, int y, int z, ushort block)
        {
            if (y < 0 || y >= Dims.Height) return false;
            var entry = ReadyEntry(x, z, out int lx, out int lz);
            if (entry == null) return false;
            ushort old = entry.Data.Get(lx, y, lz);
            if (old == block) return true;

            entry.Data.Set(lx, y, lz, block);
            Edits.Record(entry.Coord, entry.Data.Index(lx, y, lz), block);
            entry.ContentVersion++;

            // Border blocks also affect neighbouring meshes (face culling and ambient occlusion).
            int ndx = lx == 0 ? -1 : (lx == Dims.SizeX - 1 ? 1 : 0);
            int ndz = lz == 0 ? -1 : (lz == Dims.SizeZ - 1 ? 1 : 0);
            RebuildNow(entry);
            if (ndx != 0) TouchNeighbour(entry.Coord.Offset(ndx, 0));
            if (ndz != 0) TouchNeighbour(entry.Coord.Offset(0, ndz));
            if (ndx != 0 && ndz != 0) TouchNeighbour(entry.Coord.Offset(ndx, ndz));

            BlockChanged?.Invoke(x, y, z, old, block);
            return true;
        }

        private void TouchNeighbour(ChunkCoord coord)
        {
            if (!_chunks.TryGetValue(coord, out var n) || n.State != ChunkState.Ready) return;
            n.ContentVersion++;
            if (n.AppliedVersion >= 0) RebuildNow(n);
        }

        // ---------------------------------------------------------------- lifecycle

        /// <summary>Unloads everything (used when leaving or reloading a world).</summary>
        public void ClearAll()
        {
            foreach (var entry in _chunks.Values)
            {
                entry.Unloaded = true;
                if (entry.Renderer != null)
                {
                    entry.Renderer.ClearMesh();
                    entry.Renderer.gameObject.SetActive(false);
                    _rendererPool.Push(entry.Renderer);
                }
            }
            _chunks.Clear();
            _lastLookup = null;
            _focusValid = false;
        }

        private void OnDestroy()
        {
            _shuttingDown = true;
            ClearAll();
        }
    }
}
