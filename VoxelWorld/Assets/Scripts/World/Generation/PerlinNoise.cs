using System;

namespace VoxelWorld.World.Generation
{
    /// <summary>
    /// Seeded gradient (Perlin) noise in 2D and 3D. Instances are immutable after construction
    /// and therefore safe to share between generation threads.
    /// </summary>
    public sealed class PerlinNoise
    {
        private readonly int[] _perm = new int[512];

        public PerlinNoise(int seed)
        {
            var p = new int[256];
            for (int i = 0; i < 256; i++) p[i] = i;
            var rng = new Random(seed);
            for (int i = 255; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                int tmp = p[i]; p[i] = p[j]; p[j] = tmp;
            }
            for (int i = 0; i < 512; i++) _perm[i] = p[i & 255];
        }

        private static double Fade(double t) => t * t * t * (t * (t * 6 - 15) + 10);
        private static double Lerp(double a, double b, double t) => a + t * (b - a);

        private static double Grad2(int hash, double x, double y)
        {
            switch (hash & 7)
            {
                case 0: return x + y;
                case 1: return -x + y;
                case 2: return x - y;
                case 3: return -x - y;
                case 4: return x;
                case 5: return -x;
                case 6: return y;
                default: return -y;
            }
        }

        private static double Grad3(int hash, double x, double y, double z)
        {
            int h = hash & 15;
            double u = h < 8 ? x : y;
            double v = h < 4 ? y : (h == 12 || h == 14 ? x : z);
            return ((h & 1) == 0 ? u : -u) + ((h & 2) == 0 ? v : -v);
        }

        /// <summary>2D noise in roughly [-1, 1].</summary>
        public double Noise(double x, double y)
        {
            int xi = (int)Math.Floor(x), yi = (int)Math.Floor(y);
            double xf = x - xi, yf = y - yi;
            xi &= 255; yi &= 255;
            double u = Fade(xf), v = Fade(yf);
            int aa = _perm[_perm[xi] + yi], ab = _perm[_perm[xi] + yi + 1];
            int ba = _perm[_perm[xi + 1] + yi], bb = _perm[_perm[xi + 1] + yi + 1];
            double r = Lerp(
                Lerp(Grad2(aa, xf, yf), Grad2(ba, xf - 1, yf), u),
                Lerp(Grad2(ab, xf, yf - 1), Grad2(bb, xf - 1, yf - 1), u), v);
            return r * 0.7071;
        }

        /// <summary>3D noise in roughly [-1, 1].</summary>
        public double Noise(double x, double y, double z)
        {
            int xi = (int)Math.Floor(x), yi = (int)Math.Floor(y), zi = (int)Math.Floor(z);
            double xf = x - xi, yf = y - yi, zf = z - zi;
            xi &= 255; yi &= 255; zi &= 255;
            double u = Fade(xf), v = Fade(yf), w = Fade(zf);
            int a = _perm[xi] + yi, aa = _perm[a] + zi, ab = _perm[a + 1] + zi;
            int b = _perm[xi + 1] + yi, ba = _perm[b] + zi, bb = _perm[b + 1] + zi;
            return Lerp(
                Lerp(Lerp(Grad3(_perm[aa], xf, yf, zf), Grad3(_perm[ba], xf - 1, yf, zf), u),
                     Lerp(Grad3(_perm[ab], xf, yf - 1, zf), Grad3(_perm[bb], xf - 1, yf - 1, zf), u), v),
                Lerp(Lerp(Grad3(_perm[aa + 1], xf, yf, zf - 1), Grad3(_perm[ba + 1], xf - 1, yf, zf - 1), u),
                     Lerp(Grad3(_perm[ab + 1], xf, yf - 1, zf - 1), Grad3(_perm[bb + 1], xf - 1, yf - 1, zf - 1), u), v),
                w);
        }

        /// <summary>Fractal sum of 2D octaves, normalised to roughly [-1, 1].</summary>
        public double Fractal(double x, double y, int octaves, double lacunarity = 2.0, double gain = 0.5)
        {
            double sum = 0, amp = 1, norm = 0, freq = 1;
            for (int i = 0; i < octaves; i++)
            {
                sum += Noise(x * freq + i * 17.13, y * freq - i * 9.71) * amp;
                norm += amp;
                amp *= gain;
                freq *= lacunarity;
            }
            return sum / norm;
        }

        /// <summary>Ridged multifractal in [0, 1]: sharp crests suited to mountain ranges.</summary>
        public double Ridged(double x, double y, int octaves)
        {
            double sum = 0, amp = 0.5, freq = 1, norm = 0;
            for (int i = 0; i < octaves; i++)
            {
                double n = 1.0 - Math.Abs(Noise(x * freq + i * 31.7, y * freq + i * 11.3));
                sum += n * n * amp;
                norm += amp;
                amp *= 0.5;
                freq *= 2.0;
            }
            return sum / norm;
        }
    }
}
