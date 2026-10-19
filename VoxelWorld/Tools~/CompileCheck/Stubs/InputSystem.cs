namespace UnityEngine.InputSystem {
  public enum Key { None, Space, Enter, Tab, A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z, Digit1, Digit2, Digit3, Digit4, Digit5, Digit6, Digit7, Digit8, Digit9, Digit0, LeftShift, RightShift, LeftCtrl, RightCtrl, Escape, F1, F2, F3, F4 }
  namespace Controls { public class ButtonControl { public bool isPressed => false; public bool wasPressedThisFrame => false; public bool wasReleasedThisFrame => false; }
    public class KeyControl : ButtonControl {} public class Vector2Control { public Vector2 ReadValue() => default; } public class DeltaControl : Vector2Control {} }
  public class Keyboard { public static Keyboard current => null; public Controls.KeyControl this[Key key] => null; }
  public class Mouse { public static Mouse current => null; public Controls.DeltaControl delta => null; public Controls.DeltaControl scroll => null; public Controls.ButtonControl leftButton => null; public Controls.ButtonControl rightButton => null; public Controls.ButtonControl middleButton => null; }
}
namespace UnityEngine.InputSystem.UI { public class InputSystemUIInputModule : UnityEngine.EventSystems.BaseInputModule { public void AssignDefaultActions(){} } }
