import sys
import numpy as np
import soundfile as sf
import sounddevice as sd
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QPushButton, QVBoxLayout, QWidget, QListWidget, QLabel, QHBoxLayout, QSlider, QCheckBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
import matplotlib.pyplot as plt
import io

class AudioPlayer(QMainWindow):
    def setup_vu_timer(self):
        from PyQt5.QtCore import QTimer
        self.vu_timer = QTimer()
        self.vu_timer.setInterval(50)  # update every 50ms
        self.vu_timer.timeout.connect(self.update_vu_meter)
        self.vu_data = None
        self.vu_samplerate = None
        self.vu_pos = 0
        self.vu_blocksize = 2048
        self.vu_playing = False
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cross-Platform Audio Player")
        self.setGeometry(100, 100, 800, 600)
        self.playlist = []
        self.current_index = -1
        self.audio_stream = None
        self.init_ui()

    def init_ui(self):
        self.setup_vu_timer()
        main_layout = QVBoxLayout()
        self.playlist_widget = QListWidget()
        main_layout.addWidget(self.playlist_widget)

        controls_layout = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #1aff1a; color: black; border: 2px solid #006600;")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #ffff66; color: black; border: 2px solid #999900;")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #ff3333; color: white; border: 2px solid #990000;")
        self.load_button = QPushButton("Add Files")
        self.load_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #444; color: white; border: 2px solid #222;")
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.load_button)
        self.stop_button.clicked.connect(self.stop_audio)
        main_layout.addLayout(controls_layout)

        self.silence_checkbox = QCheckBox("Remove Silence (Start/End)")
        main_layout.addWidget(self.silence_checkbox)

        self.waveform_label = QLabel()
        main_layout.addWidget(self.waveform_label)

        self.vu_label = QLabel()
        self.vu_label.setFixedHeight(40)
        vu_layout = QHBoxLayout()
        vu_layout.addWidget(self.vu_label)
        main_layout.addLayout(vu_layout)
        # Dark mode stylesheet
        dark_stylesheet = """
            QWidget { background-color: #222; color: #eee; }
            QListWidget { background-color: #222; color: #eee; }
            QLabel { color: #eee; }
            QCheckBox { color: #eee; }
            QPushButton { background-color: #444; color: #eee; border: 2px solid #222; }
        """
        self.setStyleSheet(dark_stylesheet)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.load_button.clicked.connect(self.add_files)
        self.play_button.clicked.connect(self.play_audio)
        self.pause_button.clicked.connect(self.pause_audio)
        self.playlist_widget.itemDoubleClicked.connect(self.select_track)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Audio Files", "", "Audio Files (*.wav *.flac *.mp3)")
        if files:
            self.playlist.extend(files)
            self.playlist_widget.addItems(files)

    def select_track(self, item):
        self.current_index = self.playlist_widget.row(item)
        self.play_audio()

    def play_audio(self):
        if self.current_index == -1 and self.playlist:
            self.current_index = 0
        if self.current_index < 0 or self.current_index >= len(self.playlist):
            return
        file_path = self.playlist[self.current_index]
        data, samplerate = sf.read(file_path)
        if self.silence_checkbox.isChecked():
            data = self.remove_silence(data)
        self.show_waveform(data, samplerate)
        self.vu_data = data
        self.vu_samplerate = samplerate
        self.vu_pos = 0
        self.vu_playing = True
        self.vu_timer.start()
        self.play_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #1aff1a; color: black; border: 2px solid #006600; box-shadow: 0 0 10px #1aff1a;")
        self.pause_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #ffff66; color: black; border: 2px solid #999900;")
        self.stop_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #ff3333; color: white; border: 2px solid #990000;")
        self.play_stream_realtime(data, samplerate)
        self.play_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #1aff1a; color: black; border: 2px solid #006600;")

    def play_stream_realtime(self, data, samplerate):
        import threading
        def audio_thread():
            sd.play(data, samplerate)
            sd.wait()
            self.vu_playing = False
            self.vu_timer.stop()
        t = threading.Thread(target=audio_thread)
        t.start()
    def update_vu_meter(self):
        if not self.vu_playing or self.vu_data is None:
            return
        start = self.vu_pos
        end = min(start + self.vu_blocksize, len(self.vu_data))
        block = self.vu_data[start:end]
        vu = self.calculate_vu(block)
        self.show_vu_meter(vu)
        self.vu_pos += self.vu_blocksize
        if self.vu_pos >= len(self.vu_data):
            self.vu_playing = False
            self.vu_timer.stop()

    def pause_audio(self):
        sd.stop()
        self.vu_playing = False
        self.vu_timer.stop()
        self.pause_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #ffff66; color: black; border: 2px solid #999900; box-shadow: 0 0 10px #ffff66;")
    def show_vu_meter(self, vu):
        # Horizontal digital VU meter from -60dB to 0dB
        min_db = -60
        max_db = 0
        vu = max(min_db, min(max_db, vu))
        percent = int((vu - min_db) / (max_db - min_db) * 100)
        bar_length = 60
        filled = int(bar_length * percent / 100)
        empty = bar_length - filled
        # Color gradient: red (-60dB) to yellow (-30dB) to green (0dB)
        if vu > -10:
            color = '#1aff1a'
        elif vu > -30:
            color = '#ffff66'
        else:
            color = '#ff3333'
        bar_html = '<span style="font-family: monospace; font-size: 24px; color: #888;">-60dB </span>'
        bar_html += f'<span style="font-family: monospace; font-size: 24px; color: {color};">' + '|' * filled + '-' * empty + f'</span>'
        bar_html += '<span style="font-family: monospace; font-size: 24px; color: #888;"> 0dB</span>'
        bar_html += f'<span style="font-family: monospace; font-size: 18px; color: {color};">  {vu:.1f} dB</span>'
        self.vu_label.setText(bar_html)
    def stop_audio(self):
        sd.stop()
        self.vu_playing = False
        self.vu_timer.stop()
        self.stop_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #ff3333; color: white; border: 2px solid #990000; box-shadow: 0 0 10px #ff3333;")

    def show_waveform(self, data, samplerate):
        plt.figure(figsize=(8, 2))
        time_axis = np.linspace(len(data) / samplerate, 0, num=len(data))
        plt.plot(time_axis, data)
        plt.title("Waveform (Descending Time)")
        plt.xlabel("Tempo (s) Decrescente")
        plt.ylabel("Amplitude")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        self.waveform_label.setPixmap(pixmap)
    def calculate_vu(self, data):
        rms = np.sqrt(np.mean(np.square(data)))
        if rms == 0:
            return -float('inf')
        vu = 20 * np.log10(rms)
        return vu

    def remove_silence(self, data, threshold=0.01):
        abs_data = np.abs(data)
        mask = abs_data > threshold
        if not np.any(mask):
            return data
        start = np.argmax(mask)
        end = len(mask) - np.argmax(mask[::-1])
        return data[start:end]

    def closeEvent(self, event):
        sd.stop()
        event.accept()

if __name__ == "__main__":
    from PyQt5.QtWidgets import QMessageBox
    try:
        app = QApplication(sys.argv)
        window = AudioPlayer()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("Erro ao iniciar o programa")
        error_box.setText(f"Erro: {str(e)}")
        error_box.exec_()
