# How to build for Windows

## Prerequisites

| Tool | Version | Link |
|---|---|---|
| Python | 3.11 or 3.12 (64-bit) | https://python.org/downloads |
| Inno Setup *(optional)* | 6.x | https://jrsoftware.org/isinfo.php |

> **Important:** During Python installation, enable **"Add Python to PATH"**.

---

## One-step build

Double-click **`build_scripts\windows\build.bat`**.

The script automatically:
1. Checks whether Python is installed
2. Installs all required dependencies (`pyinstaller`, `pyqt5`, `numpy`, etc.)
3. Cleans previous builds
4. Builds the app with PyInstaller using `LiveProPlayer.spec`
5. Generates the `.exe` installer with Inno Setup (if installed)

---

## Output

```
dist/
├── LiveProPlayer/
│   ├── LiveProPlayer.exe       ← main executable
│   ├── Qt5Core.dll
│   ├── Qt5Gui.dll
│   └── ...                     ← required DLLs
└── installer/
    └── LiveProPlayer-setup-v0.4.3.exe   ← installer (if Inno Setup is available)
```

The `dist\LiveProPlayer\` folder is self-contained and can be copied to any Windows PC without installing Python.

---

## Manual build (alternative to `build_scripts\windows\build.bat`)

```bat
python -m pip install pyinstaller pyqt5 numpy soundfile sounddevice
python -m PyInstaller --noconfirm --clean LiveProPlayer.spec
```

---

## Troubleshooting

**Error: "Python not found"**
→ Reinstall Python and enable "Add Python to PATH"

**PyInstaller error with `sounddevice` or `soundfile`**
→ Run `python -m pip install --upgrade sounddevice soundfile` and try again

**The `.exe` opens and closes immediately**
→ Run it from the command line to inspect the error:
```bat
cd dist\LiveProPlayer
LiveProPlayer.exe
```

**A black console window appears next to the app**
→ The spec already uses `console=False`. If it still appears, make sure you built with `LiveProPlayer.spec` and not a direct command line invocation.
