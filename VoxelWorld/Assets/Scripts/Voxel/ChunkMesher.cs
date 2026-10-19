using System;

namespace VoxelWorld.Voxel
{
    /// <summary>
    /// Builds render geometry for a chunk. Only faces adjacent to non-opaque blocks are emitted
    /// (face culling across chunk borders uses the neighbouring chunks), with per-vertex ambient
    /// occlusion and biome tint. An instance keeps scratch buffers, so use one instance per thread.
    /// </summary>
    public sealed class ChunkMesher
    {
        private const float LiquidSurface = 0.875f;
        private static readonly byte[] AoLevels = { 110, 165, 212, 255 };

        private readonly BlockRegistry _registry;
        private readonly ChunkDimensions _dims;

        // Padded copy of the chunk plus a one-block border from its neighbours.
        private readonly ushort[] _padded;
        private readonly int _px, _pz, _py;
        private readonly int[] _ao = new int[4];

        public ChunkMesher(BlockRegistry registry, ChunkDimensions dims)
        {
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
            _dims = dims;
            _px = dims.SizeX + 2;
            _pz = dims.SizeZ + 2;
            _py = dims.Height + 2;
            _padded = new ushort[_px * _pz * _py];
        }

        /// <summary>
        /// Meshes <paramref name="neighbourhood"/>[4] (the centre). The array holds 9 chunks in
        /// row-major order: index = (dx + 1) + 3 * (dz + 1). Missing neighbours are treated as air.
        /// </summary>
        public void Build(ChunkData[] neighbourhood, ChunkMeshData output)
        {
            if (neighbourhood == null || neighbourhood.Length != 9) throw new ArgumentException("Need 9 chunks.");
            var center = neighbourhood[4] ?? throw new ArgumentException("Centre chunk missing.");
            output.Clear();
            if (center.MaxY < 0) return;

            int maxY = Math.Min(_dims.Height - 1, center.MaxY);
            FillPadded(neighbourhood, maxY + 2);

            int sx = _dims.SizeX, sz = _dims.SizeZ;
            output.MinY = float.MaxValue;
            output.MaxY = float.MinValue;

            for (int y = 0; y <= maxY; y++)
            {
                for (int z = 0; z < sz; z++)
                {
                    for (int x = 0; x < sx; x++)
                    {
                        ushort block = _padded[PIndex(x + 1, y + 1, z + 1)];
                        if (block == Blocks.Air) continue;
                        var type = _registry.RenderTypeOf(block);
                        switch (type)
                        {
                            case BlockRenderType.Cube:
                            case BlockRenderType.CutoutCube:
                                EmitCube(center, block, x, y, z, output);
                                break;
                            case BlockRenderType.Cross:
                                EmitCross(center, block, x, y, z, output);
                                break;
                            case BlockRenderType.Liquid:
                                EmitLiquid(block, x, y, z, output);
                                break;
                        }
                    }
                }
            }

            if (output.Vertices.Count == 0)
            {
                output.MinY = output.MaxY = 0f;
            }
            output.Combine();
        }

        private int PIndex(int px, int py, int pz) => px + _px * (pz + _pz * py);

        private void FillPadded(ChunkData[] n, int topExclusive)
        {
            int sx = _dims.SizeX, sz = _dims.SizeZ, h = _dims.Height;
            int rows = Math.Min(topExclusive + 1, _py);
            for (int py = 0; py < rows; py++)
            {
                int y = py - 1;
                for (int pz = 0; pz < _pz; pz++)
                {
                    int z = pz - 1;
                    int cz = z < 0 ? 0 : (z >= sz ? 2 : 1);
                    int lz = z < 0 ? z + sz : (z >= sz ? z - sz : z);
                    for (int px = 0; px < _px; px++)
                    {
                        int x = px - 1;
                        ushort value;
                        if (y < 0) value = Blocks.Deepstone;
                        else if (y >= h) value = Blocks.Air;
                        else
                        {
                            int cx = x < 0 ? 0 : (x >= sx ? 2 : 1);
                            int lx = x < 0 ? x + sx : (x >= sx ? x - sx : x);
                            var chunk = n[cx + 3 * cz];
                            value = chunk == null ? Blocks.Air : chunk.Get(lx, y, lz);
                        }
                        _padded[px + _px * (pz + _pz * py)] = value;
                    }
                }
            }
            // Clear the row just above the copied region so stale data from a previous build is never read.
            if (rows < _py)
            {
                int start = rows * _px * _pz;
                Array.Clear(_padded, start, _px * _pz);
            }
        }

        private bool OpaqueAt(int px, int py, int pz) => _registry.IsOpaque(_padded[PIndex(px, py, pz)]);

        private void EmitCube(ChunkData center, ushort block, int x, int y, int z, ChunkMeshData output)
        {
            var def = _registry[block];
            int px = x + 1, py = y + 1, pz = z + 1;
            bool cutout = def.RenderType == BlockRenderType.CutoutCube;

            for (int f = 0; f < BlockFaces.Count; f++)
            {
                int nx = px + BlockFaces.DX[f], ny = py + BlockFaces.DY[f], nz = pz + BlockFaces.DZ[f];
                ushort neighbour = _padded[PIndex(nx, ny, nz)];
                if (_registry.IsOpaque(neighbour)) continue;
                // Between two identical cutout blocks (leaves) only one of the two touching faces is drawn:
                // the canopy keeps visible depth while the face count is halved.
                if (cutout && neighbour == block && (f & 1) == 1)
                    continue;

                var face = (BlockFace)f;
                int layer = def.TextureForFace(face);
                float shade = def.Emissive ? 1f : BlockFaces.Shade[f];
                int tint = TintFor(center, def.TintForFace(face), x, z);

                byte r = (byte)(((tint >> 16) & 0xFF) * shade);
                byte g = (byte)(((tint >> 8) & 0xFF) * shade);
                byte b = (byte)((tint & 0xFF) * shade);
                float layerValue = def.Emissive ? layer + VoxelVertex.EmissiveLayerOffset : layer;

                int baseIndex = output.Vertices.Count;
                var ao = _ao;
                for (int c = 0; c < 4; c++)
                {
                    int cx = BlockFaces.Corners[f, c, 0];
                    int cy = BlockFaces.Corners[f, c, 1];
                    int cz = BlockFaces.Corners[f, c, 2];
                    ao[c] = def.Emissive ? 3 : CornerAo(f, nx, ny, nz, cx, cy, cz);
                    output.Vertices.Add(new VoxelVertex
                    {
                        PX = x + cx, PY = y + cy, PZ = z + cz,
                        NX = BlockFaces.DX[f], NY = BlockFaces.DY[f], NZ = BlockFaces.DZ[f],
                        R = r, G = g, B = b, A = AoLevels[ao[c]],
                        U = BlockFaces.CornerU[c], V = BlockFaces.CornerV[c], Layer = layerValue,
                    });
                }
                AddQuadIndices(output.SolidIndices, baseIndex, ao[0] + ao[2] >= ao[1] + ao[3]);
                TrackY(output, y, y + 1);
            }
        }

        /// <summary>
        /// Ambient occlusion for one face corner: counts opaque blocks next to the corner in the layer
        /// in front of the face. Returns 0 (darkest) to 3 (open).
        /// </summary>
        private int CornerAo(int f, int nx, int ny, int nz, int cx, int cy, int cz)
        {
            // The two axes spanning the face.
            int ax, ay, az, bx, by, bz;
            if (BlockFaces.DX[f] != 0)
            {
                ax = 0; ay = cy * 2 - 1; az = 0;
                bx = 0; by = 0; bz = cz * 2 - 1;
            }
            else if (BlockFaces.DY[f] != 0)
            {
                ax = cx * 2 - 1; ay = 0; az = 0;
                bx = 0; by = 0; bz = cz * 2 - 1;
            }
            else
            {
                ax = cx * 2 - 1; ay = 0; az = 0;
                bx = 0; by = cy * 2 - 1; bz = 0;
            }

            bool side1 = OpaqueAt(nx + ax, ny + ay, nz + az);
            bool side2 = OpaqueAt(nx + bx, ny + by, nz + bz);
            if (side1 && side2) return 0;
            bool corner = OpaqueAt(nx + ax + bx, ny + ay + by, nz + az + bz);
            return 3 - ((side1 ? 1 : 0) + (side2 ? 1 : 0) + (corner ? 1 : 0));
        }

        private static void AddQuadIndices(System.Collections.Generic.List<int> indices, int b, bool diagonal02)
        {
            if (diagonal02)
            {
                indices.Add(b); indices.Add(b + 1); indices.Add(b + 2);
                indices.Add(b); indices.Add(b + 2); indices.Add(b + 3);
            }
            else
            {
                indices.Add(b + 1); indices.Add(b + 2); indices.Add(b + 3);
                indices.Add(b + 1); indices.Add(b + 3); indices.Add(b);
            }
        }

        private void EmitCross(ChunkData center, ushort block, int x, int y, int z, ChunkMeshData output)
        {
            var def = _registry[block];
            int tint = TintFor(center, def.SideTint, x, z);
            byte r = (byte)((tint >> 16) & 0xFF), g = (byte)((tint >> 8) & 0xFF), b = (byte)(tint & 0xFF);

            // Small deterministic offset so plants do not line up on the grid.
            int wx = center.Coord.X * _dims.SizeX + x, wz = center.Coord.Z * _dims.SizeZ + z;
            float ox = (VoxelMath.Hash01(wx, y, wz, 911) - 0.5f) * 0.3f;
            float oz = (VoxelMath.Hash01(wx, y, wz, 397) - 0.5f) * 0.3f;
            const float inset = 0.15f;
            float x0 = x + inset + ox, x1 = x + 1f - inset + ox;
            float z0 = z + inset + oz, z1 = z + 1f - inset + oz;
            float y0 = y, y1 = y + 1f;

            AddCrossQuad(output, x0, z0, x1, z1, y0, y1, r, g, b, def.SideTexture);
            AddCrossQuad(output, x0, z1, x1, z0, y0, y1, r, g, b, def.SideTexture);
            TrackY(output, y, y + 1);
        }

        private static void AddCrossQuad(ChunkMeshData output, float xa, float za, float xb, float zb,
            float y0, float y1, byte r, byte g, byte b, int layer)
        {
            int baseIndex = output.Vertices.Count;
            AddVertex(output, xa, y0, za, 0f, 0f, r, g, b, layer);
            AddVertex(output, xa, y1, za, 0f, 1f, r, g, b, layer);
            AddVertex(output, xb, y1, zb, 1f, 1f, r, g, b, layer);
            AddVertex(output, xb, y0, zb, 1f, 0f, r, g, b, layer);
            var idx = output.SolidIndices;
            // Front and back so the plant is visible from both sides.
            idx.Add(baseIndex); idx.Add(baseIndex + 1); idx.Add(baseIndex + 2);
            idx.Add(baseIndex); idx.Add(baseIndex + 2); idx.Add(baseIndex + 3);
            idx.Add(baseIndex); idx.Add(baseIndex + 2); idx.Add(baseIndex + 1);
            idx.Add(baseIndex); idx.Add(baseIndex + 3); idx.Add(baseIndex + 2);
        }

        private static void AddVertex(ChunkMeshData output, float x, float y, float z, float u, float v,
            byte r, byte g, byte b, int layer)
        {
            output.Vertices.Add(new VoxelVertex
            {
                PX = x, PY = y, PZ = z,
                NX = 0f, NY = 1f, NZ = 0f,
                R = r, G = g, B = b, A = 255,
                U = u, V = v, Layer = layer,
            });
        }

        private void EmitLiquid(ushort block, int x, int y, int z, ChunkMeshData output)
        {
            var def = _registry[block];
            int px = x + 1, py = y + 1, pz = z + 1;
            ushort above = _padded[PIndex(px, py + 1, pz)];
            bool surface = _registry.RenderTypeOf(above) != BlockRenderType.Liquid;
            float top = surface ? LiquidSurface : 1f;

            for (int f = 0; f < BlockFaces.Count; f++)
            {
                ushort neighbour = _padded[PIndex(px + BlockFaces.DX[f], py + BlockFaces.DY[f], pz + BlockFaces.DZ[f])];
                var nType = _registry.RenderTypeOf(neighbour);
                if (nType == BlockRenderType.Liquid || _registry.IsOpaque(neighbour)) continue;
                if (f == (int)BlockFace.Down && nType != BlockRenderType.None) continue;

                byte shade = (byte)(255 * BlockFaces.Shade[f]);
                int baseIndex = output.Vertices.Count;
                for (int c = 0; c < 4; c++)
                {
                    float cy = BlockFaces.Corners[f, c, 1] == 1 ? top : 0f;
                    output.Vertices.Add(new VoxelVertex
                    {
                        PX = x + BlockFaces.Corners[f, c, 0], PY = y + cy, PZ = z + BlockFaces.Corners[f, c, 2],
                        NX = BlockFaces.DX[f], NY = BlockFaces.DY[f], NZ = BlockFaces.DZ[f],
                        R = shade, G = shade, B = shade, A = 255,
                        U = BlockFaces.CornerU[c], V = BlockFaces.CornerV[c], Layer = def.TextureForFace((BlockFace)f),
                    });
                }
                var idx = output.WaterIndices;
                idx.Add(baseIndex); idx.Add(baseIndex + 1); idx.Add(baseIndex + 2);
                idx.Add(baseIndex); idx.Add(baseIndex + 2); idx.Add(baseIndex + 3);
                TrackY(output, y, y + 1);
            }
        }

        private static int TintFor(ChunkData chunk, BlockTint tint, int x, int z)
        {
            switch (tint)
            {
                case BlockTint.Grass: return chunk.GrassTint[chunk.ColumnIndex(x, z)];
                case BlockTint.Foliage: return chunk.FoliageTint[chunk.ColumnIndex(x, z)];
                default: return 0xFFFFFF;
            }
        }

        private static void TrackY(ChunkMeshData output, float min, float max)
        {
            if (min < output.MinY) output.MinY = min;
            if (max > output.MaxY) output.MaxY = max;
        }
    }
}
