using UnityEngine;
using UnityEngine.Rendering;

namespace VoxelWorld.Rendering
{
    /// <summary>
    /// Owns the sun, sky colour, ambient light and distance fog. The day-night cycle (phase 5)
    /// will drive <see cref="SetSun"/> over time; for now the sun stays at a pleasant afternoon angle.
    /// Fog is matched to the view distance so chunk loading at the horizon is hidden.
    /// </summary>
    public sealed class AtmosphereController : MonoBehaviour
    {
        private static readonly int SkyAmbientId = Shader.PropertyToID("_VoxelSkyAmbient");
        private static readonly int GroundAmbientId = Shader.PropertyToID("_VoxelGroundAmbient");

        [SerializeField] private Color skyColor = new Color(0.55f, 0.76f, 0.95f);
        [SerializeField] private Color horizonColor = new Color(0.75f, 0.85f, 0.95f);
        [SerializeField] private Color skyAmbient = new Color(0.48f, 0.55f, 0.68f);
        [SerializeField] private Color groundAmbient = new Color(0.28f, 0.26f, 0.24f);
        [SerializeField] private Color sunColor = new Color(1f, 0.95f, 0.85f);
        [SerializeField] private float sunIntensity = 1.15f;

        private Light _sun;
        private Camera _camera;
        private float _fogEnd = 120f;

        public Light Sun => _sun;

        public void Initialize(Camera camera)
        {
            _camera = camera;
            var sunGo = new GameObject("Sun");
            sunGo.transform.SetParent(transform, false);
            _sun = sunGo.AddComponent<Light>();
            _sun.type = LightType.Directional;
            _sun.shadows = LightShadows.Soft;
            _sun.shadowStrength = 0.85f;
            _sun.shadowBias = 0.05f;
            _sun.shadowNormalBias = 0.4f;
            RenderSettings.sun = _sun;
            SetSun(52f, -35f);

            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.ambientLight = skyAmbient;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.skybox = null;

            _camera.clearFlags = CameraClearFlags.SolidColor;
            Apply();
        }

        public void SetSun(float elevation, float azimuth)
        {
            if (_sun == null) return;
            _sun.transform.rotation = Quaternion.Euler(elevation, azimuth, 0f);
            _sun.color = sunColor;
            _sun.intensity = sunIntensity;
        }

        /// <summary>Sets the fog so it fully hides terrain at the edge of the loaded area.</summary>
        public void SetViewDistance(float blocks)
        {
            _fogEnd = Mathf.Max(32f, blocks);
            Apply();
        }

        private void Apply()
        {
            RenderSettings.fogColor = horizonColor;
            RenderSettings.fogStartDistance = _fogEnd * 0.45f;
            RenderSettings.fogEndDistance = _fogEnd;
            Shader.SetGlobalColor(SkyAmbientId, skyAmbient);
            Shader.SetGlobalColor(GroundAmbientId, groundAmbient);
            if (_camera != null)
            {
                _camera.backgroundColor = horizonColor;
                _camera.farClipPlane = _fogEnd + 16f;
            }
        }

        public Color SkyColor => skyColor;
    }
}
