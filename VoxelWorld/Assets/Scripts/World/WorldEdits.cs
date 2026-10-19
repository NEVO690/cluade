using System.Collections.Generic;
using VoxelWorld.Voxel;

namespace VoxelWorld.World
{
    /// <summary>
    /// Every block the player changed, grouped by chunk. Generated terrain is never stored:
    /// on load a chunk is regenerated from the seed and these edits are re-applied, so the
    /// world can unload chunks freely and save files stay small.
    /// </summary>
    public sealed class WorldEdits
    {
        private readonly Dictionary<ChunkCoord, Dictionary<int, ushort>> _edits =
            new Dictionary<ChunkCoord, Dictionary<int, ushort>>();

        public int ChunkCount => _edits.Count;

        public IEnumerable<KeyValuePair<ChunkCoord, Dictionary<int, ushort>>> All => _edits;

        public void Record(ChunkCoord chunk, int blockIndex, ushort block)
        {
            if (!_edits.TryGetValue(chunk, out var map))
            {
                map = new Dictionary<int, ushort>();
                _edits.Add(chunk, map);
            }
            map[blockIndex] = block;
        }

        /// <summary>Writes stored edits into freshly generated chunk data.</summary>
        public void ApplyTo(ChunkData chunk)
        {
            if (!_edits.TryGetValue(chunk.Coord, out var map)) return;
            var raw = chunk.RawBlocks;
            foreach (var pair in map)
            {
                if ((uint)pair.Key < (uint)raw.Length) raw[pair.Key] = pair.Value;
            }
            chunk.RecalculateMaxY();
        }

        public bool TryGetChunk(ChunkCoord chunk, out Dictionary<int, ushort> map) => _edits.TryGetValue(chunk, out map);

        public void Clear() => _edits.Clear();
    }
}
