import logging as log
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui, uic
from PyQt5.QtWidgets import QFileDialog
import pyqtgraph as pg
from contextlib import contextmanager
# from qdarkstyle import load_stylesheet_pyqt5
import os
import datetime
from spec import SpectrumGrabber


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
        
        self._ref_selected = False
        self._dark_selected = False

        self.spec_grabber = SpectrumGrabber()
        self.spec_grabber.spec_ready.connect(self.update)
        self.max_intensity = self.spec_grabber.spec.max_intensity

        self.spec_grabber.change_integration_time(self.integration_time_edit.text())
        
        self.spec_grabber.change_number_of_spectrum(self.measure_number_spinbox.value())


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
        self.select_dark_button.clicked.connect(self.dark_file_dialog)
        self.save_folder_signal.connect(lambda x: print(os.path.basename(x)))
        self.deselect_reference_button.clicked.connect(self.deselect_reference)
        self.deselect_dark_button.clicked.connect(self.deselect_dark)
        self.relative_checkbox.stateChanged.connect(self.relative_state_changed)
        self.measure_button.clicked.connect(self.measure)
        self.prefix_line_edit.editingFinished.connect(
            lambda: self.update_prefix(self.prefix_line_edit.text()))
        

        # Changes which could interrupt spec acquisition thread
        self.measure_number_spinbox.valueChanged.connect(self.spec_num_change)
        self.integration_time_edit.editingFinished.connect(
            lambda: self.int_time_change(self.integration_time_edit.text()))


        self.spec_grabber.thread.start()
        
        self.timer = pg.QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.spec_grabber.get_spectrum)
        self.timer.start()

        self.show()

    def spec_num_change(self, num):
        self.spec_grabber.change_number_of_spectrum(num)
    
    
    def int_time_change(self, time_string_ms):
        self.spec_grabber.thread.requestInterruption()
        self.spec_grabber.thread.wait()
        self.spec_grabber.change_integration_time(time_string_ms)
        self.spec_grabber.thread.start()
        
        
    def dark_file_dialog(self):
        dialog = QFileDialog(self, caption='Dark Spectra File')
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        # dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        dialog.setLabelText(QtWidgets.QFileDialog.Accept, "Select File")

        tree_view = dialog.findChild(QtWidgets.QTreeView)
        tree_view.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        if dialog.exec_():
            files = dialog.selectedFiles()

            self.dark_xdata, self.dark_ydata = self.read_files(files)
            self.subtract_dark_checkbox.setEnabled(True)
            self.select_dark_button.setText(f'Averaged from\n{len(files)} files')
            self.select_dark_button.setFont(QtGui.QFont('Segoe UI', weight=QtGui.QFont.Bold))
            self._dark_selected = True

    def deselect_dark(self):
        self.subtract_dark_checkbox.setChecked(False)
        self.subtract_dark_checkbox.setEnabled(False)
        self.select_dark_button.setText(f'Open File(s)')
        self.select_dark_button.setFont(QtGui.QFont('Segoe UI', weight=QtGui.QFont.Normal))
        self._dark_selected = False


    def reference_file_dialog(self):
        dialog = QFileDialog(self, caption='Reference File')
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QtWidgets.QFileDialog.AnyFile)
        # dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        dialog.setLabelText(QtWidgets.QFileDialog.Accept, "Select File")

        tree_view = dialog.findChild(QtWidgets.QTreeView)
        tree_view.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        if dialog.exec_():
            files = dialog.selectedFiles()

            self.ref_xdata, self.ref_ydata = self.read_files(files)
            self._reference_data_item.setData(self.ref_xdata, self.ref_ydata)
            self.relative_checkbox.setEnabled(True)
            self.select_reference_button.setText(f'Averaged from\n{len(files)} files')
            self.select_reference_button.setFont(QtGui.QFont('Segoe UI', weight=QtGui.QFont.Bold))
            self._ref_selected= True

    def deselect_reference(self):
        self.relative_checkbox.setChecked(False)
        self.relative_checkbox.setEnabled(False)
        self._reference_data_item.clear()
        self._reference_data_item.setVisible(True)

        self.select_reference_button.setText(f'Open File(s)')
        self.select_reference_button.setFont(QtGui.QFont('Segoe UI', weight=QtGui.QFont.Normal))
        self._ref_selected= False

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

        str_display = 'Folder:  {0}\nPrefix:  {1}'.format(*_dis_ls)
        self.statusbar.showMessage(str_display, msecs=10000)
        self.folder_label.setText(str_display)

    def measure(self):
        try:
            if self.prefix != '':
                _file_directory = os.path.join(self.save_folder, self.prefix)
            else:
                self.statusbar.showMessage('⛔️Set prefix to none empty value.', msecs=5000)
                return

        except AttributeError:
            self.statusbar.showMessage('❌ Save directory was not established.', msecs=5000)
            return

        if not os.path.exists(self.save_folder):
            os.makedirs(self.save_folder)

        import glob
        data_files = glob.glob(self.save_folder + os.path.sep + self.prefix +"_*.csv")
        
        try:
            latest_idx = int(sorted([os.path.basename(f).split("_")[-1].split(".csv")[0] for f in data_files])[-1])
            fname = self.prefix + f"_{latest_idx + 1:04d}.csv"
        
        except IndexError:
            fname =  self.prefix + f"_{0:04d}.csv"
            
        np.savetxt(os.path.join(self.save_folder, fname), np.array([self.xdata,self.ydata]).T,
                    fmt='%-.18E , %-.18E', newline='\n',
                    header='# x (wavelengths), y (counts)',
                    comments='\n'.join([f'# Integration time per Spectra = {self.integration_time_edit.text()} ms',
                                        f'# Number of integrations = {self.measure_number_spinbox.value()}',
                                        f'# Spectrometer: {self.spec_grabber.spec.model}',
                                        '# Time: ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),
                                        '\n']))

        _str_display = f'👌 ' + " Files saved under" + self.save_folder + '/' + self.prefix + fname

        self.statusbar.showMessage(_str_display, msecs=10000)

    def read_files(self, paths):
        """
        Select one or more files to get an average reference. 
        Returns true if such reference spectra can be generated successfully."""
        _y_data = []

        for f in paths:
            x, y = np.loadtxt(f, delimiter=',').T

            try:
                if np.any(x != _x_data):
                    self.statusbar.showMessage(
                        '❌ Selected data files contain different wavelength selections.', msecs=5000)
                    return False

            except UnboundLocalError:
                _x_data = x

            _y_data.append(y)

        _y_data = np.mean(_y_data, axis=0)
        return _x_data, _y_data

    def readData(self):
        self.xdata = np.array(self.spec.wavelengths())
        self.ydata = np.array(self.spec.intensities())
        self.length = self.xdata.size  # the number of data
        self.mean = sum(self.xdata * self.ydata) / self.length  # note this correction
        self.sigma = (
            sum(self.ydata * (self.xdata - self.mean) ** 2) / self.length
        )  # note this correction
        return self.xdata, self.ydata

    def update(self, spec_data):
        self.xdata, self.ydata = spec_data
        x = self.xdata[:]
        y = self.ydata[:]
        
        if self._dark_selected:
            darky = self.dark_ydata
        
        if self._ref_selected:
            refy = self.ref_ydata 
        
        self.max_value_label.setText(f'Max: {np.max(y):.0f}/{self.max_intensity:.0f}')
        
        if self.subtract_dark_checkbox.isChecked():
            y = y - darky
            if self._ref_selected:
                refy = refy - darky
            
        if self.relative_checkbox.isChecked():
            # potential division by zero here
            with np.errstate(divide='ignore', invalid='ignore'):
                self._measurements_data_item.setData(x=x, y= 1 - y/refy)

        else:
            self._measurements_data_item.setData(x=x, y=y)
            if self._ref_selected:
                self._reference_data_item.setData(x, refy)

        self.timer.start()