# -*- coding: utf-8 -*-
"""
UDP Real-Time Signal and Spectrogram Viewer (Hydrophone Client)
Adapted to use QUARPCore via client package.
"""
import sys
import socket
import threading
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets
from collections import deque
from scipy import signal
import wave
import datetime
import argparse
import traceback

from client.core import QUARPCore

# --- Global Configuration ---
UDP_IP = "0.0.0.0"
UDP_PORT = 65431
DEFAULT_TCP_PORT = 65432
SAMPLE_RATE = 300000
UPDATE_RATE_MS = 20

# --- Time-Domain Plot Configuration ---
WINDOW_SECONDS = 0.5
BUFFER_SIZE = int(WINDOW_SECONDS * SAMPLE_RATE)
TRIGGER_H_POS = 0.2
MAX_TRIGGER_SEARCH_SAMPLES = BUFFER_SIZE * 2

# --- Spectrogram Configuration ---
SPEC_NPERSEG = 750
SPEC_NOVERLAP = 600
SPEC_WIDTH = 1000
MAX_SPEC_AUDIO_SAMPLES = SPEC_NPERSEG * 20

# Constants
MAX_INT16 = 32768.0

class Communicate(QtCore.QObject):
    """Signals to communicate safely from QUARPCore threads to the main GUI thread."""
    error_signal = QtCore.pyqtSignal(str)
    connected_signal = QtCore.pyqtSignal(str, int)
    disconnected_signal = QtCore.pyqtSignal()


class UDPPlotter(QtWidgets.QMainWindow):
    def __init__(self, server_ip="127.0.0.1", tcp_port=DEFAULT_TCP_PORT):
        super().__init__()
        self.default_ip = server_ip
        self.default_port = tcp_port
        
        self.running = True
        self.is_running_plots = True
        self.packet_queue = deque()
        self.trigger_is_armed = True
        self.is_recording = False
        self.wave_file = None
        
        # QUARPCore instance
        self.core = None
        
        # Setup cross-thread signal routing
        self.comm = Communicate()
        self.comm.error_signal.connect(self._show_error_dialog)
        self.comm.connected_signal.connect(self._on_core_connected)
        self.comm.disconnected_signal.connect(self._on_core_disconnected)

        self._setup_ui()
        self._connect_controls()
        self._initialize_buffers()

    def _setup_ui(self):
        self.setWindowTitle("Hydrophone Real-Time Viewer (QUARP Client)")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        controls_layout = QtWidgets.QHBoxLayout()
        self.run_stop_button = QtWidgets.QPushButton("Stop")

        self.record_button = QtWidgets.QPushButton("Start Recording")
        self.record_button.setStyleSheet("background-color: #2ecc71; color: white;")

        controls_layout.addWidget(self.run_stop_button)
        controls_layout.addWidget(self.record_button)
        controls_layout.addSpacing(20)

        tcp_label = QtWidgets.QLabel("TCP Control IP:")
        self.ip_address_input = QtWidgets.QLineEdit(self.default_ip)
        self.ip_address_input.setPlaceholderText("Enter TCP IP Address")
        self.connect_button = QtWidgets.QPushButton("Connect")
        self.disconnect_button = QtWidgets.QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False) # initially disabled
        
        controls_layout.addWidget(tcp_label)
        controls_layout.addWidget(self.ip_address_input)
        controls_layout.addWidget(self.connect_button)
        controls_layout.addWidget(self.disconnect_button)
        controls_layout.addSpacing(20)

        self.trigger_checkbox = QtWidgets.QCheckBox("Enable Trigger")
        self.trigger_level_spinbox = QtWidgets.QDoubleSpinBox()
        self.trigger_level_spinbox.setRange(-1.0, 1.0)
        self.trigger_level_spinbox.setSingleStep(0.05)
        self.trigger_level_spinbox.setValue(0.1)
        self.trigger_slope_combo = QtWidgets.QComboBox()
        self.trigger_slope_combo.addItems(["Rising", "Falling"])

        controls_layout.addWidget(self.trigger_checkbox)
        controls_layout.addWidget(QtWidgets.QLabel("Level:"))
        controls_layout.addWidget(self.trigger_level_spinbox)
        controls_layout.addWidget(QtWidgets.QLabel("Slope:"))
        controls_layout.addWidget(self.trigger_slope_combo)
        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setYRange(-1.0, 1.0)
        self.plot_widget.setXRange(0, WINDOW_SECONDS)
        self.plot_widget.setLabel('left', 'Normalized Amplitude')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.time_axis = np.linspace(0, WINDOW_SECONDS, num=BUFFER_SIZE)
        self.curve = self.plot_widget.plot(pen='y')
        main_layout.addWidget(self.plot_widget)

        spec_layout_widget = pg.GraphicsLayoutWidget()
        main_layout.addWidget(spec_layout_widget)
        self.spec_plot_item = spec_layout_widget.addPlot(row=0, col=0)
        self.spec_plot_item.setMenuEnabled(True)
        self.spec_plot_item.invertY(False)
        self.histogram = pg.HistogramLUTItem()
        spec_layout_widget.addItem(self.histogram, row=0, col=1)
        self.spec_img_item = pg.ImageItem()
        self.spec_plot_item.addItem(self.spec_img_item)
        self.histogram.setImageItem(self.spec_img_item)
        self.spec_plot_item.getAxis('left').setLabel('Frequency', units='Hz')
        self.spec_plot_item.getAxis('bottom').setLabel('Time', units='s')
        self.histogram.gradient.loadPreset('viridis')
        self.histogram.setHistogramRange(-70, 0)

        self.spec_plot_item.setXLink(self.plot_widget)

    def _initialize_buffers(self):
        self.plot_buffer = np.zeros(BUFFER_SIZE, dtype=np.float32)
        self.trigger_search_buffer = np.array([], dtype=np.float32)
        self.spectrogram_audio_buffer = np.array([], dtype=np.float32)
        freq_bins = SPEC_NPERSEG // 2 + 1
        self.spec_data = np.zeros((freq_bins, SPEC_WIDTH), dtype=np.float32)
        freq_res = SAMPLE_RATE / SPEC_NPERSEG
        time_res = (SPEC_NPERSEG - SPEC_NOVERLAP) / SAMPLE_RATE
        self.spec_img_item.setImage(self.spec_data.T)
        self.spec_img_item.setRect(0, 0, SPEC_WIDTH * time_res, (freq_bins-1) * freq_res)

    def _connect_controls(self):
        self.run_stop_button.clicked.connect(self._on_run_stop_clicked)
        self.trigger_checkbox.toggled.connect(self._rearm_trigger)
        self.trigger_level_spinbox.valueChanged.connect(self._rearm_trigger)
        self.trigger_slope_combo.currentIndexChanged.connect(self._rearm_trigger)
        self.record_button.clicked.connect(self._on_record_clicked)
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)

    # --- QUARPCore Handlers ---

    def _on_connect_clicked(self):
        """Handles the 'Connetti' button click."""
        ip_address = self.ip_address_input.text()
        print(f"[*] 'Connect' button pressed for {ip_address}:{self.default_port}.")
        
        # Initialize Core if needed or update IP/Port
        if not self.core:
            self.core = QUARPCore(ip_address, self.default_port)
            # Link core callbacks to pyqt signals
            self.core.on_error = self.comm.error_signal.emit
            self.core.on_connected = self.comm.connected_signal.emit
            self.core.on_disconnected = self.comm.disconnected_signal.emit
        else:
            self.core.server_ip = ip_address
            self.core.server_port = self.default_port
            
        self.connect_button.setEnabled(False)
        # Attempt connection
        threading.Thread(target=self._connect_task, daemon=True).start()

    def _connect_task(self):
        """Perform the blocking connect in a background thread to keep GUI responsive."""
        success = self.core.connect()
        if not success:
            # Re-enable the connect button if it failed immediately
            QtCore.QMetaObject.invokeMethod(self.connect_button, "setEnabled", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(bool, True))

    def _on_core_connected(self, ip, port):
        """Callback from signal when QUARPCore connects successfully."""
        print(f"[*] Connected to {ip}:{port}")
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        # Send start command via Core
        self.core.set_internal_mode(2)

    def _on_disconnect_clicked(self):
        """Handles the 'Disconnect' button click."""
        print("[*] 'Disconnect' button pressed.")
        if self.core and self.core.running:
            # Send stop command via Core
            self.core.set_internal_mode(0)
            self.core.disconnect()
        else:
            self._on_core_disconnected()
            
    def _on_core_disconnected(self):
        """Callback from signal when QUARPCore disconnects."""
        print("[*] Disconnected.")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)

    def _show_error_dialog(self, error_msg):
        """Shows error dialog on the main thread."""
        if self.running:
            error_dialog = QtWidgets.QMessageBox(self)
            error_dialog.setIcon(QtWidgets.QMessageBox.Critical)
            error_dialog.setText(f"Errore di rete/comunicazione:\n\n{error_msg}")
            error_dialog.setWindowTitle("Errore Modem")
            error_dialog.exec_()
            self.connect_button.setEnabled(True)

    # --- Recording and Local Display Logic ---

    def _on_record_clicked(self):
        if not self.is_recording:
            self.is_recording = True
            self.record_button.setText("Stop Recording")
            self.record_button.setStyleSheet("background-color: #e74c3c; color: white;")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.wav"
            self.wave_file = wave.open(filename, 'wb')
            self.wave_file.setnchannels(1)
            self.wave_file.setsampwidth(2)
            self.wave_file.setframerate(SAMPLE_RATE)
            print(f"[*] Starting recording to file: {filename}")
        else:
            self.is_recording = False
            self.record_button.setText("Start Recording")
            self.record_button.setStyleSheet("background-color: #2ecc71; color: white;")
            if self.wave_file:
                self.wave_file.close()
                self.wave_file = None
            print("[*] Recording stopped.")

    def _rearm_trigger(self):
        if self.trigger_checkbox.isChecked():
            print("Trigger Armed.")

    def _on_run_stop_clicked(self):
        self.is_running_plots = not self.is_running_plots
        self.run_stop_button.setText("Stop" if self.is_running_plots else "Run")
        if self.is_running_plots:
            self._rearm_trigger()

    def start(self):
        self.udp_thread = threading.Thread(target=self._udp_listener, daemon=True)
        self.udp_thread.start()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(UPDATE_RATE_MS)
        self.timer.timeout.connect(self._update_plots)
        self.timer.start()

    def _udp_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
            sock.bind((UDP_IP, UDP_PORT))
            print(f"[*] Listening on udp://{UDP_IP}:{UDP_PORT}")
            while self.running:
                try:
                    data, _ = sock.recvfrom(65535)
                    self.packet_queue.append(np.frombuffer(data, dtype=np.int16))
                except socket.error as e:
                    print(f"Socket error: {e}")

    def _update_plots(self):
        if not self.is_running_plots and not self.is_recording:
            return

        new_samples_list = []
        while self.packet_queue:
            new_samples_list.append(self.packet_queue.popleft())
        if not new_samples_list:
            return

        all_new_samples = np.concatenate(new_samples_list)

        if self.is_recording and self.wave_file:
            self.wave_file.writeframes(all_new_samples.tobytes())

        if not self.is_running_plots:
            return

        processed_samples = (all_new_samples.astype(np.float32) - np.mean(all_new_samples)) / MAX_INT16

        self.trigger_search_buffer = np.append(self.trigger_search_buffer, processed_samples)
        self.spectrogram_audio_buffer = np.append(self.spectrogram_audio_buffer, processed_samples)

        self._update_oscilloscope_plot(processed_samples)
        self._update_spectrogram()
        self._manage_buffers()

    def _update_oscilloscope_plot(self, new_data):
        drew_this_frame = False
        if self.trigger_checkbox.isChecked():
            if self.trigger_is_armed and self._find_and_draw_trigger():
                self.trigger_is_armed = False
                drew_this_frame = True
            elif self.trigger_is_armed:
                self._update_freerun_plot(new_data)
                drew_this_frame = True
        else:
            self._update_freerun_plot(new_data)
            drew_this_frame = True

        if drew_this_frame:
            self.curve.setData(x=self.time_axis, y=self.plot_buffer)

    def _update_freerun_plot(self, new_data):
        num_new = len(new_data)
        if num_new >= BUFFER_SIZE:
            self.plot_buffer[:] = new_data[-BUFFER_SIZE:]
        else:
            self.plot_buffer = np.roll(self.plot_buffer, -num_new)
            self.plot_buffer[-num_new:] = new_data

    def _find_and_draw_trigger(self):
        level = self.trigger_level_spinbox.value()
        slope_is_rising = self.trigger_slope_combo.currentText() == "Rising"
        start_cut = int(BUFFER_SIZE * TRIGGER_H_POS)
        end_cut = BUFFER_SIZE - start_cut

        if slope_is_rising:
            candidates = np.where((self.trigger_search_buffer[:-1] < level) & (self.trigger_search_buffer[1:] >= level))[0]
        else:
            candidates = np.where((self.trigger_search_buffer[:-1] > level) & (self.trigger_search_buffer[1:] <= level))[0]

        if len(candidates) > 0:
            trigger_index = candidates[0]
            if trigger_index >= start_cut and (len(self.trigger_search_buffer) - trigger_index) >= end_cut:
                print(f"Trigger caught at index {trigger_index}!")
                self.plot_buffer = self.trigger_search_buffer[trigger_index - start_cut : trigger_index + end_cut]
                self.trigger_search_buffer = self.trigger_search_buffer[trigger_index + 1:]
                return True
        return False

    def _manage_buffers(self):
        if len(self.trigger_search_buffer) > MAX_TRIGGER_SEARCH_SAMPLES:
            self.trigger_search_buffer = self.trigger_search_buffer[-MAX_TRIGGER_SEARCH_SAMPLES:]

        if len(self.spectrogram_audio_buffer) >= SPEC_NPERSEG:
            self.spectrogram_audio_buffer = self.spectrogram_audio_buffer[-SPEC_NOVERLAP:]

        if len(self.spectrogram_audio_buffer) > MAX_SPEC_AUDIO_SAMPLES:
             self.spectrogram_audio_buffer = self.spectrogram_audio_buffer[-MAX_SPEC_AUDIO_SAMPLES:]

    def _update_spectrogram(self):
        if self.trigger_checkbox.isChecked() and not self.trigger_is_armed:
            return

        if len(self.spectrogram_audio_buffer) >= SPEC_NPERSEG:
            f, t, Sxx = signal.spectrogram(self.spectrogram_audio_buffer, fs=SAMPLE_RATE,
                                           nperseg=SPEC_NPERSEG, noverlap=SPEC_NOVERLAP)

            if Sxx.size > 0:
                Sxx_db = 10 * np.log10(Sxx + 1e-12)
                num_new_cols = Sxx_db.shape[1]

                if num_new_cols > 0:
                    self.spec_data = np.roll(self.spec_data, -num_new_cols, axis=1)
                    num_cols_to_add = min(num_new_cols, SPEC_WIDTH)
                    self.spec_data[:, -num_cols_to_add:] = Sxx_db[:, -num_cols_to_add:]
                    self.spec_img_item.setImage(self.spec_data.T, autoLevels=True)

    def closeEvent(self, event):
        """Esegue azioni personalizzate prima di chiudere l'applicazione."""
        print("Closing the application...")
        self.running = False
        
        if self.core and self.core.running:
            print("[*] Sending disconnect command on exit...")
            self.core.set_internal_mode(0)
            self.core.disconnect()
        
        self.timer.stop()

        if self.is_recording and self.wave_file:
            print("Closing the recording file...")
            self.wave_file.close()

        event.accept()

def parse_args():
    parser = argparse.ArgumentParser(description="QUARP Hydrophone Client (Real-Time Viewer)")
    parser.add_argument("-s", "--server-ip", default="127.0.0.1", help="Server IP")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_TCP_PORT, help="TCP Port")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    app = QtWidgets.QApplication(sys.argv)
    viewer = UDPPlotter(server_ip=args.server_ip, tcp_port=args.port)
    viewer.show()
    viewer.start()
    sys.exit(app.exec())
