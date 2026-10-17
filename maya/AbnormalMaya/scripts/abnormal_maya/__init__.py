"""Abnormal Maya: a face-vertex normal editor for Maya 2024+ (MIT)."""
__version__ = '0.9.3'


def show():
    from .ui import show as show_panel
    return show_panel()
