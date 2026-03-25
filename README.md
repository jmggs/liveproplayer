# Cross-Platform Audio Player

A desktop app for Windows, Mac, and Linux to play sound files with playlist support, VU meter, waveform visualization, and silence removal options.

Current version: **v0.4.1**

# Live Pro Player

A Cross-Platform Audio Player, desktop app for Windows, Mac, and Linux to play sound files with playlist support, VU meter and waveform visualization.

<img width="640" height="437" alt="{0F8EFC22-A30C-4683-B880-681A3E9A4B09}" src="https://github.com/user-attachments/assets/36b8d53a-c397-4c39-8610-ad65eb5f7f76" />

## Version and Download
Download: 
https://github.com/jmggs/liveproplayer/releases

## Features
- Play/pause/stop sound files
- Playlist management
- Stereo VU meter with AES/EBU compliant color scheme
- Waveform visualization with black background and play position indicator
- Large countdown timer in upper right corner (hh:mm:ss format for long tracks)
<<<<<<< HEAD
- Remove silence at beginning/end of tracks
- Dark theme interface
- **NEW**: Automatic demo audio generation when file loading fails
=======
- Dark theme interface
>>>>>>> 9dc01fbab386c8956dd7937a71fdf5a4adfafd5d
- **NEW**: Robust error handling with debug messages
- **PERFORMANCE**: Optimized waveform cursor updates (10x less frequent) for smooth playback
- **SYNC**: Real-time audio position tracking for accurate VU meter and time display

## Requirements
- Python 3.6+
- PyQt5
- NumPy
- SoundFile
- SoundDevice
- Matplotlib

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python main.py
```

2. Click "Add Files" to load audio files (.wav, .flac, .mp3)
3. Select a track from the playlist and click "Play"
4. Use Play/Pause/Stop controls as needed
5. The waveform shows the audio with a red line indicating current position
6. The VU meter displays left/right channel levels
7. The timer in the upper right shows remaining time

## Troubleshooting

### If the application doesn't show waveform/VU meter:

1. **Check your display environment**: The application requires a graphical desktop environment. If you're running on a server or in a container without X11/display, use:
   ```bash
   export DISPLAY=:0  # Linux/Mac
   # or for Windows, ensure you have a display
   ```

2. **Font issues**: If you see font warnings, they are usually harmless but you can install system fonts.

3. **File loading issues**: If "Add Files" doesn't work, the application will automatically create a test audio file as fallback.

4. **Audio playback issues**: Ensure your system has audio output configured correctly.

### Debug Mode

The application now includes debug messages. Check the console/terminal output for messages like:
- "Loaded X files: [filenames]"
- "Audio loaded: X samples at Y Hz"
- "Waveform updated successfully"
- "VU meter displayed"
- "Demo audio created successfully"

### Common Issues Fixed

- **"name 'os' is not defined"**: Fixed by adding proper imports
- **File system errors**: Now uses in-memory demo audio when file operations fail
- **QFileDialog issues**: Automatic fallback to demo audio
- **Audio loading errors**: Graceful error handling with alternatives
- **"TypeError: unsupported operand type(s) for /: 'int' and 'NoneType'"**: Fixed samplerate initialization order
- **Performance issues**: Optimized waveform cursor updates (10x less frequent)
- **Audio sync problems**: Real-time position tracking instead of estimation

## Performance Notes

- **Waveform cursor updates**: Reduced from every 50ms to every 500ms for 10x better performance
- **Audio sync**: Uses actual playback time instead of estimated position
- **Time display**: Smart formatting (mm:ss for short tracks, hh:mm:ss for long tracks)
- **Memory usage**: Demo audio stored in RAM, no disk I/O during playback

### Alternative Execution

If you have display issues, try:
```bash
# Linux/Mac
export QT_QPA_PLATFORM=xcb
python main.py

# Or force software rendering
export QT_QPA_PLATFORM=offscreen
python main.py
```

## Supported Formats
- WAV
- FLAC
- MP3 (requires additional codecs on some systems)

## Controls
- **Add Files**: Load audio files into playlist
- **Play**: Start playback of selected track
- **Pause**: Pause current playback
- **Stop**: Stop playback and reset position
- **Remove Silence**: Trim silence from start/end of tracks

## Tech Stack
- Python 3.x
- PyQt5 or PySide6
- numpy, soundfile, pyaudio, matplotlib (for waveform)

## How to Run
1. Install Python 3.x
2. Install dependencies:
   ```bash
   pip install pyqt5 numpy soundfile pyaudio matplotlib
   ```
3. Run the app:
   ```bash
   python main.py
   ```

## To Do
- Implement main UI
- Add playlist functionality
- Integrate VU meter and waveform
- Add silence removal option

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
- `v0.4.0`: bugfixes, melhorias e integração HTTP com simulação real de teclas

## Windows Installer (.exe)

This project includes an installer pipeline in the `installer/` folder.

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
powershell -ExecutionPolicy Bypass -File .\installer\build_windows.ps1 -Version 0.4.0
```

Generated outputs:

- App bundle: `dist/LiveProPlayer/`
- Installer: `dist/installer/LiveProPlayer-setup-v0.4.0.exe`

### Manual build (optional)

If you prefer manual steps:

```bash
pyinstaller --noconfirm --clean --windowed --name LiveProPlayer main.py
```

Then compile the Inno Setup script:

```powershell
iscc /DMyAppVersion=0.4.0 .\installer\liveproplayer.iss
```
