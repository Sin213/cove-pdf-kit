import sys

from PySide6.QtWidgets import QApplication

from . import theme
from .app import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Cove PDF Kit")
    app.setOrganizationName("Cove")
    theme.apply(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
