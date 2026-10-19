using UnityEngine;

namespace VoxelWorld.Rendering
{
    /// <summary>Wireframe cube drawn around the targeted block. Pulses while the block is being mined.</summary>
    [RequireComponent(typeof(MeshFilter), typeof(MeshRenderer))]
    public sealed class SelectionOutline : MonoBehaviour
    {
        private static readonly int ColorId = Shader.PropertyToID("_Color");

        private MeshRenderer _renderer;
        private Material _material;
        private Mesh _mesh;

        public static SelectionOutline Create(Transform parent, Material lineMaterial)
        {
            var go = new GameObject("Selection Outline", typeof(MeshFilter), typeof(MeshRenderer), typeof(SelectionOutline));
            go.transform.SetParent(parent, false);
            var outline = go.GetComponent<SelectionOutline>();
            outline.Build(lineMaterial);
            return outline;
        }

        private void Build(Material lineMaterial)
        {
            _mesh = new Mesh { name = "Selection Cube" };
            const float e = 0.004f;
            var v = new Vector3[8];
            for (int i = 0; i < 8; i++)
            {
                v[i] = new Vector3((i & 1) == 0 ? -e : 1 + e, (i & 2) == 0 ? -e : 1 + e, (i & 4) == 0 ? -e : 1 + e);
            }
            _mesh.vertices = v;
            // Corner i has x = bit 0, y = bit 1, z = bit 2; the 12 edges join corners differing in one bit.
            var edges = new int[24];
            int n = 0;
            for (int i = 0; i < 8; i++)
            for (int bit = 1; bit <= 4; bit <<= 1)
            {
                if ((i & bit) != 0) continue;
                edges[n++] = i;
                edges[n++] = i | bit;
            }
            _mesh.SetIndices(edges, MeshTopology.Lines, 0);
            _mesh.bounds = new Bounds(new Vector3(0.5f, 0.5f, 0.5f), Vector3.one * 1.1f);
            GetComponent<MeshFilter>().sharedMesh = _mesh;

            _renderer = GetComponent<MeshRenderer>();
            _material = new Material(lineMaterial);
            _renderer.sharedMaterial = _material;
            _renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            _renderer.receiveShadows = false;
            Hide();
        }

        /// <summary>Shows the outline at a block position (block coordinates of the world root).</summary>
        public void Show(int x, int y, int z, float miningProgress)
        {
            transform.localPosition = new Vector3(x, y, z);
            float pulse = miningProgress > 0f ? 0.5f + 0.5f * Mathf.Sin(Time.time * 18f) : 0f;
            var color = Color.Lerp(new Color(0.05f, 0.05f, 0.08f, 0.75f), new Color(1f, 0.75f, 0.3f, 0.95f),
                miningProgress * (0.7f + 0.3f * pulse));
            _material.SetColor(ColorId, color);
            _renderer.enabled = true;
        }

        public void Hide()
        {
            if (_renderer != null) _renderer.enabled = false;
        }

        private void OnDestroy()
        {
            if (_mesh != null) Destroy(_mesh);
            if (_material != null) Destroy(_material);
        }
    }
}
