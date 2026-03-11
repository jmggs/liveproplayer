import sys
import os
import xml.etree.ElementTree as ET
import time
import json
import hashlib
import socket
import threading
import numpy as np
import soundfile as sf
import sounddevice as sd
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QPushButton, QVBoxLayout, QWidget, QLabel, QHBoxLayout, QCheckBox, QSizePolicy, QAction, QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QInputDialog
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QKeySequence


class ClickableWaveformLabel(QLabel):
    clicked = pyqtSignal(int, int)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(event.pos().x(), event.pos().y())
        super().mousePressEvent(event)


class PlaylistTable(QTableWidget):
    rows_reordered = pyqtSignal()

    def renumber_order_column(self):
        for row in range(self.rowCount()):
            order_item = self.item(row, 0)
            if order_item is None:
                order_item = QTableWidgetItem()
                self.setItem(row, 0, order_item)
            order_item.setText(str(row + 1))
            order_item.setTextAlignment(Qt.AlignCenter)

    def dropEvent(self, event):
        super().dropEvent(event)
        if event.isAccepted():
            self.renumber_order_column()
            self.rows_reordered.emit()


class RemoteControlRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        command = self.path.split('?', 1)[0].strip('/').lower()
        allowed = {'play', 'pause', 'stop', 'next', 'previous'}

        if command in allowed:
            self.server.player.remote_command_requested.emit(command)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'command': command}).encode('utf-8'))
            return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps({'ok': False, 'error': 'unknown endpoint'}).encode('utf-8'))

    def log_message(self, format, *args):
        # Silence default HTTP logs to keep console output clean.
        return


class RemoteControlHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class AudioPlayer(QMainWindow):
    remote_command_requested = pyqtSignal(str)

    def sidecar_key(self, file_path):
        raw = file_path.encode('utf-8', errors='ignore')
        return hashlib.sha1(raw).hexdigest()

    def sidecar_paths(self, file_path):
        key = self.sidecar_key(file_path)
        meta_path = os.path.join(self.sidecar_dir, f"{key}.json")
        png_path = os.path.join(self.sidecar_dir, f"{key}.png")
        return meta_path, png_path

    def try_load_sidecar_cache(self, file_path):
        if file_path == "demo_audio":
            return False
        if not os.path.exists(file_path):
            return False

        meta_path, png_path = self.sidecar_paths(file_path)
        if not os.path.exists(meta_path) or not os.path.exists(png_path):
            return False

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            file_size = os.path.getsize(file_path)
            file_mtime = os.path.getmtime(file_path)

            if meta.get('size') != file_size:
                return False
            if abs(float(meta.get('mtime', 0.0)) - float(file_mtime)) > 1e-6:
                return False

            pixmap = QPixmap(png_path)
            if pixmap.isNull():
                return False

            samplerate = int(meta.get('samplerate', 0))
            duration_samples = int(meta.get('duration_samples', 0))
            if samplerate <= 0 or duration_samples <= 0:
                return False

            if not hasattr(self, 'audio_cache'):
                self.audio_cache = {}
            self.audio_cache[file_path] = {
                'data': None,
                'samplerate': samplerate,
                'duration_samples': duration_samples,
                'waveform_pixmap': pixmap,
            }
            self.set_cached_duration(file_path, duration_samples / samplerate)
            return True
        except Exception:
            return False

    def save_sidecar_cache(self, file_path, samplerate, duration_samples, pixmap):
        if file_path == "demo_audio":
            return
        if not os.path.exists(file_path):
            return
        if pixmap is None or pixmap.isNull():
            return

        meta_path, png_path = self.sidecar_paths(file_path)
        try:
            os.makedirs(self.sidecar_dir, exist_ok=True)
            pixmap.save(png_path, "PNG")
            meta = {
                'path': file_path,
                'size': os.path.getsize(file_path),
                'mtime': os.path.getmtime(file_path),
                'samplerate': int(samplerate),
                'duration_samples': int(duration_samples),
            }
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f)
        except Exception:
            pass

    def set_cached_duration(self, file_path, seconds):
        if seconds is None:
            return
        if seconds < 0:
            seconds = 0
        self.duration_cache[file_path] = float(seconds)

    def update_preview_for_row(self, row, set_active_track=False):
        if row < 0 or row >= len(self.playlist):
            return

        file_path = self.playlist[row]
        if set_active_track:
            self.current_index = row
            self.current_file_path = file_path

        if not hasattr(self, 'audio_cache') or file_path not in self.audio_cache:
            self.cache_audio_info(file_path, row)

        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            cached = self.audio_cache[file_path]
            self.vu_data = cached['data']
            self.vu_samplerate = cached['samplerate']
            self.total_duration = cached['duration_samples']
            self.vu_pos = 0
            self.waveform_label.setPixmap(cached['waveform_pixmap'])
            self.update_time_display(self.total_duration, self.total_duration, self.vu_samplerate)
            if self.vu_data is not None and len(self.vu_data) > 0:
                vu_left, vu_right = self.calculate_vu_stereo(self.vu_data[:self.vu_blocksize])
            else:
                vu_left, vu_right = -60, -60
            self.show_vu_meter_stereo(vu_left, vu_right)
            self.update_playlist_total_display()

    def on_playlist_selection_changed(self):
        self.apply_playing_row_highlight()

        if self.vu_playing:
            return

        row = self.playlist_widget.currentRow()
        self.update_preview_for_row(row, set_active_track=False)

    def set_busy(self, busy):
        if busy:
            if self.busy_count == 0:
                QApplication.setOverrideCursor(Qt.WaitCursor)
            self.busy_count += 1
        else:
            if self.busy_count > 0:
                self.busy_count -= 1
            if self.busy_count == 0 and QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        QApplication.processEvents()

    def update_window_title(self):
        base_title = "Live Pro Player"
        if self.current_file_path and self.current_index >= 0:
            track_name = self.get_playlist_display_name(self.current_file_path)
            self.setWindowTitle(f"{base_title} - {track_name}")
        else:
            self.setWindowTitle(base_title)

    def countdown_color(self, seconds_left):
        if seconds_left <= 10:
            return '#ff3b30'
        if seconds_left <= 30:
            return '#ffd400'
        return '#1aff1a'

    def apply_track_time_color(self, seconds_left):
        color = self.countdown_color(seconds_left)
        self.time_label.setStyleSheet(
            f"font-size: 48px; color: {color}; font-weight: bold; background-color: transparent;"
        )

    def apply_playlist_time_color(self, seconds_left):
        color = self.countdown_color(seconds_left)
        self.playlist_total_time_label.setStyleSheet(
            f"font-size: 24px; color: {color}; font-weight: bold; background-color: transparent;"
        )

    def get_track_duration_seconds(self, file_path):
        if file_path in self.duration_cache:
            return self.duration_cache[file_path]

        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            cached = self.audio_cache[file_path]
            seconds = cached['duration_samples'] / cached['samplerate']
            self.set_cached_duration(file_path, seconds)
            return seconds

        if file_path == "demo_audio":
            if hasattr(self, 'demo_data') and hasattr(self, 'demo_samplerate'):
                seconds = len(self.demo_data) / self.demo_samplerate
                self.set_cached_duration(file_path, seconds)
                return seconds
            self.set_cached_duration(file_path, 3.0)
            return 3.0

        try:
            seconds = float(sf.info(file_path).duration)
            self.set_cached_duration(file_path, seconds)
            return seconds
        except Exception:
            return 0.0

    def update_playlist_total_display(self):
        if not hasattr(self, 'playlist_total_time_label'):
            return

        if not self.playlist:
            self.playlist_total_time_label.setText("-00:00:00")
            self.apply_playlist_time_color(0)
            return

        total_seconds = 0.0
        active_context = self.vu_playing or self.playback_end_mode == 'paused'
        start_index = self.current_index if (active_context and self.current_index >= 0) else 0

        for idx in range(start_index, len(self.playlist)):
            file_path = self.playlist[idx]
            if (
                active_context
                and
                idx == self.current_index
                and self.current_file_path == file_path
                and self.vu_samplerate is not None
                and self.total_duration > 0
            ):
                remaining_seconds = max(0.0, (self.total_duration - self.vu_pos) / self.vu_samplerate)
                total_seconds += remaining_seconds
            else:
                total_seconds += self.get_track_duration_seconds(file_path)

        self.playlist_total_time_label.setText(f"-{self.format_duration_label(total_seconds)}")
        self.apply_playlist_time_color(total_seconds)

    def setup_shortcuts(self):
        self.shortcut_toggle_play_pause = QAction(self)
        self.shortcut_toggle_play_pause.setShortcut(QKeySequence(Qt.Key_Space))
        self.shortcut_toggle_play_pause.triggered.connect(self.toggle_play_pause)
        self.addAction(self.shortcut_toggle_play_pause)

        self.shortcut_play_selected_return = QAction(self)
        self.shortcut_play_selected_return.setShortcut(QKeySequence(Qt.Key_Return))
        self.shortcut_play_selected_return.triggered.connect(self.play_selected_track)
        self.addAction(self.shortcut_play_selected_return)

        self.shortcut_play_selected_enter = QAction(self)
        self.shortcut_play_selected_enter.setShortcut(QKeySequence(Qt.Key_Enter))
        self.shortcut_play_selected_enter.triggered.connect(self.play_selected_track)
        self.addAction(self.shortcut_play_selected_enter)

    def toggle_play_pause(self):
        if self.vu_playing:
            self.pause_audio()
        else:
            self.play_selected_track()

    def play_selected_track(self):
        row = self.playlist_widget.currentRow()
        if row < 0 and self.playlist:
            row = 0
            self.playlist_widget.selectRow(row)
        if row >= 0:
            self.select_track(row, 0)

    def apply_playing_row_highlight(self):
        if not hasattr(self, 'playlist_widget'):
            return

        playing_row = self.current_index if self.vu_playing else -1
        normal_bg = QColor('#222222')
        playing_bg = QColor('#0f5f1f')

        for row in range(self.playlist_widget.rowCount()):
            row_bg = playing_bg if row == playing_row else normal_bg
            for col in range(self.playlist_widget.columnCount()):
                item = self.playlist_widget.item(row, col)
                if item is not None:
                    item.setBackground(row_bg)
                    item.setForeground(QColor('#eeeeee'))

    def ensure_demo_audio_data(self):
        if hasattr(self, 'demo_data') and hasattr(self, 'demo_samplerate'):
            return
        samplerate = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(samplerate * duration), False)
        freq = np.linspace(220, 880, len(t))
        data = np.sin(2 * np.pi * freq * t)
        self.demo_data = np.column_stack([data, data])
        self.demo_samplerate = samplerate

    def get_track_duration_label(self, file_path):
        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            cached = self.audio_cache[file_path]
            return self.format_duration_label(cached['duration_samples'] / cached['samplerate'])

        if file_path == "demo_audio":
            if hasattr(self, 'demo_data') and hasattr(self, 'demo_samplerate'):
                return self.format_duration_label(len(self.demo_data) / self.demo_samplerate)
            return self.format_duration_label(3)

        try:
            info = sf.info(file_path)
            return self.format_duration_label(info.duration)
        except Exception:
            return "--:--:--"

    def get_playlist_display_name(self, file_path):
        if file_path == "demo_audio":
            return "Demo Audio"
        return os.path.basename(file_path)

    def refresh_playlist_widget(self, select_index=None):
        self.playlist_widget.blockSignals(True)
        self.playlist_widget.setRowCount(len(self.playlist))
        for idx, file_path in enumerate(self.playlist, start=1):
            order_item = QTableWidgetItem(str(idx))
            name_item = QTableWidgetItem(self.get_playlist_display_name(file_path))
            name_item.setData(Qt.UserRole, file_path)
            duration_item = QTableWidgetItem(self.get_track_duration_label(file_path))

            order_item.setTextAlignment(Qt.AlignCenter)
            duration_item.setTextAlignment(Qt.AlignCenter)

            order_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            row_item_flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
            name_item.setFlags(row_item_flags)
            duration_item.setFlags(row_item_flags)

            self.playlist_widget.setItem(idx - 1, 0, order_item)
            self.playlist_widget.setItem(idx - 1, 1, name_item)
            self.playlist_widget.setItem(idx - 1, 2, duration_item)
        self.playlist_widget.blockSignals(False)
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()

        if select_index is not None and 0 <= select_index < len(self.playlist):
            self.playlist_widget.selectRow(select_index)

    def update_playlist_labels(self):
        self.refresh_playlist_widget(select_index=self.playlist_widget.currentRow())

    def on_playlist_rows_moved(self, source_parent, source_start, source_end, destination_parent, destination_row):
        moved_block = self.playlist[source_start:source_end + 1]
        del self.playlist[source_start:source_end + 1]

        insert_row = destination_row
        if destination_row > source_start:
            insert_row -= len(moved_block)

        for offset, file_path in enumerate(moved_block):
            self.playlist.insert(insert_row + offset, file_path)

        if self.current_file_path in self.playlist:
            self.current_index = self.playlist.index(self.current_file_path)
        else:
            self.current_index = self.playlist_widget.currentRow()

        self.refresh_playlist_widget(select_index=self.current_index)

    def on_playlist_row_reordered(self):
        if self.is_reordering_playlist:
            return

        self.is_reordering_playlist = True
        try:
            selected_row = self.playlist_widget.currentRow()

            new_order = []
            for row in range(self.playlist_widget.rowCount()):
                name_item = self.playlist_widget.item(row, 1)
                if name_item is None:
                    continue
                file_path = name_item.data(Qt.UserRole)
                if isinstance(file_path, str) and file_path:
                    new_order.append(file_path)

            # If table data looks incomplete after drop, keep current logical playlist.
            if len(new_order) != len(self.playlist):
                self.refresh_playlist_widget(select_index=self.current_index if self.current_index >= 0 else None)
                return

            self.playlist = new_order

            if self.current_file_path in self.playlist:
                self.current_index = self.playlist.index(self.current_file_path)
            else:
                self.current_index = selected_row

            select_index = selected_row if self.playlist else None
            if select_index is not None:
                select_index = max(0, min(select_index, len(self.playlist) - 1))
            self.refresh_playlist_widget(select_index=select_index)
            if select_index is not None:
                self.playlist_widget.selectRow(select_index)
            if not self.vu_playing:
                self.update_preview_for_row(select_index if select_index is not None else -1, set_active_track=False)
        finally:
            self.is_reordering_playlist = False

    def open_playlist_xml(self):
        xml_path, _ = QFileDialog.getOpenFileName(self, "Open Playlist", "", "XML Files (*.xml)")
        if not xml_path:
            return

        self.open_playlist_xml_path(xml_path)

    def open_playlist_xml_path(self, xml_path):
        if not os.path.exists(xml_path):
            print(f"Playlist file not found: {xml_path}")
            return

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            loaded_paths = []
            for track in root.findall('track'):
                path_node = track.find('path')
                if path_node is None or not path_node.text:
                    continue

                track_path = path_node.text.strip()
                if track_path == "demo_audio" or os.path.exists(track_path):
                    loaded_paths.append(track_path)
                else:
                    print(f"Skipping missing file from playlist: {track_path}")

            self.playlist = loaded_paths
            self.current_index = -1
            self.current_file_path = None

            if hasattr(self, 'audio_cache'):
                self.audio_cache = {k: v for k, v in self.audio_cache.items() if k in self.playlist}
            self.duration_cache = {k: v for k, v in self.duration_cache.items() if k in self.playlist}

            self.set_busy(True)
            try:
                for idx, file_path in enumerate(self.playlist):
                    if file_path == "demo_audio":
                        self.ensure_demo_audio_data()
                    self.cache_audio_info(file_path, idx)
            finally:
                self.set_busy(False)

            self.refresh_playlist_widget(select_index=0 if self.playlist else None)
            self.add_recent_item('playlist', xml_path)
            print(f"Playlist loaded from: {xml_path}")
        except Exception as e:
            print(f"Error opening playlist XML: {e}")

    def new_playlist(self):
        self.stop_audio()
        self.playlist = []
        self.current_index = -1
        self.current_file_path = None
        self.vu_data = None
        self.vu_samplerate = None
        self.total_duration = 0
        self.vu_pos = 0

        if hasattr(self, 'audio_cache'):
            self.audio_cache.clear()
        self.duration_cache.clear()

        self.refresh_playlist_widget()
        self.waveform_label.setPixmap(self.render_placeholder_waveform_pixmap(1200, 190))
        self.show_vu_meter_stereo(-60, -60)
        self.time_label.setText("-00:00")
        self.update_playlist_total_display()
        self.update_window_title()
        print("Created new empty playlist")

    def save_playlist_xml(self):
        if not self.playlist:
            print("Playlist is empty - nothing to save")
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", "XML Files (*.xml)")
        if not save_path:
            return
        if not save_path.lower().endswith('.xml'):
            save_path += '.xml'

        root = ET.Element('playlist')
        for idx, file_path in enumerate(self.playlist, start=1):
            track = ET.SubElement(root, 'track', order=str(idx))
            ET.SubElement(track, 'name').text = self.get_playlist_display_name(file_path)
            ET.SubElement(track, 'path').text = file_path

        tree = ET.ElementTree(root)
        tree.write(save_path, encoding='utf-8', xml_declaration=True)
        print(f"Playlist saved to: {save_path}")

    def setup_menu(self):
        file_menu = self.menuBar().addMenu("File")

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.add_files)
        file_menu.addAction(open_action)

        new_playlist_action = QAction("New Playlist", self)
        new_playlist_action.triggered.connect(self.new_playlist)
        file_menu.addAction(new_playlist_action)

        open_xml_action = QAction("Open Playlist (XML)", self)
        open_xml_action.triggered.connect(self.open_playlist_xml)
        file_menu.addAction(open_xml_action)

        save_action = QAction("Save Playlist (XML)", self)
        save_action.triggered.connect(self.save_playlist_xml)
        file_menu.addAction(save_action)

        self.recent_menu = file_menu.addMenu("Open Recent")
        self.refresh_recent_menu()

        file_menu.addSeparator()
        close_action = QAction("Close", self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        settings_menu = self.menuBar().addMenu("Settings")
        audio_interface_action = QAction("Audio Interface...", self)
        audio_interface_action.triggered.connect(self.select_audio_interface)
        settings_menu.addAction(audio_interface_action)

        settings_menu.addSeparator()
        self.remote_toggle_action = QAction("Enable Remote Control", self)
        self.remote_toggle_action.setCheckable(True)
        self.remote_toggle_action.toggled.connect(self.toggle_remote_control)
        settings_menu.addAction(self.remote_toggle_action)

        self.remote_port_action = QAction("", self)
        self.update_remote_port_action_label()
        self.remote_port_action.triggered.connect(self.select_remote_port)
        settings_menu.addAction(self.remote_port_action)

        self.remote_toggle_action.blockSignals(True)
        self.remote_toggle_action.setChecked(self.remote_enabled)
        self.remote_toggle_action.blockSignals(False)
        if self.remote_enabled:
            self.toggle_remote_control(True)

    def update_remote_port_action_label(self):
        if hasattr(self, 'remote_port_action'):
            self.remote_port_action.setText(f"Remote Port ({self.remote_port})...")

    def get_local_ip(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            if sock is not None:
                sock.close()

    def start_remote_server(self):
        if self.remote_server is not None:
            return True
        try:
            self.remote_server = RemoteControlHTTPServer(("0.0.0.0", self.remote_port), RemoteControlRequestHandler)
            self.remote_server.player = self
        except Exception as e:
            QMessageBox.warning(self, "Remote Control", f"Unable to start remote server on port {self.remote_port}:\n{e}")
            self.remote_server = None
            return False

        self.remote_server_thread = threading.Thread(target=self.remote_server.serve_forever, daemon=True)
        self.remote_server_thread.start()
        print(f"Remote control enabled: http://{self.get_local_ip()}:{self.remote_port}/play")
        return True

    def stop_remote_server(self):
        if self.remote_server is None:
            return
        try:
            self.remote_server.shutdown()
            self.remote_server.server_close()
        except Exception:
            pass
        self.remote_server = None
        self.remote_server_thread = None
        print("Remote control disabled")

    def toggle_remote_control(self, enabled):
        if enabled:
            if self.start_remote_server():
                self.remote_enabled = True
                self.save_app_settings()
                return
            self.remote_enabled = False
            self.save_app_settings()
            self.remote_toggle_action.blockSignals(True)
            self.remote_toggle_action.setChecked(False)
            self.remote_toggle_action.blockSignals(False)
            return

        self.remote_enabled = False
        self.stop_remote_server()
        self.save_app_settings()

    def select_remote_port(self):
        new_port, ok = QInputDialog.getInt(
            self,
            "Remote Port",
            "HTTP port:",
            self.remote_port,
            1,
            65535,
            1,
        )
        if not ok or new_port == self.remote_port:
            return

        was_enabled = self.remote_enabled
        if was_enabled:
            self.stop_remote_server()

        self.remote_port = int(new_port)
        self.update_remote_port_action_label()

        if was_enabled:
            if self.start_remote_server():
                self.remote_enabled = True
                self.remote_toggle_action.blockSignals(True)
                self.remote_toggle_action.setChecked(True)
                self.remote_toggle_action.blockSignals(False)
            else:
                self.remote_enabled = False
                self.remote_toggle_action.blockSignals(True)
                self.remote_toggle_action.setChecked(False)
                self.remote_toggle_action.blockSignals(False)

        self.save_app_settings()

    def load_recent_items(self):
        if not os.path.exists(self.recent_state_path):
            self.recent_items = []
            return

        try:
            with open(self.recent_state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                cleaned = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    kind = item.get('kind')
                    path = item.get('path')
                    if kind in ('audio', 'playlist') and isinstance(path, str) and path.strip():
                        cleaned.append({'kind': kind, 'path': path})
                self.recent_items = cleaned[:3]
            else:
                self.recent_items = []
        except Exception:
            self.recent_items = []

    def save_recent_items(self):
        try:
            os.makedirs(os.path.dirname(self.recent_state_path), exist_ok=True)
            with open(self.recent_state_path, 'w', encoding='utf-8') as f:
                json.dump(self.recent_items[:3], f)
        except Exception as e:
            print(f"Failed to save recent items: {e}")

    def load_app_settings(self):
        if not os.path.exists(self.app_settings_path):
            return

        try:
            with open(self.app_settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return

            output_device = data.get('output_device', None)
            if output_device is None:
                self.output_device = None
            elif isinstance(output_device, int):
                self.output_device = output_device

            remote_port = data.get('remote_port', 8000)
            if isinstance(remote_port, int) and 1 <= remote_port <= 65535:
                self.remote_port = remote_port

            self.remote_enabled = bool(data.get('remote_enabled', False))
        except Exception:
            # Keep defaults if settings file is invalid.
            pass

    def save_app_settings(self):
        payload = {
            'output_device': self.output_device,
            'remote_enabled': bool(self.remote_enabled),
            'remote_port': int(self.remote_port),
        }
        try:
            os.makedirs(os.path.dirname(self.app_settings_path), exist_ok=True)
            with open(self.app_settings_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f)
        except Exception as e:
            print(f"Failed to save app settings: {e}")

    def add_recent_item(self, kind, path):
        if not isinstance(path, str) or not path:
            return

        self.recent_items = [
            item for item in self.recent_items
            if not (item.get('kind') == kind and item.get('path') == path)
        ]
        self.recent_items.insert(0, {'kind': kind, 'path': path})
        self.recent_items = self.recent_items[:3]
        self.save_recent_items()
        self.refresh_recent_menu()

    def refresh_recent_menu(self):
        if not hasattr(self, 'recent_menu'):
            return

        self.recent_menu.clear()
        if not self.recent_items:
            empty_action = QAction("(Empty)", self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return

        for item in self.recent_items:
            kind = item.get('kind', 'audio')
            path = item.get('path', '')
            base_name = os.path.basename(path) if path else '(Unknown)'
            prefix = "[Playlist]" if kind == 'playlist' else "[File]"
            action = QAction(f"{prefix} {base_name}", self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path, k=kind: self.open_recent_item(p, k))
            self.recent_menu.addAction(action)

    def open_recent_item(self, path, kind):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Open Recent", f"File not found:\n{path}")
            self.recent_items = [
                item for item in self.recent_items
                if not (item.get('kind') == kind and item.get('path') == path)
            ]
            self.save_recent_items()
            self.refresh_recent_menu()
            return

        if kind == 'playlist':
            self.open_playlist_xml_path(path)
            return

        self.open_audio_file_path(path)

    def open_audio_file_path(self, file_path):
        if not os.path.exists(file_path):
            print(f"Audio file not found: {file_path}")
            return

        self.playlist.append(file_path)
        self.refresh_playlist_widget(select_index=len(self.playlist) - 1)
        self.add_recent_item('audio', file_path)
        self.set_busy(True)
        try:
            self.cache_audio_info(file_path, 0)
        finally:
            self.set_busy(False)
        print(f"Loaded file: {os.path.basename(file_path)}")

    def get_output_devices(self):
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_hostapi = None
        try:
            default_hostapi = int(sd.default.hostapi)
        except Exception:
            default_hostapi = None

        # On Windows, PortAudio can expose the same endpoint via multiple host APIs.
        # Prefer showing only WASAPI devices to match the system playback list.
        preferred_hostapi = None
        for hostapi_idx, hostapi in enumerate(hostapis):
            hostapi_name = str(hostapi.get('name', '')).lower()
            if 'wasapi' in hostapi_name:
                preferred_hostapi = hostapi_idx
                break

        target_hostapi = preferred_hostapi if preferred_hostapi is not None else default_hostapi

        candidates = []
        seen_names = set()

        for idx, device in enumerate(devices):
            if int(device.get('max_output_channels', 0)) > 0:
                hostapi_index = int(device.get('hostapi', -1))
                if target_hostapi is not None and hostapi_index != target_hostapi:
                    continue

                # Keep only devices that are currently usable by the backend.
                try:
                    sd.check_output_settings(device=idx)
                except Exception:
                    continue

                name = str(device.get('name', 'Unknown Device')).strip()
                normalized_name = name.casefold()
                if normalized_name in seen_names:
                    continue
                seen_names.add(normalized_name)

                label = f"{name}"
                candidates.append((idx, label))

        return candidates

    def select_audio_interface(self):
        try:
            output_devices = self.get_output_devices()
        except Exception as e:
            QMessageBox.warning(self, "Audio Interface", f"Unable to list audio interfaces:\n{e}")
            return

        if not output_devices:
            QMessageBox.information(self, "Audio Interface", "No output audio interfaces found.")
            return

        options = ["System Default"] + [label for _, label in output_devices]
        current_index = 0
        if self.output_device is not None:
            for idx, (device_id, _) in enumerate(output_devices, start=1):
                if device_id == self.output_device:
                    current_index = idx
                    break

        selected, ok = QInputDialog.getItem(
            self,
            "Select Audio Interface",
            "Output device:",
            options,
            current_index,
            False,
        )
        if not ok:
            return

        if selected == "System Default":
            self.output_device = None
            self.save_app_settings()
            print("Audio interface set to System Default")
            return

        for device_id, label in output_devices:
            if label == selected:
                self.output_device = device_id
                self.save_app_settings()
                print(f"Audio interface set to: {label}")
                break

    def transport_button_style(self, bg_color, text_color, border_color):
        return (
            "font-size: 24px; min-width: 120px; min-height: 60px; "
            f"background-color: {bg_color}; color: {text_color}; border: 2px solid {border_color};"
        )

    def update_transport_button_state(self, state):
        # state: 'playing', 'paused', or 'stopped'
        active = {
            'play': ('#1aff1a', 'black', '#006600'),
            'pause': ('#ffff66', 'black', '#999900'),
            'stop': ('#ff3333', 'white', '#990000'),
        }
        inactive = {
            'play': ('#0a4d0a', '#cccccc', '#063306'),
            'pause': ('#5a5a1f', '#cccccc', '#3d3d14'),
            'stop': ('#661a1a', '#dddddd', '#4a1010'),
        }

        style_map = {
            'playing': {
                'play': active['play'],
                'pause': inactive['pause'],
                'stop': inactive['stop'],
            },
            'paused': {
                'play': inactive['play'],
                'pause': active['pause'],
                'stop': inactive['stop'],
            },
            'stopped': {
                'play': inactive['play'],
                'pause': inactive['pause'],
                'stop': active['stop'],
            },
        }
        selected = style_map.get(state, style_map['stopped'])
        self.play_button.setStyleSheet(self.transport_button_style(*selected['play']))
        self.pause_button.setStyleSheet(self.transport_button_style(*selected['pause']))
        self.stop_button.setStyleSheet(self.transport_button_style(*selected['stop']))

    def on_playback_finished(self, session_id=None):
        if session_id is not None and session_id != self.playback_session_id:
            return

        self.vu_playing = False
        self.vu_timer.stop()
        self.vu_start_time = None
        self.vu_pos = self.total_duration
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()
        if self.playback_end_mode in ('paused', 'stopped', 'switching'):
            self.playback_end_mode = 'natural'
            return

        continue_enabled = hasattr(self, 'continue_checkbox') and self.continue_checkbox.isChecked()
        if continue_enabled and self.current_index + 1 < len(self.playlist):
            self.current_index += 1
            self.update_preview_for_row(self.current_index, set_active_track=True)
            self.play_audio()
            return

        self.update_transport_button_state('stopped')
        if self.total_duration > 0 and self.vu_samplerate is not None:
            self.update_time_display(0, self.total_duration, self.vu_samplerate)
            self.update_waveform_cursor(self.total_duration)

    def setup_vu_timer(self):
        from PyQt5.QtCore import QTimer
        self.vu_timer = QTimer()
        self.vu_timer.setInterval(50)  # update every 50ms
        self.vu_timer.timeout.connect(self.update_vu_meter)
        self.vu_data = None
        self.vu_samplerate = None
        self.vu_pos = 0
        self.vu_start_time = None
        self.vu_blocksize = 2048
        self.vu_playing = False
        self.waveform_update_interval = 0.5  # update cursor every 500ms
        self.last_waveform_update_time = 0
        self.current_file_path = None
        self.right_panel_width = 240
        self.vu_channel_col_width = 18
        self.vu_db_col_width = 90
        self.waveform_left_padding = 0
        self.waveform_right_padding = 0
        self.waveform_time_label_padding = 10
        self.waveform_amplitude_scale = 0.85
        self.playback_end_mode = 'natural'
        self.playback_session_id = 0
        self.playback_start_sample = 0
        self.busy_count = 0
        self.duration_cache = {}
        self.is_reordering_playlist = False
        self.output_device = None
        self.remote_enabled = False
        self.remote_port = 8000
        self.remote_server = None
        self.remote_server_thread = None
        self.sidecar_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.livepro_cache')
        os.makedirs(self.sidecar_dir, exist_ok=True)
        self.app_settings_path = os.path.join(self.sidecar_dir, 'app_settings.json')
        self.load_app_settings()
        self.recent_state_path = os.path.join(self.sidecar_dir, 'recent_items.json')
        self.recent_items = []
        self.load_recent_items()
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Pro Player")
        self.setGeometry(100, 100, 1280, 820)
        self.setMinimumSize(1100, 720)
        self.playlist = []
        self.current_index = -1
        self.audio_stream = None
        self.total_duration = 0  # Store total duration in samples
        self.current_vu_left = -60
        self.current_vu_right = -60
        self.remote_command_requested.connect(self.execute_remote_command)
        self.init_ui()
        self.update_window_title()

    def init_ui(self):
        self.setup_vu_timer()
        self.setup_menu()
        main_layout = QVBoxLayout()
        self.playlist_widget = PlaylistTable()
        self.playlist_widget.setColumnCount(3)
        self.playlist_widget.setHorizontalHeaderLabels(["#", "File", "Duration"])
        self.playlist_widget.verticalHeader().setVisible(False)
        self.playlist_widget.horizontalHeader().setSectionsMovable(False)
        self.playlist_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.playlist_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.playlist_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.playlist_widget.setColumnWidth(0, 52)
        self.playlist_widget.setColumnWidth(2, 130)
        self.playlist_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.playlist_widget.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.playlist_widget.setDragDropOverwriteMode(False)
        self.playlist_widget.setDragEnabled(False)
        self.playlist_widget.viewport().setAcceptDrops(False)
        self.playlist_widget.setDropIndicatorShown(False)
        self.playlist_widget.setDefaultDropAction(Qt.MoveAction)
        self.playlist_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.playlist_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.playlist_widget.rows_reordered.connect(self.on_playlist_row_reordered)
        self.playlist_widget.itemSelectionChanged.connect(self.on_playlist_selection_changed)
        main_layout.addWidget(self.playlist_widget)

        controls_layout = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.next_button = QPushButton("Next")
        self.next_button.setStyleSheet("font-size: 24px; min-width: 120px; min-height: 60px; background-color: #444; color: white; border: 2px solid #222;")
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.next_button)
        self.stop_button.clicked.connect(self.stop_audio)
        main_layout.addLayout(controls_layout)

        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(16)

        self.silence_checkbox = QCheckBox("Remove Silence (Start/End)")
        options_layout.addWidget(self.silence_checkbox)

        self.continue_checkbox = QCheckBox("Single")
        self.continue_checkbox.setChecked(False)
        self.continue_checkbox.toggled.connect(self.update_continue_mode_label)
        options_layout.addWidget(self.continue_checkbox)

        self.seek_checkbox = QCheckBox("Seek")
        self.seek_checkbox.setChecked(False)
        options_layout.addWidget(self.seek_checkbox)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setCheckable(True)
        self.edit_button.setStyleSheet("font-size: 14px; min-width: 56px; min-height: 30px; background-color: #444; color: white; border: 1px solid #222;")
        options_layout.addWidget(self.edit_button)

        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.up_button.setStyleSheet("font-size: 13px; min-width: 44px; min-height: 28px; background-color: #444; color: white; border: 1px solid #222;")
        self.down_button.setStyleSheet("font-size: 13px; min-width: 52px; min-height: 28px; background-color: #444; color: white; border: 1px solid #222;")
        self.up_button.setVisible(False)
        self.down_button.setVisible(False)
        options_layout.addWidget(self.up_button)
        options_layout.addWidget(self.down_button)

        options_layout.addStretch(1)
        main_layout.addLayout(options_layout)

        # Top bar: VU meter and time label horizontally aligned
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(0)
        self.vu_label = QLabel()
        self.vu_label.setFixedHeight(80)
        self.vu_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_bar_layout.addWidget(self.vu_label, 1)

        self.time_label = QLabel("-00:00")
        self.time_label.setStyleSheet("font-size: 48px; color: #1aff1a; font-weight: bold; background-color: transparent;")
        self.time_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.track_remaining_label = QLabel("Track Remaining")
        self.track_remaining_label.setStyleSheet("font-size: 14px; color: #b8ffb8; font-weight: 600; background-color: transparent;")
        self.track_remaining_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.playlist_total_title_label = QLabel("Playlist Total")
        self.playlist_total_title_label.setStyleSheet("font-size: 13px; color: #b8ffb8; font-weight: 600; background-color: transparent;")
        self.playlist_total_title_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        self.playlist_total_time_label = QLabel("-00:00:00")
        self.playlist_total_time_label.setStyleSheet("font-size: 24px; color: #1aff1a; font-weight: bold; background-color: transparent;")
        self.playlist_total_time_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        right_track_layout = QVBoxLayout()
        right_track_layout.setContentsMargins(0, 0, 0, 0)
        right_track_layout.setSpacing(0)
        right_track_layout.addStretch()
        right_track_layout.addWidget(self.time_label)
        right_track_layout.addWidget(self.track_remaining_label)
        right_track_layout.addStretch()

        self.right_track_container = QWidget()
        self.right_track_container.setFixedWidth(self.right_panel_width)
        self.right_track_container.setFixedHeight(80)
        self.right_track_container.setLayout(right_track_layout)
        top_bar_layout.addWidget(self.right_track_container, 0)
        main_layout.addLayout(top_bar_layout)

        # Initialize VU meter with default values
        self.show_vu_meter_stereo(-60, -60)

        self.waveform_label = ClickableWaveformLabel()
        self.waveform_label.setFixedHeight(190)
        self.waveform_label.setScaledContents(True)
        self.waveform_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.waveform_label.clicked.connect(self.on_waveform_clicked)
        # Keep a default waveform trace visible before loading any file.
        default_pixmap = self.render_placeholder_waveform_pixmap(1200, 190)
        self.waveform_label.setPixmap(default_pixmap)
        waveform_row_layout = QHBoxLayout()
        waveform_row_layout.setContentsMargins(0, 0, 0, 0)
        waveform_row_layout.setSpacing(0)
        waveform_row_layout.addWidget(self.waveform_label, 1)
        self.waveform_right_panel = QWidget()
        self.waveform_right_panel.setFixedWidth(self.right_panel_width)
        self.waveform_right_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        waveform_right_layout = QVBoxLayout()
        waveform_right_layout.setContentsMargins(0, 6, 0, 0)
        waveform_right_layout.setSpacing(0)
        waveform_right_layout.addStretch()
        waveform_right_layout.addWidget(self.playlist_total_title_label)
        waveform_right_layout.addWidget(self.playlist_total_time_label)
        waveform_right_layout.addStretch()
        self.waveform_right_panel.setLayout(waveform_right_layout)

        waveform_row_layout.addWidget(self.waveform_right_panel, 0)
        main_layout.addLayout(waveform_row_layout)

        # Dark mode stylesheet
        dark_stylesheet = """
            QWidget { background-color: #222; color: #eee; }
            QMenuBar { background-color: #222; color: #eee; }
            QMenuBar::item { background-color: transparent; padding: 4px 10px; }
            QMenuBar::item:selected { background-color: #2e5f2e; color: #f0fff0; }
            QMenu { background-color: #222; color: #eee; border: 1px solid #333; }
            QMenu::item { padding: 6px 18px; background-color: transparent; }
            QMenu::item:selected { background-color: #2e5f2e; color: #f0fff0; }
            QTableWidget { background-color: #222; color: #eee; gridline-color: #333; selection-background-color: transparent; selection-color: #eee; font-size: 14px; }
            QTableWidget::item:selected { background-color: transparent; border: 1px solid #7CFC00; }
            QTableWidget::item:selected:active { background-color: transparent; }
            QTableWidget::item:selected:!active { background-color: transparent; }
            QHeaderView::section { background-color: #2a2a2a; color: #ddd; border: 1px solid #333; font-size: 14px; font-weight: 600; }
            QLabel { color: #eee; }
            QCheckBox { color: #eee; }
            QPushButton { background-color: #444; color: #eee; border: 2px solid #222; }
        """
        self.setStyleSheet(dark_stylesheet)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.next_button.clicked.connect(self.play_next_track)
        self.edit_button.toggled.connect(self.toggle_edit_mode)
        self.up_button.clicked.connect(lambda: self.move_selected_track(-1))
        self.down_button.clicked.connect(lambda: self.move_selected_track(1))
        self.play_button.clicked.connect(self.play_audio)
        self.pause_button.clicked.connect(self.pause_audio)
        self.playlist_widget.cellDoubleClicked.connect(self.select_track)
        self.setup_shortcuts()
        self.sync_waveform_width_with_vu()
        self.update_transport_button_state('stopped')
        self.update_playlist_total_display()

    def play_next_track(self):
        if not self.playlist:
            print("Playlist is empty")
            return

        if self.current_index < 0:
            next_index = 0
        else:
            next_index = self.current_index + 1

        if next_index >= len(self.playlist):
            print("Already at the last track")
            return

        self.playlist_widget.selectRow(next_index)
        self.select_track(next_index, 0)

    def play_previous_track(self):
        if not self.playlist:
            print("Playlist is empty")
            return

        if self.current_index <= 0:
            prev_index = 0
        else:
            prev_index = self.current_index - 1

        self.playlist_widget.selectRow(prev_index)
        self.select_track(prev_index, 0)

    def execute_remote_command(self, command):
        if command == 'play':
            self.play_audio()
        elif command == 'pause':
            if self.vu_playing:
                self.pause_audio()
        elif command == 'stop':
            self.stop_audio()
        elif command == 'next':
            self.play_next_track()
        elif command == 'previous':
            self.play_previous_track()

    def toggle_edit_mode(self, enabled):
        self.up_button.setVisible(enabled)
        self.down_button.setVisible(enabled)
        self.edit_button.setText("Done" if enabled else "Edit")

    def move_selected_track(self, offset):
        if not self.playlist:
            return

        row = self.playlist_widget.currentRow()
        if row < 0 or row >= len(self.playlist):
            return

        target_row = row + offset
        if target_row < 0 or target_row >= len(self.playlist):
            return

        moved = self.playlist.pop(row)
        self.playlist.insert(target_row, moved)

        if self.current_file_path in self.playlist:
            self.current_index = self.playlist.index(self.current_file_path)
        else:
            self.current_index = target_row

        self.refresh_playlist_widget(select_index=target_row)
        if not self.vu_playing:
            self.update_preview_for_row(target_row, set_active_track=False)

    def add_files(self):
        try:
            default_open_dir = os.path.join(os.path.expanduser("~"), "Music")
            if not os.path.isdir(default_open_dir):
                default_open_dir = os.path.expanduser("~")
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Select Audio Files",
                default_open_dir,
                "Audio Files (*.wav *.flac *.mp3)",
            )
            if files:
                self.playlist.extend(files)
                self.refresh_playlist_widget(select_index=len(self.playlist) - len(files))
                for file_path in files:
                    self.add_recent_item('audio', file_path)
                print(f"Loaded {len(files)} files: {[os.path.basename(f) for f in files]}")
                # Immediately cache waveform, duration, and VU info for each file
                self.set_busy(True)
                try:
                    for idx, file_path in enumerate(files):
                        self.cache_audio_info(file_path, idx)
                finally:
                    self.set_busy(False)
            else:
                print("No files selected - creating demo audio")
                self.create_demo_audio()
        except Exception as e:
            print(f"Error loading files: {e}")
            print("Creating demo audio as fallback")
            self.create_demo_audio()

    def cache_audio_info(self, file_path, idx):
        """Cache waveform, duration, and VU info for file."""
        try:
            if self.try_load_sidecar_cache(file_path):
                print(f"Loaded sidecar cache for {file_path}")
                return

            if file_path == "demo_audio" and hasattr(self, 'demo_data'):
                data = self.demo_data
                samplerate = self.demo_samplerate
            else:
                data, samplerate = sf.read(file_path)
            duration_samples = len(data)
            self.set_cached_duration(file_path, duration_samples / samplerate)
            # Cache waveform pixmap
            try:
                pixmap = self.render_waveform_pixmap(data, samplerate)
                if pixmap.isNull():
                    print(f"Failed to create pixmap for {file_path}")
                    return
                # Store in cache
                if not hasattr(self, 'audio_cache'):
                    self.audio_cache = {}
                self.audio_cache[file_path] = {
                    'data': data,
                    'samplerate': samplerate,
                    'duration_samples': duration_samples,
                    'waveform_pixmap': pixmap,
                }
                self.save_sidecar_cache(file_path, samplerate, duration_samples, pixmap)
                print(f"Cached audio info for {file_path}")
            except Exception as e:
                print(f"Error generating waveform for {file_path}: {e}")
        except Exception as e:
            print(f"Error caching audio info for {file_path}: {e}")

    def render_waveform_pixmap(self, data, samplerate):
        width = 1200
        height = 190
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.black)

        if data.ndim == 2:
            mono_data = np.mean(data, axis=1)
        else:
            mono_data = data

        if len(mono_data) == 0:
            return pixmap

        left = self.waveform_left_padding
        right = self.waveform_right_padding
        top = 8
        bottom = 34
        usable_width = max(10, width - left - right)
        usable_height = max(20, height - top - bottom)
        center_y = top + usable_height // 2
        end_x = left + usable_width - 1

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Build a min/max envelope per pixel for a denser and more informative waveform.
        stride = max(1, int(np.ceil(len(mono_data) / usable_width)))
        clipped = mono_data.astype(np.float32)
        peak = float(np.percentile(np.abs(clipped), 99.5))
        if peak < 1e-9:
            peak = 1.0
        clipped = np.clip(clipped / peak, -1.0, 1.0)

        wave_pen = QPen(QColor('#00ffff'))
        wave_pen.setWidth(1)
        painter.setPen(wave_pen)
        max_amp = max(1, int(((usable_height // 2) - 2) * self.waveform_amplitude_scale))
        for i in range(usable_width):
            x = left + i
            start = i * stride
            end = min(len(clipped), start + stride)
            if start >= end:
                break
            seg = clipped[start:end]
            seg_min = float(np.min(seg))
            seg_max = float(np.max(seg))
            y1 = center_y - int(seg_max * max_amp)
            y2 = center_y - int(seg_min * max_amp)
            painter.drawLine(x, y1, x, y2)

        axis_y = top + usable_height + 2
        painter.setPen(QPen(QColor('#d0d0d0')))
        painter.drawLine(left, axis_y, end_x, axis_y)

        painter.setPen(QPen(QColor('#e6e6e6')))
        label_pad = self.waveform_time_label_padding
        painter.drawText(left + label_pad, height - 8, self.format_duration_label(0))
        end_label = self.format_duration_label(len(mono_data) / samplerate)
        end_label_width = painter.fontMetrics().horizontalAdvance(end_label)
        painter.drawText(end_x - end_label_width - label_pad, height - 8, end_label)

        painter.end()
        return pixmap

    def render_placeholder_waveform_pixmap(self, width, height):
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.black)

        left = self.waveform_left_padding
        right = self.waveform_right_padding
        top = 8
        bottom = 34
        usable_width = max(10, width - left - right)
        usable_height = max(20, height - top - bottom)
        center_y = top + usable_height // 2
        end_x = left + usable_width - 1

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Startup placeholder: silence only.
        painter.setPen(QPen(QColor('#00a8a8')))
        painter.drawLine(left, center_y, end_x, center_y)

        axis_y = top + usable_height + 2
        painter.setPen(QPen(QColor('#d0d0d0')))
        painter.drawLine(left, axis_y, end_x, axis_y)

        painter.setPen(QPen(QColor('#e6e6e6')))
        label_pad = self.waveform_time_label_padding
        painter.drawText(left + label_pad, height - 8, self.format_duration_label(0))
        end_label = self.format_duration_label(0)
        end_label_width = painter.fontMetrics().horizontalAdvance(end_label)
        painter.drawText(end_x - end_label_width - label_pad, height - 8, end_label)

        painter.end()
        return pixmap


    def create_demo_audio(self):
        """Create synthetic demo audio data"""
        try:
            samplerate = 44100
            duration = 3.0  # 3 seconds
            t = np.linspace(0, duration, int(samplerate * duration), False)
            
            # Create a stereo sine wave sweep
            freq_start = 220
            freq_end = 880
            freq = np.linspace(freq_start, freq_end, len(t))
            data = np.sin(2 * np.pi * freq * t)
            
            # Make it stereo by duplicating the channel
            data = np.column_stack([data, data])
            
            # Store in memory (don't save to file)
            self.demo_data = data
            self.demo_samplerate = samplerate
            
            # Add to playlist
            self.playlist.append("demo_audio")
            self.refresh_playlist_widget(select_index=len(self.playlist) - 1)
            self.cache_audio_info("demo_audio", 0)
            print("Demo audio created successfully")
            
        except Exception as e:
            print(f"Error creating demo audio: {e}")
            # Last resort: create minimal data
            self.demo_data = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 44100))
            self.demo_samplerate = 44100
            self.playlist.append("demo_audio")
            self.refresh_playlist_widget(select_index=len(self.playlist) - 1)
            self.cache_audio_info("demo_audio", 0)
            print("Minimal demo audio created")

    def select_track(self, row, column=0):
        self.update_preview_for_row(row, set_active_track=True)
        self.play_audio()

    def play_audio(self):
        if self.current_index == -1 and self.playlist:
            self.current_index = 0
        if self.current_index < 0 or self.current_index >= len(self.playlist):
            print("No valid track selected")
            return

        # If another track is playing, stop it first to avoid stream/thread contention.
        if self.vu_playing or self.vu_start_time is not None:
            self.playback_end_mode = 'switching'
            sd.stop()
            self.vu_playing = False
            self.vu_timer.stop()
        
        file_path = self.playlist[self.current_index]
        self.current_file_path = file_path
        self.update_window_title()
        print(f"Loading file: {file_path}")
        
        try:
            # Check if this is demo audio
            if file_path == "demo_audio" and hasattr(self, 'demo_data'):
                data = self.demo_data
                samplerate = self.demo_samplerate
                print(f"Demo audio loaded: {len(data)} samples at {samplerate} Hz, shape: {data.shape}")
            else:
                data, samplerate = sf.read(file_path)
                print(f"Audio loaded: {len(data)} samples at {samplerate} Hz, shape: {data.shape}")
        except Exception as e:
            print(f"Error loading audio file: {e}")
            return
        
        if self.silence_checkbox.isChecked():
            data = self.remove_silence(data)
            print("Silence removal applied")

        # Ensure waveform cache exists (can be missing for demo or failed pre-cache).
        if not hasattr(self, 'audio_cache') or file_path not in self.audio_cache:
            self.cache_audio_info(file_path, 0)

        resume_sample = 0
        if (
            self.playback_end_mode == 'paused'
            and self.current_file_path == file_path
            and 0 < self.vu_pos < len(data)
        ):
            resume_sample = self.vu_pos
        
        self.total_duration = len(data)  # Store total duration in samples
        self.vu_data = data
        self.vu_samplerate = samplerate  # Define samplerate before using it
        remaining_from_start = max(0, self.total_duration - resume_sample)
        self.update_time_display(remaining_from_start, self.total_duration)
        self.last_waveform_update_time = 0

        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            self.waveform_label.setPixmap(self.audio_cache[file_path]['waveform_pixmap'])
            self.update_waveform_cursor(resume_sample)
        
        self.vu_pos = resume_sample
        self.vu_playing = True
        self.vu_start_time = None  # Track actual playback start time
        self.playback_start_sample = resume_sample
        self.playback_end_mode = 'natural'
        self.playback_session_id += 1
        self.vu_timer.start()
        self.update_transport_button_state('playing')
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()
        
        print("Starting audio playback...")
        self.play_stream_realtime(data, samplerate, self.playback_session_id, resume_sample)

    def play_stream_realtime(self, data, samplerate, session_id, start_sample=0):
        self.vu_start_time = time.time() - (start_sample / samplerate)
        sd.play(data[start_sample:], samplerate, blocking=False, device=self.output_device)

    def update_vu_meter(self):
        if not self.vu_playing or self.vu_data is None or self.vu_start_time is None:
            return
        
        # Calculate actual position based on elapsed time for better sync
        import time
        elapsed_time = time.time() - self.vu_start_time
        current_pos = int(elapsed_time * self.vu_samplerate)
        
        # Ensure we don't go beyond the data length
        current_pos = min(current_pos, len(self.vu_data))

        if current_pos >= len(self.vu_data):
            self.on_playback_finished(self.playback_session_id)
            return
        
        # Update VU meter with current audio block
        start = max(0, current_pos - self.vu_blocksize // 2)
        end = min(start + self.vu_blocksize, len(self.vu_data))
        if start < end:
            block = self.vu_data[start:end]
            vu_left, vu_right = self.calculate_vu_stereo(block)
            self.show_vu_meter_stereo(vu_left, vu_right)
        
        # Keep waveform updates lightweight by only drawing the cursor periodically.
        if elapsed_time - self.last_waveform_update_time >= self.waveform_update_interval:
            self.update_waveform_cursor(current_pos)
            self.last_waveform_update_time = elapsed_time
        
        # Update time display with remaining time
        remaining_samples = max(0, self.total_duration - current_pos)
        self.update_time_display(remaining_samples, self.total_duration, self.vu_samplerate)
        self.update_playlist_total_display()
        
        # Update position for other functions
        self.vu_pos = current_pos

    def update_time_display(self, remaining_samples, total_samples, samplerate=None):
        if samplerate is None:
            samplerate = self.vu_samplerate
        if total_samples > 0 and samplerate is not None:
            remaining_time = remaining_samples / samplerate
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            seconds = int(remaining_time % 60)
            
            if hours > 0:
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                time_str = f"{minutes:02d}:{seconds:02d}"
            
            self.time_label.setText(f"-{time_str}")
            self.apply_track_time_color(remaining_time)

    def format_duration_label(self, seconds_total):
        hours = int(seconds_total // 3600)
        minutes = int((seconds_total % 3600) // 60)
        seconds = int(seconds_total % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def pause_audio(self):
        if not self.vu_playing:
            if self.playback_end_mode == 'paused' and 0 <= self.current_index < len(self.playlist):
                self.play_audio()
            return

        self.playback_end_mode = 'paused'
        if self.vu_start_time is not None and self.vu_samplerate is not None and self.vu_data is not None:
            self.vu_pos = min(len(self.vu_data), int((time.time() - self.vu_start_time) * self.vu_samplerate))
        sd.stop()
        self.vu_playing = False
        self.vu_timer.stop()
        self.vu_start_time = None
        self.update_transport_button_state('paused')
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()
        # Update time display to show remaining time when paused
        if hasattr(self, 'total_duration') and self.total_duration > 0:
            remaining_samples = self.total_duration - self.vu_pos
            self.update_time_display(remaining_samples, self.total_duration, self.vu_samplerate)
            self.update_waveform_cursor(self.vu_pos)
    def show_vu_meter_stereo(self, vu_left, vu_right):
        self.current_vu_left = vu_left
        self.current_vu_right = vu_right
        # AES/EBU VU meter: -60dB to 0dB (0 VU = -14 dBFS reference)
        min_db = -60
        max_db = 0
        width = max(200, self.vu_label.width())
        height = max(60, self.vu_label.height())
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor('#222222'))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)

        row_gap = 6
        row_height = max(10, (height - row_gap) // 2)
        bar_left = 0
        bar_width = width

        segment_width = 4
        segment_gap = 1
        segment_count = max(12, bar_width // (segment_width + segment_gap))

        def segment_color(index):
            db = min_db + (max_db - min_db) * index / max(1, segment_count - 1)
            if db >= -8:
                return QColor('#ff0000')
            if db >= -12:
                return QColor('#ff6600')
            if db >= -20:
                return QColor('#ffff00')
            if db >= -40:
                return QColor('#00ff00')
            return QColor('#66ff00')

        def draw_row(y_top, channel_label, vu_value):
            vu_clamped = max(min_db, min(max_db, vu_value))
            percent = (vu_clamped - min_db) / (max_db - min_db)
            filled = int(percent * segment_count)

            for i in range(segment_count):
                x = bar_left + i * (segment_width + segment_gap)
                if i < filled:
                    painter.fillRect(x, y_top + 2, segment_width, row_height - 4, segment_color(i))
                else:
                    painter.fillRect(x, y_top + 2, segment_width, row_height - 4, QColor('#2f2f2f'))

            # Keep labels readable while preserving full-width bars.
            painter.fillRect(0, y_top, 24, row_height, QColor('#222222'))
            painter.fillRect(width - 92, y_top, 92, row_height, QColor('#222222'))

            painter.setPen(QPen(QColor('#eeeeee')))
            painter.drawText(2, y_top, 20, row_height, Qt.AlignLeft | Qt.AlignVCenter, channel_label)

            db_text = f"{vu_clamped:6.1f}dB"
            painter.setPen(QPen(QColor('#eeeeee')))
            painter.drawText(width - 90, y_top, 88, row_height, Qt.AlignRight | Qt.AlignVCenter, db_text)

        draw_row(0, 'L', vu_left)
        draw_row(row_height + row_gap, 'R', vu_right)

        painter.end()
        self.vu_label.setPixmap(pixmap)
    def stop_audio(self):
        self.playback_end_mode = 'stopped'
        sd.stop()
        self.vu_playing = False
        self.vu_timer.stop()
        self.vu_start_time = None  # Reset start time
        self.vu_pos = 0
        self.current_file_path = None
        self.update_transport_button_state('stopped')
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()
        self.update_window_title()
        # Reset time display to full duration
        if hasattr(self, 'total_duration') and self.total_duration > 0:
            self.update_time_display(self.total_duration, self.total_duration, self.vu_samplerate)
            self.update_waveform_cursor(0)

    def update_waveform_cursor(self, current_pos):
        if (
            not hasattr(self, 'audio_cache')
            or self.current_file_path not in self.audio_cache
            or self.total_duration <= 0
        ):
            return

        base_pixmap = self.audio_cache[self.current_file_path]['waveform_pixmap']
        if base_pixmap.isNull():
            return

        pixmap = QPixmap(base_pixmap)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor('#ff0000'))
        pen.setWidth(2)
        painter.setPen(pen)

        left = self.waveform_left_padding
        right = self.waveform_right_padding
        usable_width = max(1, pixmap.width() - left - right)
        x = left + int((current_pos / self.total_duration) * (usable_width - 1))
        x = max(left, min(left + usable_width - 1, x))
        painter.drawLine(x, 0, x, pixmap.height())
        painter.end()

        self.waveform_label.setPixmap(pixmap)

    def on_waveform_clicked(self, x, y):
        if not hasattr(self, 'seek_checkbox') or not self.seek_checkbox.isChecked():
            return

        if not self.playlist:
            return

        row = self.current_index
        if row < 0:
            row = self.playlist_widget.currentRow()
        if row < 0 or row >= len(self.playlist):
            return

        # Make sure current track context is loaded before seek.
        if self.current_index != row or self.current_file_path != self.playlist[row] or self.vu_data is None:
            self.update_preview_for_row(row, set_active_track=True)

        if self.vu_data is None or self.vu_samplerate is None or self.total_duration <= 0:
            return

        label_width = max(1, self.waveform_label.width())
        left = self.waveform_left_padding
        right = self.waveform_right_padding
        usable_width = max(1, label_width - left - right)
        click_x = max(left, min(left + usable_width - 1, int(x)))
        ratio = (click_x - left) / max(1, usable_width - 1)
        target_sample = int(ratio * max(0, self.total_duration - 1))

        self.vu_pos = target_sample
        self.playback_start_sample = target_sample
        remaining_samples = max(0, self.total_duration - target_sample)
        self.update_time_display(remaining_samples, self.total_duration, self.vu_samplerate)
        self.update_waveform_cursor(target_sample)
        self.update_playlist_total_display()

        if self.vu_playing:
            self.vu_start_time = time.time() - (target_sample / self.vu_samplerate)
            try:
                sd.play(
                    self.vu_data[target_sample:],
                    self.vu_samplerate,
                    blocking=False,
                    device=self.output_device,
                )
            except Exception as e:
                print(f"Seek playback failed: {e}")
                self.playback_end_mode = 'paused'
                self.vu_playing = False
                self.vu_timer.stop()
        else:
            # Keep stopped/paused state, but allow Play to resume from clicked position.
            self.playback_end_mode = 'paused'

    def update_continue_mode_label(self, enabled):
        self.continue_checkbox.setText("Continue" if enabled else "Single")

    def calculate_vu_stereo(self, data):
        if data.ndim == 1:
            # Mono audio
            rms = np.sqrt(np.mean(np.square(data)))
            vu = 20 * np.log10(rms) if rms > 0 else -float('inf')
            return vu, vu
        else:
            # Stereo audio
            left_channel = data[:, 0] if data.shape[1] > 0 else data[:, 0]
            right_channel = data[:, 1] if data.shape[1] > 1 else data[:, 0]
            
            rms_left = np.sqrt(np.mean(np.square(left_channel)))
            rms_right = np.sqrt(np.mean(np.square(right_channel)))
            
            vu_left = 20 * np.log10(rms_left) if rms_left > 0 else -float('inf')
            vu_right = 20 * np.log10(rms_right) if rms_right > 0 else -float('inf')
            
            return vu_left, vu_right

    def remove_silence(self, data, threshold=0.01):
        abs_data = np.abs(data)
        if abs_data.ndim == 1:
            mask = abs_data > threshold
        else:
            # Collapse channels so trimming uses sample positions, not flattened arrays.
            mask = np.max(abs_data, axis=1) > threshold
        if not np.any(mask):
            return data
        start = np.argmax(mask)
        end = len(mask) - np.argmax(mask[::-1])
        return data[start:end]

    def closeEvent(self, event):
        self.save_app_settings()
        if self.vu_playing:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Playback Active")
            msg_box.setText(
                "Music is playing!\n"
                "Close the app and stop playback?\n\n"
                "Stop and Close"
            )
            stop_and_close_btn = msg_box.addButton("Stop and Close", QMessageBox.DestructiveRole)
            msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.exec_()

            if msg_box.clickedButton() is not stop_and_close_btn:
                event.ignore()
                return

            self.playback_end_mode = 'stopped'
            sd.stop()
            self.vu_playing = False
            self.vu_timer.stop()
        self.stop_remote_server()
        sd.stop()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Update VU meter on resize for responsiveness
        self.show_vu_meter_stereo(self.current_vu_left, self.current_vu_right)
        self.sync_waveform_width_with_vu()

    def sync_waveform_width_with_vu(self):
        if hasattr(self, 'right_track_container') and hasattr(self, 'waveform_right_panel'):
            right_width = self.right_track_container.width()
            width_value = max(120, right_width)
            self.right_track_container.setFixedWidth(width_value)
            self.waveform_right_panel.setFixedWidth(width_value)

if __name__ == "__main__":
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
