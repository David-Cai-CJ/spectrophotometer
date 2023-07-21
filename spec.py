
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, QThread
from PyQt5.QtWidgets import QAction, QMenu
import numpy as np
from seabreeze.spectrometers import Spectrometer



class SpectrumGrabber(QObject):
    """
    class capable of setting the collecting images from the detector in a non-blocking fashion
    """

    spec_ready = pyqtSignal(list)

    def __init__(self, serial_number=None):
        super().__init__()

        if serial_number is not None:
            self.spec = Spectrometer.from_serial_number(serial_number)
            self.serial_number = serial_number
        else:
            self.spec = Spectrometer.from_first_available()
            self.serial_number = self.spec.serial_number
            
        self.wavelengths = self.spec.wavelengths()
        self.len = len(self.wavelengths)

        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self.get_spectrum)

        
    def change_integration_time(self, time_ms):
        try:
            intt = int(float(time_ms) * 1000)
            
            lower, upper  = self.spec.integration_time_micros_limits

            if intt < upper and intt > lower:
                self.spec.integration_time_micros(intt)
                self.clear_spectrum()
                return 0 
            
            else:
                print("Integration time not within limits.")
                return 1 

        except ValueError:
            # no actual number input, just clicked inside and outside of the edit box
            print("Integration time input wasn't recognized.")

    
    def clear_spectrum(self):
        self.accumulated_spectrum = np.zeros(self.len)
        self.current_spectrum = np.zeros(self.len)
    
    def change_number_of_spectrum(self, num):
        self.number_spectrum = num
        self.clear_spectrum()
        
    def get_spectrum(self):
        _spec_read = np.zeros(self.len)
        for _ in range(self.number_spectrum):
            if self.thread.isInterruptionRequested():
                self.thread.quit()
                return
            self.current_spectrum = self.spec.intensities()
            _spec_read += self.current_spectrum

        self.accumulated_spectrum = _spec_read
        self.spec_ready.emit([self.wavelengths, _spec_read])