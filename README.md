# Live Pro Player

A desktop audio player oriented to live playback, with playlist control, waveform preview, stereo VU metering, countdown timers, and optional HTTP remote control.

## Version

Current version: **v0.4.3**

## Verified capabilities

The items below were checked against the current codebase in `modular/*.py`.

- Load multiple audio files in `WAV`, `FLAC`, `MP3`, `AIFF`, and `AIF` formats
- Create a new playlist and open/save playlists as XML
- Manage the queue with `Edit`, `Up`, `Down`, and `Delete`
- Preview the selected track waveform before playback
- Click the waveform to seek when `Seek` mode is enabled
- Use `Play`, `Cue`, `Pause`, `Stop`, and `Next` from the main UI
- Switch between `Single` and `Continue` playback modes
- View a stereo VU meter plus remaining-time displays for the current track and total playlist
- Select the output audio interface from `Settings`
- Enable HTTP remote control with configurable port and endpoints `/play`, `/pause`, `/stop`, `/next`, `/previous`, `/cue`, `/up`, and `/down`
- Keep persistent app settings, recent files/playlists, and sidecar waveform cache for faster reloads
- Operate with a dark UI optimized for visibility during playback

## Requirements

- Python `3.9+` (`3.11` / `3.12` recommended on Windows)
- `PyQt5`
- `numpy`
- `soundfile`
- `sounddevice`

## Installation

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Basic usage

1. Open files from `File > Open`, or load an existing XML playlist.
2. Select a track in the playlist table.
3. Use `Play`, `Cue`, `Pause`, `Stop`, and `Next` as needed.
4. Enable `Seek` to allow click-to-jump on the waveform.
5. Enable `Continue` to keep advancing automatically through the playlist.
6. Use `Settings > Audio Interface...` to choose the output device.
7. Use `Settings > Enable Remote Control` to enable HTTP control.

## Keyboard shortcuts

- `Space`: play/pause
- `Enter` / `Return`: play selected track
- `C`: cue (rewind to start without playing)
- `N`: next track
- `Up` / `Down`: move playlist selection

## Remote control

When remote control is enabled, the player listens on the configured port (default `8000`) and exposes:

- `GET /play`
- `GET /pause`
- `GET /stop`
- `GET /next`
- `GET /previous`
- `GET /cue`
- `GET /up`
- `GET /down`

Example:

```text
http://<your-ip>:8000/cue
```

## Persistence and performance

- Saves output device, remote control state, and remote port in per-user app data
- Stores up to 8 recent audio files/playlists under `Open Recent`
- Generates sidecar cache files for waveform images and duration metadata
- Uses reduced waveform redraw frequency for smoother playback updates

## Troubleshooting

- **No audio output**: verify the system output and select the correct device in `Settings > Audio Interface...`
- **Remote control does not start**: change the HTTP port if it is already in use
- **A recent item does not open**: the file path may no longer exist and will be removed from the recent list
- **Installed build cannot write near the app folder**: settings and cache are automatically redirected to per-user app data

## Git Versioning Workflow

Use this workflow to keep changes organized and create clear versions.

### 1) Initialize repository (first time)

```bash
git init
git add .
git commit -m "chore: initial project snapshot"
```

### 2) Branch strategy

- `main`: stable code only
- `develop`: integration branch for upcoming release
- `feature/<name>`: new features (example: `feature/remote-http`)
- `fix/<name>`: bug fixes (example: `fix/playlist-reorder`)

Create and switch branches:

```bash
git checkout -b develop
git checkout -b feature/remote-http
```

### 3) Commit message convention

Use Conventional Commits:

- `feat:` new functionality
- `fix:` bug fix
- `refactor:` internal code change
- `docs:` documentation changes
- `chore:` maintenance/setup

Examples:

```bash
git commit -m "feat: add HTTP remote control endpoints"
git commit -m "fix: stabilize playlist reorder with edit mode"
git commit -m "docs: add git versioning workflow"
```

### 4) Daily flow

```bash
git status
git add .
git commit -m "feat: your change summary"
git checkout develop
git merge feature/your-branch
```

### 5) Release versioning (SemVer)

- `MAJOR` (`1.0.0`): breaking changes
- `MINOR` (`0.3.0`): new features, compatible
- `PATCH` (`0.3.1`): fixes only

Create release tags:

```bash
git checkout main
git merge develop
git tag -a v0.3.0 -m "Release v0.3.0"
```

### 6) Push to remote (GitHub/GitLab)

```bash
git remote add origin <your-repo-url>
git push -u origin main
git push -u origin develop
git push origin --tags
```


### 7) Version history

- `v0.1.0`: base player + playlist + waveform + VU
- `v0.2.0`: settings, recent files, UI improvements
- `v0.3.0`: HTTP remote control + configurable remote port
- `v0.4.3`: bug fixes, improvements, and HTTP integration with real key simulation

## Windows Installer (.exe)

This project includes a Windows build pipeline in the `build_scripts/windows/` folder.

### Prerequisites

- Python environment with dependencies installed
- PyInstaller
- Inno Setup 6

Install PyInstaller:

```bash
pip install pyinstaller
```

### Build installer

From the project root, run:


```powershell
powershell -ExecutionPolicy Bypass -File .\build_scripts\windows\build_windows.ps1 -Version 0.4.3
```

Generated outputs:

- App bundle: `dist/LiveProPlayer/`
- Installer: `dist/installer/LiveProPlayer-setup-v0.4.3.exe`

### Manual build (optional)

If you prefer manual steps:

```bash
pyinstaller --noconfirm --clean --windowed --name LiveProPlayer main.py
```

Then compile the Inno Setup script:

```powershell
iscc /DMyAppVersion=0.4.3 .\build_scripts\windows\liveproplayer.iss
```
