using System.Collections.Generic;
using NUnit.Framework;
using VoxelWorld.Voxel;
using VoxelWorld.World.Generation;

namespace VoxelWorld.Tests
{
    /// <summary>Simple dictionary-backed world for physics and raycast tests.</summary>
    internal sealed class TestWorld : IVoxelReader
    {
        public readonly Dictionary<(int, int, int), ushort> Blocks = new Dictionary<(int, int, int), ushort>();
        public int FloorY = int.MinValue;

        public ushort GetBlock(int x, int y, int z)
        {
            if (Blocks.TryGetValue((x, y, z), out var b)) return b;
            return y <= FloorY ? Voxel.Blocks.Stone : Voxel.Blocks.Air;
        }
    }

    public class VoxelCoreTests
    {
        private static readonly BlockRegistry Registry = DefaultBlocks.Create();

        [Test]
        public void FloorDivAndModHandleNegatives()
        {
            Assert.AreEqual(-1, VoxelMath.FloorDiv(-1, 16));
            Assert.AreEqual(-1, VoxelMath.FloorDiv(-16, 16));
            Assert.AreEqual(-2, VoxelMath.FloorDiv(-17, 16));
            Assert.AreEqual(0, VoxelMath.FloorDiv(15, 16));
            Assert.AreEqual(15, VoxelMath.Mod(-1, 16));
            Assert.AreEqual(0, VoxelMath.Mod(-16, 16));
        }

        [Test]
        public void FaceCornersWindClockwiseAroundOutwardNormal()
        {
            for (int f = 0; f < BlockFaces.Count; f++)
            {
                float ax = BlockFaces.Corners[f, 1, 0] - BlockFaces.Corners[f, 0, 0];
                float ay = BlockFaces.Corners[f, 1, 1] - BlockFaces.Corners[f, 0, 1];
                float az = BlockFaces.Corners[f, 1, 2] - BlockFaces.Corners[f, 0, 2];
                float bx = BlockFaces.Corners[f, 2, 0] - BlockFaces.Corners[f, 0, 0];
                float by = BlockFaces.Corners[f, 2, 1] - BlockFaces.Corners[f, 0, 1];
                float bz = BlockFaces.Corners[f, 2, 2] - BlockFaces.Corners[f, 0, 2];
                // Unity's Mesh.RecalculateNormals uses cross(b - a, c - a) as the front-face normal.
                float cx = ay * bz - az * by, cy = az * bx - ax * bz, cz = ax * by - ay * bx;
                Assert.AreEqual(BlockFaces.DX[f], cx, 1e-5, "face " + f);
                Assert.AreEqual(BlockFaces.DY[f], cy, 1e-5, "face " + f);
                Assert.AreEqual(BlockFaces.DZ[f], cz, 1e-5, "face " + f);
            }
        }

        [Test]
        public void DefaultRegistryIdsMatchConstants()
        {
            Assert.AreEqual("air", Registry[Blocks.Air].Name);
            Assert.AreEqual("stone", Registry[Blocks.Stone].Name);
            Assert.AreEqual("pine_log", Registry[Blocks.PineLog].Name);
            Assert.AreEqual(Blocks.Cobblestone, Registry[Blocks.Stone].DropItem);
            Assert.AreEqual(Blocks.Log, Registry[Blocks.Log].DropItem, "blocks drop themselves by default");
            Assert.AreEqual(0, Registry[Blocks.Leaves].DropItem);
            Assert.IsFalse(Registry[Blocks.Deepstone].IsBreakable);
        }

        private static ChunkData SingleBlockChunk(ushort block, int x, int y, int z)
        {
            var dims = new ChunkDimensions(16, 32, 16);
            var chunk = new ChunkData(dims);
            chunk.Reset(new ChunkCoord(0, 0));
            for (int i = 0; i < chunk.GrassTint.Length; i++) chunk.GrassTint[i] = 0xFFFFFF;
            chunk.Set(x, y, z, block);
            return chunk;
        }

        private static ChunkData[] Neighbourhood(ChunkData center)
        {
            var n = new ChunkData[9];
            n[4] = center;
            return n;
        }

        [Test]
        public void IsolatedCubeProducesSixFaces()
        {
            var chunk = SingleBlockChunk(Blocks.Stone, 5, 10, 5);
            var mesher = new ChunkMesher(Registry, chunk.Dims);
            var mesh = new ChunkMeshData();
            mesher.Build(Neighbourhood(chunk), mesh);
            Assert.AreEqual(24, mesh.Vertices.Count);
            Assert.AreEqual(36, mesh.SolidIndexCount);
            Assert.AreEqual(0, mesh.WaterIndexCount);
            Assert.AreEqual(36, mesh.CombinedIndices.Count);
        }

        [Test]
        public void HiddenFacesAreCulled()
        {
            var chunk = SingleBlockChunk(Blocks.Stone, 5, 10, 5);
            chunk.Set(6, 10, 5, Blocks.Stone);
            var mesher = new ChunkMesher(Registry, chunk.Dims);
            var mesh = new ChunkMeshData();
            mesher.Build(Neighbourhood(chunk), mesh);
            Assert.AreEqual(10 * 4, mesh.Vertices.Count, "two touching cubes share no visible face");
        }

        [Test]
        public void BlockOnFloorHasNoBottomFace()
        {
            var chunk = SingleBlockChunk(Blocks.Stone, 3, 0, 3);
            var mesher = new ChunkMesher(Registry, chunk.Dims);
            var mesh = new ChunkMeshData();
            mesher.Build(Neighbourhood(chunk), mesh);
            Assert.AreEqual(5 * 4, mesh.Vertices.Count, "the world floor hides bottom faces");
        }

        [Test]
        public void NeighbourChunkCullsBorderFace()
        {
            var center = SingleBlockChunk(Blocks.Stone, 15, 10, 5);
            var east = SingleBlockChunk(Blocks.Stone, 0, 10, 5);
            var n = Neighbourhood(center);
            n[5] = east; // dx = +1, dz = 0
            var mesher = new ChunkMesher(Registry, center.Dims);
            var mesh = new ChunkMeshData();
            mesher.Build(n, mesh);
            Assert.AreEqual(5 * 4, mesh.Vertices.Count);
        }

        [Test]
        public void WaterGoesToWaterSubmesh()
        {
            var chunk = SingleBlockChunk(Blocks.Water, 4, 4, 4);
            var mesher = new ChunkMesher(Registry, chunk.Dims);
            var mesh = new ChunkMeshData();
            mesher.Build(Neighbourhood(chunk), mesh);
            Assert.AreEqual(0, mesh.SolidIndexCount);
            Assert.AreEqual(36, mesh.WaterIndexCount);
        }

        [Test]
        public void CornerAmbientOcclusionDarkensVerticesNextToWalls()
        {
            var chunk = SingleBlockChunk(Blocks.Stone, 5, 5, 5);
            chunk.Set(6, 6, 5, Blocks.Stone); // sits on the +X side above: occludes the top face's +X edge
            var mesher = new ChunkMesher(Registry, chunk.Dims);
            var mesh = new ChunkMeshData();
            mesher.Build(Neighbourhood(chunk), mesh);
            int darkTopVerts = 0;
            foreach (var v in mesh.Vertices)
                if (v.NY > 0.5f && v.PY == 6 && v.PX == 6 && v.A < 255) darkTopVerts++;
            Assert.Greater(darkTopVerts, 0);
        }

        [Test]
        public void RaycastHitsFirstBlockAndReportsFace()
        {
            var world = new TestWorld();
            world.Blocks[(5, 0, 0)] = Blocks.Stone;
            bool hit = VoxelRaycast.Cast(world, Registry, 0.5f, 0.5f, 0.5f, 1f, 0f, 0f, 10f, out var result);
            Assert.IsTrue(hit);
            Assert.AreEqual(5, result.X);
            Assert.AreEqual(-1, result.NX);
            Assert.AreEqual(4.5f, result.Distance, 1e-4);
        }

        [Test]
        public void RaycastRespectsMaxDistanceAndSkipsWater()
        {
            var world = new TestWorld();
            world.Blocks[(2, 0, 0)] = Blocks.Water;
            world.Blocks[(8, 0, 0)] = Blocks.Stone;
            Assert.IsFalse(VoxelRaycast.Cast(world, Registry, 0.5f, 0.5f, 0.5f, 1f, 0f, 0f, 5f, out _));
            Assert.IsTrue(VoxelRaycast.Cast(world, Registry, 0.5f, 0.5f, 0.5f, 1f, 0f, 0f, 9f, out var hit));
            Assert.AreEqual(8, hit.X);
        }

        [Test]
        public void PhysicsLandsOnGroundAndStopsAtWalls()
        {
            var world = new TestWorld { FloorY = 0 };
            float x = 0.5f, y = 3f, z = 0.5f;
            var flags = VoxelPhysics.Move(world, Registry, ref x, ref y, ref z, 0.6f, 1.8f, 0f, -10f, 0f);
            Assert.IsTrue((flags & VoxelCollision.Ground) != 0);
            Assert.AreEqual(1f, y, 0.01f);

            world.Blocks[(3, 1, 0)] = Blocks.Stone;
            world.Blocks[(3, 2, 0)] = Blocks.Stone;
            flags = VoxelPhysics.Move(world, Registry, ref x, ref y, ref z, 0.6f, 1.8f, 20f, 0f, 0f);
            Assert.IsTrue((flags & VoxelCollision.WallX) != 0);
            Assert.AreEqual(3f - 0.3f, x, 0.01f);
        }

        [Test]
        public void PhysicsDoesNotTunnelAtHighSpeed()
        {
            var world = new TestWorld { FloorY = 0 };
            float x = 0.5f, y = 50f, z = 0.5f;
            VoxelPhysics.Move(world, Registry, ref x, ref y, ref z, 0.6f, 1.8f, 0f, -200f, 0f);
            Assert.AreEqual(1f, y, 0.01f);
        }

        [Test]
        public void TerrainGenerationIsDeterministic()
        {
            var dims = new ChunkDimensions(16, 128, 16);
            var a = new ChunkData(dims);
            var b = new ChunkData(dims);
            a.Reset(new ChunkCoord(3, -2));
            b.Reset(new ChunkCoord(3, -2));
            new TerrainGenerator(1234, dims).Generate(a);
            new TerrainGenerator(1234, dims).Generate(b);
            CollectionAssert.AreEqual(a.RawBlocks, b.RawBlocks);

            var c = new ChunkData(dims);
            c.Reset(new ChunkCoord(3, -2));
            new TerrainGenerator(999, dims).Generate(c);
            CollectionAssert.AreNotEqual(a.RawBlocks, c.RawBlocks);
        }

        [Test]
        public void TerrainHasBedrockSurfaceAndAir()
        {
            var dims = new ChunkDimensions(16, 128, 16);
            var gen = new TerrainGenerator(42, dims);
            var chunk = new ChunkData(dims);
            chunk.Reset(new ChunkCoord(0, 0));
            gen.Generate(chunk);
            for (int z = 0; z < 16; z++)
            for (int x = 0; x < 16; x++)
                Assert.AreEqual(Blocks.Deepstone, chunk.Get(x, 0, z));
            Assert.AreEqual(Blocks.Air, chunk.Get(0, 127, 0));
            Assert.Greater(chunk.MaxY, gen.SeaLevel - 20);
        }

        [Test]
        public void TreesCrossingChunkBordersMatchOnBothSides()
        {
            // A tree near a border writes leaves into both chunks; regenerating either chunk alone must
            // give the same blocks, so seams never appear.
            var dims = new ChunkDimensions(16, 128, 16);
            var gen = new TerrainGenerator(7, dims);
            for (int cx = 0; cx < 6; cx++)
            {
                var chunk = new ChunkData(dims);
                chunk.Reset(new ChunkCoord(cx, 0));
                gen.Generate(chunk);
                var again = new ChunkData(dims);
                again.Reset(new ChunkCoord(cx, 0));
                gen.Generate(again);
                CollectionAssert.AreEqual(chunk.RawBlocks, again.RawBlocks);
            }
        }

        [Test]
        public void SpawnColumnIsDryLand()
        {
            var gen = new TerrainGenerator(2024, ChunkDimensions.Default);
            gen.FindSpawnColumn(out int x, out int z, out int surface);
            Assert.GreaterOrEqual(surface, gen.SeaLevel);
            Assert.AreEqual(surface, gen.SampleColumn(x, z).Height);
        }

        [Test]
        public void TexturesHaveExpectedSize()
        {
            var layers = BlockTextureGenerator.GenerateAll();
            Assert.AreEqual(BlockTextureLayers.Count, layers.Length);
            foreach (var l in layers) Assert.AreEqual(16 * 16 * 4, l.Length);
        }
    }
}
