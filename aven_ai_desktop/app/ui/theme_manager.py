"""Light and dark themes: color tokens and the application stylesheet."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

UI_FONT_FAMILIES = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'
CODE_FONT_FAMILIES = '"Cascadia Code", "Cascadia Mono", Consolas, "JetBrains Mono", "DejaVu Sans Mono", monospace'


@dataclass(frozen=True)
class Palette:
    name: str
    dark: bool
    window: str
    sidebar: str
    surface: str
    surface_alt: str
    hover: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    accent_soft: str
    gradient_start: str
    gradient_end: str
    user_bubble: str
    code_bg: str
    code_header: str
    danger: str
    danger_soft: str
    success: str
    warning_soft: str
    selection: str


DARK = Palette(
    name="dark",
    dark=True,
    window="#0f1116",
    sidebar="#0a0c10",
    surface="#161920",
    surface_alt="#1c2029",
    hover="#232733",
    border="#262b36",
    text="#e8eaf0",
    text_muted="#959cab",
    accent="#7b6cff",
    accent_hover="#8f82ff",
    accent_text="#ffffff",
    accent_soft="#262347",
    gradient_start="#7b6cff",
    gradient_end="#22c7e8",
    user_bubble="#222737",
    code_bg="#11131a",
    code_header="#1a1d26",
    danger="#f87171",
    danger_soft="#3a1d22",
    success="#34d399",
    warning_soft="#3a311b",
    selection="#3b3570",
)

LIGHT = Palette(
    name="light",
    dark=False,
    window="#ffffff",
    sidebar="#f5f6f8",
    surface="#ffffff",
    surface_alt="#f2f3f6",
    hover="#e9ebf0",
    border="#e2e5eb",
    text="#161a22",
    text_muted="#5d6577",
    accent="#5a4af0",
    accent_hover="#4a3ae0",
    accent_text="#ffffff",
    accent_soft="#ecebfe",
    gradient_start="#6a5af9",
    gradient_end="#14b3d6",
    user_bubble="#eef0f9",
    code_bg="#f6f7fa",
    code_header="#eceef3",
    danger="#d93a3a",
    danger_soft="#fdecec",
    success="#119868",
    warning_soft="#fff6e0",
    selection="#d7d3fd",
)


def build_stylesheet(p: Palette) -> str:
    return f"""
    * {{ font-family: {UI_FONT_FAMILIES}; }}
    QMainWindow, QDialog {{ background: {p.window}; color: {p.text}; }}
    QWidget {{ color: {p.text}; font-size: 14px; }}
    QToolTip {{ background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border}; padding: 4px 8px; }}

    /* Sidebar */
    #Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
    #BrandName {{ font-size: 17px; font-weight: 700; letter-spacing: 0.5px; }}
    #BrandEdition {{ color: {p.text_muted}; font-size: 11px; }}
    #SectionLabel {{ color: {p.text_muted}; font-size: 11px; font-weight: 600; letter-spacing: 0.8px; }}
    #NewChatButton {{
        background: {p.accent}; color: {p.accent_text}; border: none; border-radius: 10px;
        padding: 10px 14px; font-weight: 600; text-align: left;
    }}
    #NewChatButton:hover {{ background: {p.accent_hover}; }}
    #SearchField {{
        background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 9px; padding: 7px 10px;
    }}
    #SearchField:focus {{ border-color: {p.accent}; }}
    #ConversationList {{ background: transparent; border: none; outline: none; }}
    #ConversationList::item {{ padding: 9px 10px; border-radius: 8px; margin: 1px 0; color: {p.text}; }}
    #ConversationList::item:hover {{ background: {p.hover}; }}
    #ConversationList::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
    #SidebarFooterButton {{
        background: transparent; border: none; border-radius: 8px; padding: 8px 10px; text-align: left;
        color: {p.text};
    }}
    #SidebarFooterButton:hover {{ background: {p.hover}; }}

    /* Header */
    #ChatHeader {{ background: {p.window}; border-bottom: 1px solid {p.border}; }}
    #ConversationTitle {{ font-size: 15px; font-weight: 600; }}
    #ModelLabel {{ color: {p.text_muted}; font-size: 12px; }}
    #ModeSwitch {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; }}
    #ModeButton {{
        background: transparent; border: none; border-radius: 8px; padding: 6px 14px;
        color: {p.text_muted}; font-weight: 600; font-size: 13px;
    }}
    #ModeButton:hover {{ color: {p.text}; }}
    #ModeButton:checked {{ background: {p.surface}; color: {p.accent}; border: 1px solid {p.border}; }}

    /* Chat area */
    #ChatScroll, #ChatScroll > QWidget > QWidget {{ background: {p.window}; border: none; }}
    #MessageList {{ background: {p.window}; }}
    #UserBubble {{ background: {p.user_bubble}; border-radius: 16px; }}
    #MessageMeta {{ color: {p.text_muted}; font-size: 12px; }}
    #AssistantName {{ font-weight: 600; font-size: 13px; }}
    #MessageAction {{
        background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 3px 8px;
        color: {p.text_muted}; font-size: 12px;
    }}
    #MessageAction:hover {{ background: {p.hover}; color: {p.text}; }}
    #StatusNote {{ color: {p.text_muted}; font-size: 12px; font-style: italic; }}
    #TypingLabel {{ color: {p.text_muted}; font-size: 13px; }}

    #CodeBlock {{ background: {p.code_bg}; border: 1px solid {p.border}; border-radius: 10px; }}
    #CodeHeader {{ background: {p.code_header}; border-top-left-radius: 10px; border-top-right-radius: 10px;
        border-bottom: 1px solid {p.border}; }}
    #CodeLanguage {{ color: {p.text_muted}; font-size: 12px; font-weight: 600; }}
    #CodeCopy {{ background: transparent; border: none; color: {p.text_muted}; font-size: 12px; padding: 3px 8px;
        border-radius: 6px; }}
    #CodeCopy:hover {{ background: {p.hover}; color: {p.text}; }}

    #ErrorCard {{ background: {p.danger_soft}; border: 1px solid {p.danger}; border-radius: 12px; }}
    #ErrorTitle {{ color: {p.danger}; font-weight: 700; }}
    #SetupCard {{ background: {p.warning_soft}; border: 1px solid {p.border}; border-radius: 12px; }}

    /* Welcome */
    #WelcomeTitle {{ font-size: 26px; font-weight: 700; }}
    #WelcomeSubtitle {{ color: {p.text_muted}; font-size: 14px; }}
    #SuggestionCard {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; padding: 12px 14px;
        text-align: left; color: {p.text};
    }}
    #SuggestionCard:hover {{ border-color: {p.accent}; background: {p.surface_alt}; }}

    /* Composer */
    #ComposerFrame {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
    #ComposerFrame[focused="true"] {{ border-color: {p.accent}; }}
    #ComposerInput {{ background: transparent; border: none; font-size: 14px; }}
    #SendButton {{
        background: {p.accent}; color: {p.accent_text}; border: none; border-radius: 10px;
        padding: 8px 16px; font-weight: 600;
    }}
    #SendButton:hover {{ background: {p.accent_hover}; }}
    #SendButton:disabled {{ background: {p.hover}; color: {p.text_muted}; }}
    #SendButton[stop="true"] {{ background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border}; }}
    #ComposerHint {{ color: {p.text_muted}; font-size: 11px; }}
    #ModelPicker {{
        background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 9px; padding: 6px 10px;
        color: {p.text}; font-weight: 600; font-size: 13px;
    }}
    #ModelPicker:hover {{ border-color: {p.accent}; }}
    #ModelPicker::menu-indicator {{ image: none; width: 0px; }}
    #ModelMenu {{ padding: 6px; min-width: 300px; }}
    #ModelOption {{ border-radius: 8px; }}
    #ModelOption:hover {{ background: {p.hover}; }}
    #ModelOption[selected="true"] {{ background: {p.accent_soft}; }}
    #ModelOptionName {{ font-weight: 600; background: transparent; }}
    #ModelOptionDescription {{ color: {p.text_muted}; font-size: 12px; background: transparent; }}
    #ModelOptionCheck {{ color: {p.accent}; font-weight: 700; background: transparent; }}

    /* Generic controls */
    QPushButton {{
        background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px; padding: 7px 14px;
        color: {p.text};
    }}
    QPushButton:hover {{ background: {p.hover}; }}
    QPushButton:disabled {{ color: {p.text_muted}; }}
    QPushButton#PrimaryButton {{ background: {p.accent}; color: {p.accent_text}; border: none; font-weight: 600; }}
    QPushButton#PrimaryButton:hover {{ background: {p.accent_hover}; }}
    QPushButton#DangerButton {{ color: {p.danger}; }}
    QLineEdit, QComboBox, QSpinBox {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px 9px;
        selection-background-color: {p.selection};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
    /* Values are edited by typing or the mouse wheel; hide the unstyled stepper buttons. */
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; border: none; }}
    QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
        selection-background-color: {p.accent_soft}; selection-color: {p.text}; }}
    QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 10px; top: -1px; background: {p.window}; }}
    QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {p.text_muted}; border: none; }}
    QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
    QLabel#HelpText {{ color: {p.text_muted}; font-size: 12px; }}
    QLabel#ResultOk {{ color: {p.success}; }}
    QLabel#ResultError {{ color: {p.danger}; }}
    QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 4px; border-radius: 8px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p.hover}; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """


def message_css(p: Palette) -> str:
    """Stylesheet for rendered Markdown inside QTextDocument (subset of CSS)."""
    return f"""
    body {{ color: {p.text}; }}
    p {{ margin-top: 0px; margin-bottom: 10px; line-height: 150%; }}
    li {{ margin-bottom: 4px; line-height: 150%; }}
    ul, ol {{ margin-top: 0px; margin-bottom: 10px; }}
    h1 {{ font-size: 21px; margin-top: 8px; margin-bottom: 8px; }}
    h2 {{ font-size: 18px; margin-top: 8px; margin-bottom: 8px; }}
    h3 {{ font-size: 16px; margin-top: 6px; margin-bottom: 6px; }}
    h4, h5, h6 {{ font-size: 14px; margin-top: 6px; margin-bottom: 6px; }}
    a {{ color: {p.accent}; text-decoration: none; }}
    code {{ font-family: {CODE_FONT_FAMILIES}; background-color: {p.surface_alt}; color: {p.text}; }}
    pre {{ font-family: {CODE_FONT_FAMILIES}; background-color: {p.code_bg}; padding: 8px; }}
    blockquote {{ color: {p.text_muted}; margin-left: 12px; }}
    table {{ border-color: {p.border}; margin-bottom: 10px; }}
    th {{ background-color: {p.surface_alt}; font-weight: 600; }}
    hr {{ color: {p.border}; }}
    """


class ThemeManager(QObject):
    changed = Signal(object)  # Palette

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.setting = "system"
        self.palette: Palette = LIGHT
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

    def resolve(self, setting: str) -> Palette:
        if setting == "dark":
            return DARK
        if setting == "light":
            return LIGHT
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme() if hasattr(hints, "colorScheme") else Qt.ColorScheme.Unknown
        return DARK if scheme == Qt.ColorScheme.Dark else LIGHT

    def apply(self, setting: str) -> None:
        self.setting = setting
        self.palette = self.resolve(setting)
        p = self.palette
        qp = QPalette()
        for role, color in (
            (QPalette.ColorRole.Window, p.window),
            (QPalette.ColorRole.WindowText, p.text),
            (QPalette.ColorRole.Base, p.surface),
            (QPalette.ColorRole.AlternateBase, p.surface_alt),
            (QPalette.ColorRole.Text, p.text),
            (QPalette.ColorRole.Button, p.surface_alt),
            (QPalette.ColorRole.ButtonText, p.text),
            (QPalette.ColorRole.Highlight, p.selection),
            (QPalette.ColorRole.HighlightedText, p.text),
            (QPalette.ColorRole.Link, p.accent),
            (QPalette.ColorRole.PlaceholderText, p.text_muted),
            (QPalette.ColorRole.ToolTipBase, p.surface_alt),
            (QPalette.ColorRole.ToolTipText, p.text),
        ):
            qp.setColor(role, QColor(color))
        self.app.setPalette(qp)
        self.app.setStyleSheet(build_stylesheet(p))
        self.changed.emit(p)

    def _on_system_scheme_changed(self, *_args: object) -> None:
        if self.setting == "system":
            self.apply("system")
