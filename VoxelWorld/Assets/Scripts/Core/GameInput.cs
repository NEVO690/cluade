using UnityEngine;
#if ENABLE_INPUT_SYSTEM && VOXEL_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace VoxelWorld.Core
{
    /// <summary>
    /// Single place that reads player input. Uses the Input System package when it is installed
    /// and enabled in Player Settings, otherwise the legacy Input Manager, so the game works with
    /// either "Active Input Handling" setting.
    /// </summary>
    public static class GameInput
    {
        /// <summary>Legacy "Mouse X/Y" axes report roughly 1/10 of the pixel delta.</summary>
        private const float LegacyMouseToPixels = 10f;

#if ENABLE_INPUT_SYSTEM && VOXEL_INPUT_SYSTEM
        private static Keyboard K => Keyboard.current;
        private static Mouse M => Mouse.current;

        private static bool Held(Key key) => K != null && K[key].isPressed;
        private static bool Down(Key key) => K != null && K[key].wasPressedThisFrame;

        public static Vector2 Move
        {
            get
            {
                float x = (Held(Key.D) ? 1f : 0f) - (Held(Key.A) ? 1f : 0f);
                float y = (Held(Key.W) ? 1f : 0f) - (Held(Key.S) ? 1f : 0f);
                var v = new Vector2(x, y);
                return v.sqrMagnitude > 1f ? v.normalized : v;
            }
        }

        /// <summary>Mouse movement this frame in pixels.</summary>
        public static Vector2 LookDelta => M != null ? M.delta.ReadValue() : Vector2.zero;
        public static bool JumpHeld => Held(Key.Space);
        public static bool JumpPressed => Down(Key.Space);
        public static bool SprintHeld => Held(Key.LeftShift) || Held(Key.LeftCtrl);
        public static bool CrouchHeld => Held(Key.C);
        public static bool PrimaryHeld => M != null && M.leftButton.isPressed;
        public static bool PrimaryPressed => M != null && M.leftButton.wasPressedThisFrame;
        public static bool SecondaryHeld => M != null && M.rightButton.isPressed;
        public static bool SecondaryPressed => M != null && M.rightButton.wasPressedThisFrame;
        public static bool PickBlockPressed => M != null && M.middleButton.wasPressedThisFrame;
        public static float Scroll
        {
            get
            {
                float y = M != null ? M.scroll.ReadValue().y : 0f;
                return Mathf.Abs(y) > 0.01f ? Mathf.Sign(y) : 0f;
            }
        }
        public static bool PausePressed => Down(Key.Escape);
        public static bool DebugPressed => Down(Key.F3);
        public static bool InventoryPressed => Down(Key.E) || Down(Key.Tab);

        private static readonly Key[] NumberKeys =
        {
            Key.Digit1, Key.Digit2, Key.Digit3, Key.Digit4, Key.Digit5, Key.Digit6, Key.Digit7, Key.Digit8, Key.Digit9,
        };

        /// <summary>Returns 0-8 when a number key was pressed this frame, otherwise -1.</summary>
        public static int NumberKeyPressed()
        {
            for (int i = 0; i < NumberKeys.Length; i++) if (Down(NumberKeys[i])) return i;
            return -1;
        }
#else
        public static Vector2 Move
        {
            get
            {
                float x = (Input.GetKey(KeyCode.D) ? 1f : 0f) - (Input.GetKey(KeyCode.A) ? 1f : 0f);
                float y = (Input.GetKey(KeyCode.W) ? 1f : 0f) - (Input.GetKey(KeyCode.S) ? 1f : 0f);
                var v = new Vector2(x, y);
                return v.sqrMagnitude > 1f ? v.normalized : v;
            }
        }

        public static Vector2 LookDelta =>
            new Vector2(Input.GetAxisRaw("Mouse X"), Input.GetAxisRaw("Mouse Y")) * LegacyMouseToPixels;
        public static bool JumpHeld => Input.GetKey(KeyCode.Space);
        public static bool JumpPressed => Input.GetKeyDown(KeyCode.Space);
        public static bool SprintHeld => Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.LeftControl);
        public static bool CrouchHeld => Input.GetKey(KeyCode.C);
        public static bool PrimaryHeld => Input.GetMouseButton(0);
        public static bool PrimaryPressed => Input.GetMouseButtonDown(0);
        public static bool SecondaryHeld => Input.GetMouseButton(1);
        public static bool SecondaryPressed => Input.GetMouseButtonDown(1);
        public static bool PickBlockPressed => Input.GetMouseButtonDown(2);
        public static float Scroll
        {
            get
            {
                float y = Input.mouseScrollDelta.y;
                return Mathf.Abs(y) > 0.01f ? Mathf.Sign(y) : 0f;
            }
        }
        public static bool PausePressed => Input.GetKeyDown(KeyCode.Escape);
        public static bool DebugPressed => Input.GetKeyDown(KeyCode.F3);
        public static bool InventoryPressed => Input.GetKeyDown(KeyCode.E) || Input.GetKeyDown(KeyCode.Tab);

        public static int NumberKeyPressed()
        {
            for (int i = 0; i < 9; i++) if (Input.GetKeyDown(KeyCode.Alpha1 + i)) return i;
            return -1;
        }
#endif
    }
}
