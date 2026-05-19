import sys
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication
from theme import apply_dark_palette, QSS
from window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TVSeriesTracker")
    apply_dark_palette(app)
    app.setStyleSheet(QSS)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.setWindowTitle("My Series Tracker")
    window.resize(1380, 880)
    window.setMinimumSize(900, 560)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
