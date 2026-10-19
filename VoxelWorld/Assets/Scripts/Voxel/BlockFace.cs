namespace VoxelWorld.Voxel
{
    /// <summary>The six faces of a voxel, in the order used by the mesher.</summary>
    public enum BlockFace : byte
    {
        East = 0,   // +X
        West = 1,   // -X
        Up = 2,     // +Y
        Down = 3,   // -Y
        North = 4,  // +Z
        South = 5,  // -Z
    }

    public static class BlockFaces
    {
        public const int Count = 6;

        public static readonly int[] DX = { 1, -1, 0, 0, 0, 0 };
        public static readonly int[] DY = { 0, 0, 1, -1, 0, 0 };
        public static readonly int[] DZ = { 0, 0, 0, 0, 1, -1 };

        /// <summary>
        /// Corner offsets (x, y, z) of each face's quad. Corners are ordered so that
        /// triangles (0,1,2) and (0,2,3) are clockwise when seen from outside the block,
        /// which is Unity's front-face winding. For side faces corner 0 is bottom-left,
        /// 1 top-left, 2 top-right and 3 bottom-right as seen from outside.
        /// </summary>
        public static readonly int[,,] Corners =
        {
            { { 1, 0, 0 }, { 1, 1, 0 }, { 1, 1, 1 }, { 1, 0, 1 } }, // East
            { { 0, 0, 1 }, { 0, 1, 1 }, { 0, 1, 0 }, { 0, 0, 0 } }, // West
            { { 0, 1, 0 }, { 0, 1, 1 }, { 1, 1, 1 }, { 1, 1, 0 } }, // Up
            { { 0, 0, 1 }, { 0, 0, 0 }, { 1, 0, 0 }, { 1, 0, 1 } }, // Down
            { { 1, 0, 1 }, { 1, 1, 1 }, { 0, 1, 1 }, { 0, 0, 1 } }, // North
            { { 0, 0, 0 }, { 0, 1, 0 }, { 1, 1, 0 }, { 1, 0, 0 } }, // South
        };

        /// <summary>Texture coordinates for corners 0..3.</summary>
        public static readonly float[] CornerU = { 0f, 0f, 1f, 1f };
        public static readonly float[] CornerV = { 0f, 1f, 1f, 0f };

        /// <summary>Directional shading baked into vertex colours so blocks read clearly.</summary>
        public static readonly float[] Shade = { 0.86f, 0.86f, 1f, 0.62f, 0.76f, 0.76f };

        public static BlockFace FromNormal(int nx, int ny, int nz)
        {
            if (nx > 0) return BlockFace.East;
            if (nx < 0) return BlockFace.West;
            if (ny > 0) return BlockFace.Up;
            if (ny < 0) return BlockFace.Down;
            if (nz > 0) return BlockFace.North;
            return BlockFace.South;
        }
    }
}
