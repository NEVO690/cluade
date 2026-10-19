using System;
using System.Collections.Generic;

namespace VoxelWorld.Voxel
{
    /// <summary>
    /// Holds every block definition, indexed by id. Lookups are array accesses so the
    /// mesher and physics can query block properties in tight loops.
    /// </summary>
    public sealed class BlockRegistry
    {
        public const ushort AirId = 0;

        private readonly List<BlockDefinition> _blocks = new List<BlockDefinition>();
        private readonly Dictionary<string, BlockDefinition> _byName = new Dictionary<string, BlockDefinition>(StringComparer.Ordinal);

        // Flattened property tables for hot paths.
        private bool[] _solid = Array.Empty<bool>();
        private bool[] _opaque = Array.Empty<bool>();
        private BlockRenderType[] _renderType = Array.Empty<BlockRenderType>();

        public int Count => _blocks.Count;

        public BlockDefinition this[ushort id] => id < _blocks.Count ? _blocks[id] : _blocks[AirId];

        public IReadOnlyList<BlockDefinition> All => _blocks;

        /// <summary>Registers a block. Ids are assigned sequentially in registration order.</summary>
        public ushort Register(BlockDefinition definition)
        {
            if (definition == null) throw new ArgumentNullException(nameof(definition));
            if (string.IsNullOrEmpty(definition.Name)) throw new ArgumentException("Block needs a name.");
            if (_byName.ContainsKey(definition.Name)) throw new ArgumentException($"Block '{definition.Name}' already registered.");
            if (_blocks.Count >= ushort.MaxValue) throw new InvalidOperationException("Too many block types.");

            definition.Id = (ushort)_blocks.Count;
            if (string.IsNullOrEmpty(definition.DisplayName)) definition.DisplayName = definition.Name;
            _blocks.Add(definition);
            _byName.Add(definition.Name, definition);
            RebuildTables();
            return definition.Id;
        }

        public bool TryGet(string name, out BlockDefinition definition) => _byName.TryGetValue(name, out definition);

        public ushort IdOf(string name)
        {
            if (!_byName.TryGetValue(name, out var def)) throw new KeyNotFoundException($"Unknown block '{name}'.");
            return def.Id;
        }

        public bool IsSolid(ushort id) => id < _solid.Length && _solid[id];
        public bool IsOpaque(ushort id) => id < _opaque.Length && _opaque[id];
        public BlockRenderType RenderTypeOf(ushort id) => id < _renderType.Length ? _renderType[id] : BlockRenderType.None;

        private void RebuildTables()
        {
            int n = _blocks.Count;
            _solid = new bool[n];
            _opaque = new bool[n];
            _renderType = new BlockRenderType[n];
            for (int i = 0; i < n; i++)
            {
                _solid[i] = _blocks[i].IsSolid;
                _opaque[i] = _blocks[i].IsOpaque;
                _renderType[i] = _blocks[i].RenderType;
            }
        }
    }
}
