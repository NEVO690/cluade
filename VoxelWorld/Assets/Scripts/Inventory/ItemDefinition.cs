namespace VoxelWorld.Inventory
{
    /// <summary>
    /// Data for an item type. Block items use the block's id as their item id; other items
    /// (tools, materials) use ids from <see cref="ItemRegistry.FirstNonBlockId"/> upwards.
    /// </summary>
    public sealed class ItemDefinition
    {
        public int Id { get; internal set; }
        public string Name;
        public string DisplayName;
        public int MaxStack = 64;

        /// <summary>Block placed when the item is used on the world, or 0 for none.</summary>
        public ushort PlacesBlock;

        /// <summary>Texture-array layer used to draw the item's icon.</summary>
        public int IconLayer;
        public bool IconIsBlock;

        public bool IsPlaceable => PlacesBlock != 0;
    }
}
