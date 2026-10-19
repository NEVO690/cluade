using System;
using VoxelWorld.Voxel;

namespace VoxelWorld.World.Generation
{
    /// <summary>Climate and height of one world column, before caves are carved.</summary>
    public struct ColumnSample
    {
        public int Height;
        public BiomeId Biome;
        public float Temperature;
        public float Humidity;
        public int GrassTint;
        public int FoliageTint;
    }

    /// <summary>
    /// Deterministic terrain generator. The same seed and coordinates always produce the same
    /// blocks, so only player modifications need to be saved. Thread-safe: <see cref="Generate"/>
    /// may run on several worker threads at once.
    /// </summary>
    public sealed class TerrainGenerator
    {
        private const int StructureMargin = 3;

        public readonly int Seed;
        public readonly ChunkDimensions Dims;
        public readonly int SeaLevel;

        private readonly PerlinNoise _continent, _hills, _detail, _mountainMask, _ridges;
        private readonly PerlinNoise _temperature, _humidity;
        private readonly PerlinNoise _caveA, _caveB, _cavern, _ore;

        [ThreadStatic] private static ColumnSample[] _columns;

        public TerrainGenerator(int seed, ChunkDimensions dims, int seaLevel = -1)
        {
            Seed = seed;
            Dims = dims;
            SeaLevel = seaLevel > 0 ? seaLevel : Math.Max(8, dims.Height * 3 / 8);

            // Each layer gets an independent permutation derived from the world seed.
            _continent = new PerlinNoise(seed);
            _hills = new PerlinNoise(seed + 101);
            _detail = new PerlinNoise(seed + 202);
            _mountainMask = new PerlinNoise(seed + 303);
            _ridges = new PerlinNoise(seed + 404);
            _temperature = new PerlinNoise(seed + 505);
            _humidity = new PerlinNoise(seed + 606);
            _caveA = new PerlinNoise(seed + 707);
            _caveB = new PerlinNoise(seed + 808);
            _cavern = new PerlinNoise(seed + 909);
            _ore = new PerlinNoise(seed + 1010);
        }

        private static float Smoothstep(float a, float b, float x)
        {
            float t = Math.Max(0f, Math.Min(1f, (x - a) / (b - a)));
            return t * t * (3f - 2f * t);
        }

        private static float Clamp01(float v) => v < 0f ? 0f : (v > 1f ? 1f : v);

        /// <summary>Terrain height and biome for a world column (ignores caves).</summary>
        public ColumnSample SampleColumn(int wx, int wz)
        {
            float c = (float)_continent.Fractal(wx * 0.0016, wz * 0.0016, 4) * 1.5f + 0.12f;
            float hills = (float)_hills.Fractal(wx * 0.011, wz * 0.011, 4) * 9f
                          + (float)_detail.Fractal(wx * 0.04, wz * 0.04, 2) * 1.6f;

            float land = Smoothstep(-0.08f, 0.2f, c);
            float mask = Smoothstep(-0.04f, 0.32f, (float)_mountainMask.Fractal(wx * 0.0022, wz * 0.0022, 3)) * land;
            float ridges = (float)_ridges.Ridged(wx * 0.0055, wz * 0.0055, 4);
            float mountain = mask * (float)Math.Pow(ridges, 1.7) * 58f;

            // Land rises quickly away from the coast so beaches stay narrow.
            float coast = c > 0f ? (float)Math.Sqrt(c) * 22f : -(float)Math.Sqrt(-c) * 20f;
            float heightF = SeaLevel + 1.5f + coast + hills * (0.35f + 0.65f * land + mask) + mountain;
            int height = (int)Math.Round(heightF);
            height = Math.Max(6, Math.Min(Dims.Height - 14, height));

            float altitude = Math.Max(0, height - SeaLevel) / 110f;
            float temperature = (float)_temperature.Fractal(wx * 0.0012, wz * 0.0012, 3) * 1.4f - altitude;
            float humidity = (float)_humidity.Fractal(wx * 0.0014, wz * 0.0014, 3) * 1.4f;

            BiomeId biome;
            if (height < SeaLevel - 1) biome = BiomeId.Ocean;
            else if (height <= SeaLevel + 1 && temperature > -0.25f) biome = BiomeId.Beach;
            else if (height > SeaLevel + 34) biome = BiomeId.Highlands;
            else if (temperature > 0.2f && humidity < 0.05f) biome = BiomeId.Dunes;
            else if (temperature < -0.22f) biome = BiomeId.Frostpine;
            else if (humidity > 0.06f) biome = BiomeId.Woodland;
            else biome = BiomeId.Meadow;

            // Continuous tint so colours blend smoothly across biome borders.
            float hN = Clamp01(humidity * 1.6f + 0.5f);
            float tN = Clamp01(temperature * 1.6f + 0.55f);
            int warm = LerpColor(0xB9B35E, 0x4F9F3A, hN);
            int cool = LerpColor(0x93B08E, 0x5C9670, hN);
            int grass = LerpColor(cool, warm, tN);
            int foliage = LerpColor(grass, 0x2F6E2A, 0.3f);

            return new ColumnSample
            {
                Height = height, Biome = biome, Temperature = temperature, Humidity = humidity,
                GrassTint = grass, FoliageTint = foliage,
            };
        }

        private static int LerpColor(int a, int b, float t)
        {
            int r = (int)(((a >> 16) & 0xFF) + ((((b >> 16) & 0xFF) - ((a >> 16) & 0xFF)) * t));
            int g = (int)(((a >> 8) & 0xFF) + ((((b >> 8) & 0xFF) - ((a >> 8) & 0xFF)) * t));
            int bl = (int)((a & 0xFF) + (((b & 0xFF) - (a & 0xFF)) * t));
            return (r << 16) | (g << 8) | bl;
        }

        /// <summary>True where caves are carved out of the ground.</summary>
        public bool IsCave(int wx, int y, int wz, int surfaceHeight)
        {
            if (y <= 2) return false;
            // Do not breach sea and lake floors: water would hang over open caves.
            if (surfaceHeight < SeaLevel + 1 && y > surfaceHeight - 5) return false;

            double a = _caveA.Noise(wx * 0.021, y * 0.033, wz * 0.021);
            double b = _caveB.Noise(wx * 0.021 + 71.3, y * 0.033 + 13.1, wz * 0.021 - 37.9);
            double width = 0.0045 + Math.Max(0, (SeaLevel - y)) * 0.00008;
            if (a * a + b * b < width) return true;

            if (y < surfaceHeight - 9)
            {
                double cavern = _cavern.Noise(wx * 0.013, y * 0.022, wz * 0.013);
                double threshold = 0.47 + Math.Abs(y - SeaLevel * 0.45) * 0.006;
                if (cavern > threshold) return true;
            }
            return false;
        }

        /// <summary>Fills a chunk with terrain, caves, ores, water and vegetation.</summary>
        public void Generate(ChunkData chunk)
        {
            int sx = Dims.SizeX, sz = Dims.SizeZ, h = Dims.Height;
            int baseX = chunk.Coord.X * sx, baseZ = chunk.Coord.Z * sz;
            int pw = sx + StructureMargin * 2, pd = sz + StructureMargin * 2;

            var columns = _columns;
            if (columns == null || columns.Length < pw * pd) columns = _columns = new ColumnSample[pw * pd];
            for (int pz = 0; pz < pd; pz++)
            for (int px = 0; px < pw; px++)
                columns[px + pw * pz] = SampleColumn(baseX + px - StructureMargin, baseZ + pz - StructureMargin);

            for (int z = 0; z < sz; z++)
            for (int x = 0; x < sx; x++)
            {
                int ci = (x + StructureMargin) + pw * (z + StructureMargin);
                var col = columns[ci];
                int slope = MaxNeighbourDifference(columns, pw, x + StructureMargin, z + StructureMargin);
                FillColumn(chunk, x, z, baseX + x, baseZ + z, col, slope);

                int colIndex = chunk.ColumnIndex(x, z);
                chunk.Biome[colIndex] = (byte)col.Biome;
                chunk.GrassTint[colIndex] = col.GrassTint;
                chunk.FoliageTint[colIndex] = col.FoliageTint;
            }

            PlaceCrystals(chunk, baseX, baseZ);
            PlaceTrees(chunk, columns, pw, pd, baseX, baseZ);
            PlacePlants(chunk, columns, pw, baseX, baseZ);
            chunk.RecalculateMaxY();
        }

        private static int MaxNeighbourDifference(ColumnSample[] columns, int pw, int px, int pz)
        {
            int hgt = columns[px + pw * pz].Height;
            int d = Math.Abs(columns[px + 1 + pw * pz].Height - hgt);
            d = Math.Max(d, Math.Abs(columns[px - 1 + pw * pz].Height - hgt));
            d = Math.Max(d, Math.Abs(columns[px + pw * (pz + 1)].Height - hgt));
            d = Math.Max(d, Math.Abs(columns[px + pw * (pz - 1)].Height - hgt));
            return d;
        }

        private void FillColumn(ChunkData chunk, int x, int z, int wx, int wz, ColumnSample col, int slope)
        {
            var biome = Biomes.Get(col.Biome);
            int height = col.Height;
            bool underwater = height < SeaLevel;

            ushort surface = underwater ? biome.UnderwaterBlock : biome.SurfaceBlock;
            ushort filler = underwater ? biome.UnderwaterBlock : biome.FillerBlock;
            int fillerDepth = biome.FillerDepth;

            if (col.Biome == BiomeId.Highlands)
            {
                if (height > SeaLevel + 52) { surface = Blocks.Snow; filler = Blocks.Stone; fillerDepth = 1; }
                else if (slope >= 3) { surface = Blocks.Stone; filler = Blocks.Stone; }
            }
            else if (slope >= 4 && !underwater && col.Biome != BiomeId.Dunes)
            {
                surface = Blocks.Stone;
                filler = Blocks.Stone;
            }

            for (int y = 0; y <= height && y < Dims.Height; y++)
            {
                ushort block;
                if (y == 0 || (y <= 3 && VoxelMath.Hash01(wx, y, wz, Seed) < 0.6f - y * 0.15f))
                {
                    block = Blocks.Deepstone;
                }
                else if (IsCave(wx, y, wz, height))
                {
                    block = y <= 4 ? Blocks.Water : Blocks.Air;
                }
                else if (y == height) block = surface;
                else if (y > height - fillerDepth) block = filler;
                else block = OreAt(wx, y, wz, height);

                chunk.SetRaw(x, y, z, block);
            }

            // Lakes and seas: fill everything between the terrain and sea level.
            for (int y = height + 1; y <= SeaLevel && y < Dims.Height; y++)
                chunk.SetRaw(x, y, z, Blocks.Water);
        }

        private ushort OreAt(int wx, int y, int wz, int height)
        {
            double n = _ore.Noise(wx * 0.11, y * 0.11, wz * 0.11);
            float r = VoxelMath.Hash01(wx, y, wz, Seed + 17);
            if (y < height - 4 && n > 0.52 && r < 0.75f) return Blocks.CoalOre;
            if (y < SeaLevel + 4 && n < -0.58 && r < 0.6f) return Blocks.IronOre;
            if (y < 12 && r < 0.002f) return Blocks.IronOre;
            return Blocks.Stone;
        }

        /// <summary>
        /// Lumen crystals grow on the ceilings and walls of deep caves, lighting them up.
        /// Only neighbours inside this chunk are checked, which keeps generation chunk-local.
        /// </summary>
        private void PlaceCrystals(ChunkData chunk, int baseX, int baseZ)
        {
            int sx = Dims.SizeX, sz = Dims.SizeZ;
            int top = Math.Min(Dims.Height - 2, SeaLevel - 14);
            for (int y = 4; y < top; y++)
            for (int z = 1; z < sz - 1; z++)
            for (int x = 1; x < sx - 1; x++)
            {
                if (chunk.Get(x, y, z) != Blocks.Stone) continue;
                if (chunk.Get(x, y - 1, z) != Blocks.Air) continue;
                if (VoxelMath.Hash01(baseX + x, y, baseZ + z, Seed + 23) > 0.035f) continue;
                chunk.SetRaw(x, y, z, Blocks.LumenCrystal);
            }
        }

        private void PlaceTrees(ChunkData chunk, ColumnSample[] columns, int pw, int pd, int baseX, int baseZ)
        {
            for (int pz = 1; pz < pd - 1; pz++)
            for (int px = 1; px < pw - 1; px++)
            {
                var col = columns[px + pw * pz];
                var biome = Biomes.Get(col.Biome);
                if (biome.TreeChance <= 0f || col.Height < SeaLevel + 1) continue;
                int wx = baseX + px - StructureMargin, wz = baseZ + pz - StructureMargin;
                if (VoxelMath.Hash01(wx, 0, wz, Seed + 31) >= biome.TreeChance) continue;
                if (MaxNeighbourDifference(columns, pw, px, pz) >= 3) continue;
                if (IsCave(wx, col.Height, wz, col.Height) || IsCave(wx, col.Height - 1, wz, col.Height)) continue;

                int lx = px - StructureMargin, lz = pz - StructureMargin;
                uint variant = VoxelMath.Hash(wx, 1, wz, Seed + 37);
                int groundY = col.Height + 1;
                switch (biome.Tree)
                {
                    case TreeKind.Oak: Oak(chunk, lx, groundY, lz, variant); break;
                    case TreeKind.Pine: Pine(chunk, lx, groundY, lz, variant); break;
                    case TreeKind.Cactus: CactusColumn(chunk, lx, groundY, lz, variant); break;
                }
            }
        }

        private void Put(ChunkData chunk, int x, int y, int z, ushort block, bool overwriteSoft)
        {
            if (!chunk.InBounds(x, y, z)) return;
            ushort existing = chunk.Get(x, y, z);
            bool soft = existing == Blocks.Air || existing == Blocks.TallGrass || existing == Blocks.Emberbloom
                        || existing == Blocks.Skybell || existing == Blocks.DryShrub;
            if (soft || (overwriteSoft && (existing == Blocks.Leaves || existing == Blocks.PineLeaves)))
                chunk.SetRaw(x, y, z, block);
        }

        private void Oak(ChunkData chunk, int x, int y, int z, uint variant)
        {
            int trunk = 4 + (int)(variant % 3);
            int top = y + trunk;
            for (int ly = top - 2; ly <= top + 1; ly++)
            {
                int radius = ly <= top - 1 ? 2 : 1;
                for (int dz = -radius; dz <= radius; dz++)
                for (int dx = -radius; dx <= radius; dx++)
                {
                    bool corner = Math.Abs(dx) == radius && Math.Abs(dz) == radius;
                    if (corner && (radius == 1 || ((variant >> ((dx + dz + ly) & 15)) & 1) == 0)) continue;
                    Put(chunk, x + dx, ly, z + dz, Blocks.Leaves, false);
                }
            }
            for (int i = 0; i < trunk; i++) Put(chunk, x, y + i, z, Blocks.Log, true);
            if (chunk.InBounds(x, y - 1, z) && chunk.Get(x, y - 1, z) == Blocks.Grass) chunk.SetRaw(x, y - 1, z, Blocks.Dirt);
        }

        private void Pine(ChunkData chunk, int x, int y, int z, uint variant)
        {
            int trunk = 6 + (int)(variant % 4);
            int top = y + trunk;
            Put(chunk, x, top + 1, z, Blocks.PineLeaves, false);
            Put(chunk, x, top, z, Blocks.PineLeaves, false);
            int radius = 1;
            for (int ly = top - 1; ly >= y + 2; ly--)
            {
                for (int dz = -radius; dz <= radius; dz++)
                for (int dx = -radius; dx <= radius; dx++)
                {
                    if (Math.Abs(dx) + Math.Abs(dz) > radius + (radius > 1 ? 1 : 0)) continue;
                    Put(chunk, x + dx, ly, z + dz, Blocks.PineLeaves, false);
                }
                radius = radius >= 2 + (int)((variant >> 4) % 2) ? 1 : radius + 1;
            }
            for (int i = 0; i < trunk; i++) Put(chunk, x, y + i, z, Blocks.PineLog, true);
        }

        private void CactusColumn(ChunkData chunk, int x, int y, int z, uint variant)
        {
            if (!chunk.InBounds(x, y - 1, z) || chunk.Get(x, y - 1, z) != Blocks.Sand) return;
            int height = 2 + (int)(variant % 3);
            for (int i = 0; i < height; i++) Put(chunk, x, y + i, z, Blocks.Cactus, false);
        }

        private void PlacePlants(ChunkData chunk, ColumnSample[] columns, int pw, int baseX, int baseZ)
        {
            int sx = Dims.SizeX, sz = Dims.SizeZ;
            for (int z = 0; z < sz; z++)
            for (int x = 0; x < sx; x++)
            {
                var col = columns[(x + StructureMargin) + pw * (z + StructureMargin)];
                int y = col.Height + 1;
                if (y >= Dims.Height || col.Height < SeaLevel) continue;
                var biome = Biomes.Get(col.Biome);
                int wx = baseX + x, wz = baseZ + z;
                float roll = VoxelMath.Hash01(wx, 2, wz, Seed + 41);
                if (roll >= biome.PlantChance) continue;
                if (chunk.Get(x, y, z) != Blocks.Air) continue;

                ushort ground = chunk.Get(x, y - 1, z);
                ushort plant;
                if (ground == Blocks.Grass || ground == Blocks.SnowyGrass)
                {
                    float flower = VoxelMath.Hash01(wx, 3, wz, Seed + 43);
                    if (flower < biome.FlowerShare)
                        plant = VoxelMath.Hash01(wx, 4, wz, Seed + 47) < 0.5f ? Blocks.Emberbloom : Blocks.Skybell;
                    else plant = Blocks.TallGrass;
                }
                else if (ground == Blocks.Sand && col.Biome == BiomeId.Dunes) plant = Blocks.DryShrub;
                else continue;

                chunk.SetRaw(x, y, z, plant);
            }
        }

        /// <summary>
        /// Finds a dry land column near the origin for the player to spawn on.
        /// Returns the world x/z of the column and its surface height.
        /// </summary>
        public void FindSpawnColumn(out int wx, out int wz, out int surface)
        {
            for (int radius = 0; radius < 2048; radius += 8)
            {
                for (int i = 0; i < 16; i++)
                {
                    double angle = i * Math.PI / 8;
                    int x = (int)(Math.Cos(angle) * radius), z = (int)(Math.Sin(angle) * radius);
                    var col = SampleColumn(x, z);
                    if (col.Height >= SeaLevel + 2 && col.Height < SeaLevel + 30 && col.Biome != BiomeId.Ocean)
                    {
                        wx = x; wz = z; surface = col.Height;
                        return;
                    }
                    if (radius == 0) break;
                }
            }
            wx = 0; wz = 0; surface = SampleColumn(0, 0).Height;
        }
    }
}
