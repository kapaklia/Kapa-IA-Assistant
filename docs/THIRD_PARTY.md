# Third-party review — GPL-3.0-only source distribution

## Scope and outcome

Kapa's own code is GPL-3.0-only. This review covers the source ZIP, whose installer
downloads dependencies separately. No dependency binaries, Python distributions,
model weights or external application binaries are redistributed in the ZIP.
This does not remove obligations arising from linked or combined software.
Existing virtualenv metadata is recorded in [DEPENDENCIES.md](DEPENDENCIES.md).
There is no lockfile and future resolutions can differ; this is not a complete
binary compliance audit or an assertion that all files have known provenance.

## Direct dependencies and model

| Component | Observed version | License evidence | Review for this source distribution |
| --- | --- | --- | --- |
| Groq Python SDK | 1.7.0 | Apache-2.0, installed metadata and upstream LICENSE | GPLv3-compatible; preserve notices if bundled later |
| python-dotenv | 1.2.4 | BSD-3-Clause, installed metadata | Permissive; no incompatibility identified |
| websocket-client | 1.9.2 | Apache-2.0, installed metadata and upstream LICENSE | GPLv3-compatible; no binary bundled |
| faster-whisper | 1.2.1 | MIT, installed metadata and upstream LICENSE | Permissive; no incompatibility identified |
| CTranslate2 | 4.9.0 | MIT, installed metadata | No incompatibility identified from metadata; no binary audit |
| NumPy | 2.5.5 | BSD-3-Clause plus 0BSD/MIT/Zlib/CC0 components, installed metadata | No obvious GPLv3 incompatibility; wheel notices matter if bundled |
| PySide6 / Qt | 6.12.0 | LGPLv3 / GPLv3 alternatives, metadata and Qt documentation | GPLv3 route available; retain individual Qt component obligations |
| global-shortcut-portal | 0.2.1 | AGPL-3.0-only, installed metadata and included LICENSE | Special GPLv3 section 13 combination rules; NOT GPL-only relicensed |
| dbus-next | 0.2.3 | MIT, installed metadata | Permissive |
| Whisper Small | downloaded on first use, not bundled | Upstream Whisper MIT license | Model remains Small; service/download provenance must be retained if bundled later |

GPLv3 section 13 allows combination with AGPLv3 while preserving the GPL-covered
part's license and applying the AGPL's relevant requirements to the combination.
Kapa's license remains GPL-3.0-only. Do not describe the installed combination as
exclusively GPL-only, or assume separate installation exempts it from compliance.
For any redistributed combined binaries, provide the applicable licenses, notices
and corresponding sources, and assess AGPL network-source obligations if relevant.
No replacement or removal of the shortcut library has been made.

Transitive environment metadata includes MIT, BSD, Apache-2.0, MPL-2.0, PSF-2.0
and Qt alternatives. No clear incompatible license was identified from these
metadata declarations. Those declarations alone do not verify embedded wheel
components (FFmpeg, Qt/Chromium, BLAS etc.). Such binaries are not in this ZIP;
future bundling requires a separate audit. Pytest is not installed in this snapshot.

## Included assets — provenance record

### Project-generated PNG resources: maintainer declaration

The maintainer confirms that:

- `assets/assistant-icon.png` was generated through Codex specifically for Kapa.
- `assets/sfondo.png` was generated through OpenAI ChatGPT specifically for Kapa.
- Neither image was downloaded from an external image website.

This records the maintainer's firsthand declaration. Provenance for these two
files is now documented; they are no longer listed as assets of unknown origin.
No external artist, stock-image license or generation date has been invented.
This record does not assert exclusivity, copyrightability or independently verified
absence of third-party rights. No change to either image has been made.

### Common vocabulary: maintainer declaration

The maintainer confirms that `assets/vocabolario_comune.txt` was developed during
Kapa's implementation using common Italian and English terms and commands.
Its project origin is now documented based on this declaration. No external
vocabulary source or author has been inferred. The file itself is unchanged.

### Microphone SVG: maintainer declaration

The maintainer confirms that `assets/microphone.svg` was created through Codex
specifically for Kapa. Its provenance is now documented on that basis. The earlier
inspection could not establish its origin from file metadata or the available
history; this new declaration resolves that outstanding provenance question.
No external icon set, external author or generation date has been inferred.
The SVG and all other assets remain unchanged.

| Asset | SHA256 | Provenance status |
| --- | --- | --- |
| assets/assistant-icon.png | `ecc8000c372612bfff0c4dd30c9b7b658fa1493693af4e34bc280f5f3518e49e` | Generated through Codex for Kapa; confirmed by maintainer |
| assets/sfondo.png | `da804c0173081dd02beff61b4566b49959205c08d9a535cdebef91fb56d2bfd1` | Generated through OpenAI ChatGPT for Kapa; confirmed by maintainer |
| assets/microphone.svg | `8a3077ba99ff28641fdf3da0ab4007e4de33af8d8218136f5cddc2004754aade` | Created through Codex specifically for Kapa; confirmed by maintainer |
| assets/vocabolario_comune.txt | `083e606337071015d04351023704d7f33c193b274c54863caa5e46c3a995601b` | Developed during Kapa implementation using common Italian/English terms and commands; confirmed by maintainer |

The GPL notice for Kapa does not establish ownership of third-party material.
Provenance for all four included assets is now documented from maintainer
declarations; no undocumented external source has been assigned.

## External tools and services

OBS, GPU Screen Recorder, desktop tools and package managers are invoked as
external programs, not bundled. Groq and optional YouTube services have separate
account/service terms; API availability and costs are not conferred by GPL.
No legal right is inferred from a service's availability or from an asset's filename.

## Evidence and primary references

- [Groq SDK license](https://github.com/groq/groq-python/blob/main/LICENSE)
- [faster-whisper license](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE)
- [Whisper license](https://github.com/openai/whisper/blob/main/LICENSE)
- [websocket-client license](https://github.com/websocket-client/websocket-client/blob/master/LICENSE)
- [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
- [global-shortcut-portal 0.2.1 metadata and source links](https://pypi.org/pypi/global-shortcut-portal/0.2.1/json)
- [GPLv3, including section 13](https://www.gnu.org/licenses/gpl-3.0.html)
- GPLv3 canonical text also included locally in LICENSE; dependency license
  files and metadata read from the existing virtualenv, without installation.

All four asset origins have been declared by the maintainer. No asset provenance
clarification remains pending in this review. This records those declarations
rather than an independent legal clearance or a guarantee of exclusive rights.
Code license: GPL-3.0-only. Public release still requires maintainer authorization.
