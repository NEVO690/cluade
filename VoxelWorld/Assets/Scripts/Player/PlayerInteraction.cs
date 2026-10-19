using System;
using UnityEngine;
using VoxelWorld.Core;
using VoxelWorld.Inventory;
using VoxelWorld.Rendering;
using VoxelWorld.Voxel;
using VoxelWorld.World;

namespace VoxelWorld.Player
{
    /// <summary>
    /// Targets blocks with a camera ray, mines them over time (left mouse), places the selected
    /// hotbar block (right mouse) and handles hotbar selection. All rules come from block data,
    /// so new block types work without changes here.
    /// </summary>
    public sealed class PlayerInteraction : MonoBehaviour
    {
        [SerializeField] private float reach = 5f;
        [SerializeField] private float breakCooldown = 0.18f;
        [SerializeField] private float placeRepeatDelay = 0.22f;
        [Tooltip("Multiplier applied to every block's hardness (mining time in seconds).")]
        [SerializeField] private float miningTimeScale = 1f;

        private WorldManager _world;
        private PlayerController _player;
        private PlayerInventory _inventory;
        private SelectionOutline _outline;

        private bool _hasTarget;
        private VoxelHit _target;
        private float _progress;
        private float _cooldownUntil;
        private float _nextPlaceTime;

        public bool HasTarget => _hasTarget;
        public VoxelHit Target => _target;
        /// <summary>Mining progress of the current target in [0, 1].</summary>
        public float MiningProgress => _progress;

        /// <summary>Raised after a block is broken: (x, y, z, block).</summary>
        public event Action<int, int, int, ushort> BlockBroken;
        /// <summary>Raised after a block is placed: (x, y, z, block).</summary>
        public event Action<int, int, int, ushort> BlockPlaced;

        public void Initialize(WorldManager world, PlayerController player, PlayerInventory inventory, SelectionOutline outline)
        {
            _world = world;
            _player = player;
            _inventory = inventory;
            _outline = outline;
        }

        private void Update()
        {
            if (_world == null) return;
            if (GameState.InputBlocked)
            {
                _hasTarget = false;
                _progress = 0f;
                _outline.Hide();
                return;
            }

            HandleHotbar();
            UpdateTarget();
            HandleMining(Time.deltaTime);
            HandlePlacing();
            HandlePickBlock();

            if (_hasTarget) _outline.Show(_target.X, _target.Y, _target.Z, _progress);
            else _outline.Hide();
        }

        private void HandleHotbar()
        {
            int number = GameInput.NumberKeyPressed();
            if (number >= 0) _inventory.SelectedSlot = number;
            float scroll = GameInput.Scroll;
            if (scroll != 0f) _inventory.SelectedSlot = _inventory.SelectedSlot - (int)scroll;
        }

        private void UpdateTarget()
        {
            var cam = _player.Camera.transform;
            var root = _world.transform;
            Vector3 origin = root.InverseTransformPoint(cam.position);
            Vector3 dir = root.InverseTransformDirection(cam.forward);

            bool hadTarget = _hasTarget;
            var previous = _target;
            _hasTarget = VoxelRaycast.Cast(_world, _world.Registry, origin.x, origin.y, origin.z,
                dir.x, dir.y, dir.z, reach, out _target);

            if (!_hasTarget || !hadTarget || previous.X != _target.X || previous.Y != _target.Y || previous.Z != _target.Z)
                _progress = 0f;
        }

        private void HandleMining(float dt)
        {
            if (!_hasTarget || !GameInput.PrimaryHeld)
            {
                _progress = 0f;
                return;
            }
            if (Time.time < _cooldownUntil) return;

            var def = _world.Registry[_target.Block];
            if (!def.IsBreakable) return;

            float time = def.Hardness * miningTimeScale;
            if (time <= 0f)
            {
                // Instant blocks (plants) break on click, or repeatedly while held after the cooldown.
                Break();
                return;
            }

            _progress += dt / time;
            if (_progress >= 1f) Break();
        }

        private void Break()
        {
            int x = _target.X, y = _target.Y, z = _target.Z;
            ushort block = _target.Block;
            if (!_world.SetBlock(x, y, z, Blocks.Air)) return;

            Collect(_world.Registry[block]);
            BlockBroken?.Invoke(x, y, z, block);

            // Plants standing on the removed block lose their support.
            ushort above = _world.GetBlock(x, y + 1, z);
            var aboveDef = _world.Registry[above];
            if (aboveDef.NeedsSupport && _world.SetBlock(x, y + 1, z, Blocks.Air))
            {
                Collect(aboveDef);
                BlockBroken?.Invoke(x, y + 1, z, above);
            }

            _progress = 0f;
            _hasTarget = false;
            _cooldownUntil = Time.time + breakCooldown;
        }

        private void Collect(BlockDefinition def)
        {
            if (def.DropItem <= 0 || def.DropCount <= 0) return;
            // Items that do not fit are lost for now; dropped item entities come with the item phase.
            _inventory.Add(def.DropItem, def.DropCount);
        }

        private void HandlePlacing()
        {
            if (!_hasTarget) return;
            bool pressed = GameInput.SecondaryPressed;
            if (!pressed && !(GameInput.SecondaryHeld && Time.time >= _nextPlaceTime)) return;
            _nextPlaceTime = Time.time + placeRepeatDelay;
            TryPlace();
        }

        private bool TryPlace()
        {
            var stack = _inventory.SelectedStack;
            if (stack.IsEmpty) return false;
            var item = _inventory.Items.Get(stack.ItemId);
            if (item == null || !item.IsPlaceable) return false;

            var registry = _world.Registry;
            int x = _target.X, y = _target.Y, z = _target.Z;
            if (!registry[_target.Block].IsReplaceable)
            {
                x += _target.NX;
                y += _target.NY;
                z += _target.NZ;
            }

            if (y < 0 || y >= _world.Dims.Height) return false;
            ushort existing = _world.GetBlock(x, y, z);
            if (existing == Blocks.Unloaded || !registry[existing].IsReplaceable) return false;

            var def = registry[item.PlacesBlock];
            if (def.NeedsSupport && !registry.IsOpaque(_world.GetBlock(x, y - 1, z))) return false;
            if (def.IsSolid && _player.Bounds.IntersectsBlock(x, y, z)) return false;

            if (!_world.SetBlock(x, y, z, def.Id)) return false;
            _inventory.RemoveFromSlot(_inventory.SelectedSlot, 1);
            BlockPlaced?.Invoke(x, y, z, def.Id);
            _hasTarget = false;
            return true;
        }

        private void HandlePickBlock()
        {
            if (!_hasTarget || !GameInput.PickBlockPressed) return;
            int itemId = _target.Block;
            for (int i = 0; i < PlayerInventory.HotbarSize; i++)
            {
                if (_inventory[i].ItemId == itemId)
                {
                    _inventory.SelectedSlot = i;
                    return;
                }
            }
        }
    }
}
