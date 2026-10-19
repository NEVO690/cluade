using System;

namespace VoxelWorld.Voxel
{
    /// <summary>
    /// Paints inventory icons from block textures: full blocks as a small isometric cube
    /// (top, left and right faces with different shading) and plants as their flat sprite.
    /// Output is RGBA32, bottom row first.
    /// </summary>
    public static class BlockIconPainter
    {
        public const int IconSize = 32;

        public static byte[] Paint(BlockDefinition block, byte[][] tiles, int grassTint = 0x7CC04F, int foliageTint = 0x5FAE3E)
        {
            var icon = new byte[IconSize * IconSize * 4];
            bool cube = block.RenderType == BlockRenderType.Cube || block.RenderType == BlockRenderType.CutoutCube;
            if (!cube)
            {
                PaintFlat(icon, tiles[block.SideTexture], TintColor(block.SideTint, grassTint, foliageTint));
                return icon;
            }

            int topTint = TintColor(block.TopTint, grassTint, foliageTint);
            int sideTint = TintColor(block.SideTint, grassTint, foliageTint);

            // Screen space with y pointing down; converted to bottom-up rows when writing.
            // Corners of the cube outline.
            const float cx = 16f;
            float topY = 1.5f, midY = 9f, lowY = 16.5f, bottomY = 31f, sideBottomY = 23.5f;
            float leftX = 1.5f, rightX = 30.5f;

            for (int py = 0; py < IconSize; py++)
            for (int px = 0; px < IconSize; px++)
            {
                float x = px + 0.5f, y = py + 0.5f;
                float a, b;
                byte[] tile;
                float shade;
                int tint;

                // Top face: parallelogram from left corner with edges to top corner and front corner.
                if (Solve(x - leftX, y - midY, cx - leftX, topY - midY, cx - leftX, lowY - midY, out a, out b))
                {
                    tile = tiles[block.TopTexture];
                    shade = 1f;
                    tint = topTint;
                    Sample(tile, a, b, out float r, out float g, out float bl, out float al);
                    Write(icon, px, py, r, g, bl, al, shade, tint);
                }
                // Left face: from left corner, edge to front corner and straight down.
                else if (Solve(x - leftX, y - midY, cx - leftX, lowY - midY, 0f, sideBottomY - midY, out a, out b))
                {
                    tile = tiles[block.SideTexture];
                    shade = 0.78f;
                    tint = sideTint;
                    Sample(tile, a, 1f - b, out float r, out float g, out float bl, out float al);
                    Write(icon, px, py, r, g, bl, al, shade, tint);
                }
                // Right face: from front corner, edge to right corner and straight down.
                else if (Solve(x - cx, y - lowY, rightX - cx, midY - lowY, 0f, bottomY - lowY, out a, out b))
                {
                    tile = tiles[block.SideTexture];
                    shade = 0.6f;
                    tint = sideTint;
                    Sample(tile, a, 1f - b, out float r, out float g, out float bl, out float al);
                    Write(icon, px, py, r, g, bl, al, shade, tint);
                }
            }
            return icon;
        }

        /// <summary>Solves p = a*e1 + b*e2; true when both coefficients are inside [0, 1).</summary>
        private static bool Solve(float px, float py, float e1x, float e1y, float e2x, float e2y, out float a, out float b)
        {
            float det = e1x * e2y - e1y * e2x;
            a = b = 0f;
            if (Math.Abs(det) < 1e-6f) return false;
            a = (px * e2y - py * e2x) / det;
            b = (e1x * py - e1y * px) / det;
            return a >= 0f && a < 1f && b >= 0f && b < 1f;
        }

        private static void Sample(byte[] tile, float u, float v, out float r, out float g, out float b, out float a)
        {
            int size = BlockTextureGenerator.TileSize;
            int tx = Math.Min(size - 1, (int)(u * size));
            int ty = Math.Min(size - 1, (int)(v * size));
            int i = (ty * size + tx) * 4;
            r = tile[i]; g = tile[i + 1]; b = tile[i + 2]; a = tile[i + 3];
        }

        private static void Write(byte[] icon, int px, int screenY, float r, float g, float b, float a, float shade, int tint)
        {
            if (a < 128f) return;
            int row = IconSize - 1 - screenY;
            int i = (row * IconSize + px) * 4;
            icon[i] = Clamp(r * ((tint >> 16) & 0xFF) / 255f * shade);
            icon[i + 1] = Clamp(g * ((tint >> 8) & 0xFF) / 255f * shade);
            icon[i + 2] = Clamp(b * (tint & 0xFF) / 255f * shade);
            icon[i + 3] = 255;
        }

        private static void PaintFlat(byte[] icon, byte[] tile, int tint)
        {
            int size = BlockTextureGenerator.TileSize;
            int scale = IconSize / size;
            for (int y = 0; y < IconSize; y++)
            for (int x = 0; x < IconSize; x++)
            {
                int i = ((y / scale) * size + (x / scale)) * 4;
                if (tile[i + 3] < 128) continue;
                int o = (y * IconSize + x) * 4;
                icon[o] = Clamp(tile[i] * ((tint >> 16) & 0xFF) / 255f);
                icon[o + 1] = Clamp(tile[i + 1] * ((tint >> 8) & 0xFF) / 255f);
                icon[o + 2] = Clamp(tile[i + 2] * (tint & 0xFF) / 255f);
                icon[o + 3] = 255;
            }
        }

        private static int TintColor(BlockTint tint, int grass, int foliage)
        {
            switch (tint)
            {
                case BlockTint.Grass: return grass;
                case BlockTint.Foliage: return foliage;
                default: return 0xFFFFFF;
            }
        }

        private static byte Clamp(float v) => (byte)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
}
