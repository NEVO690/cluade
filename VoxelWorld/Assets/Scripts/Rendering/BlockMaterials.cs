using UnityEngine;
using VoxelWorld.Voxel;

namespace VoxelWorld.Rendering
{
    /// <summary>
    /// Builds the shared block texture array and the two chunk materials (solid and water).
    /// One material instance of each is shared by every chunk, which keeps draw calls batched
    /// by the SRP Batcher.
    /// </summary>
    public sealed class BlockMaterials
    {
        private static readonly int BlockTexturesId = Shader.PropertyToID("_BlockTextures");

        public Texture2DArray TextureArray { get; private set; }
        public Material Solid { get; private set; }
        public Material Water { get; private set; }
        public Material Line { get; private set; }

        /// <summary>CPU copies of every tile (RGBA32, bottom row first), used for item icons.</summary>
        public byte[][] TilePixels { get; private set; }

        public static BlockMaterials Create()
        {
            var m = new BlockMaterials();
            m.TilePixels = BlockTextureGenerator.GenerateAll();
            m.TextureArray = BuildArray(m.TilePixels);

            m.Solid = new Material(LoadShader("VoxelLit")) { name = "Voxel Solid" };
            m.Solid.SetTexture(BlockTexturesId, m.TextureArray);
            m.Solid.enableInstancing = false;

            m.Water = new Material(LoadShader("VoxelWater")) { name = "Voxel Water" };
            m.Water.SetTexture(BlockTexturesId, m.TextureArray);
            m.Water.renderQueue = 3000;

            m.Line = new Material(LoadShader("VoxelLine")) { name = "Voxel Selection" };
            return m;
        }

        private static Shader LoadShader(string name)
        {
            var shader = Resources.Load<Shader>("Shaders/" + name);
            if (shader == null) shader = Shader.Find("VoxelWorld/" + name);
            if (shader == null || !shader.isSupported)
            {
                Debug.LogError($"[VoxelWorld] Shader '{name}' is missing or unsupported on this GPU/pipeline. " +
                               "Check that the Universal Render Pipeline is active (Voxel World > Configure Project).");
                shader = Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Hidden/InternalErrorShader");
            }
            return shader;
        }

        private static Texture2DArray BuildArray(byte[][] tiles)
        {
            int size = BlockTextureGenerator.TileSize;
            int mipCount = 1;
            for (int s = size; s > 1; s >>= 1) mipCount++;

            var array = new Texture2DArray(size, size, tiles.Length, TextureFormat.RGBA32, mipCount, false)
            {
                name = "Block Textures",
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Repeat,
                anisoLevel = 0,
                mipMapBias = -0.5f,
            };

            for (int layer = 0; layer < tiles.Length; layer++)
            {
                byte[] level = tiles[layer];
                int levelSize = size;
                for (int mip = 0; mip < mipCount; mip++)
                {
                    array.SetPixelData(level, mip, layer);
                    if (levelSize > 1)
                    {
                        level = Downsample(level, levelSize);
                        levelSize >>= 1;
                    }
                }
            }
            array.Apply(false, true);
            return array;
        }

        /// <summary>
        /// 2x2 box filter that weights colour by alpha and boosts alpha slightly, so alpha-tested
        /// leaves keep their coverage instead of vanishing in the distance.
        /// </summary>
        private static byte[] Downsample(byte[] src, int size)
        {
            int half = size >> 1;
            var dst = new byte[half * half * 4];
            for (int y = 0; y < half; y++)
            for (int x = 0; x < half; x++)
            {
                float r = 0, g = 0, b = 0, a = 0;
                for (int oy = 0; oy < 2; oy++)
                for (int ox = 0; ox < 2; ox++)
                {
                    int i = ((y * 2 + oy) * size + (x * 2 + ox)) * 4;
                    float pa = src[i + 3] / 255f;
                    r += src[i] * pa; g += src[i + 1] * pa; b += src[i + 2] * pa; a += pa;
                }
                int o = (y * half + x) * 4;
                if (a > 0f)
                {
                    dst[o] = (byte)Mathf.Clamp(r / a, 0, 255);
                    dst[o + 1] = (byte)Mathf.Clamp(g / a, 0, 255);
                    dst[o + 2] = (byte)Mathf.Clamp(b / a, 0, 255);
                }
                dst[o + 3] = (byte)Mathf.Clamp(a / 4f * 1.35f * 255f, 0, 255);
            }
            return dst;
        }

        public void Destroy()
        {
            if (Solid != null) Object.Destroy(Solid);
            if (Water != null) Object.Destroy(Water);
            if (Line != null) Object.Destroy(Line);
            if (TextureArray != null) Object.Destroy(TextureArray);
        }
    }
}
