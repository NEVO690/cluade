using System;
using System.Collections.Generic;
using VoxelWorld.Voxel;

namespace VoxelWorld.Inventory
{
    /// <summary>All item types. Block items are created automatically from the block registry.</summary>
    public sealed class ItemRegistry
    {
        public const int FirstNonBlockId = 1000;

        private readonly Dictionary<int, ItemDefinition> _items = new Dictionary<int, ItemDefinition>();
        private readonly Dictionary<string, ItemDefinition> _byName = new Dictionary<string, ItemDefinition>(StringComparer.Ordinal);
        private int _nextId = FirstNonBlockId;

        public IEnumerable<ItemDefinition> All => _items.Values;

        public static ItemRegistry CreateDefault(BlockRegistry blocks)
        {
            var items = new ItemRegistry();
            foreach (var block in blocks.All)
            {
                if (block.Id == Blocks.Air || block.Id == Blocks.Unloaded || block.RenderType == BlockRenderType.Liquid) continue;
                items.RegisterWithId(block.Id, new ItemDefinition
                {
                    Name = block.Name,
                    DisplayName = block.DisplayName,
                    PlacesBlock = block.Id,
                    IconLayer = block.SideTexture,
                    IconIsBlock = block.RenderType == BlockRenderType.Cube || block.RenderType == BlockRenderType.CutoutCube,
                });
            }
            return items;
        }

        private void RegisterWithId(int id, ItemDefinition def)
        {
            def.Id = id;
            if (string.IsNullOrEmpty(def.DisplayName)) def.DisplayName = def.Name;
            _items.Add(id, def);
            _byName.Add(def.Name, def);
        }

        /// <summary>Registers a non-block item and returns its new id.</summary>
        public int Register(ItemDefinition def)
        {
            if (def == null) throw new ArgumentNullException(nameof(def));
            if (_byName.ContainsKey(def.Name)) throw new ArgumentException($"Item '{def.Name}' already registered.");
            int id = _nextId++;
            RegisterWithId(id, def);
            return id;
        }

        public bool TryGet(int id, out ItemDefinition def) => _items.TryGetValue(id, out def);

        public ItemDefinition Get(int id) => _items.TryGetValue(id, out var def) ? def : null;

        public bool TryGet(string name, out ItemDefinition def) => _byName.TryGetValue(name, out def);

        public int MaxStackOf(int id) => _items.TryGetValue(id, out var def) ? def.MaxStack : 64;
    }
}
