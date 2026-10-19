using System;

namespace VoxelWorld.Voxel
{
    /// <summary>Horizontal coordinate of a chunk column.</summary>
    public readonly struct ChunkCoord : IEquatable<ChunkCoord>
    {
        public readonly int X;
        public readonly int Z;

        public ChunkCoord(int x, int z)
        {
            X = x;
            Z = z;
        }

        public bool Equals(ChunkCoord other) => X == other.X && Z == other.Z;
        public override bool Equals(object obj) => obj is ChunkCoord other && Equals(other);
        public override int GetHashCode() => unchecked((X * 73856093) ^ (Z * 19349663));
        public override string ToString() => $"({X}, {Z})";

        public static bool operator ==(ChunkCoord a, ChunkCoord b) => a.Equals(b);
        public static bool operator !=(ChunkCoord a, ChunkCoord b) => !a.Equals(b);

        public ChunkCoord Offset(int dx, int dz) => new ChunkCoord(X + dx, Z + dz);

        public int ChebyshevDistance(ChunkCoord other) => Math.Max(Math.Abs(X - other.X), Math.Abs(Z - other.Z));
    }
}
