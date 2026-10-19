using UnityEngine;
using UnityEngine.Rendering;
using VoxelWorld.Voxel;

namespace VoxelWorld.Rendering
{
    /// <summary>
    /// Owns the mesh of one chunk. The mesh has two sub-meshes: opaque/alpha-tested blocks and water.
    /// Vertex data is uploaded with the advanced Mesh API straight from the mesher's buffers.
    /// </summary>
    [RequireComponent(typeof(MeshFilter), typeof(MeshRenderer))]
    public sealed class ChunkRenderer : MonoBehaviour
    {
        private static readonly VertexAttributeDescriptor[] Layout =
        {
            new VertexAttributeDescriptor(VertexAttribute.Position, VertexAttributeFormat.Float32, 3),
            new VertexAttributeDescriptor(VertexAttribute.Normal, VertexAttributeFormat.Float32, 3),
            new VertexAttributeDescriptor(VertexAttribute.Color, VertexAttributeFormat.UNorm8, 4),
            new VertexAttributeDescriptor(VertexAttribute.TexCoord0, VertexAttributeFormat.Float32, 3),
        };

        private const MeshUpdateFlags UploadFlags =
            MeshUpdateFlags.DontRecalculateBounds | MeshUpdateFlags.DontValidateIndices |
            MeshUpdateFlags.DontNotifyMeshUsers;

        private Mesh _mesh;
        private MeshRenderer _renderer;
        private MeshFilter _filter;

        public ChunkCoord Coord { get; private set; }

        public void Initialize(Material solid, Material water)
        {
            _filter = GetComponent<MeshFilter>();
            _renderer = GetComponent<MeshRenderer>();
            _mesh = new Mesh { name = "Chunk" };
            _mesh.MarkDynamic();
            _filter.sharedMesh = _mesh;
            _renderer.sharedMaterials = new[] { solid, water };
            _renderer.shadowCastingMode = ShadowCastingMode.On;
            _renderer.receiveShadows = true;
            _renderer.lightProbeUsage = LightProbeUsage.Off;
            _renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            _renderer.allowOcclusionWhenDynamic = true;
        }

        public void Place(ChunkCoord coord, ChunkDimensions dims)
        {
            Coord = coord;
            transform.localPosition = new Vector3(coord.X * dims.SizeX, 0f, coord.Z * dims.SizeZ);
            transform.localRotation = Quaternion.identity;
            transform.localScale = Vector3.one;
            gameObject.name = $"Chunk {coord.X},{coord.Z}";
        }

        public void Apply(ChunkMeshData data, ChunkDimensions dims)
        {
            if (data.IsEmpty)
            {
                _mesh.Clear();
                _renderer.enabled = false;
                return;
            }

            int vertexCount = data.Vertices.Count;
            int indexCount = data.CombinedIndices.Count;
            _mesh.Clear();
            _mesh.SetVertexBufferParams(vertexCount, Layout);
            _mesh.SetVertexBufferData(data.Vertices, 0, 0, vertexCount, 0, UploadFlags);
            _mesh.SetIndexBufferParams(indexCount, IndexFormat.UInt32);
            _mesh.SetIndexBufferData(data.CombinedIndices, 0, 0, indexCount, UploadFlags);
            _mesh.subMeshCount = 2;
            _mesh.SetSubMesh(0, new SubMeshDescriptor(0, data.SolidIndexCount), UploadFlags);
            _mesh.SetSubMesh(1, new SubMeshDescriptor(data.SolidIndexCount, data.WaterIndexCount), UploadFlags);

            float minY = data.MinY, maxY = Mathf.Max(data.MaxY, minY + 1f);
            _mesh.bounds = new Bounds(
                new Vector3(dims.SizeX * 0.5f, (minY + maxY) * 0.5f, dims.SizeZ * 0.5f),
                new Vector3(dims.SizeX, maxY - minY, dims.SizeZ));
            _renderer.enabled = true;
        }

        public void ClearMesh()
        {
            if (_mesh != null) _mesh.Clear();
            if (_renderer != null) _renderer.enabled = false;
        }

        private void OnDestroy()
        {
            if (_mesh != null) Destroy(_mesh);
        }
    }
}
