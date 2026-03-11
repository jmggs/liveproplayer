import os
import xml.etree.ElementTree as ET

import soundfile as sf

from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class PlaylistMixin:
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

    def get_track_duration_seconds(self, file_path):
        if file_path in self.duration_cache:
            return self.duration_cache[file_path]

        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            cached = self.audio_cache[file_path]
            seconds = cached['duration_samples'] / cached['samplerate']
            self.set_cached_duration(file_path, seconds)
            return seconds

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
            self.playlist_total_time_label.setText('-00:00:00')
            self.apply_playlist_time_color(0)
            return

        total_seconds = 0.0
        active_context = self.vu_playing or self.playback_end_mode == 'paused'
        start_index = self.current_index if (active_context and self.current_index >= 0) else 0

        for idx in range(start_index, len(self.playlist)):
            file_path = self.playlist[idx]
            if (
                active_context
                and idx == self.current_index
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

    def get_track_duration_label(self, file_path):
        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            cached = self.audio_cache[file_path]
            return self.format_duration_label(cached['duration_samples'] / cached['samplerate'])

        try:
            info = sf.info(file_path)
            return self.format_duration_label(info.duration)
        except Exception:
            return '--:--:--'

    def get_playlist_display_name(self, file_path):
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
        xml_path, _ = QFileDialog.getOpenFileName(self, 'Open Playlist', '', 'XML Files (*.xml)')
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
                if os.path.exists(track_path):
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
        self.time_label.setText('-00:00')
        self.update_playlist_total_display()
        self.update_window_title()
        print('Created new empty playlist')

    def save_playlist_xml(self):
        if not self.playlist:
            print('Playlist is empty - nothing to save')
            return

        save_path, _ = QFileDialog.getSaveFileName(self, 'Save Playlist', '', 'XML Files (*.xml)')
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

    def toggle_edit_mode(self, enabled):
        self.up_button.setVisible(enabled)
        self.down_button.setVisible(enabled)
        self.edit_button.setText('Done' if enabled else 'Edit')

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
            default_open_dir = os.path.join(os.path.expanduser('~'), 'Music')
            if not os.path.isdir(default_open_dir):
                default_open_dir = os.path.expanduser('~')
            files, _ = QFileDialog.getOpenFileNames(
                self,
                'Select Audio Files',
                default_open_dir,
                'Audio Files (*.wav *.flac *.mp3)',
            )
            if files:
                self.playlist.extend(files)
                self.refresh_playlist_widget(select_index=len(self.playlist) - len(files))
                for file_path in files:
                    self.add_recent_item('audio', file_path)
                print(f"Loaded {len(files)} files: {[os.path.basename(f) for f in files]}")
                self.set_busy(True)
                try:
                    for idx, file_path in enumerate(files):
                        self.cache_audio_info(file_path, idx)
                finally:
                    self.set_busy(False)
            else:
                print('No files selected')
        except Exception as e:
            print(f"Error loading files: {e}")
            QMessageBox.warning(self, 'Add Files', f"Could not load selected files:\n{e}")

    def play_next_track(self):
        if not self.playlist:
            print('Playlist is empty')
            return

        if self.current_index < 0:
            next_index = 0
        else:
            next_index = self.current_index + 1

        if next_index >= len(self.playlist):
            print('Already at the last track')
            return

        self.playlist_widget.selectRow(next_index)
        self.select_track(next_index, 0)

    def play_previous_track(self):
        if not self.playlist:
            print('Playlist is empty')
            return

        if self.current_index <= 0:
            prev_index = 0
        else:
            prev_index = self.current_index - 1

        self.playlist_widget.selectRow(prev_index)
        self.select_track(prev_index, 0)

    def select_track(self, row, column=0):
        self.update_preview_for_row(row, set_active_track=True)
        self.on_play_requested()
