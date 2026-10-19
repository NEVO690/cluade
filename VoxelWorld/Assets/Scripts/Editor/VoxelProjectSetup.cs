using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using VoxelWorld.Core;
#if VOXEL_URP
using UnityEngine.Rendering.Universal;
#endif

namespace VoxelWorld.EditorTools
{
    /// <summary>
    /// One-time project configuration so the repository opens ready to play:
    /// assigns a Universal Render Pipeline asset when none is active (an existing URP setup is
    /// never replaced), puts the game scene in the build list and opens it.
    /// Everything is also available from the "Voxel World" menu.
    /// </summary>
    [InitializeOnLoad]
    public static class VoxelProjectSetup
    {
        private const string ScenePath = "Assets/Scenes/" + GameBootstrap.SceneName + ".unity";
        private const string SettingsFolder = "Assets/Settings";
        private const string PipelinePath = SettingsFolder + "/VoxelWorld_URP.asset";
        private const string RendererPath = SettingsFolder + "/VoxelWorld_Renderer.asset";
        private const string SessionKey = "VoxelWorld.SetupChecked";

        static VoxelProjectSetup()
        {
            EditorApplication.delayCall += AutoSetup;
        }

        private static void AutoSetup()
        {
            if (SessionState.GetBool(SessionKey, false)) return;
            SessionState.SetBool(SessionKey, true);
            if (EditorApplication.isPlayingOrWillChangePlaymode) return;

            EnsureRenderPipeline(false);
            EnsureScene();
            EnsureBuildSettings();

            // Open the game scene when the editor starts on an empty untitled scene.
            var active = SceneManager.GetActiveScene();
            if (string.IsNullOrEmpty(active.path) && !active.isDirty && File.Exists(ScenePath))
                EditorSceneManager.OpenScene(ScenePath);
        }

        [MenuItem("Voxel World/Configure Project", priority = 0)]
        public static void ConfigureProject()
        {
            bool pipelineOk = EnsureRenderPipeline(true);
            EnsureScene();
            EnsureBuildSettings();
            EditorUtility.DisplayDialog("Voxel World",
                pipelineOk
                    ? "Project configured: URP active, game scene added to the build list.\nPress Play in the VoxelWorld scene."
                    : "The game scene is configured, but no Universal Render Pipeline asset could be assigned. " +
                      "Install the 'Universal RP' package (Window > Package Manager) and run this command again.",
                "OK");
        }

        [MenuItem("Voxel World/Open Game Scene", priority = 1)]
        public static void OpenGameScene()
        {
            EnsureScene();
            if (EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                EditorSceneManager.OpenScene(ScenePath);
        }

        [MenuItem("Voxel World/Rebuild Game Scene", priority = 2)]
        public static void RebuildGameScene()
        {
            if (!EditorUtility.DisplayDialog("Voxel World", "Recreate " + ScenePath + "? Changes made to that scene will be lost.", "Recreate", "Cancel"))
                return;
            CreateScene();
            EnsureBuildSettings();
        }

        private static void EnsureScene()
        {
            if (!File.Exists(ScenePath)) CreateScene();
        }

        private static void CreateScene()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath) ?? "Assets/Scenes");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            new GameObject("Game Bootstrap").AddComponent<GameBootstrap>();
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.Refresh();
        }

        private static void EnsureBuildSettings()
        {
            var scenes = EditorBuildSettings.scenes.ToList();
            if (scenes.Count > 0 && scenes[0].path == ScenePath && scenes[0].enabled) return;
            scenes.RemoveAll(s => s.path == ScenePath);
            scenes.Insert(0, new EditorBuildSettingsScene(ScenePath, true));
            EditorBuildSettings.scenes = scenes.ToArray();
        }

        /// <summary>Returns true when a URP asset is active after the call.</summary>
        private static bool EnsureRenderPipeline(bool verbose)
        {
#if VOXEL_URP
            var current = GraphicsSettings.defaultRenderPipeline;
            if (current is UniversalRenderPipelineAsset) return true;
            if (current != null)
            {
                Debug.LogWarning("[VoxelWorld] A non-URP render pipeline is active (" + current.name + "). " +
                                 "The voxel shaders require the Universal Render Pipeline; it was left unchanged.");
                return false;
            }

            var asset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(PipelinePath);
            if (asset == null)
            {
                Directory.CreateDirectory(SettingsFolder);
                var rendererData = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(RendererPath);
                if (rendererData == null)
                {
                    rendererData = ScriptableObject.CreateInstance<UniversalRendererData>();
                    var postProcess = AssetDatabase.LoadAssetAtPath<PostProcessData>(
                        "Packages/com.unity.render-pipelines.universal/Runtime/Data/PostProcessData.asset");
                    if (postProcess != null) rendererData.postProcessData = postProcess;
                    AssetDatabase.CreateAsset(rendererData, RendererPath);
                }

                asset = UniversalRenderPipelineAsset.Create(rendererData);
                asset.shadowDistance = 96f;
                asset.shadowCascadeCount = 2;
                asset.supportsHDR = true;
                asset.msaaSampleCount = 4;
                AssetDatabase.CreateAsset(asset, PipelinePath);
                AssetDatabase.SaveAssets();
            }

            GraphicsSettings.defaultRenderPipeline = asset;
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                var levelPipeline = QualitySettings.GetRenderPipelineAssetAt(i);
                if (levelPipeline != null && !(levelPipeline is UniversalRenderPipelineAsset))
                    Debug.LogWarning("[VoxelWorld] Quality level " + QualitySettings.names[i] + " overrides the render pipeline.");
            }

            if (PlayerSettings.colorSpace != ColorSpace.Linear) PlayerSettings.colorSpace = ColorSpace.Linear;
            Debug.Log("[VoxelWorld] Assigned Universal Render Pipeline asset " + PipelinePath + ".");
            return true;
#else
            if (verbose) Debug.LogError("[VoxelWorld] The Universal RP package is not installed.");
            return false;
#endif
        }
    }
}
