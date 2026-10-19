using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace VoxelWorld.Voxel
{
    /// <summary>
    /// Interleaved chunk vertex. Layout must match the vertex attribute descriptors in
    /// <c>ChunkRenderer</c>: position (3 floats), normal (3 floats), colour (4 unorm bytes),
    /// texcoord0 (u, v, texture layer).
    /// Colour rgb is biome tint times face shade; alpha is ambient occlusion (1 = unoccluded).
    /// A texture layer of 512 or more marks an emissive face.
    /// </summary>
    [StructLayout(LayoutKind.Sequential)]
    public struct VoxelVertex
    {
        public float PX, PY, PZ;
        public float NX, NY, NZ;
        public byte R, G, B, A;
        public float U, V, Layer;

        public const int EmissiveLayerOffset = 512;
        public const int SizeInBytes = 40;
    }

    /// <summary>Reusable output buffers of the mesher.</summary>
    public sealed class ChunkMeshData
    {
        public readonly List<VoxelVertex> Vertices = new List<VoxelVertex>(8192);
        public readonly List<int> SolidIndices = new List<int>(12288);
        public readonly List<int> WaterIndices = new List<int>(1024);

        /// <summary>Solid indices followed by water indices, ready for upload.</summary>
        public readonly List<int> CombinedIndices = new List<int>(13312);

        public float MinY, MaxY;

        public int SolidIndexCount => SolidIndices.Count;
        public int WaterIndexCount => WaterIndices.Count;
        public bool IsEmpty => Vertices.Count == 0;

        public void Clear()
        {
            Vertices.Clear();
            SolidIndices.Clear();
            WaterIndices.Clear();
            CombinedIndices.Clear();
            MinY = 0f;
            MaxY = 0f;
        }

        public void Combine()
        {
            CombinedIndices.Clear();
            CombinedIndices.AddRange(SolidIndices);
            CombinedIndices.AddRange(WaterIndices);
        }
    }
}
