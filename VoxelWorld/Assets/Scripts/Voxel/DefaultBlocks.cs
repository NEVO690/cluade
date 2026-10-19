using System;
using T = VoxelWorld.Voxel.BlockTextureLayers;

namespace VoxelWorld.Voxel
{
    /// <summary>Creates the registry with the game's built-in blocks.</summary>
    public static class DefaultBlocks
    {
        public static BlockRegistry Create()
        {
            var r = new BlockRegistry();

            Add(r, Blocks.Air, new BlockDefinition
            {
                Name = "air", DisplayName = "Air", RenderType = BlockRenderType.None,
                IsSolid = false, IsSelectable = false, IsReplaceable = true, Hardness = 0f,
            });
            Add(r, Blocks.Unloaded, new BlockDefinition
            {
                Name = "unloaded", DisplayName = "Unloaded", RenderType = BlockRenderType.None,
                IsSolid = true, IsSelectable = false, Hardness = -1f,
            });
            Add(r, Blocks.Deepstone, Solid("deepstone", "Deepstone", -1f, T.Deepstone, ToolType.Pickaxe));
            Add(r, Blocks.Stone, Solid("stone", "Stone", 1.6f, T.Stone, ToolType.Pickaxe, drop: Blocks.Cobblestone));
            Add(r, Blocks.Dirt, Solid("dirt", "Dirt", 0.5f, T.Dirt, ToolType.Shovel));
            Add(r, Blocks.Grass, new BlockDefinition
            {
                Name = "grass", DisplayName = "Meadow Turf", Hardness = 0.6f, PreferredTool = ToolType.Shovel,
                TopTint = BlockTint.Grass, DropItem = Blocks.Dirt,
            }.WithTextures(T.GrassTop, T.GrassSide, T.Dirt));
            Add(r, Blocks.Sand, Solid("sand", "Sand", 0.5f, T.Sand, ToolType.Shovel));
            Add(r, Blocks.Gravel, Solid("gravel", "Gravel", 0.6f, T.Gravel, ToolType.Shovel));
            Add(r, Blocks.Water, new BlockDefinition
            {
                Name = "water", DisplayName = "Water", RenderType = BlockRenderType.Liquid,
                IsSolid = false, IsSelectable = false, IsReplaceable = true, Hardness = -1f,
            }.WithTexture(T.Water));
            Add(r, Blocks.Log, new BlockDefinition
            {
                Name = "log", DisplayName = "Oakwood Log", Hardness = 1.2f, PreferredTool = ToolType.Axe,
            }.WithTextures(T.LogTop, T.LogSide, T.LogTop));
            Add(r, Blocks.Leaves, new BlockDefinition
            {
                Name = "leaves", DisplayName = "Leaves", RenderType = BlockRenderType.CutoutCube,
                Hardness = 0.25f, TopTint = BlockTint.Foliage, SideTint = BlockTint.Foliage, BottomTint = BlockTint.Foliage,
                DropItem = 0,
            }.WithTexture(T.Leaves));
            Add(r, Blocks.Planks, Solid("planks", "Planks", 1.0f, T.Planks, ToolType.Axe));
            Add(r, Blocks.Cobblestone, Solid("cobblestone", "Rubblestone", 1.8f, T.Cobblestone, ToolType.Pickaxe));
            Add(r, Blocks.CoalOre, Solid("coal_ore", "Coal Seam", 2.2f, T.CoalOre, ToolType.Pickaxe));
            Add(r, Blocks.IronOre, Solid("iron_ore", "Iron Vein", 2.8f, T.IronOre, ToolType.Pickaxe));
            var crystal = Solid("lumen_crystal", "Lumen Crystal", 2.0f, T.LumenCrystal, ToolType.Pickaxe);
            crystal.Emissive = true;
            Add(r, Blocks.LumenCrystal, crystal);
            Add(r, Blocks.Snow, Solid("snow", "Snow", 0.3f, T.Snow, ToolType.Shovel));
            Add(r, Blocks.SnowyGrass, new BlockDefinition
            {
                Name = "snowy_grass", DisplayName = "Frosted Turf", Hardness = 0.6f, PreferredTool = ToolType.Shovel,
                DropItem = Blocks.Dirt,
            }.WithTextures(T.Snow, T.SnowySide, T.Dirt));
            Add(r, Blocks.TallGrass, Plant("tall_grass", "Tall Grass", T.TallGrass, BlockTint.Grass));
            Add(r, Blocks.Emberbloom, Plant("emberbloom", "Emberbloom", T.Emberbloom, BlockTint.None, dropsSelf: true));
            Add(r, Blocks.Skybell, Plant("skybell", "Skybell", T.Skybell, BlockTint.None, dropsSelf: true));
            Add(r, Blocks.Cactus, new BlockDefinition
            {
                Name = "cactus", DisplayName = "Spinecactus", Hardness = 0.4f,
            }.WithTextures(T.CactusTop, T.CactusSide, T.CactusTop));
            Add(r, Blocks.DryShrub, Plant("dry_shrub", "Dry Shrub", T.DryShrub, BlockTint.None));
            Add(r, Blocks.Sandstone, Solid("sandstone", "Sandstone", 1.2f, T.Sandstone, ToolType.Pickaxe));
            Add(r, Blocks.PineLeaves, new BlockDefinition
            {
                Name = "pine_leaves", DisplayName = "Pine Needles", RenderType = BlockRenderType.CutoutCube,
                Hardness = 0.25f, DropItem = 0,
            }.WithTexture(T.PineLeaves));
            Add(r, Blocks.PineLog, new BlockDefinition
            {
                Name = "pine_log", DisplayName = "Pine Log", Hardness = 1.2f, PreferredTool = ToolType.Axe,
            }.WithTextures(T.LogTop, T.PineLogSide, T.LogTop));

            // Blocks drop themselves unless configured otherwise.
            foreach (var def in r.All)
            {
                if (def.DropItem < 0) def.DropItem = def.Id;
            }
            return r;
        }

        private static void Add(BlockRegistry registry, ushort expectedId, BlockDefinition def)
        {
            ushort id = registry.Register(def);
            if (id != expectedId)
                throw new InvalidOperationException($"Block '{def.Name}' registered as {id}, expected {expectedId}.");
        }

        private static BlockDefinition Solid(string name, string display, float hardness, int texture,
            ToolType tool, int drop = -1)
        {
            return new BlockDefinition
            {
                Name = name, DisplayName = display, Hardness = hardness, PreferredTool = tool, DropItem = drop,
            }.WithTexture(texture);
        }

        private static BlockDefinition Plant(string name, string display, int texture, BlockTint tint, bool dropsSelf = false)
        {
            return new BlockDefinition
            {
                Name = name, DisplayName = display, RenderType = BlockRenderType.Cross,
                IsSolid = false, IsReplaceable = !dropsSelf, NeedsSupport = true, Hardness = 0f,
                TopTint = tint, SideTint = tint, BottomTint = tint,
                DropItem = dropsSelf ? -1 : 0,
            }.WithTexture(texture);
        }
    }
}
