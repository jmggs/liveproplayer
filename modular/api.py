import json
import socket
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PyQt5.QtWidgets import QMessageBox, QInputDialog


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


class ApiMixin:
    def update_remote_port_action_label(self):
        if hasattr(self, 'remote_port_action'):
            self.remote_port_action.setText(f"Remote Port ({self.remote_port})...")

    def get_local_ip(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
        except Exception:
            return '127.0.0.1'
        finally:
            if sock is not None:
                sock.close()

    def start_remote_server(self):
        if self.remote_server is not None:
            return True
        try:
            self.remote_server = RemoteControlHTTPServer(('0.0.0.0', self.remote_port), RemoteControlRequestHandler)
            self.remote_server.player = self
        except Exception as e:
            QMessageBox.warning(self, 'Remote Control', f"Unable to start remote server on port {self.remote_port}:\n{e}")
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
        print('Remote control disabled')

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
            'Remote Port',
            'HTTP port:',
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

    def execute_remote_command(self, command):
        if command == 'play':
            self.on_play_requested()
        elif command == 'pause':
            if self.vu_playing:
                self.on_pause_requested()
        elif command == 'stop':
            self.on_stop_requested()
        elif command == 'next':
            self.on_next_requested()
        elif command == 'previous':
            self.play_previous_track()
