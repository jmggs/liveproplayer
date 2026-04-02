import os
import sys
import numpy as np

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


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


class GuiMixin:
    def on_delete_selected_track(self):
        row = self.playlist_widget.currentRow()
        if 0 <= row < len(self.playlist):
            del self.playlist[row]
            self.refresh_playlist_widget(select_index=min(row, len(self.playlist)-1) if self.playlist else None)
    def resource_path(self, filename):
        package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        base_dir = getattr(sys, '_MEIPASS', package_root)
        return os.path.join(base_dir, filename)

    def apply_app_icon(self):
        for candidate in ('liveproplayer.ico', 'liveproplayer.png', 'liveproplayer_logo.png'):
            icon_path = self.resource_path(candidate)
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                return

    def update_window_title(self):
        base_title = 'Live Pro Player'
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

    def setup_shortcuts(self):
        # Atalho para tecla N: Next
        self.shortcut_next = QAction(self)
        self.shortcut_next.setShortcut(QKeySequence(Qt.Key_N))
        self.shortcut_next.triggered.connect(self.on_next_requested)
        self.addAction(self.shortcut_next)
        self.shortcut_toggle_play_pause = QAction(self)
        self.shortcut_toggle_play_pause.setShortcut(QKeySequence(Qt.Key_Space))
        self.shortcut_toggle_play_pause.triggered.connect(self.on_toggle_play_pause_requested)
        self.addAction(self.shortcut_toggle_play_pause)

        self.shortcut_play_selected_return = QAction(self)
        self.shortcut_play_selected_return.setShortcut(QKeySequence(Qt.Key_Return))
        self.shortcut_play_selected_return.triggered.connect(self.on_play_selected_requested)
        self.addAction(self.shortcut_play_selected_return)

        self.shortcut_play_selected_enter = QAction(self)
        self.shortcut_play_selected_enter.setShortcut(QKeySequence(Qt.Key_Enter))
        self.shortcut_play_selected_enter.triggered.connect(self.on_play_selected_requested)
        self.addAction(self.shortcut_play_selected_enter)

        # Atalho para tecla C: voltar ao início sem dar play
        self.shortcut_rewind_to_start = QAction(self)
        self.shortcut_rewind_to_start.setShortcut(QKeySequence(Qt.Key_C))
        self.shortcut_rewind_to_start.triggered.connect(self.on_rewind_to_start_requested)
        self.addAction(self.shortcut_rewind_to_start)

    def on_rewind_to_start_requested(self):
        # Volta a faixa atual ao início, sem dar play
        if hasattr(self, 'vu_playing') and self.vu_playing:
            # Se estiver a tocar, apenas pausa e volta ao início
            self.pause_audio()
        if hasattr(self, 'vu_pos'):
            self.vu_pos = 0
        if hasattr(self, 'vu_timer'):
            self.vu_timer.stop()
        if hasattr(self, 'vu_start_time'):
            self.vu_start_time = None
        if hasattr(self, 'update_time_display') and hasattr(self, 'total_duration') and hasattr(self, 'vu_samplerate'):
            self.update_time_display(self.total_duration, self.total_duration, self.vu_samplerate)
        if hasattr(self, 'update_waveform_cursor') and hasattr(self, 'total_duration'):
            self.update_waveform_cursor(0)
        if hasattr(self, 'show_vu_meter_stereo'):
            # Limpa o VU (mostra vazio)
            self.show_vu_meter_stereo(-60, -60)
        if hasattr(self, 'update_transport_button_state'):
            self.update_transport_button_state('paused')

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


    def setup_menu(self):
        # File menu
        file_menu = self.menuBar().addMenu('File')
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.add_files)
        file_menu.addAction(open_action)

        new_playlist_action = QAction('New Playlist', self)
        new_playlist_action.triggered.connect(self.new_playlist)
        file_menu.addAction(new_playlist_action)

        open_xml_action = QAction('Open Playlist (XML)', self)
        open_xml_action.triggered.connect(self.open_playlist_xml)
        file_menu.addAction(open_xml_action)

        save_action = QAction('Save Playlist (XML)', self)
        save_action.triggered.connect(self.save_playlist_xml)
        file_menu.addAction(save_action)

        self.recent_menu = file_menu.addMenu('Open Recent')
        self.refresh_recent_menu()

        file_menu.addSeparator()
        close_action = QAction('Close', self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        # Settings menu
        settings_menu = self.menuBar().addMenu('Settings')
        audio_interface_action = QAction('Audio Interface...', self)
        audio_interface_action.triggered.connect(self.on_select_audio_interface_requested)
        settings_menu.addAction(audio_interface_action)

        settings_menu.addSeparator()
        self.remote_toggle_action = QAction('Enable Remote Control', self)
        self.remote_toggle_action.setCheckable(True)
        self.remote_toggle_action.toggled.connect(self.toggle_remote_control)
        settings_menu.addAction(self.remote_toggle_action)

        self.remote_port_action = QAction('', self)
        self.update_remote_port_action_label()
        self.remote_port_action.triggered.connect(self.select_remote_port)
        settings_menu.addAction(self.remote_port_action)

        self.remote_toggle_action.blockSignals(True)
        self.remote_toggle_action.setChecked(self.remote_enabled)
        self.remote_toggle_action.blockSignals(False)
        if self.remote_enabled:
            self.toggle_remote_control(True)

        # Help direct action (not a menu)
        help_action = QAction('Help', self)
        help_action.triggered.connect(self.show_help_dialog)
        self.menuBar().addAction(help_action)

    def show_help_dialog(self):
        from PyQt5.QtWidgets import QLabel, QVBoxLayout, QDialog, QPushButton
        from PyQt5.QtCore import Qt
        dialog = QDialog(self)
        dialog.setWindowTitle('LiveProPlayer Help')
        layout = QVBoxLayout(dialog)

        version_label = QLabel('LiveProPlayer v0.4.2')
        version_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(version_label)

        github_label = QLabel('<a href="https://github.com/jmggs/liveproplayer/">GitHub Repository</a>')
        github_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        github_label.setOpenExternalLinks(True)
        github_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(github_label)

        shortcuts = QLabel(
            'Keyboard Shortcuts:<br>'
            '&nbsp;&nbsp;Space: Play/Pause<br>'
            '&nbsp;&nbsp;Enter/Return: Play selected track<br>'
            '&nbsp;&nbsp;C: Cue (rewind to start without playing)<br>'
            '&nbsp;&nbsp;N: Next track<br>'
            '&nbsp;&nbsp;Up/Down: Move selection in playlist<br>'
        )
        shortcuts.setAlignment(Qt.AlignLeft)
        layout.addWidget(shortcuts)

        endpoints = QLabel(
            'HTTP Endpoints:<br>'
            '&nbsp;&nbsp;/play, /pause, /stop, /next, /cue, /up, /down<br><br>'
            'Example: http://&lt;ip&gt;:8000/cue<br>'
        )
        endpoints.setAlignment(Qt.AlignLeft)
        layout.addWidget(endpoints)

        ok_button = QPushButton('OK')
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)

        dialog.setLayout(layout)
        dialog.exec_()

    def transport_button_style(self, bg_color, text_color, border_color):
        return (
            'font-size: 24px; min-width: 120px; min-height: 60px; '
            f'background-color: {bg_color}; color: {text_color}; border: 2px solid {border_color};'
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
        # Cue: restore to normal style; pressed/released flash connected once in init_ui
        if hasattr(self, 'cue_button'):
            self.cue_button.setStyleSheet(self._cue_style_normal)

    def render_waveform_pixmap(self, data, samplerate):
        width = 1200
        height = 190
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.black)

        if data.ndim == 2:
            mono_data = data.mean(axis=1)
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

        stride = max(1, int((len(mono_data) + usable_width - 1) / usable_width))
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
            seg_min = float(seg.min())
            seg_max = float(seg.max())
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

    def show_vu_meter_stereo(self, vu_left, vu_right):
        self.current_vu_left = vu_left
        self.current_vu_right = vu_right
        min_db = -60
        max_db = 0
        if not hasattr(self, 'vu_label') or self.vu_label is None:
            return
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

    def init_ui(self):
        self.setup_vu_timer()
        self.setup_menu()
        main_layout = QVBoxLayout()
        self.playlist_widget = PlaylistTable()
        self.playlist_widget.setColumnCount(3)
        self.playlist_widget.setHorizontalHeaderLabels(['#', 'File', 'Duration'])
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
        self.play_button = QPushButton('Play')
        # Dividir botão Pause em Cue (esquerda) e Pause (direita), mantendo proporção e espaçamento igual aos outros
        self.cue_pause_widget = QWidget()
        self.cue_pause_layout = QHBoxLayout()
        self.cue_pause_layout.setContentsMargins(0, 0, 0, 0)
        self.cue_pause_layout.setSpacing(0)
        self.cue_button = QPushButton('Cue')
        self.pause_button = QPushButton('Pause')
        # Manter tamanhos originais, apenas corrigir espaçamento entre Cue e Pause
        cue_pause_style = 'font-size: 24px; min-width: 60px; min-height: 60px; background-color: #444; color: white; border: 2px solid #222; border-radius: 0px;'
        self.cue_button.setStyleSheet(cue_pause_style)
        self.pause_button.setStyleSheet(cue_pause_style)
        self.cue_button.setFixedHeight(60)
        self.pause_button.setFixedHeight(60)
        self.cue_pause_layout.addWidget(self.cue_button)
        self.cue_pause_layout.addSpacing(16)
        self.cue_pause_layout.addWidget(self.pause_button)
        self.cue_pause_widget.setLayout(self.cue_pause_layout)
        self.stop_button = QPushButton('Stop')
        self.next_button = QPushButton('Next')
        self.next_button.setStyleSheet('font-size: 24px; min-width: 120px; min-height: 60px; background-color: #444; color: white; border: 2px solid #222;')
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.cue_pause_widget)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.next_button)
        controls_layout.setSpacing(16)
        self.cue_button.clicked.connect(self.on_rewind_to_start_requested)
        self.pause_button.clicked.connect(self.on_pause_requested)
        self.stop_button.clicked.connect(self.on_stop_requested)

        # Cue flash styles — defined once here, reused by update_transport_button_state
        self._cue_style_normal = (
            'font-size: 24px; min-width: 60px; min-height: 60px; '
            'background-color: #4d2a0a; color: #cccccc; '
            'border: 2px solid #332006; border-radius: 0px;'
        )
        self._cue_style_active = (
            'font-size: 24px; min-width: 60px; min-height: 60px; '
            'background-color: #ff9900; color: black; '
            'border: 2px solid #cc7a00; border-radius: 0px;'
        )
        self.cue_button.pressed.connect(
            lambda: self.cue_button.setStyleSheet(self._cue_style_active)
        )
        self.cue_button.released.connect(
            lambda: self.cue_button.setStyleSheet(self._cue_style_normal)
        )
        main_layout.addLayout(controls_layout)

        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(16)

        # ...removed silence checkbox...

        self.continue_checkbox = QCheckBox('Single')
        self.continue_checkbox.setChecked(False)
        self.continue_checkbox.toggled.connect(self.update_continue_mode_label)
        options_layout.addWidget(self.continue_checkbox)

        self.seek_checkbox = QCheckBox('Seek')
        self.seek_checkbox.setChecked(False)
        options_layout.addWidget(self.seek_checkbox)

        self.edit_button = QPushButton('Edit')
        self.edit_button.setCheckable(True)
        self.edit_button.setStyleSheet('font-size: 14px; min-width: 56px; min-height: 30px; background-color: #444; color: white; border: 1px solid #222;')
        options_layout.addWidget(self.edit_button)

        self.up_button = QPushButton('Up')
        self.down_button = QPushButton('Down')
        self.up_button.setStyleSheet('font-size: 13px; min-width: 44px; min-height: 28px; background-color: #444; color: white; border: 1px solid #222;')
        self.down_button.setStyleSheet('font-size: 13px; min-width: 52px; min-height: 28px; background-color: #444; color: white; border: 1px solid #222;')
        self.up_button.setVisible(False)
        self.down_button.setVisible(False)
        options_layout.addWidget(self.up_button)
        options_layout.addWidget(self.down_button)
        self.delete_button = QPushButton('Delete')
        self.delete_button.setStyleSheet('font-size: 13px; min-width: 60px; min-height: 28px; background-color: #a22; color: white; border: 1px solid #222;')
        self.delete_button.setVisible(False)
        self.delete_button.clicked.connect(self.on_delete_selected_track)
        options_layout.addWidget(self.delete_button)
        options_layout.addStretch(1)
        main_layout.addLayout(options_layout)

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(0)
        self.vu_label = QLabel()
        self.vu_label.setFixedHeight(80)
        self.vu_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_bar_layout.addWidget(self.vu_label, 1)

        self.time_label = QLabel('-00:00')
        self.time_label.setStyleSheet('font-size: 48px; color: #1aff1a; font-weight: bold; background-color: transparent;')
        self.time_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.track_remaining_label = QLabel('Track Remaining')
        self.track_remaining_label.setStyleSheet('font-size: 14px; color: #b8ffb8; font-weight: 600; background-color: transparent;')
        self.track_remaining_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.playlist_total_title_label = QLabel('Playlist Total')
        self.playlist_total_title_label.setStyleSheet('font-size: 13px; color: #b8ffb8; font-weight: 600; background-color: transparent;')
        self.playlist_total_title_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        self.playlist_total_time_label = QLabel('-00:00:00')
        self.playlist_total_time_label.setStyleSheet('font-size: 24px; color: #1aff1a; font-weight: bold; background-color: transparent;')
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

        self.show_vu_meter_stereo(-60, -60)

        self.waveform_label = ClickableWaveformLabel()
        self.waveform_label.setFixedHeight(190)
        self.waveform_label.setScaledContents(True)
        self.waveform_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.waveform_label.clicked.connect(self.on_waveform_clicked_requested)
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

        self.next_button.clicked.connect(self.on_next_requested)
        self.edit_button.toggled.connect(self.on_edit_mode_toggled)
        self.up_button.clicked.connect(lambda: self.on_move_selected_track_requested(-1))
        self.down_button.clicked.connect(lambda: self.on_move_selected_track_requested(1))
        self.play_button.clicked.connect(self.on_play_requested)
        # Atalhos já configurados em setup_shortcuts()
        # self.pause_button e self.cue_button já conectados acima
        self.playlist_widget.cellDoubleClicked.connect(self.on_track_activated)
        self.setup_shortcuts()
        self.sync_waveform_width_with_vu()
        QTimer.singleShot(0, self.refresh_top_bar_layout)
        self.update_transport_button_state('stopped')
        self.update_playlist_total_display()

    def update_continue_mode_label(self, enabled):
        self.continue_checkbox.setText('Continue' if enabled else 'Single')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'vu_label') and self.vu_label is not None:
            self.show_vu_meter_stereo(self.current_vu_left, self.current_vu_right)
        self.sync_waveform_width_with_vu()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.startup_layout_fixed:
            QTimer.singleShot(0, self.refresh_top_bar_layout)
            self.startup_layout_fixed = True

    def refresh_top_bar_layout(self):
        self.sync_waveform_width_with_vu()
        self.show_vu_meter_stereo(self.current_vu_left, self.current_vu_right)

    def sync_waveform_width_with_vu(self):
        if hasattr(self, 'right_track_container') and hasattr(self, 'waveform_right_panel'):
            right_width = self.right_track_container.width()
            width_value = max(120, right_width)
            self.right_track_container.setFixedWidth(width_value)
            self.waveform_right_panel.setFixedWidth(width_value)
