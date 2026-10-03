import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import DARK_QSS, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
