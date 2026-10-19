using NUnit.Framework;
using VoxelWorld.Inventory;
using VoxelWorld.Voxel;
using VoxelWorld.World;

namespace VoxelWorld.Tests
{
    public class InventoryAndEditsTests
    {
        private static readonly BlockRegistry Blocks = DefaultBlocks.Create();

        private static PlayerInventory NewInventory() => new PlayerInventory(ItemRegistry.CreateDefault(Blocks));

        [Test]
        public void BlockItemsExistForPlaceableBlocks()
        {
            var items = ItemRegistry.CreateDefault(Blocks);
            Assert.IsTrue(items.TryGet(Voxel.Blocks.Dirt, out var dirt));
            Assert.AreEqual(Voxel.Blocks.Dirt, dirt.PlacesBlock);
            Assert.IsNull(items.Get(Voxel.Blocks.Water), "liquids are not items");
            Assert.IsNull(items.Get(Voxel.Blocks.Air));
        }

        [Test]
        public void AddStacksUpToLimitThenUsesNewSlots()
        {
            var inv = NewInventory();
            Assert.AreEqual(0, inv.Add(Voxel.Blocks.Dirt, 100));
            Assert.AreEqual(64, inv[0].Count);
            Assert.AreEqual(36, inv[1].Count);
            Assert.AreEqual(100, inv.CountOf(Voxel.Blocks.Dirt));

            Assert.AreEqual(0, inv.Add(Voxel.Blocks.Dirt, 10));
            Assert.AreEqual(46, inv[1].Count, "existing stacks fill first");
        }

        [Test]
        public void AddReportsOverflowWhenFull()
        {
            var inv = new PlayerInventory(ItemRegistry.CreateDefault(Blocks), 9);
            Assert.AreEqual(0, inv.Add(Voxel.Blocks.Stone, 9 * 64));
            Assert.AreEqual(5, inv.Add(Voxel.Blocks.Stone, 5));
            Assert.AreEqual(3, inv.Add(Voxel.Blocks.Sand, 3));
        }

        [Test]
        public void TryRemoveIsAllOrNothing()
        {
            var inv = NewInventory();
            inv.Add(Voxel.Blocks.Planks, 5);
            Assert.IsFalse(inv.TryRemove(Voxel.Blocks.Planks, 6));
            Assert.AreEqual(5, inv.CountOf(Voxel.Blocks.Planks));
            Assert.IsTrue(inv.TryRemove(Voxel.Blocks.Planks, 5));
            Assert.IsTrue(inv[0].IsEmpty);
        }

        [Test]
        public void SelectedSlotWrapsAround()
        {
            var inv = NewInventory();
            inv.SelectedSlot = -1;
            Assert.AreEqual(8, inv.SelectedSlot);
            inv.SelectedSlot = 9;
            Assert.AreEqual(0, inv.SelectedSlot);
        }

        [Test]
        public void ChangedEventFires()
        {
            var inv = NewInventory();
            int calls = 0;
            inv.Changed += () => calls++;
            inv.Add(Voxel.Blocks.Dirt, 1);
            inv.RemoveFromSlot(0, 1);
            Assert.AreEqual(2, calls);
        }

        [Test]
        public void EditsSurviveRegeneration()
        {
            var dims = new ChunkDimensions(16, 64, 16);
            var edits = new WorldEdits();
            var chunk = new ChunkData(dims);
            chunk.Reset(new ChunkCoord(2, 3));
            int index = chunk.Index(4, 60, 5);
            edits.Record(chunk.Coord, index, Voxel.Blocks.Planks);

            // Simulate unloading and reloading: fresh data, then edits applied.
            var reloaded = new ChunkData(dims);
            reloaded.Reset(new ChunkCoord(2, 3));
            edits.ApplyTo(reloaded);
            Assert.AreEqual(Voxel.Blocks.Planks, reloaded.Get(4, 60, 5));
            Assert.AreEqual(60, reloaded.MaxY);

            var other = new ChunkData(dims);
            other.Reset(new ChunkCoord(0, 0));
            edits.ApplyTo(other);
            Assert.AreEqual(Voxel.Blocks.Air, other.Get(4, 60, 5));
        }

        [Test]
        public void ChunkMaxYTracksEdits()
        {
            var chunk = new ChunkData(new ChunkDimensions(16, 64, 16));
            chunk.Reset(new ChunkCoord(0, 0));
            chunk.Set(1, 10, 1, Voxel.Blocks.Stone);
            chunk.Set(1, 20, 1, Voxel.Blocks.Stone);
            Assert.AreEqual(20, chunk.MaxY);
            chunk.Set(1, 20, 1, Voxel.Blocks.Air);
            Assert.AreEqual(10, chunk.MaxY);
        }

        [Test]
        public void IconsAreOpaqueInTheMiddle()
        {
            var tiles = BlockTextureGenerator.GenerateAll();
            var icon = BlockIconPainter.Paint(Blocks[Voxel.Blocks.Grass], tiles);
            int mid = (16 * BlockIconPainter.IconSize + 16) * 4;
            Assert.AreEqual(255, icon[mid + 3]);
            Assert.AreEqual(0, icon[3], "corner of the icon is transparent");
        }
    }
}
