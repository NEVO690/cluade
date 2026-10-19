using System;
using UnityEngine;

namespace VoxelWorld.Core
{
    /// <summary>Player-adjustable options, persisted with PlayerPrefs.</summary>
    public static class GameSettings
    {
        private const string SensitivityKey = "vw.mouseSensitivity";
        private const string InvertKey = "vw.invertY";
        private const string FovKey = "vw.fov";
        private const string RenderDistanceKey = "vw.renderDistance";

        public const float MinSensitivity = 0.1f, MaxSensitivity = 5f;
        public const int MinRenderDistance = 3, MaxRenderDistance = 16;
        public const float MinFov = 55f, MaxFov = 100f;

        public static event Action Changed;

        private static bool _loaded;
        private static float _sensitivity = 1f;
        private static bool _invertY;
        private static float _fov = 75f;
        private static int _renderDistance = 8;

        public static float MouseSensitivity
        {
            get { EnsureLoaded(); return _sensitivity; }
            set { EnsureLoaded(); _sensitivity = Mathf.Clamp(value, MinSensitivity, MaxSensitivity); Save(); }
        }

        public static bool InvertY
        {
            get { EnsureLoaded(); return _invertY; }
            set { EnsureLoaded(); _invertY = value; Save(); }
        }

        public static float FieldOfView
        {
            get { EnsureLoaded(); return _fov; }
            set { EnsureLoaded(); _fov = Mathf.Clamp(value, MinFov, MaxFov); Save(); }
        }

        /// <summary>View distance in chunks around the player.</summary>
        public static int RenderDistance
        {
            get { EnsureLoaded(); return _renderDistance; }
            set { EnsureLoaded(); _renderDistance = Mathf.Clamp(value, MinRenderDistance, MaxRenderDistance); Save(); }
        }

        private static void EnsureLoaded()
        {
            if (_loaded) return;
            _loaded = true;
            _sensitivity = Mathf.Clamp(PlayerPrefs.GetFloat(SensitivityKey, 1f), MinSensitivity, MaxSensitivity);
            _invertY = PlayerPrefs.GetInt(InvertKey, 0) == 1;
            _fov = Mathf.Clamp(PlayerPrefs.GetFloat(FovKey, 75f), MinFov, MaxFov);
            _renderDistance = Mathf.Clamp(PlayerPrefs.GetInt(RenderDistanceKey, 8), MinRenderDistance, MaxRenderDistance);
        }

        private static void Save()
        {
            PlayerPrefs.SetFloat(SensitivityKey, _sensitivity);
            PlayerPrefs.SetInt(InvertKey, _invertY ? 1 : 0);
            PlayerPrefs.SetFloat(FovKey, _fov);
            PlayerPrefs.SetInt(RenderDistanceKey, _renderDistance);
            PlayerPrefs.Save();
            Changed?.Invoke();
        }

        /// <summary>Clears cached values (needed when domain reload is disabled in the editor).</summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetStatics()
        {
            _loaded = false;
            Changed = null;
        }
    }
}
