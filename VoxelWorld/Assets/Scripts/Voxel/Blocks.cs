namespace VoxelWorld.Voxel
{
    /// <summary>
    /// Ids of the built-in blocks. <see cref="DefaultBlocks"/> registers them in exactly this
    /// order and verifies the ids, so these constants can be used in generation code.
    /// Never reorder: ids are written to save files (via block names, but also kept stable).
    /// </summary>
    public static class Blocks
    {
        public const ushort Air = 0;
        /// <summary>Internal marker returned for positions inside chunks that are not loaded.</summary>
        public const ushort Unloaded = 1;
        public const ushort Deepstone = 2;
        public const ushort Stone = 3;
        public const ushort Dirt = 4;
        public const ushort Grass = 5;
        public const ushort Sand = 6;
        public const ushort Gravel = 7;
        public const ushort Water = 8;
        public const ushort Log = 9;
        public const ushort Leaves = 10;
        public const ushort Planks = 11;
        public const ushort Cobblestone = 12;
        public const ushort CoalOre = 13;
        public const ushort IronOre = 14;
        public const ushort LumenCrystal = 15;
        public const ushort Snow = 16;
        public const ushort SnowyGrass = 17;
        public const ushort TallGrass = 18;
        public const ushort Emberbloom = 19;
        public const ushort Skybell = 20;
        public const ushort Cactus = 21;
        public const ushort DryShrub = 22;
        public const ushort Sandstone = 23;
        public const ushort PineLeaves = 24;
        public const ushort PineLog = 25;
    }
}
