using System;
using UnityEngine;

namespace VoxelWorld.Core
{
    /// <summary>Global play state: whether gameplay input is active and the cursor is captured.</summary>
    public static class GameState
    {
        private static int _uiLocks;

        /// <summary>True while the world is loading or a menu is open.</summary>
        public static bool InputBlocked => _uiLocks > 0 || !WorldReady;

        public static bool WorldReady { get; set; }

        public static event Action Changed;

        /// <summary>Opens a UI layer that releases the cursor. Balance with <see cref="PopUi"/>.</summary>
        public static void PushUi()
        {
            _uiLocks++;
            ApplyCursor();
            Changed?.Invoke();
        }

        public static void PopUi()
        {
            _uiLocks = Math.Max(0, _uiLocks - 1);
            ApplyCursor();
            Changed?.Invoke();
        }

        public static void ApplyCursor()
        {
            bool captured = _uiLocks == 0 && WorldReady;
            Cursor.lockState = captured ? CursorLockMode.Locked : CursorLockMode.None;
            Cursor.visible = !captured;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetStatics()
        {
            _uiLocks = 0;
            WorldReady = false;
            Changed = null;
        }
    }
}
