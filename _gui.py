from deepdiff import DeepDiff
from pprint import pprint
from PyQt5 import QtWidgets, uic, QtGui, QtCore
from PyQt5 import uic
import logging
import sys
import pyqtgraph as pg
import numpy as np
import logging
from collections import deque
from modules.utils import Settings
import copy


class GuiLogger(logging.Handler, QtCore.QObject):
    appendPlainText = QtCore.pyqtSignal(str)

    def __init__(self, edit):
        super().__init__()
        QtCore.QObject.__init__(self)
        self.edit = edit
        self.edit.setReadOnly(True)
        self.appendPlainText.connect(self.edit.appendPlainText)

    def emit(self, record):
        self.appendPlainText.emit(self.format(record))


class _GuiMainWindow(QtWidgets.QMainWindow):

    settings_signal = QtCore.pyqtSignal(object)

    def __init__(self, cmd_arg, log_level=logging.DEBUG, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi("tab_template.ui", self)

        gui_logger_handler = GuiLogger(self.textedit)
        gui_logger_handler.setLevel(log_level)
        gui_logger_handler.setFormatter(logging.root.handlers[0].formatter)
        logging.getLogger().addHandler(gui_logger_handler)

        self.cam1 = None
        self.cam2 = None
        self.mc = None

        self.init_buttons()
        self.init_settings()

        # Set up plotting page
        # # labels
        self.dist_1_history.getPlotItem().getAxis("left").setLabel("Offset 1 (mag.)")
        self.dist_2_history.getPlotItem().getAxis("left").setLabel("Offset 2 (mag.)")
        self.int_1_history.getPlotItem().getAxis("left").setLabel("Image Sum 1")
        self.int_2_history.getPlotItem().getAxis("left").setLabel("Image Sum 2")
        # # axis-linkes
        self.dist_2_history.setXLink(self.dist_1_history)
        self.int_1_history.setXLink(self.dist_1_history)
        self.int_2_history.setXLink(self.dist_1_history)

        # set histogram for pixel values 0 to 255
        self.hist_1 = self.viewer_1.getHistogramWidget()
        self.hist_2 = self.viewer_2.getHistogramWidget()
        self.hist_1.setHistogramRange(-10, 270)
        self.hist_2.setHistogramRange(-10, 270)

        self.viewer_1.cursor_changed.connect(self.update_cursor_info)
        self.viewer_2.cursor_changed.connect(self.update_cursor_info)

        self.centroid_pen = pg.mkPen(cosmetic=True, width=5,
                                     color=pg.mkColor(184, 134, 11, 100))

        self.centroid_1_lines = [pg.InfiniteLine(
            pos=None, angle=135, pen=self.centroid_pen),
            pg.InfiniteLine(pos=None, angle=45, pen=self.centroid_pen)]

        self.centroid_2_lines = [pg.InfiniteLine(
            pos=None, angle=135, pen=self.centroid_pen),
            pg.InfiniteLine(pos=None, angle=45, pen=self.centroid_pen)]

        self.target_pen = pg.mkPen(cosmetic=True, width=5,
                                   color=pg.mkColor(100, 149, 237, 100), dash=[4, 2])

        self.target_1_lines = [pg.InfiniteLine(
            pos=None, angle=0, pen=self.target_pen),
            pg.InfiniteLine(pos=None, angle=90, pen=self.target_pen)]

        self.target_2_lines = [pg.InfiniteLine(
            pos=None, angle=0, pen=self.target_pen),
            pg.InfiniteLine(pos=None, angle=90, pen=self.target_pen)]

        self.traj_color = (178, 34, 34, 150)

        self.traj_1 = pg.ScatterPlotItem()
        self.traj_2 = pg.ScatterPlotItem()
        self.traj_1.setBrush(self.traj_color)
        self.traj_2.setBrush(self.traj_color)
        self.traj_1.setSymbol('x')
        self.traj_2.setSymbol('x')
        self.traj_1.setSize(15)
        self.traj_2.setSize(15)

        self.viewer_1.getView().addItem(self.traj_1)
        self.viewer_2.getView().addItem(self.traj_2)
        self.traj_1.setVisible(False)
        self.traj_2.setVisible(False)

        [self.viewer_1.getView().addItem(l) for l in self.centroid_1_lines]
        [self.viewer_2.getView().addItem(l) for l in self.centroid_2_lines]
        [self.viewer_1.getView().addItem(l) for l in self.target_1_lines]
        [self.viewer_2.getView().addItem(l) for l in self.target_2_lines]

        self.traj_1_data = deque(maxlen=50)
        self.traj_2_data = deque(maxlen=50)

        self.center_locked_label.setText("Center Locked: 🔴")
        self.align_label.setText("Alignment: 🔴")
        self.blocked_label.setText("Blocking: False 🟢")

    @ QtCore.pyqtSlot(list)
    def update_image(self, images):
        '''Updates image viewer 1 and 2 separately. If any of them is none, put blank'''
        self.new_image(images)

        self.viewer_1.clear()
        self.viewer_1.setImage(self.image_1, autoRange=False, autoLevels=False,
                               autoHistogramRange=False)

        self.viewer_2.clear()
        self.viewer_2.setImage(self.image_2, autoRange=False, autoLevels=False,
                               autoHistogramRange=False)

    @ QtCore.pyqtSlot(list)
    def new_image(self, images):
        del (self.image_1)
        del (self.image_2)
        self.image_1, self.image_2 = images

    @ QtCore.pyqtSlot(list)
    def new_centroid(self, centroids):
        self.centroid_1, self.centroid_2 = centroids

    @ QtCore.pyqtSlot(list)
    def new_intensity(self, intensities):
        self.intensity_1, self.intensity_2 = intensities

    @ QtCore.pyqtSlot(list)
    def update_intensity(self, intensities):
        self.new_intensity(intensities)
        pass

    @ QtCore.pyqtSlot(list)
    def update_centroid(self, centroids):
        self.new_centroid(centroids)
        c1 = self.centroid_1
        c2 = self.centroid_2
        if True not in np.isnan(c1):
            [l.setPos(c1) for l in self.centroid_1_lines]
        if True not in np.isnan(c2):
            [l.setPos(c2) for l in self.centroid_2_lines]

    @ QtCore.pyqtSlot(list)
    def update_target(self, targets):
        self.new_target(targets)
        t1 = self.target1
        t2 = self.target2
        [l.setPos(t1) for l in self.target_1_lines]
        [l.setPos(t2) for l in self.target_2_lines]

    @ QtCore.pyqtSlot(list)
    def new_target(self, targets):
        self.target1, self.target2 = targets

    def _check_centroids(self, state):
        if state == QtCore.Qt.Checked:
            [l.setVisible(True) for l in self.centroid_1_lines]
            [l.setVisible(True) for l in self.centroid_2_lines]

        else:
            [l.setVisible(False) for l in self.centroid_1_lines]
            [l.setVisible(False) for l in self.centroid_2_lines]

    def _check_trajectories(self, state):
        if state == QtCore.Qt.Checked:
            self.traj_1.setVisible(True)
            self.traj_2.setVisible(True)

        else:
            self.traj_1.setVisible(False)
            self.traj_2.setVisible(False)

    def update_cursor_info(self, pos):
        x, y = pos
        """Determine cursor information from mouse event."""
        self.cursor_info_label.setText(
            f"Position: ({x},{y})"
        )

    def init_buttons(self):
        self.lock_cbox.stateChanged.connect(self._check_lock)
        self.centroids_cbox.stateChanged.connect(self._check_centroids)
        self.trajectories_cbox.stateChanged.connect(self._check_trajectories)
        self.save_btn.clicked.connect(self.push_settings)

    def init_settings(self):
        self.settings = Settings.load()
        self.new_settings = copy.deepcopy(self.settings)
        settings = self.settings

        self.cbox = ['cam_mask',
                     'cam_crop']
        self.sbox = ['cam_1', 'cam_2', 'm1x', 'm1y', 'm2x', 'm2y', 'cam_interval',
                     'lower_threshold', 'upper_threshold', 'amm_steps_1',
                     'amm_steps_2', 'gain', 'alignment_threshold', 'min_movement_threshold',
                     'intensity_threshold', 'samples']

        for c in self.cbox:
            vars(self)[c].setChecked(vars(settings)[c.upper()])
            vars(self)[c].stateChanged.connect(self.commit_settings)

        for s in self.sbox:
            vars(self)[s].setValue(vars(settings)[s.upper()])
            vars(self)[s].valueChanged.connect(self.commit_settings)

    @QtCore.pyqtSlot()
    def commit_settings(self):
        new_settings = self.new_settings

        for c in self.cbox:
            vars(new_settings)[c.upper()] = vars(self)[c].isChecked()

        for s in self.sbox:
            vars(new_settings)[s.upper()] = vars(self)[s].value()

    @QtCore.pyqtSlot(bool)
    def update_center_locked_label(self, state):
        if state == True:
            self.center_locked_label.setText("Center Locked: 🟢")
        else:
            self.center_locked_label.setText("Center Locked: 🔴")

    @QtCore.pyqtSlot(bool)
    def update_align_label(self, state):
        if state == True:
            self.align_label.setText("Alignment: 🟢")
        else:
            self.align_label.setText("Alignment: 🔴")

    @QtCore.pyqtSlot(bool)
    def update_blocked_label(self, state):
        if state == True:
            self.blocked_label.setText("Blocking: DETECTED 🔴")
        else:
            self.blocked_label.setText("Blocking: NOT 🟢")

    @QtCore.pyqtSlot()
    def push_settings(self):
        settings = self.settings
        new_settings = self.new_settings
        self.settings = new_settings
        self.new_settings = copy.deepcopy(self.settings)
        self.settings.save()

        logging.info("Settings saved:\n" +
                     DeepDiff(settings, new_settings).pretty())

        # Restart the timer
        self.image_timer.stop()
        self.cam_worker._clear_deque()
        self.settings_signal.emit(self.settings)
        self.image_timer.start(self.settings.CAM_INTERVAL)


if __name__ == "__main__":
    print("yay")
    app = QtWidgets.QApplication([])
    win = _GuiMainWindow(None)
    win.show()
    sys.exit(app.exec_())
