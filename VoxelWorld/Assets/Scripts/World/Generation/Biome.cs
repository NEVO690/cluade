using VoxelWorld.Voxel;

namespace VoxelWorld.World.Generation
{
    public enum BiomeId : byte
    {
        Ocean = 0,
        Beach = 1,
        Meadow = 2,
        Woodland = 3,
        Dunes = 4,
        Frostpine = 5,
        Highlands = 6,
    }

    /// <summary>Surface materials and vegetation settings of one biome.</summary>
    public sealed class BiomeDefinition
    {
        public BiomeId Id;
        public string DisplayName;
        public ushort SurfaceBlock;
        public ushort FillerBlock;
        public int FillerDepth = 3;
        public ushort UnderwaterBlock = Blocks.Sand;

        /// <summary>Chance per surface column of growing a tree.</summary>
        public float TreeChance;
        public TreeKind Tree = TreeKind.Oak;

        /// <summary>Chance per surface column of a plant (grass/flower/shrub).</summary>
        public float PlantChance;
        public float FlowerShare;

        public int GrassColor;
        public int FoliageColor;
        /// <summary>Fog/sky colour hint for the atmosphere system.</summary>
        public int AtmosphereColor;
    }

    public enum TreeKind : byte
    {
        None,
        Oak,
        Pine,
        Cactus,
    }

    public static class Biomes
    {
        public static readonly BiomeDefinition[] All =
        {
            new BiomeDefinition
            {
                Id = BiomeId.Ocean, DisplayName = "Open Water", SurfaceBlock = Blocks.Sand, FillerBlock = Blocks.Sand,
                UnderwaterBlock = Blocks.Gravel, GrassColor = 0x6DA548, FoliageColor = 0x5A9A3E, AtmosphereColor = 0x8EC5F0,
            },
            new BiomeDefinition
            {
                Id = BiomeId.Beach, DisplayName = "Shoreline", SurfaceBlock = Blocks.Sand, FillerBlock = Blocks.Sand,
                FillerDepth = 4, PlantChance = 0.01f, GrassColor = 0x7DB651, FoliageColor = 0x63A644, AtmosphereColor = 0x9CCDF2,
            },
            new BiomeDefinition
            {
                Id = BiomeId.Meadow, DisplayName = "Sunlit Meadow", SurfaceBlock = Blocks.Grass, FillerBlock = Blocks.Dirt,
                TreeChance = 0.004f, PlantChance = 0.22f, FlowerShare = 0.18f,
                GrassColor = 0x7CC04F, FoliageColor = 0x5FAE3E, AtmosphereColor = 0x9BCBF2,
            },
            new BiomeDefinition
            {
                Id = BiomeId.Woodland, DisplayName = "Old Woodland", SurfaceBlock = Blocks.Grass, FillerBlock = Blocks.Dirt,
                TreeChance = 0.045f, PlantChance = 0.14f, FlowerShare = 0.08f,
                GrassColor = 0x5EA542, FoliageColor = 0x3F8A2F, AtmosphereColor = 0x8DBFE0,
            },
            new BiomeDefinition
            {
                Id = BiomeId.Dunes, DisplayName = "Amber Dunes", SurfaceBlock = Blocks.Sand, FillerBlock = Blocks.Sandstone,
                FillerDepth = 5, TreeChance = 0.006f, Tree = TreeKind.Cactus, PlantChance = 0.012f,
                GrassColor = 0xB5B65A, FoliageColor = 0xA4AA4E, AtmosphereColor = 0xE8D3A8,
            },
            new BiomeDefinition
            {
                Id = BiomeId.Frostpine, DisplayName = "Frostpine Taiga", SurfaceBlock = Blocks.SnowyGrass, FillerBlock = Blocks.Dirt,
                TreeChance = 0.03f, Tree = TreeKind.Pine, PlantChance = 0.03f,
                GrassColor = 0x86B48E, FoliageColor = 0x4F7F62, AtmosphereColor = 0xC4D8EA,
            },
            new BiomeDefinition
            {
                Id = BiomeId.Highlands, DisplayName = "Stone Highlands", SurfaceBlock = Blocks.Grass, FillerBlock = Blocks.Dirt,
                FillerDepth = 2, TreeChance = 0.006f, Tree = TreeKind.Pine, PlantChance = 0.08f,
                GrassColor = 0x8AAE5E, FoliageColor = 0x5A8A48, AtmosphereColor = 0xB3CCE4,
            },
        };

        public static BiomeDefinition Get(BiomeId id) => All[(int)id];
    }
}
