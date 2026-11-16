# Contributing

This is an Italian-only Alpha. Project code is licensed under GNU GPLv3-only (`GPL-3.0-only`); see LICENSE.
Contributions to project code must be offered under that same license.
Do not contribute third-party material without documented compatible rights.

For bug reports include distribution/version, desktop/version, Wayland or X11,
Python version, relevant optional backend, reproduction steps and expected result.
Never attach `.env`, credentials, conversation archives or diagnostic voice recordings.

Development checks (with dependencies already installed):

```bash
.venv/bin/python -B tests/run_safe_tests.py
.venv/bin/python -B -m pytest -p no:cacheprovider tests
```

Preserve Whisper Small, Groq, on-demand microphone access and existing shortcuts.
Administrative actions must stay limited to package installation and system updates;
Nobara updates must use `nobara-sync cli`. No removal or arbitrary root commands.
Test changes with synthetic configuration and temporary files, without real root actions.
