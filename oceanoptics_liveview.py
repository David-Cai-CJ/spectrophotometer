from seabreeze.spectrometers import Spectrometer
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtGui
import numpy as np
from contextlib import contextmanager
from qdarkstyle import load_stylesheet_pyqt5
import sys
import os
from scipy.optimize import curve_fit, OptimizeWarning
from scipy.signal import find_peaks


def gaus(x, a, x0, sigma): return a * np.exp(-((x - x0) ** 2) / (2 * sigma ** 2))


@contextmanager
def gui_environment():
    """
    Prepare the environment in which egun GUI will run by setting
    the PyQtGraph QT library to PyQt5 while egun GUI is running. Revert back when done.
    """
    old_qt_lib = os.environ.get(
        "PYQTGRAPH_QT_LIB", "PyQt5"
    )  # environment variable might not exist
    os.environ["PYQTGRAPH_QT_LIB"] = "PyQt5"
    yield
    os.environ["PYQTGRAPH_QT_LIB"] = old_qt_lib


def run():
    with gui_environment():
        app = QtWidgets.QApplication(sys.argv)
        app.setStyleSheet(load_stylesheet_pyqt5())
        if len(sys.argv) > 1:
            gui = liveview(interval=1, serial_number=sys.argv[1])
        else:
            gui = liveview(interval=1)
        sys.exit(app.exec_())


class liveview(QtWidgets.QMainWindow):
    def __init__(self, interval, serial_number=None):
        super().__init__()
        self.interval = interval
        if serial_number is not None:
            self.spec = Spectrometer.from_serial_number(serial_number)
            self.serial_no = serial_number
        else:
            self.spec = Spectrometer.from_first_available()
            self.serial_no = self.spec.serial_number
        self.change_integration_time()

        self.setWindowTitle(f"Liveview - {self.serial_no}")
        self.setWindowIcon(QtGui.QIcon('icon.png'))

        self.dark_btn = QtWidgets.QPushButton("Dark spectra")
        self.dark_btn.setCheckable(True)
        self.dark_btn.setChecked(False)
        self.dark_btn.clicked.connect(self.dark_spectra)

        self.fit_gaussian_btn = QtWidgets.QPushButton("Fit Gaussian")
        self.fit_gaussian_btn.setCheckable(True)
        self.fit_gaussian_btn.setChecked(False)
        self.fit_gaussian_btn.clicked.connect(self.fit_gaussian)

        self.integration_label = QtWidgets.QLabel("Integration time [ms]: ")
        self.integration_label.setFixedWidth(150)

        self.set_integration_btn = QtWidgets.QLineEdit(parent=self)
        self.set_integration_btn.setPlaceholderText("100")
        self.set_integration_btn.editingFinished.connect(
            lambda: self.change_integration_time(self.set_integration_btn.text())
        )
        self.set_integration_btn.setFixedWidth(100)
        self.qGraph = pg.PlotWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.qGraph)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.dark_btn)
        btns.addWidget(self.fit_gaussian_btn)
        btns.addWidget(self.integration_label)
        btns.addWidget(self.set_integration_btn)
        layout.addLayout(btns)

        # self.p1 = self.qGraph.addPlot()
        self.qGraph.getPlotItem().setLabel("left", "Counts [au]")
        self.qGraph.getPlotItem().setLabel("bottom", "Wavelength [nm]")
        self._measurements_data_item = pg.PlotDataItem(
            pen=pg.mkPen("r", width=2),
        )
        self._measurements_fit_item = pg.PlotDataItem(
            pen=pg.mkPen("g", width=1),
        )

        self.qGraph.addItem(self._measurements_data_item)
        self.qGraph.addItem(self._measurements_fit_item)
        self.arrows = []
        self.texts = []

        self.update()
        self.dark = np.zeros_like(self.ydata)

        # self.curve1 = self.p1.plot(self.xdata, self.ydata, pen=pg.mkPen('r'))

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)

        self.setCentralWidget(central_widget)
        # self.setCentralWidget(self.qGraph)

        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(int(1e3 * self.interval))  # fires every 1000ms = 1s

        self.setGeometry(0, 0, 1000, 400)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.show()

    def change_integration_time(self, integration_time=100):  # argument is in ms
        try:
            intt = float(integration_time)
            self.spec.integration_time_micros(1e3 * intt)  # 0.1 seconds

        except ValueError:
            # no actual number input, just clicked inside and outside of the edit box
            pass

    def readData(self):
        self.xdata = self.spec.wavelengths()
        self.ydata = self.spec.intensities()
        self.length = self.xdata.size  # the number of data
        self.mean = sum(self.xdata * self.ydata) / self.length  # note this correction
        self.sigma = (
            sum(self.ydata * (self.xdata - self.mean) ** 2) / self.length
        )  # note this correction

    def update(self):
        self.readData()
        xmin, xmax = self.qGraph.getAxis("bottom").range
        in_range = np.logical_and(self.xdata > xmin, self.xdata < xmax)

        for arrow, text in zip(self.arrows, self.texts):
            self.qGraph.removeItem(arrow)
            self.qGraph.removeItem(text)
        if self.ydata[in_range].size > 0:
            avg = np.average(self.ydata[in_range])
        else:
            avg = 1000

        peaks, _ = find_peaks(self.ydata, prominence=min(1000, avg))
        try:
            y = self.ydata - self.dark
            yp = self.ydata[peaks] - self.dark[peaks]
        except AttributeError:
            y = self.ydata
            yp = self.ydata[peaks]

        self._measurements_data_item.setData(x=np.array(self.xdata), y=y)
        for idp, peak in enumerate(peaks):
            arrow = pg.ArrowItem(pos=(self.xdata[peak], yp[idp]), angle=-90)
            self.qGraph.addItem(arrow)
            self.arrows.append(arrow)

            text = pg.TextItem(f"{self.xdata[peak]:.1f} nm", anchor=(0.5, 2.0))
            text.setPos(self.xdata[peak], yp[idp])
            text.setParentItem(arrow)
            self.qGraph.addItem(text)
            self.texts.append(text)

    def dark_spectra(self):
        self.readData()
        self.dark = self.ydata

    def fit_gaussian(self):
        xmin, xmax = self.qGraph.getAxis("bottom").range
        in_range = np.logical_and(self.xdata > xmin, self.xdata < xmax)
        x = self.xdata[in_range]
        y = self.ydata[in_range]
        self.mean = np.average(x)  # note this correction
        self.sigma = np.sqrt(sum(y * (x - self.mean) ** 2) / x.size)
        self.disp = np.average(y)

        try:
            popts, pcov = curve_fit(
                gaus, x, y, p0=[0.5 * y.max(), self.mean, self.sigma / 2]
            )
            self._measurements_fit_item.setData(x=x, y=gaus(x, *popts))
        except OptimizeWarning:
            self._measurements_fit_item.setData(
                x=x, y=gaus(x, y.max, self.mean, self.sigma)
            )
        return


# Start Qt event loop unless running in interactive mode or using pyside.
if __name__ == "__main__":
    run()
