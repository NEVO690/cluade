using System.Text;
using UnityEngine;
using UnityEngine.UI;
using VoxelWorld.Core;
using VoxelWorld.Inventory;
using VoxelWorld.Player;
using VoxelWorld.Rendering;
using VoxelWorld.World;
using VoxelWorld.World.Generation;

namespace VoxelWorld.UI
{
    /// <summary>In-game overlay: crosshair, hotbar, mining progress, target name, loading screen and F3 debug info.</summary>
    public sealed class HudController : MonoBehaviour
    {
        private const float SlotSize = 84f;
        private const float SlotSpacing = 8f;

        private PlayerInventory _inventory;
        private PlayerController _player;
        private PlayerInteraction _interaction;
        private WorldManager _world;
        private ItemIconFactory _icons;

        private Canvas _canvas;
        private RectTransform _hotbar;
        private readonly Image[] _slotFrames = new Image[PlayerInventory.HotbarSize];
        private readonly Image[] _slotIcons = new Image[PlayerInventory.HotbarSize];
        private readonly Text[] _slotCounts = new Text[PlayerInventory.HotbarSize];
        private RectTransform _selector;
        private Text _itemName;
        private float _itemNameTimer;
        private Image _miningBack;
        private Image _miningFill;
        private Text _targetName;
        private Text _debugText;
        private GameObject _crosshair;
        private GameObject _loading;
        private Text _loadingText;
        private bool _showDebug;
        private float _fpsSmoothed = 60f;
        private readonly StringBuilder _sb = new StringBuilder(256);

        public void Initialize(PlayerInventory inventory, PlayerController player, PlayerInteraction interaction,
            WorldManager world, ItemIconFactory icons)
        {
            _inventory = inventory;
            _player = player;
            _interaction = interaction;
            _world = world;
            _icons = icons;

            _canvas = UIFactory.CreateCanvas("HUD", 0);
            _canvas.transform.SetParent(transform, false);
            var root = (RectTransform)_canvas.transform;

            BuildCrosshair(root);
            BuildHotbar(root);
            BuildMiningBar(root);
            BuildDebug(root);
            BuildLoading(root);

            _inventory.Changed += RefreshHotbar;
            RefreshHotbar();
        }

        private void OnDestroy()
        {
            if (_inventory != null) _inventory.Changed -= RefreshHotbar;
        }

        private void BuildCrosshair(RectTransform root)
        {
            var holder = UIFactory.Rect("Crosshair", root).Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(28f, 28f));
            _crosshair = holder.gameObject;
            var shadow = new Color(0f, 0f, 0f, 0.55f);
            var color = new Color(1f, 1f, 1f, 0.92f);
            // Shadowed plus shape with a gap in the centre.
            foreach (var (pos, size) in new[]
                     {
                         (new Vector2(0f, 8f), new Vector2(3f, 9f)), (new Vector2(0f, -8f), new Vector2(3f, 9f)),
                         (new Vector2(8f, 0f), new Vector2(9f, 3f)), (new Vector2(-8f, 0f), new Vector2(9f, 3f)),
                     })
            {
                UIFactory.Image("Shadow", holder, shadow).rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), pos + new Vector2(1f, -1f), size + new Vector2(2f, 2f));
                UIFactory.Image("Bar", holder, color).rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), pos, size);
            }
            UIFactory.Image("Dot", holder, color).rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(2f, 2f));
        }

        private void BuildHotbar(RectTransform root)
        {
            float width = PlayerInventory.HotbarSize * SlotSize + (PlayerInventory.HotbarSize - 1) * SlotSpacing + 24f;
            var panel = UIFactory.Image("Hotbar", root, UITheme.Panel, UIFactory.Rounded);
            _hotbar = panel.rectTransform.Anchor(new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 24f), new Vector2(width, SlotSize + 24f));

            for (int i = 0; i < PlayerInventory.HotbarSize; i++)
            {
                float x = 12f + i * (SlotSize + SlotSpacing);
                var frame = UIFactory.Image("Slot " + (i + 1), _hotbar, UITheme.PanelLight, UIFactory.RoundedSmall);
                frame.rectTransform.Anchor(new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(x, 0f), new Vector2(SlotSize, SlotSize));
                _slotFrames[i] = frame;

                var icon = UIFactory.Image("Icon", frame.rectTransform, Color.white);
                icon.rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(60f, 60f));
                icon.preserveAspect = true;
                _slotIcons[i] = icon;

                var count = UIFactory.Text("Count", frame.rectTransform, "", 24, UITheme.Text, TextAnchor.LowerRight, FontStyle.Bold);
                count.rectTransform.Stretch(6f);
                UIFactory.AddShadow(count);
                _slotCounts[i] = count;

                var number = UIFactory.Text("Key", frame.rectTransform, (i + 1).ToString(), 16, UITheme.TextDim, TextAnchor.UpperLeft);
                number.rectTransform.Stretch(6f);
            }

            // Sliced sprite without its centre: only the rounded accent border is drawn.
            var selector = UIFactory.Image("Selector", _hotbar, UITheme.Accent, UIFactory.RoundedSmall);
            selector.fillCenter = false;
            _selector = selector.rectTransform.Anchor(new Vector2(0f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(SlotSize + 10f, SlotSize + 10f));

            _itemName = UIFactory.Text("Item Name", root, "", 30, UITheme.Text, TextAnchor.MiddleCenter, FontStyle.Bold);
            _itemName.rectTransform.Anchor(new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, SlotSize + 66f), new Vector2(600f, 40f));
            UIFactory.AddShadow(_itemName);
        }

        private void BuildMiningBar(RectTransform root)
        {
            _miningBack = UIFactory.Image("Mining Progress", root, new Color(0f, 0f, 0f, 0.55f), UIFactory.RoundedSmall);
            _miningBack.rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 1f), new Vector2(0f, -34f), new Vector2(120f, 12f));
            _miningFill = UIFactory.Image("Fill", _miningBack.rectTransform, UITheme.Accent, UIFactory.RoundedSmall);
            var fr = _miningFill.rectTransform;
            fr.anchorMin = Vector2.zero;
            fr.anchorMax = new Vector2(0f, 1f);
            fr.offsetMin = new Vector2(2f, 2f);
            fr.offsetMax = new Vector2(-2f, -2f);

            _targetName = UIFactory.Text("Target", root, "", 22, UITheme.Text, TextAnchor.UpperCenter);
            _targetName.rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 1f), new Vector2(0f, -52f), new Vector2(400f, 30f));
            UIFactory.AddShadow(_targetName, 1.5f);
        }

        private void BuildDebug(RectTransform root)
        {
            _debugText = UIFactory.Text("Debug", root, "", 22, UITheme.Text, TextAnchor.UpperLeft);
            _debugText.rectTransform.Anchor(new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(20f, -16f), new Vector2(900f, 400f));
            UIFactory.AddShadow(_debugText, 1.5f, 0.8f);
            _debugText.gameObject.SetActive(false);

            var hint = UIFactory.Text("Hint", root, "F3  debug    Esc  menu", 18, new Color(1f, 1f, 1f, 0.45f), TextAnchor.UpperRight);
            hint.rectTransform.Anchor(new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-20f, -16f), new Vector2(400f, 30f));
        }

        private void BuildLoading(RectTransform root)
        {
            var bg = UIFactory.Image("Loading", root, new Color(0.05f, 0.07f, 0.10f, 1f));
            bg.rectTransform.Stretch();
            bg.raycastTarget = true;
            _loading = bg.gameObject;
            var title = UIFactory.Text("Title", bg.rectTransform, "VOXEL WORLD", 84, UITheme.Accent, TextAnchor.MiddleCenter, FontStyle.Bold);
            title.rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 60f), new Vector2(1200f, 120f));
            UIFactory.AddShadow(title, 4f);
            _loadingText = UIFactory.Text("Status", bg.rectTransform, "Shaping the land...", 30, UITheme.TextDim);
            _loadingText.rectTransform.Anchor(new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, -40f), new Vector2(1200f, 50f));
        }

        public void SetLoading(bool visible, string status = null)
        {
            if (_loading == null) return;
            _loading.SetActive(visible);
            if (status != null) _loadingText.text = status;
        }

        private void RefreshHotbar()
        {
            for (int i = 0; i < PlayerInventory.HotbarSize; i++)
            {
                var stack = _inventory[i];
                var sprite = stack.IsEmpty ? null : _icons.Get(stack.ItemId);
                _slotIcons[i].sprite = sprite;
                _slotIcons[i].enabled = sprite != null;
                _slotCounts[i].text = stack.Count > 1 ? stack.Count.ToString() : "";
            }

            float x = 12f + _inventory.SelectedSlot * (SlotSize + SlotSpacing) + SlotSize * 0.5f;
            _selector.anchoredPosition = new Vector2(x, 0f);

            var selected = _inventory.SelectedStack;
            string name = selected.IsEmpty ? "" : _inventory.Items.Get(selected.ItemId)?.DisplayName ?? "";
            if (name != _itemName.text)
            {
                _itemName.text = name;
                _itemNameTimer = 2.2f;
            }
        }

        private void Update()
        {
            if (_inventory == null) return;

            bool playing = !GameState.InputBlocked;
            _crosshair.SetActive(playing);
            _hotbar.gameObject.SetActive(GameState.WorldReady);

            _itemNameTimer -= Time.unscaledDeltaTime;
            var c = _itemName.color;
            c.a = Mathf.Clamp01(_itemNameTimer);
            _itemName.color = c;

            float progress = _interaction.MiningProgress;
            bool mining = playing && progress > 0f;
            _miningBack.gameObject.SetActive(mining);
            if (mining) _miningFill.rectTransform.anchorMax = new Vector2(Mathf.Clamp01(progress), 1f);

            if (playing && _interaction.HasTarget)
                _targetName.text = _world.Registry[_interaction.Target.Block].DisplayName;
            else
                _targetName.text = "";

            if (GameInput.DebugPressed)
            {
                _showDebug = !_showDebug;
                _debugText.gameObject.SetActive(_showDebug);
            }
            if (_showDebug) UpdateDebug();
        }

        private void UpdateDebug()
        {
            float dt = Mathf.Max(Time.unscaledDeltaTime, 1e-4f);
            _fpsSmoothed = Mathf.Lerp(_fpsSmoothed, 1f / dt, 0.05f);
            var p = _player.Position;
            int bx = Mathf.FloorToInt(p.x), by = Mathf.FloorToInt(p.y), bz = Mathf.FloorToInt(p.z);
            var column = _world.Generator.SampleColumn(bx, bz);
            var chunk = _world.ChunkOf(bx, bz);

            _sb.Clear();
            _sb.Append("VOXEL WORLD  ").Append(Mathf.RoundToInt(_fpsSmoothed)).Append(" fps\n");
            _sb.Append("Position  ").Append(p.x.ToString("F1")).Append(" / ").Append(p.y.ToString("F1")).Append(" / ").Append(p.z.ToString("F1")).Append('\n');
            _sb.Append("Block  ").Append(bx).Append(' ').Append(by).Append(' ').Append(bz)
               .Append("   Chunk  ").Append(chunk.X).Append(", ").Append(chunk.Z).Append('\n');
            _sb.Append("Biome  ").Append(Biomes.Get(column.Biome).DisplayName)
               .Append("   Temp ").Append(column.Temperature.ToString("F2"))
               .Append("   Humidity ").Append(column.Humidity.ToString("F2")).Append('\n');
            _sb.Append("Chunks loaded  ").Append(_world.LoadedChunkCount).Append("   jobs ").Append(_world.PendingJobs)
               .Append("   view ").Append(_world.RenderDistance).Append('\n');
            _sb.Append("Seed  ").Append(_world.Seed).Append("   Edited chunks  ").Append(_world.Edits.ChunkCount).Append('\n');
            _sb.Append(_player.IsGrounded ? "On ground" : "Airborne").Append(_player.IsInWater ? "   In water" : "")
               .Append(_player.IsSprinting ? "   Sprinting" : "");
            _debugText.text = _sb.ToString();
        }
    }
}
