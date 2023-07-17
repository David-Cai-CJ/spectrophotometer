import logging as log
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui, uic
from PyQt5.QtWidgets import QFileDialog
import pyqtgraph as pg
from seabreeze.spectrometers import Spectrometer
from contextlib import contextmanager
# from qdarkstyle import load_stylesheet_pyqt5
import sys
import os
from scipy.optimize import curve_fit, OptimizeWarning
from scipy.signal import find_peaks


class LiveViewUi(QtWidgets.QMainWindow):
    save_folder_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, interval, serial_number=None,  *args, **kwargs):
        log.debug("Initializing Spectrometer Window")
        super().__init__(*args, **kwargs)
        uic.loadUi("spec_viewer.ui", self)

        
        self.statusbar.showMessage('Ready')
        
        self.settings = QtCore.QSettings(
            "Siwick Research Group", "Spectrometer Liveview", parent=self
        )

        self.interval = interval    # Nothing to do with integration time
        
        if serial_number is not None:
            self.spec = Spectrometer.from_serial_number(serial_number)
            self.serial_number = serial_number
        else:
            # _serials_in_lab = ['USB2G9152', 
            #                    'HRC2000+']
            self.spec = Spectrometer.from_first_available()
            self.serial_number = self.spec.serial_number         


        self.integration_time_edit.editingFinished.connect(
            lambda: self.change_integration_time(self.integration_time_edit.text()))
        
        self.integration_time_edit.editingFinished.emit() # Initialize to 100 ms int. time.
        

        self.viewer.getPlotItem().setLabel("left", "Counts [au]")
        self.viewer.getPlotItem().setLabel("bottom", "Wavelength [nm]")
        self.viewer.setLogMode(False, True)
        
        self._measurements_data_item = pg.PlotDataItem(
            pen=pg.mkPen("r", width=1),
        )
        self._reference_data_item = pg.PlotDataItem(
            pen=pg.mkPen("g", width=0.5),
        )


        self.viewer.addItem(self._measurements_data_item)
        self.viewer.addItem(self._reference_data_item)

        self.arrows = []
        self.texts = []

        self.select_folder_button.clicked.connect(self.save_file_dialog)
        self.select_reference_button.clicked.connect(self.reference_file_dialog)
        self.save_folder_signal.connect(lambda x:print(os.path.basename(x)))
        self.deselect_reference_button.clicked.connect(self.deselect_reference)
        self.relative_checkbox.stateChanged.connect(self.relative_state_changed)
        self.measure_button.clicked.connect(self.measure)
        self.prefix_line_edit.editingFinished.connect(
            lambda: self.update_prefix(self.prefix_line_edit.text()))

        self.update()

        self.timer = pg.QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(int(1e3 * self.interval))  # fires every 1000ms = 1s

        self.show()
    
    def reference_file_dialog(self):
        dialog = QFileDialog(self, caption='Reference File')

        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        # dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        dialog.setLabelText(QtWidgets.QFileDialog.Accept, "Select File")
        if dialog.exec_():
            files = dialog.selectedFiles()
            
            if len(files) > 1:
                pass
            
            if len(files) ==1:
                self.reference_file = files[0]
                
                self.read_reference(self.reference_file)
                self._reference_data_item.setData(self.ref_xdata, self.ref_ydata)
                self.relative_checkbox.setEnabled(True)
            
    def deselect_reference(self):
        self.relative_checkbox.setChecked(False)
        self.relative_checkbox.setEnabled(False)
        self._reference_data_item.clear()
        self._reference_data_item.setVisible(True)
    
    def relative_state_changed(self, state):
        if self.relative_checkbox.isChecked():
            self._reference_data_item.setVisible(False)
        
        else:
            self._reference_data_item.setVisible(True)


    def save_file_dialog(self):
        dialog = QFileDialog(self, caption='Data Log File Dir')

        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        # dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        dialog.setLabelText(QtWidgets.QFileDialog.Accept, "Select Folder")
        if dialog.exec_():
            folders = dialog.selectedFiles()
            self.save_folder = folders[0]
            self.save_folder_signal.emit(self.save_folder)
            self.update_save_folder()

    def update_prefix(self, prefix):
        self.prefix = prefix
        self.update_save_folder()
        
    def update_save_folder(self):
        _dis_ls = []
        
        try:
            _dis_ls.append(os.path.basename(self.save_folder))
            self.select_folder_button.setFont(QtGui.QFont('Times', weight=QtGui.QFont.Bold))
            self.select_folder_button.setText(os.path.basename(self.save_folder))
            
        except AttributeError:
            _dis_ls.append('❌')
            
        try:
            if self.prefix != '':
                _dis_ls.append(self.prefix)
            else:
                _dis_ls.append('❌')
        except AttributeError:
            _dis_ls.append('❌')

        str_display = 'Folder:{0}\tPrefix:{1}'.format(*_dis_ls)
        self.statusbar.showMessage(str_display, msecs= 10000)
        self.folder_label.setText(str_display)

    def measure(self):
        try:
            if self.prefix != '':
                _file_directory = os.path.join(self.save_folder, self.prefix)
            else:
                self.statusbar.showMessage('⛔️Set prefix to none empty value.', msecs= 5000)
                return
        except AttributeError:
            self.statusbar.showMessage('❌ Save directory was not established.', msecs= 5000)
            return
        
        # except FileNotFoundError:
        #     os.mkdir(path=directory)
        n_times = int(self.measure_number_spinbox.value())
        
        for n in np.arange(n_times):
            np.savetxt(_file_directory + f"_{n}.csv", self.spec.spectrum(), delimiter=',')
        
        _str_display = f'{n}'+ "Files saved under"+ _file_directory
        
        self.statusbar.showMessage(_str_display, msecs= 5000)
        
    def read_reference(self, path):
        x, y = np.loadtxt(path, delimiter = ',')
        self.ref_xdata = np.array(x)
        self.ref_ydata = np.array(y)

    def change_integration_time(self, integration_time=100):  # argument is in ms
        try:
            intt = float(integration_time)
            self.spec.integration_time_micros(1e3 * intt)  # 0.1 seconds

        except ValueError:
            # no actual number input, just clicked inside and outside of the edit box
            pass

    def readData(self):
        self.xdata = np.array(self.spec.wavelengths())
        self.ydata = np.array(self.spec.intensities())
        self.length = self.xdata.size  # the number of data
        self.mean = sum(self.xdata * self.ydata) / self.length  # note this correction
        self.sigma = (
            sum(self.ydata * (self.xdata - self.mean) ** 2) / self.length
        )  # note this correction
        return self.xdata, self.ydata
        

    def update(self):
        x,y = self.readData()
        
        self.max_value_label.setText(f'Max: {np.max(y):.0f}/{self.spec.max_intensity:.0f}')
        
        if self.relative_checkbox.isChecked():
            # potential division by zero here
            with np.errstate(divide='ignore',invalid='ignore'):
                self._measurements_data_item.setData(x=self.xdata, y=self.ydata/self.ref_ydata)
        
        else:
            self._measurements_data_item.setData(x=self.xdata, y=self.ydata)
