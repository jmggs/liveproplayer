import sys
import threading
import traceback
from dataclasses import dataclass, field

from PyQt5.QtWidgets import QApplication, QMessageBox

from .controller import AudioPlayer


@dataclass
class BootstrapResult:
    data: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def store(self, name, payload):
        with self.lock:
            self.data[name] = payload

    def store_error(self, name, exc):
        with self.lock:
            self.errors.append((name, str(exc), traceback.format_exc()))


def _init_settings_component():
    from . import settings

    return {
        'module': settings.__name__,
        'ready': True,
    }


def _init_audio_engine_component():
    from . import audio_engine
    import sounddevice as sd

    try:
        device_count = len(sd.query_devices())
    except Exception:
        device_count = 0

    return {
        'module': audio_engine.__name__,
        'detected_output_devices': device_count,
        'ready': True,
    }


def _init_controller_component():
    from . import controller

    return {
        'module': controller.__name__,
        'states': [state.value for state in controller.PlayerState],
        'ready': True,
    }


def _init_api_component():
    from . import api

    return {
        'module': api.__name__,
        'ready': True,
    }


def _run_component(name, func, bootstrap):
    try:
        bootstrap.store(name, func())
    except Exception as exc:
        bootstrap.store_error(name, exc)


def bootstrap_components():
    bootstrap = BootstrapResult()
    tasks = [
        ('settings', _init_settings_component),
        ('audio_engine', _init_audio_engine_component),
        ('controller', _init_controller_component),
        ('api_server', _init_api_component),
    ]

    threads = []
    for name, func in tasks:
        thread = threading.Thread(
            target=_run_component,
            args=(name, func, bootstrap),
            daemon=True,
            name=f'{name}-init-thread',
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return bootstrap


def run():
    # Initialize non-GUI components in background threads.
    bootstrap = bootstrap_components()

    # GUI must stay on the main thread.
    app = QApplication(sys.argv)
    window = AudioPlayer()

    # Ensure API server runtime uses a dedicated thread when enabled.
    if window.remote_enabled and window.remote_server is None:
        threading.Thread(
            target=window.start_remote_server,
            daemon=True,
            name='api-runtime-thread',
        ).start()

    if bootstrap.errors:
        for name, message, _tb in bootstrap.errors:
            print(f'Bootstrap error in {name}: {message}')

    window.show()
    return app.exec_()


if __name__ == '__main__':
    try:
        sys.exit(run())
    except Exception as e:
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle('Erro ao iniciar o programa')
        error_box.setText(f'Erro: {str(e)}')
        error_box.exec_()
