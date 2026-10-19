using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM && VOXEL_INPUT_SYSTEM
using UnityEngine.InputSystem.UI;
#endif

namespace VoxelWorld.UI
{
    /// <summary>Shared palette for the game's interface.</summary>
    public static class UITheme
    {
        public static readonly Color Panel = new Color(0.07f, 0.09f, 0.12f, 0.86f);
        public static readonly Color PanelLight = new Color(0.16f, 0.19f, 0.24f, 0.92f);
        public static readonly Color Accent = new Color(0.96f, 0.72f, 0.30f, 1f);
        public static readonly Color AccentSoft = new Color(0.96f, 0.72f, 0.30f, 0.35f);
        public static readonly Color Text = new Color(0.94f, 0.95f, 0.97f, 1f);
        public static readonly Color TextDim = new Color(0.70f, 0.74f, 0.80f, 1f);
        public static readonly Color Button = new Color(0.20f, 0.24f, 0.30f, 0.95f);
        public static readonly Color ButtonHover = new Color(0.30f, 0.36f, 0.44f, 1f);
        public static readonly Color ButtonPressed = new Color(0.86f, 0.62f, 0.24f, 1f);
    }

    /// <summary>
    /// Builds uGUI elements from code so the game needs no hand-authored prefabs. Generates a
    /// rounded, 9-sliced panel sprite at runtime and uses Unity's built-in font.
    /// </summary>
    public static class UIFactory
    {
        private static Font _font;
        private static Sprite _rounded;
        private static Sprite _roundedSmall;
        private static Sprite _circle;

        public static Font Font
        {
            get
            {
                if (_font == null)
                {
                    // LegacyRuntime.ttf is the built-in font since Unity 2022.2; Arial.ttf before that.
                    try { _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf"); }
                    catch (ArgumentException) { _font = null; }
                    if (_font == null)
                    {
                        try { _font = Resources.GetBuiltinResource<Font>("Arial.ttf"); }
                        catch (ArgumentException) { _font = null; }
                    }
                    if (_font == null) _font = Font.CreateDynamicFontFromOSFont("Arial", 16);
                }
                return _font;
            }
        }

        public static Sprite Rounded => _rounded != null ? _rounded : (_rounded = MakeRounded(32, 10));
        public static Sprite RoundedSmall => _roundedSmall != null ? _roundedSmall : (_roundedSmall = MakeRounded(16, 4));
        public static Sprite Circle => _circle != null ? _circle : (_circle = MakeRounded(32, 16));

        private static Sprite MakeRounded(int size, int radius)
        {
            var tex = new Texture2D(size, size, TextureFormat.RGBA32, false)
            {
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                name = "UI Rounded " + radius,
            };
            var pixels = new Color32[size * size];
            for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                float cx = Mathf.Clamp(x + 0.5f, radius, size - radius);
                float cy = Mathf.Clamp(y + 0.5f, radius, size - radius);
                float d = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(cx, cy));
                float a = Mathf.Clamp01(radius - d + 0.5f);
                pixels[y * size + x] = new Color32(255, 255, 255, (byte)(a * 255));
            }
            tex.SetPixels32(pixels);
            tex.Apply(false, true);
            float border = Mathf.Min(radius, size / 2 - 1);
            return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0,
                SpriteMeshType.FullRect, new Vector4(border, border, border, border));
        }

        public static Canvas CreateCanvas(string name, int sortingOrder)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = go.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = sortingOrder;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 0.5f;
            return canvas;
        }

        public static void EnsureEventSystem()
        {
            if (UnityEngine.Object.FindFirstObjectByType<EventSystem>() != null) return;
            var go = new GameObject("EventSystem", typeof(EventSystem));
#if ENABLE_INPUT_SYSTEM && VOXEL_INPUT_SYSTEM
            var module = go.AddComponent<InputSystemUIInputModule>();
            module.AssignDefaultActions();
#else
            go.AddComponent<StandaloneInputModule>();
#endif
        }

        public static RectTransform Rect(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform));
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            return rt;
        }

        public static RectTransform Stretch(this RectTransform rt, float inset = 0f)
        {
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = new Vector2(inset, inset);
            rt.offsetMax = new Vector2(-inset, -inset);
            return rt;
        }

        public static RectTransform Anchor(this RectTransform rt, Vector2 anchor, Vector2 pivot, Vector2 position, Vector2 size)
        {
            rt.anchorMin = anchor;
            rt.anchorMax = anchor;
            rt.pivot = pivot;
            rt.anchoredPosition = position;
            rt.sizeDelta = size;
            return rt;
        }

        public static Image Image(string name, Transform parent, Color color, Sprite sprite = null)
        {
            var rt = Rect(name, parent);
            var img = rt.gameObject.AddComponent<Image>();
            img.color = color;
            if (sprite != null)
            {
                img.sprite = sprite;
                img.type = sprite.border.sqrMagnitude > 0f ? UnityEngine.UI.Image.Type.Sliced : UnityEngine.UI.Image.Type.Simple;
            }
            img.raycastTarget = false;
            return img;
        }

        public static Text Text(string name, Transform parent, string content, int size, Color color,
            TextAnchor alignment = TextAnchor.MiddleCenter, FontStyle style = FontStyle.Normal)
        {
            var rt = Rect(name, parent);
            var text = rt.gameObject.AddComponent<Text>();
            text.font = Font;
            text.text = content;
            text.fontSize = size;
            text.color = color;
            text.alignment = alignment;
            text.fontStyle = style;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            text.raycastTarget = false;
            return text;
        }

        public static Shadow AddShadow(Graphic graphic, float distance = 2f, float alpha = 0.6f)
        {
            var shadow = graphic.gameObject.AddComponent<Shadow>();
            shadow.effectColor = new Color(0f, 0f, 0f, alpha);
            shadow.effectDistance = new Vector2(distance, -distance);
            return shadow;
        }

        public static Button Button(string name, Transform parent, string label, Action onClick, Vector2 size)
        {
            var img = Image(name, parent, Color.white, Rounded);
            img.raycastTarget = true;
            var rt = img.rectTransform;
            rt.sizeDelta = size;
            var button = img.gameObject.AddComponent<Button>();
            var colors = button.colors;
            colors.normalColor = UITheme.Button;
            colors.highlightedColor = UITheme.ButtonHover;
            colors.selectedColor = UITheme.Button;
            colors.pressedColor = UITheme.ButtonPressed;
            colors.disabledColor = new Color(0.2f, 0.2f, 0.2f, 0.5f);
            colors.fadeDuration = 0.08f;
            button.colors = colors;
            button.targetGraphic = img;
            button.onClick.AddListener(() => onClick?.Invoke());

            var text = Text("Label", rt, label, 30, UITheme.Text);
            text.rectTransform.Stretch();
            return button;
        }

        /// <summary>Horizontal slider with a caption on the left and the live value on the right.</summary>
        public static Slider Slider(string name, Transform parent, string caption, float min, float max, float value,
            bool wholeNumbers, Func<float, string> format, Action<float> onChanged, float width = 620f)
        {
            var row = Rect(name, parent);
            row.sizeDelta = new Vector2(width, 64f);

            var label = Text("Caption", row, caption, 26, UITheme.TextDim, TextAnchor.MiddleLeft);
            label.rectTransform.Anchor(new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), Vector2.zero, new Vector2(220f, 40f));

            var valueText = Text("Value", row, format(value), 26, UITheme.Text, TextAnchor.MiddleRight);
            valueText.rectTransform.Anchor(new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), Vector2.zero, new Vector2(90f, 40f));

            var sliderRt = Rect("Slider", row);
            sliderRt.anchorMin = new Vector2(0f, 0.5f);
            sliderRt.anchorMax = new Vector2(1f, 0.5f);
            sliderRt.offsetMin = new Vector2(235f, -12f);
            sliderRt.offsetMax = new Vector2(-105f, 12f);

            var background = Image("Background", sliderRt, UITheme.PanelLight, RoundedSmall);
            background.rectTransform.Stretch();
            background.raycastTarget = true;

            var fillArea = Rect("Fill Area", sliderRt).Stretch();
            fillArea.offsetMin = new Vector2(6f, 6f);
            fillArea.offsetMax = new Vector2(-6f, -6f);
            var fill = Image("Fill", fillArea, UITheme.Accent, RoundedSmall);
            fill.rectTransform.anchorMin = Vector2.zero;
            fill.rectTransform.anchorMax = new Vector2(0f, 1f);
            fill.rectTransform.offsetMin = Vector2.zero;
            fill.rectTransform.offsetMax = Vector2.zero;

            var handleArea = Rect("Handle Area", sliderRt).Stretch();
            handleArea.offsetMin = new Vector2(12f, 0f);
            handleArea.offsetMax = new Vector2(-12f, 0f);
            var handle = Image("Handle", handleArea, Color.white, Circle);
            handle.raycastTarget = true;
            handle.rectTransform.sizeDelta = new Vector2(30f, 30f);
            handle.rectTransform.anchorMin = new Vector2(0f, 0.5f);
            handle.rectTransform.anchorMax = new Vector2(0f, 0.5f);

            var slider = sliderRt.gameObject.AddComponent<Slider>();
            slider.fillRect = fill.rectTransform;
            slider.handleRect = handle.rectTransform;
            slider.targetGraphic = handle;
            slider.direction = UnityEngine.UI.Slider.Direction.LeftToRight;
            slider.minValue = min;
            slider.maxValue = max;
            slider.wholeNumbers = wholeNumbers;
            slider.SetValueWithoutNotify(value);
            slider.onValueChanged.AddListener(v =>
            {
                valueText.text = format(v);
                onChanged?.Invoke(v);
            });
            return slider;
        }

        public static VerticalLayoutGroup VerticalLayout(GameObject go, float spacing, TextAnchor alignment)
        {
            var layout = go.AddComponent<VerticalLayoutGroup>();
            layout.spacing = spacing;
            layout.childAlignment = alignment;
            layout.childControlWidth = false;
            layout.childControlHeight = false;
            layout.childForceExpandWidth = false;
            layout.childForceExpandHeight = false;
            return layout;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetStatics()
        {
            _font = null;
            _rounded = null;
            _roundedSmall = null;
            _circle = null;
        }
    }
}
