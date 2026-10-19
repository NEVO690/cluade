// Compile-check stubs mirroring the public uGUI API surface used by the game.
using UnityEngine.Events;
namespace UnityEngine.EventSystems {
  public class UIBehaviour : MonoBehaviour {}
  public class EventSystem : UIBehaviour {}
  public abstract class BaseInputModule : UIBehaviour {}
  public class StandaloneInputModule : BaseInputModule {}
}
namespace UnityEngine.UI {
  public class Graphic : EventSystems.UIBehaviour { public virtual Color color {get;set;} public virtual bool raycastTarget {get;set;} public RectTransform rectTransform => null; }
  public class MaskableGraphic : Graphic {}
  public class Image : MaskableGraphic { public enum Type { Simple, Sliced, Tiled, Filled } public Sprite sprite {get;set;} public Type type {get;set;} public bool fillCenter {get;set;} public bool preserveAspect {get;set;} }
  public class RawImage : MaskableGraphic {}
  public class Text : MaskableGraphic { public Font font {get;set;} public virtual string text {get;set;} public int fontSize {get;set;} public TextAnchor alignment {get;set;} public FontStyle fontStyle {get;set;} public HorizontalWrapMode horizontalOverflow {get;set;} public VerticalWrapMode verticalOverflow {get;set;} }
  public class CanvasScaler : EventSystems.UIBehaviour { public enum ScaleMode { ConstantPixelSize, ScaleWithScreenSize, ConstantPhysicalSize } public enum ScreenMatchMode { MatchWidthOrHeight, Expand, Shrink } public ScaleMode uiScaleMode {get;set;} public Vector2 referenceResolution {get;set;} public ScreenMatchMode screenMatchMode {get;set;} public float matchWidthOrHeight {get;set;} }
  public class GraphicRaycaster : EventSystems.UIBehaviour {}
  public struct ColorBlock { public Color normalColor {get;set;} public Color highlightedColor {get;set;} public Color pressedColor {get;set;} public Color selectedColor {get;set;} public Color disabledColor {get;set;} public float colorMultiplier {get;set;} public float fadeDuration {get;set;} }
  public class Selectable : EventSystems.UIBehaviour { public ColorBlock colors {get;set;} public Graphic targetGraphic {get;set;} public bool interactable {get;set;} }
  public class Button : Selectable { public class ButtonClickedEvent : UnityEvent {} public ButtonClickedEvent onClick {get;set;} }
  public class Slider : Selectable { public enum Direction { LeftToRight, RightToLeft, BottomToTop, TopToBottom } public class SliderEvent : UnityEvent<float> {}
    public RectTransform fillRect {get;set;} public RectTransform handleRect {get;set;} public Direction direction {get;set;} public float minValue {get;set;} public float maxValue {get;set;} public bool wholeNumbers {get;set;} public float value {get;set;} public SliderEvent onValueChanged {get;set;} public void SetValueWithoutNotify(float v){} }
  public class BaseMeshEffect : EventSystems.UIBehaviour {}
  public class Shadow : BaseMeshEffect { public Color effectColor {get;set;} public Vector2 effectDistance {get;set;} }
  public class Outline : Shadow {}
  public abstract class LayoutGroup : EventSystems.UIBehaviour { public TextAnchor childAlignment {get;set;} public RectOffset padding {get;set;} }
  public abstract class HorizontalOrVerticalLayoutGroup : LayoutGroup { public float spacing {get;set;} public bool childForceExpandWidth {get;set;} public bool childForceExpandHeight {get;set;} public bool childControlWidth {get;set;} public bool childControlHeight {get;set;} }
  public class VerticalLayoutGroup : HorizontalOrVerticalLayoutGroup {}
  public class HorizontalLayoutGroup : HorizontalOrVerticalLayoutGroup {}
}
