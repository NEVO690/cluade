using System;

namespace VoxelWorld.Voxel
{
    /// <summary>Axis-aligned box in block coordinates.</summary>
    public struct VoxelBox
    {
        public float MinX, MinY, MinZ, MaxX, MaxY, MaxZ;

        /// <summary>Box with its bottom centre at (x, y, z).</summary>
        public static VoxelBox FromFeet(float x, float y, float z, float width, float height)
        {
            float h = width * 0.5f;
            return new VoxelBox { MinX = x - h, MinY = y, MinZ = z - h, MaxX = x + h, MaxY = y + height, MaxZ = z + h };
        }

        public bool IntersectsBlock(int bx, int by, int bz) =>
            MaxX > bx && MinX < bx + 1 && MaxY > by && MinY < by + 1 && MaxZ > bz && MinZ < bz + 1;
    }

    [Flags]
    public enum VoxelCollision
    {
        None = 0,
        Ground = 1,
        Ceiling = 2,
        WallX = 4,
        WallZ = 8,
    }

    /// <summary>
    /// Kinematic box-versus-voxel collision. Movement is resolved one axis at a time
    /// (Y first, then X, then Z), sub-stepped so that no step moves more than half a block,
    /// which makes tunnelling through blocks impossible at any speed.
    /// </summary>
    public static class VoxelPhysics
    {
        private const float Skin = 0.001f;

        /// <summary>
        /// Moves a box with bottom-centre <paramref name="x"/>,<paramref name="y"/>,<paramref name="z"/>
        /// by the given displacement, stopping at solid blocks. Velocity components that hit a block
        /// are zeroed by the caller using the returned flags.
        /// </summary>
        public static VoxelCollision Move(IVoxelReader world, BlockRegistry registry,
            ref float x, ref float y, ref float z, float width, float height,
            float moveX, float moveY, float moveZ)
        {
            var flags = VoxelCollision.None;
            float largest = Math.Max(Math.Abs(moveX), Math.Max(Math.Abs(moveY), Math.Abs(moveZ)));
            int steps = Math.Max(1, (int)Math.Ceiling(largest / 0.45f));
            float sx = moveX / steps, sy = moveY / steps, sz = moveZ / steps;

            for (int i = 0; i < steps; i++)
            {
                if (sy != 0f)
                {
                    if (MoveAxis(world, registry, ref x, ref y, ref z, width, height, 1, sy))
                    {
                        flags |= sy < 0 ? VoxelCollision.Ground : VoxelCollision.Ceiling;
                        sy = 0f;
                    }
                }
                if (sx != 0f)
                {
                    if (MoveAxis(world, registry, ref x, ref y, ref z, width, height, 0, sx))
                    {
                        flags |= VoxelCollision.WallX;
                        sx = 0f;
                    }
                }
                if (sz != 0f)
                {
                    if (MoveAxis(world, registry, ref x, ref y, ref z, width, height, 2, sz))
                    {
                        flags |= VoxelCollision.WallZ;
                        sz = 0f;
                    }
                }
            }
            return flags;
        }

        /// <summary>Moves along one axis; returns true if a block stopped the movement.</summary>
        private static bool MoveAxis(IVoxelReader world, BlockRegistry registry,
            ref float x, ref float y, ref float z, float width, float height, int axis, float delta)
        {
            var box = VoxelBox.FromFeet(x, y, z, width, height);
            switch (axis)
            {
                case 0: box.MinX += delta; box.MaxX += delta; break;
                case 1: box.MinY += delta; box.MaxY += delta; break;
                default: box.MinZ += delta; box.MaxZ += delta; break;
            }

            int x0 = VoxelMath.FloorToInt(box.MinX + Skin), x1 = VoxelMath.FloorToInt(box.MaxX - Skin);
            int y0 = VoxelMath.FloorToInt(box.MinY + Skin), y1 = VoxelMath.FloorToInt(box.MaxY - Skin);
            int z0 = VoxelMath.FloorToInt(box.MinZ + Skin), z1 = VoxelMath.FloorToInt(box.MaxZ - Skin);

            bool hit = false;
            float limit = delta > 0 ? float.MaxValue : float.MinValue;
            for (int by = y0; by <= y1; by++)
            for (int bz = z0; bz <= z1; bz++)
            for (int bx = x0; bx <= x1; bx++)
            {
                if (!registry.IsSolid(world.GetBlock(bx, by, bz))) continue;
                hit = true;
                switch (axis)
                {
                    case 0: limit = delta > 0 ? Math.Min(limit, bx) : Math.Max(limit, bx + 1); break;
                    case 1: limit = delta > 0 ? Math.Min(limit, by) : Math.Max(limit, by + 1); break;
                    default: limit = delta > 0 ? Math.Min(limit, bz) : Math.Max(limit, bz + 1); break;
                }
            }

            float half = width * 0.5f;
            if (!hit)
            {
                switch (axis)
                {
                    case 0: x += delta; break;
                    case 1: y += delta; break;
                    default: z += delta; break;
                }
                return false;
            }

            // Snap flush against the blocking face.
            switch (axis)
            {
                case 0: x = delta > 0 ? limit - half - Skin : limit + half + Skin; break;
                case 1: y = delta > 0 ? limit - height - Skin : limit + Skin; break;
                default: z = delta > 0 ? limit - half - Skin : limit + half + Skin; break;
            }
            return true;
        }

        /// <summary>True if the box overlaps any solid block.</summary>
        public static bool Overlaps(IVoxelReader world, BlockRegistry registry, VoxelBox box)
        {
            int x0 = VoxelMath.FloorToInt(box.MinX + Skin), x1 = VoxelMath.FloorToInt(box.MaxX - Skin);
            int y0 = VoxelMath.FloorToInt(box.MinY + Skin), y1 = VoxelMath.FloorToInt(box.MaxY - Skin);
            int z0 = VoxelMath.FloorToInt(box.MinZ + Skin), z1 = VoxelMath.FloorToInt(box.MaxZ - Skin);
            for (int by = y0; by <= y1; by++)
            for (int bz = z0; bz <= z1; bz++)
            for (int bx = x0; bx <= x1; bx++)
                if (registry.IsSolid(world.GetBlock(bx, by, bz))) return true;
            return false;
        }

        /// <summary>True if any block overlapping the box is a liquid.</summary>
        public static bool TouchesLiquid(IVoxelReader world, BlockRegistry registry, VoxelBox box)
        {
            int x0 = VoxelMath.FloorToInt(box.MinX), x1 = VoxelMath.FloorToInt(box.MaxX);
            int y0 = VoxelMath.FloorToInt(box.MinY), y1 = VoxelMath.FloorToInt(box.MaxY);
            int z0 = VoxelMath.FloorToInt(box.MinZ), z1 = VoxelMath.FloorToInt(box.MaxZ);
            for (int by = y0; by <= y1; by++)
            for (int bz = z0; bz <= z1; bz++)
            for (int bx = x0; bx <= x1; bx++)
                if (registry.RenderTypeOf(world.GetBlock(bx, by, bz)) == BlockRenderType.Liquid) return true;
            return false;
        }
    }
}
