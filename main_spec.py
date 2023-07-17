import sys
from PyQt5 import QtCore, QtWidgets, QtGui
import sys
import pyqtgraph as pg
from live_view_spec import LiveViewUi


def run():
    pg.setConfigOption("background", "k")
    pg.setConfigOption("foreground", "w")

    app = QtWidgets.QApplication(sys.argv)
    ui = LiveViewUi(1)
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
