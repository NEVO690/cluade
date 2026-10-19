using System;

namespace VoxelWorld.Voxel
{
    public struct VoxelHit
    {
        public int X, Y, Z;
        /// <summary>Normal of the face that was hit; the adjacent block is (X+NX, Y+NY, Z+NZ).</summary>
        public int NX, NY, NZ;
        public float Distance;
        public ushort Block;
    }

    /// <summary>Grid traversal raycast (Amanatides &amp; Woo) through the voxel world.</summary>
    public static class VoxelRaycast
    {
        /// <summary>
        /// Walks the voxels along the ray and returns the first selectable block within
        /// <paramref name="maxDistance"/>. Unloaded space stops the ray without a hit.
        /// Direction must be non-zero; it does not need to be normalised.
        /// </summary>
        public static bool Cast(IVoxelReader world, BlockRegistry registry,
            float ox, float oy, float oz, float dx, float dy, float dz, float maxDistance, out VoxelHit hit)
        {
            hit = default;
            float len = (float)Math.Sqrt(dx * dx + dy * dy + dz * dz);
            if (len < 1e-6f) return false;
            dx /= len; dy /= len; dz /= len;

            int x = VoxelMath.FloorToInt(ox), y = VoxelMath.FloorToInt(oy), z = VoxelMath.FloorToInt(oz);
            int stepX = dx > 0 ? 1 : (dx < 0 ? -1 : 0);
            int stepY = dy > 0 ? 1 : (dy < 0 ? -1 : 0);
            int stepZ = dz > 0 ? 1 : (dz < 0 ? -1 : 0);

            float tDeltaX = stepX != 0 ? Math.Abs(1f / dx) : float.PositiveInfinity;
            float tDeltaY = stepY != 0 ? Math.Abs(1f / dy) : float.PositiveInfinity;
            float tDeltaZ = stepZ != 0 ? Math.Abs(1f / dz) : float.PositiveInfinity;

            float tMaxX = stepX > 0 ? (x + 1 - ox) * tDeltaX : (stepX < 0 ? (ox - x) * tDeltaX : float.PositiveInfinity);
            float tMaxY = stepY > 0 ? (y + 1 - oy) * tDeltaY : (stepY < 0 ? (oy - y) * tDeltaY : float.PositiveInfinity);
            float tMaxZ = stepZ > 0 ? (z + 1 - oz) * tDeltaZ : (stepZ < 0 ? (oz - z) * tDeltaZ : float.PositiveInfinity);

            int nx = 0, ny = 0, nz = 0;
            float t = 0f;
            // Bounded loop: a ray of length L crosses at most ~3L cells.
            int maxSteps = (int)(maxDistance * 3f) + 3;
            for (int i = 0; i < maxSteps && t <= maxDistance; i++)
            {
                ushort block = world.GetBlock(x, y, z);
                if (block == Blocks.Unloaded) return false;
                if (block != Blocks.Air && registry[block].IsSelectable)
                {
                    hit = new VoxelHit { X = x, Y = y, Z = z, NX = nx, NY = ny, NZ = nz, Distance = t, Block = block };
                    return true;
                }

                if (tMaxX < tMaxY && tMaxX < tMaxZ)
                {
                    x += stepX; t = tMaxX; tMaxX += tDeltaX;
                    nx = -stepX; ny = 0; nz = 0;
                }
                else if (tMaxY < tMaxZ)
                {
                    y += stepY; t = tMaxY; tMaxY += tDeltaY;
                    nx = 0; ny = -stepY; nz = 0;
                }
                else
                {
                    z += stepZ; t = tMaxZ; tMaxZ += tDeltaZ;
                    nx = 0; ny = 0; nz = -stepZ;
                }
            }
            return false;
        }
    }
}
