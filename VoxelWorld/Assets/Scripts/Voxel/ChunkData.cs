using System;

namespace VoxelWorld.Voxel
{
    /// <summary>Configurable chunk dimensions shared by the whole world.</summary>
    public readonly struct ChunkDimensions
    {
        public readonly int SizeX;
        public readonly int Height;
        public readonly int SizeZ;

        public ChunkDimensions(int sizeX, int height, int sizeZ)
        {
            if (sizeX < 4 || sizeZ < 4 || height < 16) throw new ArgumentException("Chunk dimensions too small.");
            SizeX = sizeX;
            Height = height;
            SizeZ = sizeZ;
        }

        public int Volume => SizeX * Height * SizeZ;

        public static ChunkDimensions Default => new ChunkDimensions(16, 128, 16);
    }

    /// <summary>
    /// Block storage for one chunk column. Blocks are stored in a flat ushort array
    /// (2 bytes per voxel) indexed x-fastest, then z, then y.
    /// </summary>
    public sealed class ChunkData
    {
        public readonly ChunkDimensions Dims;
        public ChunkCoord Coord { get; private set; }

        private readonly ushort[] _blocks;

        /// <summary>Per-column biome tint colours packed as 0xRRGGBB, used for grass and foliage.</summary>
        public readonly int[] GrassTint;
        public readonly int[] FoliageTint;

        /// <summary>Per-column biome id (see generation code).</summary>
        public readonly byte[] Biome;

        /// <summary>Highest y that contains a non-air block, or -1 when empty.</summary>
        public int MaxY { get; private set; } = -1;

        /// <summary>Incremented whenever block content changes after generation.</summary>
        public int Version;

        public ChunkData(ChunkDimensions dims)
        {
            Dims = dims;
            _blocks = new ushort[dims.Volume];
            GrassTint = new int[dims.SizeX * dims.SizeZ];
            FoliageTint = new int[dims.SizeX * dims.SizeZ];
            Biome = new byte[dims.SizeX * dims.SizeZ];
        }

        /// <summary>Resets the chunk for reuse at a new coordinate.</summary>
        public void Reset(ChunkCoord coord)
        {
            Coord = coord;
            Array.Clear(_blocks, 0, _blocks.Length);
            MaxY = -1;
            Version = 0;
        }

        public ushort[] RawBlocks => _blocks;

        public int Index(int x, int y, int z) => x + Dims.SizeX * (z + Dims.SizeZ * y);

        public int ColumnIndex(int x, int z) => x + Dims.SizeX * z;

        public bool InBounds(int x, int y, int z) =>
            (uint)x < (uint)Dims.SizeX && (uint)y < (uint)Dims.Height && (uint)z < (uint)Dims.SizeZ;

        public ushort Get(int x, int y, int z) => _blocks[x + Dims.SizeX * (z + Dims.SizeZ * y)];

        public ushort GetSafe(int x, int y, int z) => InBounds(x, y, z) ? Get(x, y, z) : Blocks.Air;

        /// <summary>Raw write used by terrain generation. Call <see cref="RecalculateMaxY"/> afterwards.</summary>
        public void SetRaw(int x, int y, int z, ushort block) => _blocks[x + Dims.SizeX * (z + Dims.SizeZ * y)] = block;

        /// <summary>Gameplay write: keeps <see cref="MaxY"/> current and bumps <see cref="Version"/>.</summary>
        public void Set(int x, int y, int z, ushort block)
        {
            _blocks[Index(x, y, z)] = block;
            if (block != Blocks.Air && y > MaxY) MaxY = y;
            else if (block == Blocks.Air && y == MaxY) RecalculateMaxY();
            Version++;
        }

        public void RecalculateMaxY()
        {
            int layer = Dims.SizeX * Dims.SizeZ;
            for (int y = Dims.Height - 1; y >= 0; y--)
            {
                int start = y * layer;
                for (int i = 0; i < layer; i++)
                {
                    if (_blocks[start + i] != Blocks.Air)
                    {
                        MaxY = y;
                        return;
                    }
                }
            }
            MaxY = -1;
        }
    }
}
