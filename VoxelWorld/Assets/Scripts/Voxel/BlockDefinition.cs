namespace VoxelWorld.Voxel
{
    /// <summary>How a block is turned into geometry by the chunk mesher.</summary>
    public enum BlockRenderType : byte
    {
        /// <summary>Not rendered (air, internal markers).</summary>
        None,
        /// <summary>Full opaque cube. Hides neighbouring faces.</summary>
        Cube,
        /// <summary>Full cube with alpha-tested holes (leaves). Does not hide neighbours.</summary>
        CutoutCube,
        /// <summary>Two crossed quads (grass, flowers).</summary>
        Cross,
        /// <summary>Transparent liquid rendered in the water sub-mesh.</summary>
        Liquid,
    }

    /// <summary>Which biome colour (if any) multiplies a face's texture.</summary>
    public enum BlockTint : byte
    {
        None,
        Grass,
        Foliage,
    }

    /// <summary>Tool family that mines a block faster.</summary>
    public enum ToolType : byte
    {
        None,
        Pickaxe,
        Axe,
        Shovel,
    }

    /// <summary>
    /// Data describing one block type. Instances are registered in a <see cref="BlockRegistry"/>
    /// and looked up by numeric id at runtime; adding a block only requires a new definition.
    /// </summary>
    public sealed class BlockDefinition
    {
        public ushort Id { get; internal set; }

        /// <summary>Stable identifier used in save files, e.g. "stone".</summary>
        public string Name;
        public string DisplayName;

        public BlockRenderType RenderType = BlockRenderType.Cube;

        /// <summary>Blocks the player and creatures.</summary>
        public bool IsSolid = true;

        /// <summary>Can be targeted by the block-selection ray.</summary>
        public bool IsSelectable = true;

        /// <summary>Can be overwritten by placing a block into it (air, water, tall grass).</summary>
        public bool IsReplaceable;

        /// <summary>Breaks when the block below is removed (plants).</summary>
        public bool NeedsSupport;

        /// <summary>Seconds needed to break by hand. Negative means unbreakable, zero is instant.</summary>
        public float Hardness = 1f;

        public ToolType PreferredTool = ToolType.None;

        /// <summary>Minimum tool tier needed for the block to drop anything (0 = hand).</summary>
        public int RequiredToolTier;

        /// <summary>Texture-array layer for the top, side and bottom faces.</summary>
        public int TopTexture;
        public int SideTexture;
        public int BottomTexture;

        public BlockTint TopTint = BlockTint.None;
        public BlockTint SideTint = BlockTint.None;
        public BlockTint BottomTint = BlockTint.None;

        /// <summary>Faces glow (rendered unlit at full brightness).</summary>
        public bool Emissive;

        /// <summary>
        /// Item id given to the player when the block is broken. 0 means nothing; -1 (the default)
        /// is resolved to the block's own item when the registry is built.
        /// </summary>
        public int DropItem = -1;
        public int DropCount = 1;

        /// <summary>True when the face completely hides the face behind it.</summary>
        public bool IsOpaque => RenderType == BlockRenderType.Cube;

        public bool IsBreakable => Hardness >= 0f;

        public BlockDefinition WithTexture(int all)
        {
            TopTexture = SideTexture = BottomTexture = all;
            return this;
        }

        public BlockDefinition WithTextures(int top, int side, int bottom)
        {
            TopTexture = top;
            SideTexture = side;
            BottomTexture = bottom;
            return this;
        }

        public int TextureForFace(BlockFace face)
        {
            switch (face)
            {
                case BlockFace.Up: return TopTexture;
                case BlockFace.Down: return BottomTexture;
                default: return SideTexture;
            }
        }

        public BlockTint TintForFace(BlockFace face)
        {
            switch (face)
            {
                case BlockFace.Up: return TopTint;
                case BlockFace.Down: return BottomTint;
                default: return SideTint;
            }
        }
    }
}
