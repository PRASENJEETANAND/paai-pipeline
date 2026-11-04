"""Open the Render Browser: prefer Qt (Nuke look in-process), else web fallback."""


def _have_qt():
    try:
        from PySide6 import QtWidgets  # noqa: F401
        return "PySide6"
    except Exception:
        pass
    try:
        from PySide2 import QtWidgets  # noqa: F401
        return "PySide2"
    except Exception:
        return None


def show(context=None):
    qt = _have_qt()
    if qt:
        from . import browser_qt
        print("[PAAI Pipeline] opening Qt Render Browser (%s)" % qt)
        return browser_qt.show(context)
    from . import browser_web
    print("[PAAI Pipeline] PySide not found — opening web Render Browser")
    return browser_web.show(context)
