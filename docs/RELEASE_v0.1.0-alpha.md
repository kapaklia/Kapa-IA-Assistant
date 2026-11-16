# Kapa IA Assistant v0.1.0 Alpha

LOCAL RELEASE CANDIDATE — not published. Code license: GNU GPLv3-only.
All included asset origins are documented from maintainer declarations.
Planned tag: `v0.1.0-alpha`. Mark as a GitHub pre-release.

First Italian-only Alpha for Linux desktops. Speak or type requests using Groq
AI interpretation and local Whisper Small transcription. Responses are written.

Includes applications and constrained system administration, multimedia and volume,
YouTube/browser searches, files and clipboard, reminders, screenshots, recording
and replay integration, desktop launcher and shortcuts.

Tested by the author on Nobara KDE, Ubuntu GNOME and Linux Mint Cinnamon.
Fedora and Arch have not been fully verified; Arch needs manual system dependencies.

## Installation

Download `Kapa-0.1.0-alpha.zip`, extract the entire folder in a permanent location,
open a terminal there and run `bash installa.sh` as a normal user. Enter the
system password only when the terminal requests it. Fill in `GROQ_API_KEY` in
the hidden `.env` file, then launch Kapa from the application menu.
The first voice use downloads Whisper Small. Do not move the folder afterward.
Read README.md or README.it.md for optional OBS, video and screenshot setup.

## Known limitations

Italian only; network/API access needed for Groq; no dependency lockfile.
Shortcuts and captures depend on desktop/session/hardware. XDG Portal screenshots
are not implemented. Optional capture programs are installed separately. Reminders
are not retained after exit. Practical distro tests do not cover every feature.

## Assets to attach after approval

- `Kapa-0.1.0-alpha.zip`: source, installer, docs, tests and empty examples.
- `Kapa-0.1.0-alpha.zip.sha256`: archive checksum.

No credentials, personal data, virtual environment or model weights are included.
LICENSE is included. Asset provenance and dependency obligations are documented
in THIRD_PARTY.md. Publication still requires maintainer authorization.
For ZIP verification: `sha256sum -c Kapa-0.1.0-alpha.zip.sha256`.
After extraction: `sha256sum -c MANIFEST.sha256`.
