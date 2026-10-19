using System;

namespace VoxelWorld.Voxel
{
    /// <summary>
    /// Procedurally paints the game's original block textures (16x16 pixel art).
    /// Output is RGBA32 bytes with row 0 at the bottom, matching Unity's texture layout.
    /// Everything is deterministic so the art is identical on every run.
    /// </summary>
    public static class BlockTextureGenerator
    {
        public const int TileSize = 16;

        private sealed class Tile
        {
            public readonly byte[] Data = new byte[TileSize * TileSize * 4];
            public readonly int Seed;
            public Tile(int seed) { Seed = seed; }

            public void Set(int x, int y, float r, float g, float b, float a = 255f)
            {
                if ((uint)x >= TileSize || (uint)y >= TileSize) return;
                int i = (y * TileSize + x) * 4;
                Data[i] = ToByte(r);
                Data[i + 1] = ToByte(g);
                Data[i + 2] = ToByte(b);
                Data[i + 3] = ToByte(a);
            }

            public void Get(int x, int y, out float r, out float g, out float b, out float a)
            {
                int i = (y * TileSize + x) * 4;
                r = Data[i]; g = Data[i + 1]; b = Data[i + 2]; a = Data[i + 3];
            }

            /// <summary>Per-pixel random value in [0, 1).</summary>
            public float Rand(int x, int y, int salt = 0) => VoxelMath.Hash01(x, y, salt, Seed);

            /// <summary>Smooth tileable value noise in [0, 1).</summary>
            public float Smooth(float x, float y, int cells, int salt = 0)
            {
                float fx = x / TileSize * cells, fy = y / TileSize * cells;
                int ix = (int)Math.Floor(fx), iy = (int)Math.Floor(fy);
                float tx = fx - ix, ty = fy - iy;
                tx = tx * tx * (3 - 2 * tx);
                ty = ty * ty * (3 - 2 * ty);
                float a = Lattice(ix, iy, cells, salt), b = Lattice(ix + 1, iy, cells, salt);
                float c = Lattice(ix, iy + 1, cells, salt), d = Lattice(ix + 1, iy + 1, cells, salt);
                return Lerp(Lerp(a, b, tx), Lerp(c, d, tx), ty);
            }

            private float Lattice(int x, int y, int cells, int salt) =>
                VoxelMath.Hash01(VoxelMath.Mod(x, cells), VoxelMath.Mod(y, cells), 1000 + salt, Seed);
        }

        private static byte ToByte(float v) => (byte)(v < 0 ? 0 : v > 255 ? 255 : v + 0.5f);
        private static float Lerp(float a, float b, float t) => a + (b - a) * t;

        /// <summary>Generates every layer listed in <see cref="BlockTextureLayers"/>.</summary>
        public static byte[][] GenerateAll()
        {
            var layers = new byte[BlockTextureLayers.Count][];
            for (int i = 0; i < layers.Length; i++) layers[i] = Generate(i);
            return layers;
        }

        public static byte[] Generate(int layer)
        {
            var t = new Tile(7919 * (layer + 1));
            switch (layer)
            {
                case BlockTextureLayers.GrassTop: GrassTop(t); break;
                case BlockTextureLayers.GrassSide: Dirt(t); GrassFringe(t, 0x6FAE45, 0x5A9638); break;
                case BlockTextureLayers.Dirt: Dirt(t); break;
                case BlockTextureLayers.Stone: Stone(t, 0x8A8C90, 0.10f); break;
                case BlockTextureLayers.Sand: Speckled(t, 0xDCCB93, 10f, 0xC9B47C, 0.12f); break;
                case BlockTextureLayers.Water: Water(t); break;
                case BlockTextureLayers.LogSide: Bark(t, 0x6B4E31, 0x4E3822); break;
                case BlockTextureLayers.LogTop: LogTop(t); break;
                case BlockTextureLayers.Leaves: Leaves(t, 0xC8C8C8, 0.24f); break;
                case BlockTextureLayers.Planks: Planks(t); break;
                case BlockTextureLayers.Cobblestone: Cells(t, 0x8C8D8F, 0x5D5E62, 5, 22f); break;
                case BlockTextureLayers.CoalOre: Stone(t, 0x8A8C90, 0.10f); Ore(t, 0x222326, 0x3B3C40, 1); break;
                case BlockTextureLayers.IronOre: Stone(t, 0x8A8C90, 0.10f); Ore(t, 0xC9905F, 0xE2B48A, 2); break;
                case BlockTextureLayers.LumenCrystal: Crystal(t); break;
                case BlockTextureLayers.Snow: Speckled(t, 0xF0F5FA, 6f, 0xD9E6F2, 0.10f); break;
                case BlockTextureLayers.SnowySide: Dirt(t); SnowFringe(t); break;
                case BlockTextureLayers.Gravel: Cells(t, 0x8B847C, 0x6A645E, 7, 30f); break;
                case BlockTextureLayers.Deepstone: Stone(t, 0x2E2C36, 0.18f); Ore(t, 0x4A3F66, 0x5B4E7C, 3); break;
                case BlockTextureLayers.TallGrass: Blades(t); break;
                case BlockTextureLayers.Emberbloom: Flower(t, 0xF0642D, 0xFFB347); break;
                case BlockTextureLayers.Skybell: Flower(t, 0x4F8DF5, 0xBFE3FF); break;
                case BlockTextureLayers.CactusSide: CactusSide(t); break;
                case BlockTextureLayers.CactusTop: CactusTop(t); break;
                case BlockTextureLayers.DryShrub: Shrub(t); break;
                case BlockTextureLayers.Sandstone: Sandstone(t); break;
                case BlockTextureLayers.PineLeaves: Leaves(t, 0x3D6B4F, 0.2f); break;
                case BlockTextureLayers.PineLogSide: Bark(t, 0x553A28, 0x3C281A); break;
                default: Speckled(t, 0xFF00FF, 0f, 0xFF00FF, 0f); break;
            }
            return t.Data;
        }

        private static void Rgb(int hex, out float r, out float g, out float b)
        {
            r = (hex >> 16) & 0xFF;
            g = (hex >> 8) & 0xFF;
            b = hex & 0xFF;
        }

        private static void Speckled(Tile t, int baseHex, float jitter, int speckHex, float speckChance)
        {
            Rgb(baseHex, out float br, out float bg, out float bb);
            Rgb(speckHex, out float sr, out float sg, out float sb);
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float n = (t.Rand(x, y) - 0.5f) * 2f * jitter + (t.Smooth(x, y, 4) - 0.5f) * jitter;
                if (t.Rand(x, y, 1) < speckChance) t.Set(x, y, sr + n, sg + n, sb + n);
                else t.Set(x, y, br + n, bg + n, bb + n);
            }
        }

        private static void Dirt(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float n = (t.Smooth(x, y, 4) - 0.5f) * 26f + (t.Rand(x, y) - 0.5f) * 16f;
                float r = 122 + n, g = 87 + n * 0.8f, b = 59 + n * 0.6f;
                float s = t.Rand(x, y, 3);
                if (s < 0.07f) { r -= 30; g -= 24; b -= 18; }
                else if (s > 0.95f) { r += 26; g += 22; b += 16; }
                t.Set(x, y, r, g, b);
            }
        }

        private static void GrassTop(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float v = 200 + (t.Smooth(x, y, 4) - 0.5f) * 30f + (t.Rand(x, y) - 0.5f) * 30f;
                if (t.Rand(x, y, 5) < 0.08f) v += 34;
                t.Set(x, y, v, v, v);
            }
        }

        private static void GrassFringe(Tile t, int hex, int darkHex)
        {
            Rgb(hex, out float r, out float g, out float b);
            Rgb(darkHex, out float dr, out float dg, out float db);
            for (int x = 0; x < TileSize; x++)
            {
                int depth = 3 + (int)(t.Rand(x, 0, 7) * 3f);
                for (int i = 0; i < depth; i++)
                {
                    int y = TileSize - 1 - i;
                    float n = (t.Rand(x, y, 8) - 0.5f) * 22f;
                    if (i == depth - 1) t.Set(x, y, dr + n, dg + n, db + n);
                    else t.Set(x, y, r + n, g + n, b + n);
                }
            }
        }

        private static void SnowFringe(Tile t)
        {
            for (int x = 0; x < TileSize; x++)
            {
                int depth = 3 + (int)(t.Rand(x, 0, 9) * 4f);
                for (int i = 0; i < depth; i++)
                {
                    int y = TileSize - 1 - i;
                    float n = (t.Rand(x, y, 2) - 0.5f) * 10f;
                    t.Set(x, y, 236 + n, 242 + n, 248 + n);
                }
            }
        }

        private static void Stone(Tile t, int hex, float contrast)
        {
            Rgb(hex, out float r, out float g, out float b);
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float n = (t.Smooth(x, y, 4) - 0.5f) * 255f * contrast * 1.6f + (t.Rand(x, y) - 0.5f) * 255f * contrast * 0.6f;
                // Faint cracks along a second noise field's mid band.
                float c = t.Smooth(x, y, 8, 11);
                if (c > 0.47f && c < 0.53f) n -= 18f;
                t.Set(x, y, r + n, g + n, b + n * 1.05f);
            }
        }

        private static void Ore(Tile t, int hex, int lightHex, int salt)
        {
            Rgb(hex, out float r, out float g, out float b);
            Rgb(lightHex, out float lr, out float lg, out float lb);
            for (int cluster = 0; cluster < 5; cluster++)
            {
                int cx = 2 + (int)(VoxelMath.Hash01(cluster, salt, 1, t.Seed) * 12f);
                int cy = 2 + (int)(VoxelMath.Hash01(cluster, salt, 2, t.Seed) * 12f);
                for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++)
                {
                    if (Math.Abs(dx) + Math.Abs(dy) == 2 && t.Rand(cx + dx, cy + dy, salt) < 0.6f) continue;
                    bool light = dx == -1 && dy == 1;
                    if (light) t.Set(cx + dx, cy + dy, lr, lg, lb);
                    else t.Set(cx + dx, cy + dy, r, g, b);
                }
            }
        }

        private static void Water(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float wave = (float)Math.Sin((x + y * 0.5f + t.Smooth(x, y, 2) * 6f) * 0.8f);
                float n = wave * 10f + (t.Rand(x, y) - 0.5f) * 6f;
                float hi = wave > 0.85f ? 30f : 0f;
                t.Set(x, y, 48 + n + hi, 112 + n + hi, 196 + n * 0.5f + hi);
            }
        }

        private static void Bark(Tile t, int hex, int darkHex)
        {
            Rgb(hex, out float r, out float g, out float b);
            Rgb(darkHex, out float dr, out float dg, out float db);
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float stripe = t.Smooth(x * 3f, y * 0.35f, 4);
                float n = (t.Rand(x, y) - 0.5f) * 12f;
                if (stripe < 0.38f) t.Set(x, y, dr + n, dg + n, db + n);
                else t.Set(x, y, r + n + stripe * 12f, g + n + stripe * 9f, b + n + stripe * 6f);
            }
        }

        private static void LogTop(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float dx = x - 7.5f, dy = y - 7.5f;
                float d = (float)Math.Sqrt(dx * dx + dy * dy);
                float n = (t.Rand(x, y) - 0.5f) * 10f;
                if (Math.Max(Math.Abs(dx), Math.Abs(dy)) > 6.6f) { t.Set(x, y, 98 + n, 72 + n, 45 + n); continue; }
                bool ring = ((int)(d + t.Smooth(x, y, 4) * 1.2f) & 1) == 0;
                if (ring) t.Set(x, y, 184 + n, 146 + n, 96 + n);
                else t.Set(x, y, 160 + n, 122 + n, 76 + n);
            }
        }

        private static void Leaves(Tile t, int hex, float holeChance)
        {
            Rgb(hex, out float r, out float g, out float b);
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                if (t.Rand(x, y, 4) < holeChance) { t.Set(x, y, 0, 0, 0, 0); continue; }
                float n = (t.Smooth(x, y, 4) - 0.5f) * 50f + (t.Rand(x, y) - 0.5f) * 40f;
                t.Set(x, y, r + n, g + n, b + n);
            }
        }

        private static void Planks(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            {
                int board = y / 4;
                int offset = (board & 1) == 0 ? 0 : 8;
                for (int x = 0; x < TileSize; x++)
                {
                    float grain = t.Smooth(x * 0.5f, y * 3f + board * 5, 4) - 0.5f;
                    float n = grain * 26f + (t.Rand(x, y) - 0.5f) * 8f + (VoxelMath.Hash01(board, 0, 0, t.Seed) - 0.5f) * 18f;
                    float r = 180 + n, g = 138 + n * 0.85f, b = 86 + n * 0.6f;
                    if (y % 4 == 0) { r -= 46; g -= 40; b -= 30; }
                    if ((x + offset) % 16 == 0) { r -= 30; g -= 26; b -= 20; }
                    t.Set(x, y, r, g, b);
                }
            }
        }

        /// <summary>Voronoi cells with dark borders: cobblestone and gravel.</summary>
        private static void Cells(Tile t, int hex, int mortarHex, int points, float variation)
        {
            Rgb(hex, out float r, out float g, out float b);
            Rgb(mortarHex, out float mr, out float mg, out float mb);
            var px = new float[points * points];
            var py = new float[points * points];
            float cell = TileSize / (float)points;
            for (int j = 0; j < points; j++)
            for (int i = 0; i < points; i++)
            {
                px[j * points + i] = (i + 0.2f + VoxelMath.Hash01(i, j, 1, t.Seed) * 0.6f) * cell;
                py[j * points + i] = (j + 0.2f + VoxelMath.Hash01(i, j, 2, t.Seed) * 0.6f) * cell;
            }

            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float best = float.MaxValue, second = float.MaxValue;
                int bestId = 0;
                for (int k = 0; k < px.Length; k++)
                {
                    for (int oy = -1; oy <= 1; oy++)
                    for (int ox = -1; ox <= 1; ox++)
                    {
                        float dx = x + 0.5f - (px[k] + ox * TileSize), dy = y + 0.5f - (py[k] + oy * TileSize);
                        float d = dx * dx + dy * dy;
                        if (d < best) { second = best; best = d; bestId = k; }
                        else if (d < second) second = d;
                    }
                }
                float edge = (float)(Math.Sqrt(second) - Math.Sqrt(best));
                float cellShade = (VoxelMath.Hash01(bestId, 0, 3, t.Seed) - 0.5f) * variation * 2f;
                float n = (t.Rand(x, y) - 0.5f) * 10f + cellShade;
                if (edge < 0.9f) t.Set(x, y, mr + n * 0.3f, mg + n * 0.3f, mb + n * 0.3f);
                else t.Set(x, y, r + n, g + n, b + n);
            }
        }

        private static void Crystal(Tile t)
        {
            Stone(t, 0x2B2440, 0.15f);
            for (int s = 0; s < 4; s++)
            {
                int cx = 2 + (int)(VoxelMath.Hash01(s, 0, 1, t.Seed) * 12f);
                int cy = 2 + (int)(VoxelMath.Hash01(s, 0, 2, t.Seed) * 12f);
                int len = 3 + (int)(VoxelMath.Hash01(s, 0, 3, t.Seed) * 3f);
                for (int i = -len; i <= len; i++)
                {
                    int w = Math.Max(0, 1 - Math.Abs(i) / 3);
                    for (int k = -w; k <= w; k++)
                    {
                        float bright = 1f - Math.Abs(i) / (float)(len + 1);
                        t.Set(cx + i, cy + i / 2 + k, 90 + 140 * bright, 220 + 35 * bright, 230 + 25 * bright);
                    }
                }
            }
        }

        private static void Blades(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
                t.Set(x, y, 0, 0, 0, 0);
            for (int blade = 0; blade < 9; blade++)
            {
                float bx = 1 + VoxelMath.Hash01(blade, 0, 1, t.Seed) * 14f;
                int height = 7 + (int)(VoxelMath.Hash01(blade, 0, 2, t.Seed) * 8f);
                float lean = (VoxelMath.Hash01(blade, 0, 3, t.Seed) - 0.5f) * 0.6f;
                for (int y = 0; y < height; y++)
                {
                    int x = (int)(bx + lean * y);
                    float v = 150 + y * 6 + (t.Rand(x, y) - 0.5f) * 20f;
                    t.Set(x, y, v, v, v);
                }
            }
        }

        private static void Flower(Tile t, int petalHex, int centreHex)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
                t.Set(x, y, 0, 0, 0, 0);
            Rgb(petalHex, out float r, out float g, out float b);
            Rgb(centreHex, out float cr, out float cg, out float cb);
            for (int y = 0; y < 10; y++) t.Set(8, y, 72, 138, 52);
            t.Set(7, 4, 84, 156, 60); t.Set(6, 5, 84, 156, 60);
            t.Set(9, 6, 84, 156, 60); t.Set(10, 7, 84, 156, 60);
            for (int dy = -2; dy <= 2; dy++)
            for (int dx = -2; dx <= 2; dx++)
            {
                if (Math.Abs(dx) + Math.Abs(dy) > 3) continue;
                float n = (t.Rand(dx + 8, dy + 12) - 0.5f) * 30f;
                if (dx == 0 && dy == 0) t.Set(8, 12, cr, cg, cb);
                else t.Set(8 + dx, 12 + dy, r + n, g + n, b + n);
            }
        }

        private static void CactusSide(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float n = (t.Rand(x, y) - 0.5f) * 14f;
                bool ridge = x % 4 == 1;
                float r = 66 + n, g = 140 + n, b = 64 + n;
                if (ridge) { r += 22; g += 30; b += 18; }
                if (x == 0 || x == 15) { r -= 20; g -= 30; b -= 20; }
                if (ridge && (y + x) % 5 == 0) { r = 230; g = 225; b = 190; }
                t.Set(x, y, r, g, b);
            }
        }

        private static void CactusTop(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float n = (t.Rand(x, y) - 0.5f) * 14f;
                int ring = Math.Max(Math.Abs(x * 2 - 15), Math.Abs(y * 2 - 15)) / 4;
                float shade = ring % 2 == 0 ? 18f : 0f;
                t.Set(x, y, 70 + n + shade, 148 + n + shade, 70 + n + shade * 0.5f);
            }
        }

        private static void Shrub(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
                t.Set(x, y, 0, 0, 0, 0);
            for (int branch = 0; branch < 6; branch++)
            {
                float angle = -1.2f + branch * 0.48f + (VoxelMath.Hash01(branch, 0, 1, t.Seed) - 0.5f) * 0.3f;
                float len = 6 + VoxelMath.Hash01(branch, 0, 2, t.Seed) * 7f;
                for (float s = 0; s < len; s += 0.5f)
                {
                    int x = (int)(8 + Math.Sin(angle) * s);
                    int y = (int)(Math.Cos(angle) * s);
                    float n = (t.Rand(x, y) - 0.5f) * 16f;
                    t.Set(x, y, 128 + n, 92 + n, 52 + n);
                }
            }
        }

        private static void Sandstone(Tile t)
        {
            for (int y = 0; y < TileSize; y++)
            for (int x = 0; x < TileSize; x++)
            {
                float layer = (float)Math.Sin(y * 1.3f + t.Smooth(x, y, 2) * 2f) * 8f;
                float n = (t.Rand(x, y) - 0.5f) * 10f + layer;
                if (y == 0 || y == 15 || y == 8) n -= 22f;
                t.Set(x, y, 214 + n, 192 + n, 138 + n * 0.8f);
            }
        }
    }
}
