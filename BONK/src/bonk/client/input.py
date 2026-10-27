"""Player input: keyboard + mouse today, gamepads through the same interface.

Every source produces an abstract `InputFrame` (move vector relative to the
camera, look delta, buttons).  The game turns that into a world-space
InputCommand using the camera heading, so adding a new device only means
writing another source class.
"""

from dataclasses import dataclass

from panda3d.core import InputDevice, KeyboardButton, WindowProperties

from ..sim.character import InputCommand


def _button(name):
    special = {"space": KeyboardButton.space(), "shift": KeyboardButton.shift(),
               "arrow_up": KeyboardButton.up(), "arrow_down": KeyboardButton.down(),
               "arrow_left": KeyboardButton.left(), "arrow_right": KeyboardButton.right()}
    return special.get(name) or KeyboardButton.asciiKey(name)


@dataclass
class InputFrame:
    forward: float = 0.0  # -1..1
    strafe: float = 0.0  # -1..1 (right positive)
    look_x: float = 0.0  # degrees this frame
    look_y: float = 0.0
    jump: bool = False
    walk: bool = False


class KeyboardMouse:
    """Polls button state every frame (robust with modifier keys held down)."""

    BINDINGS = {
        "forward": ("w", "arrow_up"),
        "back": ("s", "arrow_down"),
        "left": ("a", "arrow_left"),
        "right": ("d", "arrow_right"),
        "jump": ("space",),
        "walk": ("shift",),
        "cam_left": ("q",),
        "cam_right": ("e",),
    }

    def __init__(self, base, settings):
        self.base = base
        self.settings = settings
        self.captured = False
        self._skip_frames = 0
        self.buttons = {a: [_button(k) for k in keys]
                        for a, keys in self.BINDINGS.items()}

    def pressed(self, action):
        mw = self.base.mouseWatcherNode
        if mw is None:
            return False
        return any(mw.isButtonDown(b) for b in self.buttons[action])

    def capture_mouse(self, flag):
        """Hide and recentre the pointer while playing; release it in menus."""
        if self.base.win is None or not hasattr(self.base.win, "requestProperties"):
            return
        props = WindowProperties()
        props.setCursorHidden(flag)
        props.setMouseMode(WindowProperties.M_confined if flag else WindowProperties.M_absolute)
        self.base.win.requestProperties(props)
        self.captured = flag
        self._skip_frames = 2
        if flag:
            self._recenter()

    def _recenter(self):
        win = self.base.win
        win.movePointer(0, win.getXSize() // 2, win.getYSize() // 2)

    def poll(self, dt):
        f = InputFrame()
        f.forward = (1.0 if self.pressed("forward") else 0.0) - (1.0 if self.pressed("back") else 0.0)
        f.strafe = (1.0 if self.pressed("right") else 0.0) - (1.0 if self.pressed("left") else 0.0)
        f.jump = self.pressed("jump")
        walk_key = self.pressed("walk")
        f.walk = walk_key if self.settings.get("always_run", True) else not walk_key
        sens = self.settings.get("mouse_sensitivity", 1.0)
        if self.pressed("cam_left"):
            f.look_x += 120.0 * dt
        if self.pressed("cam_right"):
            f.look_x -= 120.0 * dt
        win = self.base.win
        if self.captured and win is not None and hasattr(win, "getPointer"):
            md = win.getPointer(0)
            cx, cy = win.getXSize() // 2, win.getYSize() // 2
            if self._skip_frames > 0:
                self._skip_frames -= 1
            elif md.getInWindow():
                f.look_x -= (md.getX() - cx) * 0.18 * sens
                dy = (md.getY() - cy) * 0.14 * sens
                f.look_y -= -dy if self.settings.get("invert_y") else dy
            self._recenter()
        return f


class Gamepad:
    """Optional gamepad (left stick move, right stick camera, A/cross jump, B/circle walk)."""

    def __init__(self, base):
        self.base = base
        self.device = None
        mgr = getattr(base, "devices", None)
        if mgr is None:
            return
        pads = mgr.getDevices(InputDevice.DeviceClass.gamepad)
        if pads:
            self.attach(pads[0])

    def attach(self, device):
        self.device = device
        self.base.attachInputDevice(device, prefix="pad")

    def _axis(self, axis):
        try:
            a = self.device.findAxis(axis)
            return a.value if a else 0.0
        except Exception:  # a device can vanish at any time
            return 0.0

    def poll(self, dt):
        if self.device is None or not self.device.connected:
            return None
        f = InputFrame()
        dz = 0.18
        lx, ly = self._axis(InputDevice.Axis.left_x), self._axis(InputDevice.Axis.left_y)
        rx, ry = self._axis(InputDevice.Axis.right_x), self._axis(InputDevice.Axis.right_y)
        f.strafe = lx if abs(lx) > dz else 0.0
        f.forward = ly if abs(ly) > dz else 0.0
        f.look_x = -rx * 160.0 * dt if abs(rx) > dz else 0.0
        f.look_y = ry * 100.0 * dt if abs(ry) > dz else 0.0
        try:
            f.jump = self.device.findButton("face_a").pressed
            f.walk = self.device.findButton("face_b").pressed
        except Exception:
            pass
        # Analog stick: small deflection = walk speed naturally (magnitude < 1).
        return f


def frame_to_command(frame, cam):
    """Camera-relative input -> world-space InputCommand."""
    (fx, fy), (rx, ry) = cam.heading_vectors()
    mx = fx * frame.forward + rx * frame.strafe
    my = fy * frame.forward + ry * frame.strafe
    return InputCommand(mx, my, frame.jump, frame.walk).sanitized()
