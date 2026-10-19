namespace VoxelWorld.Voxel
{
    /// <summary>Read access to blocks in world (block) coordinates.</summary>
    public interface IVoxelReader
    {
        /// <summary>
        /// Returns the block at a world position. Positions below the world return
        /// <see cref="Blocks.Deepstone"/>, above return <see cref="Blocks.Air"/>, and positions in
        /// chunks that are not loaded return <see cref="Blocks.Unloaded"/>.
        /// </summary>
        ushort GetBlock(int x, int y, int z);
    }
}
