using System;

namespace VoxelWorld.Inventory
{
    [Serializable]
    public struct ItemStack
    {
        public int ItemId;
        public int Count;

        public ItemStack(int itemId, int count)
        {
            ItemId = itemId;
            Count = count;
        }

        public bool IsEmpty => ItemId == 0 || Count <= 0;
        public static ItemStack Empty => default;
    }

    /// <summary>
    /// Slot-based inventory. The first <see cref="HotbarSize"/> slots form the hotbar.
    /// Pure data: the UI listens to <see cref="Changed"/>.
    /// </summary>
    public sealed class PlayerInventory
    {
        public const int HotbarSize = 9;

        private readonly ItemStack[] _slots;
        private readonly ItemRegistry _items;
        private int _selected;

        public event Action Changed;

        public PlayerInventory(ItemRegistry items, int slotCount = 36)
        {
            if (slotCount < HotbarSize) throw new ArgumentException("Inventory must hold at least the hotbar.");
            _items = items ?? throw new ArgumentNullException(nameof(items));
            _slots = new ItemStack[slotCount];
        }

        public int SlotCount => _slots.Length;
        public ItemRegistry Items => _items;

        public ItemStack this[int slot] => _slots[slot];

        public int SelectedSlot
        {
            get => _selected;
            set
            {
                int v = ((value % HotbarSize) + HotbarSize) % HotbarSize;
                if (v == _selected) return;
                _selected = v;
                Changed?.Invoke();
            }
        }

        public ItemStack SelectedStack => _slots[_selected];

        /// <summary>
        /// Adds items, filling existing stacks first, then empty slots (hotbar first).
        /// Returns the number of items that did not fit.
        /// </summary>
        public int Add(int itemId, int count)
        {
            if (itemId == 0 || count <= 0) return 0;
            int max = Math.Max(1, _items.MaxStackOf(itemId));
            int remaining = count;

            for (int i = 0; i < _slots.Length && remaining > 0; i++)
            {
                if (_slots[i].ItemId != itemId || _slots[i].Count >= max) continue;
                int move = Math.Min(max - _slots[i].Count, remaining);
                _slots[i].Count += move;
                remaining -= move;
            }
            for (int i = 0; i < _slots.Length && remaining > 0; i++)
            {
                if (!_slots[i].IsEmpty) continue;
                int move = Math.Min(max, remaining);
                _slots[i] = new ItemStack(itemId, move);
                remaining -= move;
            }

            if (remaining != count) Changed?.Invoke();
            return remaining;
        }

        /// <summary>Removes up to <paramref name="count"/> items from a slot; returns how many were removed.</summary>
        public int RemoveFromSlot(int slot, int count)
        {
            if (count <= 0 || _slots[slot].IsEmpty) return 0;
            int removed = Math.Min(count, _slots[slot].Count);
            _slots[slot].Count -= removed;
            if (_slots[slot].Count <= 0) _slots[slot] = ItemStack.Empty;
            Changed?.Invoke();
            return removed;
        }

        /// <summary>Total number of an item across all slots.</summary>
        public int CountOf(int itemId)
        {
            int total = 0;
            foreach (var s in _slots) if (s.ItemId == itemId) total += s.Count;
            return total;
        }

        /// <summary>Removes items from anywhere in the inventory. Returns false (and removes nothing) if there are not enough.</summary>
        public bool TryRemove(int itemId, int count)
        {
            if (CountOf(itemId) < count) return false;
            int remaining = count;
            for (int i = _slots.Length - 1; i >= 0 && remaining > 0; i--)
            {
                if (_slots[i].ItemId != itemId) continue;
                int take = Math.Min(remaining, _slots[i].Count);
                _slots[i].Count -= take;
                remaining -= take;
                if (_slots[i].Count <= 0) _slots[i] = ItemStack.Empty;
            }
            Changed?.Invoke();
            return true;
        }

        public void SetSlot(int slot, ItemStack stack)
        {
            _slots[slot] = stack.IsEmpty ? ItemStack.Empty : stack;
            Changed?.Invoke();
        }

        public void Clear()
        {
            Array.Clear(_slots, 0, _slots.Length);
            Changed?.Invoke();
        }
    }
}
