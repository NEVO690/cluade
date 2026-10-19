using System;
using UnityEngine;
using VoxelWorld.Core;

namespace VoxelWorld.UI
{
    /// <summary>Escape menu with resume, live settings and quit. Every control performs its action immediately.</summary>
    public sealed class PauseMenu : MonoBehaviour
    {
        private GameObject _root;
        private bool _open;

        /// <summary>Raised when the view distance slider changes (in chunks).</summary>
        public event Action<int> RenderDistanceChanged;

        public bool IsOpen => _open;

        public void Initialize()
        {
            var canvas = UIFactory.CreateCanvas("Pause Menu", 10);
            canvas.transform.SetParent(transform, false);
            var root = (RectTransform)canvas.transform;

            var dim = UIFactory.Image("Dim", root, new Color(0f, 0f, 0f, 0.55f));
            dim.rectTransform.Stretch();
            dim.raycastTarget = true;
            _root = dim.gameObject;

            var panel = UIFactory.Image("Panel", dim.rectTransform, UITheme.Panel, UIFactory.Rounded);
            panel.rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(720f, 690f));
            var content = UIFactory.Rect("Content", panel.rectTransform).Stretch(40f);
            UIFactory.VerticalLayout(content.gameObject, 18f, TextAnchor.UpperCenter);

            var title = UIFactory.Text("Title", content, "Paused", 54, UITheme.Accent, TextAnchor.MiddleCenter, FontStyle.Bold);
            title.rectTransform.sizeDelta = new Vector2(620f, 70f);
            UIFactory.AddShadow(title, 3f);

            UIFactory.Button("Resume", content, "Resume", Close, new Vector2(620f, 70f));

            UIFactory.Slider("Sensitivity", content, "Mouse sensitivity", GameSettings.MinSensitivity, GameSettings.MaxSensitivity,
                GameSettings.MouseSensitivity, false, v => v.ToString("F2"), v => GameSettings.MouseSensitivity = v);
            UIFactory.Slider("Field of View", content, "Field of view", GameSettings.MinFov, GameSettings.MaxFov,
                GameSettings.FieldOfView, true, v => Mathf.RoundToInt(v) + "°", v => GameSettings.FieldOfView = v);
            UIFactory.Slider("View Distance", content, "View distance", GameSettings.MinRenderDistance, GameSettings.MaxRenderDistance,
                GameSettings.RenderDistance, true, v => Mathf.RoundToInt(v) + " ch", v =>
                {
                    GameSettings.RenderDistance = Mathf.RoundToInt(v);
                    RenderDistanceChanged?.Invoke(GameSettings.RenderDistance);
                });

            var invert = UIFactory.Button("Invert Y", content, InvertLabel(), null, new Vector2(620f, 60f));
            var invertText = invert.GetComponentInChildren<UnityEngine.UI.Text>();
            invert.onClick.AddListener(() =>
            {
                GameSettings.InvertY = !GameSettings.InvertY;
                invertText.text = InvertLabel();
            });

            UIFactory.Button("Quit", content, "Quit Game", Quit, new Vector2(620f, 70f));

            _root.SetActive(false);
        }

        private static string InvertLabel() => "Invert mouse Y: " + (GameSettings.InvertY ? "On" : "Off");

        private void Update()
        {
            if (!GameState.WorldReady) return;
            if (GameInput.PausePressed)
            {
                if (_open) Close();
                else Open();
            }
        }

        public void Open()
        {
            if (_open) return;
            _open = true;
            _root.SetActive(true);
            GameState.PushUi();
        }

        public void Close()
        {
            if (!_open) return;
            _open = false;
            _root.SetActive(false);
            GameState.PopUi();
        }

        private static void Quit()
        {
#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
            Application.Quit();
#endif
        }
    }
}
