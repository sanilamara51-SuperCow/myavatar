import sys

from storage.persona_registry import init_persona_registry
from storage.provider_registry import init_provider_registry


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        print(
            "PySide6 is not installed or unavailable. "
            "Install with: pip install PySide6"
        )
        print(f"Raw error: {exc}")
        return 1

    from desktop.main_window import MainWindow

    init_provider_registry()
    init_persona_registry()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
