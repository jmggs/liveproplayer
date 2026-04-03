from enum import Enum

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QInputDialog, QMainWindow, QMessageBox

from .api import ApiMixin
from .audio_engine import AudioEngineMixin
from modular.gui import GuiMixin
from .playlist import PlaylistMixin
from .settings import SettingsMixin


class PlayerState(str, Enum):
    STOPPED = 'STOPPED'
    PLAYING = 'PLAYING'
    PAUSED = 'PAUSED'


class AudioPlayer(
    ApiMixin,
    SettingsMixin,
    PlaylistMixin,
    AudioEngineMixin,
    GuiMixin,
    QMainWindow,
):
    remote_command_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.apply_app_icon()
        self.setWindowTitle('Live Pro Player')
        self.setGeometry(100, 100, 1280, 820)
        self.setMinimumSize(1100, 720)
        self.playlist = []
        self.current_index = -1
        self.audio_stream = None
        self.total_duration = 0
        self.current_vu_left = -60
        self.current_vu_right = -60
        self.state = PlayerState.STOPPED
        self.remote_command_requested.connect(self.execute_remote_command, Qt.QueuedConnection)
        self.init_ui()
        self.update_window_title()

    def play(self):
        row = self.playlist_widget.currentRow() if hasattr(self, 'playlist_widget') else -1
        if row < 0 and self.playlist:
            row = 0
            self.playlist_widget.selectRow(row)

        if row < 0:
            return

        if self.current_index != row or self.current_file_path != self.playlist[row]:
            self.select_track(row, 0)
        else:
            # Se cue_pos estiver definida, restaurar dela
            if hasattr(self, 'cue_pos') and self.cue_pos is not None:
                self.vu_pos = self.cue_pos
            self.play_audio()
        self.state = PlayerState.PLAYING

    def pause(self):
        self.pause_audio()
        self.state = PlayerState.PAUSED

    def stop(self):
        self.stop_audio()
        self.state = PlayerState.STOPPED

    def next(self):
        self.play_next_track()
        if self.playlist:
            self.state = PlayerState.PLAYING

    def closeEvent(self, event):
        self.save_app_settings()
        if self.vu_playing:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle('Playback Active')
            msg_box.setText(
                'Music is playing!\n\n'
                'Do you want to lose your job and ruin your carreer?'
            )
            stop_and_close_btn = msg_box.addButton('Yes and Close', QMessageBox.DestructiveRole)
            msg_box.addButton('Cancel', QMessageBox.RejectRole)
            msg_box.exec_()

            if msg_box.clickedButton() is not stop_and_close_btn:
                event.ignore()
                return

        self.stop()
        self.stop_remote_server()
        event.accept()

    def on_toggle_play_pause_requested(self):
        if self.state == PlayerState.PLAYING:
            self.pause()
        else:
            self.play()

    def on_play_selected_requested(self):
        self.play()

    def on_play_requested(self):
        self.play()

    def on_pause_requested(self):
        self.pause()

    def on_stop_requested(self):
        self.stop()

    def on_next_requested(self):
        self.next()

    def on_track_activated(self, row, column=0):
        self.select_track(row, column)

    def on_waveform_clicked_requested(self, x, y):
        # O print de debug deve vir após a definição de target_sample
        if not hasattr(self, 'seek_checkbox') or not self.seek_checkbox.isChecked():
            return

        if not self.playlist:
            return

        row = self.current_index
        if row < 0:
            row = self.playlist_widget.currentRow()
        if row < 0 or row >= len(self.playlist):
            return


        # Se não há áudio carregado, força carregamento
        label_width = max(1, self.waveform_label.width())
        left = self.waveform_left_padding
        right = self.waveform_right_padding
        usable_width = max(1, label_width - left - right)
        click_x = max(left, min(left + usable_width - 1, int(x)))
        ratio = (click_x - left) / max(1, usable_width - 1)
        target_sample = int(ratio * max(0, self.total_duration - 1))

        # ...debug removido...

        # Se não há áudio carregado, força carregamento, mas preserva o target_sample
        if self.current_index != row or self.current_file_path != self.playlist[row] or self.vu_data is None:
            # Sinaliza para o preview não zerar vu_pos
            self._preserve_vu_pos = True
            self.vu_pos = target_sample
            self.update_preview_for_row(row, set_active_track=True)
            # Após carregar, se ainda não há áudio válido, aborta
            if self.vu_data is None or self.vu_samplerate is None or self.total_duration <= 0:
                return
        else:
            self.seek_to_sample(target_sample)
        # Atualiza a linha vermelha de posição mesmo sem tocar
        if hasattr(self, 'update_waveform_cursor'):
            self.update_waveform_cursor(self.vu_pos)
        if not self.vu_playing:
            self.play_audio()

    def on_edit_mode_toggled(self, enabled):
        self.toggle_edit_mode(enabled)

    def on_move_selected_track_requested(self, offset):
        self.move_selected_track(offset)

    def on_select_audio_interface_requested(self):
        try:
            output_devices = self.get_output_devices()
        except Exception as e:
            QMessageBox.warning(self, 'Audio Interface', f"Unable to list audio interfaces:\n{e}")
            return

        if not output_devices:
            QMessageBox.information(self, 'Audio Interface', 'No output audio interfaces found.')
            return

        options = ['System Default'] + [label for _, label in output_devices]
        current_index = 0
        if self.output_device is not None:
            for idx, (device_id, _) in enumerate(output_devices, start=1):
                if device_id == self.output_device:
                    current_index = idx
                    break

        selected, ok = QInputDialog.getItem(
            self,
            'Select Audio Interface',
            'Output device:',
            options,
            current_index,
            False,
        )
        if not ok:
            return

        if selected == 'System Default':
            self.set_output_device(None)
            print('Audio interface set to System Default')
            self.restart_output_stream_at_current_position()
            return

        for device_id, label in output_devices:
            if label == selected:
                self.set_output_device(device_id)
                print(f"Audio interface set to: {label}")
                self.restart_output_stream_at_current_position()
                break

    def should_continue_playback(self):
        return hasattr(self, 'continue_checkbox') and self.continue_checkbox.isChecked()

    def on_playback_finished(self, session_id=None):
        super().on_playback_finished(session_id)
        if not self.vu_playing:
            self.state = PlayerState.STOPPED

    def on_audio_track_loaded(self, file_path, resume_sample):
        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            self.waveform_label.setPixmap(self.audio_cache[file_path]['waveform_pixmap'])
            self.update_waveform_cursor(resume_sample)

