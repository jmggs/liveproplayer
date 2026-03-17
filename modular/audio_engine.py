import os
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from PyQt5.QtCore import QTimer


class AudioEngineMixin:
    def set_fade_durations(self, fade_in_ms=0, fade_out_ms=0):
        self.fade_in_ms = max(0, int(fade_in_ms))
        self.fade_out_ms = max(0, int(fade_out_ms))

    def get_output_devices(self):
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_hostapi = None
        try:
            default_hostapi = int(sd.default.hostapi)
        except Exception:
            default_hostapi = None

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

    def set_output_device(self, device_id=None):
        self.output_device = None if device_id is None else int(device_id)
        self.save_app_settings()

    def resolve_output_device_for_stream(self, samplerate, data):
        if self.output_device is None:
            return None

        channels = 1 if data.ndim == 1 else int(data.shape[1])
        try:
            sd.check_output_settings(
                device=int(self.output_device),
                samplerate=int(samplerate),
                channels=channels,
            )
            return int(self.output_device)
        except Exception as e:
            print(f"Selected output device is not available ({self.output_device}): {e}")
            self.output_device = None
            self.save_app_settings()
            return None

    def restart_output_stream_at_current_position(self):
        if not self.vu_playing or self.vu_data is None or self.vu_samplerate is None:
            return

        if self.vu_start_time is not None:
            current_pos = min(len(self.vu_data), int((time.time() - self.vu_start_time) * self.vu_samplerate))
        else:
            current_pos = min(len(self.vu_data), int(self.vu_pos))

        self.vu_pos = current_pos
        try:
            sd.stop()
            self.play_stream_realtime(self.vu_data, self.vu_samplerate, self.playback_session_id, current_pos)
            print('Audio interface applied to current playback')
        except Exception as e:
            print(f"Unable to apply output device during playback: {e}")
            self.playback_end_mode = 'paused'
            self.vu_playing = False
            self.vu_timer.stop()
            self.vu_start_time = None
            self.update_transport_button_state('paused')

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

        continue_enabled = self.should_continue_playback()
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
        self.vu_timer = QTimer()
        self.vu_timer.setInterval(50)
        self.vu_timer.timeout.connect(self.update_vu_meter)
        self.vu_data = None
        self.vu_samplerate = None
        self.vu_pos = 0
        self.vu_start_time = None
        self.vu_blocksize = 2048
        self.vu_playing = False
        self.waveform_update_interval = 0.5
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
        self.startup_layout_fixed = False
        self.is_reordering_playlist = False
        self.output_device = None
        self.remote_enabled = False
        self.remote_port = 8000
        self.remote_server = None
        self.remote_server_thread = None
        self.sidecar_dir = self.resolve_sidecar_dir()
        self.app_settings_path = os.path.join(self.sidecar_dir, 'app_settings.json')
        self.load_app_settings()
        self.recent_state_path = os.path.join(self.sidecar_dir, 'recent_items.json')
        self.recent_items = []
        self.load_recent_items()
        self.fade_in_ms = 0
        self.fade_out_ms = 0
        self.remove_silence_enabled = False

    def cache_audio_info(self, file_path, idx):
        """Cache waveform, duration, and VU info for file."""
        try:
            if self.try_load_sidecar_cache(file_path):
                print(f"Loaded sidecar cache for {file_path}")
                return

            data, samplerate = sf.read(file_path)
            duration_samples = len(data)
            self.set_cached_duration(file_path, duration_samples / samplerate)
            try:
                pixmap = self.render_waveform_pixmap(data, samplerate)
                if pixmap.isNull():
                    print(f"Failed to create pixmap for {file_path}")
                    return
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


    def apply_fades(self, data, samplerate):
        if data is None or len(data) == 0:
            return data

        processed = np.array(data, copy=True)
        fade_in_samples = max(0, int((self.fade_in_ms / 1000.0) * samplerate))
        fade_out_samples = max(0, int((self.fade_out_ms / 1000.0) * samplerate))
        length = len(processed)

        if fade_in_samples > 0:
            n = min(fade_in_samples, length)
            ramp = np.linspace(0.0, 1.0, n, endpoint=True)
            if processed.ndim == 1:
                processed[:n] *= ramp
            else:
                processed[:n] *= ramp[:, None]

        if fade_out_samples > 0:
            n = min(fade_out_samples, length)
            ramp = np.linspace(1.0, 0.0, n, endpoint=True)
            if processed.ndim == 1:
                processed[-n:] *= ramp
            else:
                processed[-n:] *= ramp[:, None]

        return processed

    def play_audio(self, remove_silence_enabled=None):
        if remove_silence_enabled is not None:
            self.remove_silence_enabled = bool(remove_silence_enabled)
        if self.current_index == -1 and self.playlist:
            self.current_index = 0
        if self.current_index < 0 or self.current_index >= len(self.playlist):
            print('No valid track selected')
            return

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
            data, samplerate = sf.read(file_path)
            print(f"Audio loaded: {len(data)} samples at {samplerate} Hz, shape: {data.shape}")
        except Exception as e:
            print(f"Error loading audio file: {e}")
            return

        if self.remove_silence_enabled:
            data = self.remove_silence(data)
            print('Silence removal applied')

        data = self.apply_fades(data, samplerate)

        if not hasattr(self, 'audio_cache') or file_path not in self.audio_cache:
            self.cache_audio_info(file_path, 0)

        resume_sample = 0
        if (
            self.playback_end_mode == 'paused'
            and self.current_file_path == file_path
            and 0 < self.vu_pos < len(data)
        ):
            resume_sample = self.vu_pos

        self.total_duration = len(data)
        self.vu_data = data
        self.vu_samplerate = samplerate
        remaining_from_start = max(0, self.total_duration - resume_sample)
        self.update_time_display(remaining_from_start, self.total_duration)
        self.last_waveform_update_time = 0

        if hasattr(self, 'audio_cache') and file_path in self.audio_cache:
            self.on_audio_track_loaded(file_path, resume_sample)

        self.vu_pos = resume_sample
        self.vu_playing = True
        self.vu_start_time = None
        self.playback_start_sample = resume_sample
        self.playback_end_mode = 'natural'
        self.playback_session_id += 1
        self.vu_timer.start()
        self.update_transport_button_state('playing')
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()

        print('Starting audio playback...')
        try:
            self.play_stream_realtime(data, samplerate, self.playback_session_id, resume_sample)
        except Exception as e:
            self.vu_playing = False
            self.vu_timer.stop()
            self.vu_start_time = None
            self.update_transport_button_state('stopped')
            self.apply_playing_row_highlight()
            print(f"Playback start failed: {e}")

    def play_stream_realtime(self, data, samplerate, session_id, start_sample=0):
        device = self.resolve_output_device_for_stream(samplerate, data)
        self.vu_start_time = time.time() - (start_sample / samplerate)
        sd.play(data[start_sample:], samplerate, blocking=False, device=device)

    def update_vu_meter(self):
        if not self.vu_playing or self.vu_data is None or self.vu_start_time is None:
            return

        elapsed_time = time.time() - self.vu_start_time
        current_pos = int(elapsed_time * self.vu_samplerate)

        current_pos = min(current_pos, len(self.vu_data))

        if current_pos >= len(self.vu_data):
            self.on_playback_finished(self.playback_session_id)
            return

        start = max(0, current_pos - self.vu_blocksize // 2)
        end = min(start + self.vu_blocksize, len(self.vu_data))
        if start < end:
            block = self.vu_data[start:end]
            vu_left, vu_right = self.calculate_vu_stereo(block)
            self.show_vu_meter_stereo(vu_left, vu_right)

        if elapsed_time - self.last_waveform_update_time >= self.waveform_update_interval:
            self.update_waveform_cursor(current_pos)
            self.last_waveform_update_time = elapsed_time

        remaining_samples = max(0, self.total_duration - current_pos)
        self.update_time_display(remaining_samples, self.total_duration, self.vu_samplerate)
        self.update_playlist_total_display()

        self.vu_pos = current_pos

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
        if hasattr(self, 'total_duration') and self.total_duration > 0:
            remaining_samples = self.total_duration - self.vu_pos
            self.update_time_display(remaining_samples, self.total_duration, self.vu_samplerate)
            self.update_waveform_cursor(self.vu_pos)

    def stop_audio(self):
        self.playback_end_mode = 'stopped'
        sd.stop()
        self.vu_playing = False
        self.vu_timer.stop()
        self.vu_start_time = None
        self.vu_pos = 0
        self.current_file_path = None
        self.update_transport_button_state('stopped')
        self.apply_playing_row_highlight()
        self.update_playlist_total_display()
        self.update_window_title()
        if hasattr(self, 'total_duration') and self.total_duration > 0:
            self.update_time_display(self.total_duration, self.total_duration, self.vu_samplerate)
            self.update_waveform_cursor(0)

    def seek_to_sample(self, target_sample):
        if self.vu_data is None or self.vu_samplerate is None or self.total_duration <= 0:
            return

        target_sample = int(max(0, min(target_sample, self.total_duration - 1)))
        self.vu_pos = target_sample
        self.playback_start_sample = target_sample
        remaining_samples = max(0, self.total_duration - target_sample)
        self.update_time_display(remaining_samples, self.total_duration, self.vu_samplerate)
        self.update_waveform_cursor(target_sample)
        self.update_playlist_total_display()

        if self.vu_playing:
            try:
                sd.stop()
                self.play_stream_realtime(self.vu_data, self.vu_samplerate, self.playback_session_id, target_sample)
            except Exception as e:
                print(f"Seek playback failed: {e}")
                self.playback_end_mode = 'paused'
                self.vu_playing = False
                self.vu_timer.stop()
        else:
            self.playback_end_mode = 'paused'

    def should_continue_playback(self):
        return False

    def on_audio_track_loaded(self, file_path, resume_sample):
        return

    def calculate_vu_stereo(self, data):
        if data.ndim == 1:
            rms = np.sqrt(np.mean(np.square(data)))
            vu = 20 * np.log10(rms) if rms > 0 else -float('inf')
            return vu, vu
        else:
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
            mask = np.max(abs_data, axis=1) > threshold
        if not np.any(mask):
            return data
        start = np.argmax(mask)
        end = len(mask) - np.argmax(mask[::-1])
        return data[start:end]
