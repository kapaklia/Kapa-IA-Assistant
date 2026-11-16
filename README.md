# Kapa IA Assistant

**v0.1.0 Alpha — Linux desktop assistant. Italian only.**

Type or speak an Italian request to control your Linux desktop. Kapa uses
**Groq** for AI interpretation and **Whisper Small** for local speech recognition.
Replies appear as text; there is no speech synthesis. This English README helps
people discover the project: it does not indicate English support in the app.

[Guida completa in italiano](README.it.md) · [Capabilities](COSA_SA_FARE.md) ·
[Changelog](CHANGELOG.md) · [Release notes](docs/RELEASE_v0.1.0-alpha.md)

> Licensed under **GNU GPLv3-only** (`GPL-3.0-only`); see [LICENSE](LICENSE).
> Local release candidate: all included asset origins are documented from maintainer declarations.
> See [third-party review](docs/THIRD_PARTY.md).

## Features

- Voice input on demand and typed requests, with written Italian responses.
- Local Whisper Small transcription; Groq handles AI requests. No local language model.
- Launch, close and check installed applications; search distribution repositories.
- Install a requested package or update Linux through a separate confirmation terminal.
  Nobara updates use `nobara-sync cli`.
- Volume and MPRIS media controls using `pactl` and `playerctl`.
- Google searches and YouTube searches in your browser; optional YouTube API for direct video lookup.
- Create, read, append, find, copy, move and rename files; clipboard and reminders.
  File deletion and emptying the trash are restricted to text mode.
- Screenshots through desktop tools; recordings and replay through GPU Screen Recorder or OBS.
- Desktop launcher, tray and desktop-dependent global shortcuts.

## Tested systems

Practical installation/use tests reported by the author:

| Distribution / desktop | Status |
| --- | --- |
| Nobara / KDE Plasma | Tested |
| Ubuntu / GNOME | Tested |
| Linux Mint / Cinnamon | Tested |
| Fedora | Not fully verified |
| Arch Linux | Not fully verified; no automatic system-package installer |

These reports do not certify every capture backend, GPU, desktop version or feature.
Exact OS versions and per-feature test results have not yet been recorded.

## Install — no Python knowledge required

You need a graphical Linux session, Python 3.10+, Internet and a Groq API key.
Use a normal user account, not root. The initial installation downloads Python
packages; the first voice use downloads Whisper Small.

1. Download the Alpha ZIP from the project's GitHub Releases once published.
2. Extract the **whole folder** to a permanent location in your home directory.
3. Open a terminal in the extracted folder (the one containing `installa.sh`). Run:

   ```bash
   bash installa.sh
   ```

4. When asked, enter your Linux password in the terminal for system dependencies.
   The installer creates a private `.venv` and adds Kapa to your application menu.
5. Show hidden files in your file manager. Open `.env` in the extracted folder
   with a text editor and fill in `GROQ_API_KEY=`. Never share this file.
6. Launch **Kapa** from the application menu. Alternatively run:

   ```bash
   .venv/bin/python gui.py
   ```

Try: **«Metti il volume al trenta per cento»** or **«Apri Firefox»**.
Use **Parla ora** for voice input and **Scorciatoie** to configure the shortcut.
The microphone opens on request, not continuously. Closing the window may hide
it in the tray; choose **Chiudi** there to exit completely.

Keep the extracted folder in place. If moved, regenerate the launcher:

```bash
.venv/bin/python scripts/installa_launcher.py
.venv/bin/python scripts/installa_launcher.py --local
```

The local `Kapa.desktop` is generated during installation, not shipped with
machine-specific paths. Existing `.env` files are preserved by the installer.
Do not copy `.venv` between machines.

## Configuration

The installer creates `.env` if missing. For manual setup copy `.env.example`
to `.env`. Restart Kapa after editing it.

| Setting | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Required AI service credential |
| `YOUTUBE_API_KEY` | Optional YouTube Data API v3 direct video lookup |
| `OBS_PORT` | Optional OBS WebSocket port, default `4455` |
| `OBS_PASSWORD` | Optional local OBS WebSocket password |

Without a YouTube key, Kapa can open search results. Browser playback restrictions
still apply. Groq needs an Internet connection; account quotas and service availability apply.

## Dependencies

Python packages are split into `requirements.txt` (Groq, dotenv, OBS WebSocket),
`requirements-voce.txt` (faster-whisper, numpy), `requirements-gui.txt` (PySide6,
global-shortcut-portal), and optional `requirements-dev.txt` (pytest).
There is currently no lockfile: installation resolves the declared versions.

`installa.sh` supports system packages through DNF on Nobara/Fedora and APT on
Ubuntu/Mint/Debian. It installs Python, audio utilities, notifications, MPRIS,
clipboard/XDG utilities and Qt runtime libraries. It then installs all runtime
Python requirements, runs `pip check`, reports dependencies and creates launchers.

On other distributions, install equivalent system dependencies yourself, then
use `bash installa.sh --skip-system`. This still creates the environment and installs
Python packages. Arch support is experimental, not a tested installation recipe.

Optional features require additional software:

| Feature | Requirement |
| --- | --- |
| Screenshots | Spectacle, Grim, GNOME Screenshot or Scrot, compatible with your session |
| Recording / replay | GPU Screen Recorder CLI, or configured OBS Studio 28+ |
| OBS control | Enabled local WebSocket server, configured sources and output |
| Notifications | Desktop notification service |
| Shortcuts | Compatible portal or desktop shortcut configuration |

For OBS, replay duration comes from OBS settings. GPU Screen Recorder is preferred
when installed; request **«con OBS»** to select OBS. Kapa does not take over OBS
captures started manually. See [the Italian guide](README.it.md) for setup details.

## Privacy and administrative operations

Audio is transcribed locally. The text of requests and relevant conversation/tool
context can be sent to Groq; do not treat the assistant as fully offline. Reading
files or clipboard contents through the assistant may expose that content to the
AI service. Browser searches contact the respective services.

Conversation JSON and logs are stored under
`${XDG_DATA_HOME:-~/.local/share}/ia-assistant`. Conversation context resets on
restart, but saved files remain on disk. Optional audio diagnostics can save
local WAV recordings. Personal vocabulary and `.env` stay in the project folder.

Administrative operations only install one named repository package or update
the system. A separate terminal requests confirmation and any system password.
No arbitrary root shell commands or package removal are offered. Never dictate
passwords to the assistant. This is an Alpha desktop tool, not a security sandbox.

## Limitations and troubleshooting

- Italian interface, commands and responses only. No English mode yet.
- Capture and global shortcuts depend on desktop, Wayland/X11, GPU and installed tools.
  Screenshot capture through XDG Portal is not implemented.
- Reminders require Kapa to stay running and are not persisted after exit.
- Dependency resolution is not fully reproducible without a lockfile.
- Firmware, driver and virtual-machine audio issues need separate testing.
- If the menu entry is missing, regenerate it with the command above.
- For startup problems check `.env`, then run the read-only diagnostic:

  ```bash
  .venv/bin/python scripts/setup_assistant.py --check
  ```

Report the OS/desktop version, session type and steps to reproduce, with secrets
and personal data removed. See [contributing](CONTRIBUTING.md) and [security](SECURITY.md).

## Development and source layout

`kapa/` holds the application; root Python files and `scripts/` are entry points.
`assets/` supplies images and vocabulary; `docs/` holds guides; `tests/` holds
isolated automatic tests. The exact public inventory is in
[FILE_DISTRIBUITI.txt](docs/FILE_DISTRIBUITI.txt).

```bash
.venv/bin/python -B tests/run_safe_tests.py
.venv/bin/python -B -m pytest -p no:cacheprovider tests
```

Tests use synthetic configuration and temporary files rather than real credentials,
microphone capture or administrative installations. The pytest command requires
pytest already installed. Packaging: `python -B scripts/package_private.py`.
The script name is historical; it builds an allowlisted source ZIP and tests its
extracted copy. The source ZIP includes LICENSE. Asset provenance and dependency review are
documented in THIRD_PARTY.md. Public release requires maintainer authorization.

## License and acknowledgements

Kapa project code is licensed under the **GNU General Public License, version 3 only**
(SPDX: `GPL-3.0-only`), without an “or any later version” grant.
You may redistribute and modify it under that license. It comes without warranty;
see the complete [LICENSE](LICENSE) and [license scope](docs/LICENZA.md).
Third-party libraries, models and services retain their own terms; see
[third-party notes](docs/THIRD_PARTY.md). No credentials, virtual environment,
model weights or third-party application binaries are bundled.
