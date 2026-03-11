import hashlib
import json
import os

from PyQt5.QtCore import QStandardPaths, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QAction, QMessageBox


class SettingsMixin:
    def resolve_sidecar_dir(self):
        # Use per-user writable app data for installed builds (Program Files is read-only).
        base_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if not base_dir:
            base_dir = os.path.join(os.path.expanduser('~'), '.liveproplayer')

        target_dir = os.path.join(base_dir, 'cache')
        try:
            os.makedirs(target_dir, exist_ok=True)
            return target_dir
        except Exception:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fallback = os.path.join(project_root, '.livepro_cache')
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def sidecar_key(self, file_path):
        raw = file_path.encode('utf-8', errors='ignore')
        return hashlib.sha1(raw).hexdigest()

    def sidecar_paths(self, file_path):
        key = self.sidecar_key(file_path)
        meta_path = os.path.join(self.sidecar_dir, f"{key}.json")
        png_path = os.path.join(self.sidecar_dir, f"{key}.png")
        return meta_path, png_path

    def try_load_sidecar_cache(self, file_path):
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
            empty_action = QAction('(Empty)', self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return

        for item in self.recent_items:
            kind = item.get('kind', 'audio')
            path = item.get('path', '')
            base_name = os.path.basename(path) if path else '(Unknown)'
            prefix = '[Playlist]' if kind == 'playlist' else '[File]'
            action = QAction(f"{prefix} {base_name}", self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path, k=kind: self.open_recent_item(p, k))
            self.recent_menu.addAction(action)

    def open_recent_item(self, path, kind):
        if not os.path.exists(path):
            QMessageBox.warning(self, 'Open Recent', f"File not found:\n{path}")
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
