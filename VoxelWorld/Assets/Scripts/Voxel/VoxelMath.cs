namespace VoxelWorld.Voxel
{
    public static class VoxelMath
    {
        /// <summary>Integer division rounding toward negative infinity.</summary>
        public static int FloorDiv(int a, int b)
        {
            int q = a / b;
            if ((a % b != 0) && ((a < 0) != (b < 0))) q--;
            return q;
        }

        /// <summary>Always-positive modulo.</summary>
        public static int Mod(int a, int b)
        {
            int m = a % b;
            return m < 0 ? m + b : m;
        }

        public static int FloorToInt(double v)
        {
            int i = (int)v;
            return v < i ? i - 1 : i;
        }

        public static int FloorToInt(float v)
        {
            int i = (int)v;
            return v < i ? i - 1 : i;
        }

        /// <summary>Fast deterministic 32-bit hash of integer coordinates and a seed.</summary>
        public static uint Hash(int x, int y, int z, int seed)
        {
            unchecked
            {
                uint h = (uint)seed * 0x9E3779B1u;
                h ^= (uint)x * 0x85EBCA77u;
                h = (h << 13) | (h >> 19);
                h ^= (uint)y * 0xC2B2AE3Du;
                h = (h << 17) | (h >> 15);
                h ^= (uint)z * 0x27D4EB2Fu;
                h ^= h >> 15;
                h *= 0x2C1B3C6Du;
                h ^= h >> 12;
                h *= 0x297A2D39u;
                h ^= h >> 15;
                return h;
            }
        }

        /// <summary>Hash mapped to [0, 1).</summary>
        public static float Hash01(int x, int y, int z, int seed) => (Hash(x, y, z, seed) & 0xFFFFFF) / 16777216f;
    }
}
