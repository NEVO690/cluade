using System.Collections.Generic;
using UnityEngine;
using VoxelWorld.Inventory;
using VoxelWorld.Voxel;

namespace VoxelWorld.Rendering
{
    /// <summary>Creates and caches UI sprites for items.</summary>
    public sealed class ItemIconFactory
    {
        private readonly Dictionary<int, Sprite> _cache = new Dictionary<int, Sprite>();
        private readonly List<Object> _owned = new List<Object>();
        private readonly BlockRegistry _blocks;
        private readonly ItemRegistry _items;
        private readonly byte[][] _tiles;

        public ItemIconFactory(BlockRegistry blocks, ItemRegistry items, byte[][] tiles)
        {
            _blocks = blocks;
            _items = items;
            _tiles = tiles;
        }

        public Sprite Get(int itemId)
        {
            if (itemId == 0) return null;
            if (_cache.TryGetValue(itemId, out var sprite)) return sprite;

            var item = _items.Get(itemId);
            byte[] pixels;
            if (item != null && item.PlacesBlock != 0)
            {
                pixels = BlockIconPainter.Paint(_blocks[item.PlacesBlock], _tiles);
            }
            else
            {
                // Non-block items: flat tile, or a neutral placeholder for items without art yet.
                pixels = new byte[BlockIconPainter.IconSize * BlockIconPainter.IconSize * 4];
                if (item != null && item.IconLayer >= 0 && item.IconLayer < _tiles.Length)
                {
                    var flat = new BlockDefinition { RenderType = BlockRenderType.Cross, SideTexture = item.IconLayer };
                    pixels = BlockIconPainter.Paint(flat, _tiles);
                }
            }

            var tex = new Texture2D(BlockIconPainter.IconSize, BlockIconPainter.IconSize, TextureFormat.RGBA32, false)
            {
                filterMode = FilterMode.Point,
                wrapMode = TextureWrapMode.Clamp,
                name = "Icon " + itemId,
            };
            tex.SetPixelData(pixels, 0);
            tex.Apply(false, true);
            sprite = Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), 32f);
            sprite.name = tex.name;
            _owned.Add(tex);
            _owned.Add(sprite);
            _cache.Add(itemId, sprite);
            return sprite;
        }

        public void Destroy()
        {
            foreach (var o in _owned) if (o != null) Object.Destroy(o);
            _owned.Clear();
            _cache.Clear();
        }
    }
}
