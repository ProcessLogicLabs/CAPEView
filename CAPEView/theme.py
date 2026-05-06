"""CAPEView theme — muted cyan base palette.

Modeled on theme_reference.py in the DevHouston tree. Apply via apply_theme()
which converts the dict into a QPalette and applies it to the QApplication.
"""

from PyQt5.QtGui import QColor, QPalette

MUTED_CYAN = {
    "Window":          (232, 242, 244),   # pale cool gray-cyan background
    "WindowText":      (28, 42, 48),
    "Base":            (245, 250, 251),   # input/list backgrounds
    "AlternateBase":   (220, 234, 237),   # zebra rows
    "ToolTipBase":     (255, 255, 255),
    "ToolTipText":     (28, 42, 48),
    "Text":            (28, 42, 48),
    "Button":          (78, 140, 155),    # muted cyan primary
    "ButtonText":      (255, 255, 255),
    "BrightText":      (200, 70, 70),
    "Link":            (50, 120, 145),
    "Highlight":       (95, 165, 180),    # selection
    "HighlightedText": (255, 255, 255),
}

BUTTON_STYLES = {
    "primary": "background: #4E8C9B; color: #fff; font-weight: bold; padding: 6px 14px;",
    "info":    "background: #5FA5B4; color: #fff; font-weight: bold; padding: 6px 14px;",
    "success": "background: #4F8E6F; color: #fff; font-weight: bold; padding: 6px 14px;",
    "warning": "background: #C9A227; color: #222; font-weight: bold; padding: 6px 14px;",
    "danger":  "background: #A4515A; color: #fff; font-weight: bold; padding: 6px 14px;",
    "ghost":   "background: transparent; color: #28323A; padding: 6px 14px;",
}

# Splash colors (consumed by animated_splash.py)
SPLASH_COLORS = {
    "bg_top":    (232, 242, 244),
    "bg_mid":    (208, 226, 230),
    "bg_bottom": (232, 242, 244),
    "border":    (78, 140, 155, 140),
    "ring_a":    (78, 140, 155, 200),
    "ring_b":    (95, 165, 180, 200),
    "ring_c":    (110, 175, 188, 150),
    "emblem_bg_outer": (210, 228, 232),
    "emblem_bg_inner": (240, 248, 250),
    "emblem_border":   (140, 175, 185),
    "emblem_pulse":    (78, 140, 155, 200),
    "emblem_text":     (28, 50, 60),
    "title":     (28, 50, 60),
    "tagline":   (90, 115, 122),
    "progress_track": (200, 218, 222),
    "progress_fill_a": (78, 140, 155),
    "progress_fill_b": (95, 165, 180),
    "progress_fill_c": (60, 120, 138),
    "version":   (110, 130, 138),
    "corner_accent": (78, 140, 155),
}


def apply_theme(app, palette_dict=None):
    """Apply a palette dict (default MUTED_CYAN) to a QApplication."""
    palette_dict = palette_dict or MUTED_CYAN
    palette = QPalette()
    role_map = {
        "Window":          QPalette.Window,
        "WindowText":      QPalette.WindowText,
        "Base":            QPalette.Base,
        "AlternateBase":   QPalette.AlternateBase,
        "ToolTipBase":     QPalette.ToolTipBase,
        "ToolTipText":     QPalette.ToolTipText,
        "Text":            QPalette.Text,
        "Button":          QPalette.Button,
        "ButtonText":      QPalette.ButtonText,
        "BrightText":      QPalette.BrightText,
        "Link":            QPalette.Link,
        "Highlight":       QPalette.Highlight,
        "HighlightedText": QPalette.HighlightedText,
    }
    for name, role in role_map.items():
        if name in palette_dict:
            palette.setColor(role, QColor(*palette_dict[name]))
    app.setPalette(palette)


def style(button_kind: str) -> str:
    """Return the QSS string for a named button style ('primary', 'info', ...)."""
    return BUTTON_STYLES.get(button_kind, BUTTON_STYLES["primary"])
