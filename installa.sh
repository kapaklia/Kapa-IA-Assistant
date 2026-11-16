#!/usr/bin/env bash
# Installazione locale: eseguire con bash installa.sh, senza sudo.
set -Eeuo pipefail
trap 'printf "\nInstallazione interrotta (riga %s). Correggi l’errore e riesegui bash installa.sh.\n" "$LINENO" >&2' ERR

skip_system=0
case "${1:-}" in
    --skip-system) skip_system=1 ;;
    -h|--help)
        printf 'Uso: bash installa.sh [--skip-system]\nInstalla Kapa nella cartella estratta e crea i collegamenti.\n--skip-system: installa solo le dipendenze Python, senza sudo.\n'
        exit 0 ;;
    '') ;;
    *) printf 'Opzione sconosciuta: %s\n' "$1" >&2; exit 1 ;;
esac
if (( $# > 1 )); then
    printf 'Troppi argomenti. Usa --help.\n' >&2
    exit 1
fi
if [[ $(id -u) == 0 ]]; then
    printf 'Esegui come utente normale: bash installa.sh (senza sudo).\n' >&2
    exit 1
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd -- "$project_dir"
for required in requirements.txt requirements-voce.txt requirements-gui.txt scripts/setup_assistant.py; do
    if [[ ! -f "$required" ]]; then
        printf 'File mancante: %s. Estrai tutto lo ZIP prima di installare.\n' "$required" >&2
        exit 1
    fi
done

if (( ! skip_system )); then
    if ! command -v sudo >/dev/null; then
        printf 'Serve sudo per i pacchetti di sistema; usa --skip-system se sono già installati.\n' >&2
        exit 1
    fi
    printf 'Installazione dipendenze di sistema: potrebbe essere richiesta la password di sudo.\n'
    if command -v dnf >/dev/null; then
        sudo dnf install python3 python3-pip pulseaudio-utils libnotify playerctl \
            wl-clipboard xclip xdg-utils xdg-user-dirs libxkbcommon-x11 \
            xcb-util-cursor mesa-libEGL libglvnd-opengl
    elif command -v apt-get >/dev/null; then
        sudo apt-get update
        sudo apt-get install python3 python3-venv python3-pip pulseaudio-utils \
            libnotify-bin playerctl wl-clipboard xclip xdg-utils xdg-user-dirs \
            libxcb-cursor0 libxkbcommon-x11-0 libegl1 libopengl0
    else
        printf 'Installazione automatica dei pacchetti disponibile per Fedora/Nobara e Debian/Ubuntu/Mint.\nInstalla le dipendenze di sistema della tua distro e rilancia con --skip-system.\n' >&2
        exit 1
    fi
fi

if ! command -v python3 >/dev/null; then
    printf 'Python 3 non trovato. Installa Python >= 3.10.\n' >&2
    exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Serve Python >= 3.10")'
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
if [[ ! -x .venv/bin/python ]]; then
    printf 'Ambiente .venv incompleto. Rinominalo e riesegui l’installazione.\n' >&2
    exit 1
fi
printf '\nInstallazione dipendenze Python nell’ambiente locale…\n'
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-voce.txt -r requirements-gui.txt
.venv/bin/python -m pip check

# Non legge o sovrascrive chiavi già configurate.
if [[ ! -e .env && ! -L .env ]]; then
    (umask 077; set -o noclobber; printf 'GROQ_API_KEY=\nYOUTUBE_API_KEY=\n' > .env)
fi
.venv/bin/python scripts/setup_assistant.py --check
.venv/bin/python scripts/installa_launcher.py
.venv/bin/python scripts/installa_launcher.py --local
printf '\nInstallazione completata.\nApri il file .env e inserisci la tua GROQ_API_KEY; YOUTUBE_API_KEY è facoltativa.\nPoi cerca Kapa nel menu applicazioni oppure apri Kapa.desktop.\nMantieni questa cartella nella stessa posizione: i collegamenti la usano.\nAl primo avvio vocale verrà scaricato Whisper Small: serve Internet.\n'
if ! command -v gpu-screen-recorder >/dev/null; then
    printf '\nRegistrazione e replay: installa GPU Screen Recorder oppure configura OBS (vedi README.md e COSA_SA_FARE.md).\n'
fi
if ! command -v spectacle >/dev/null && ! command -v grim >/dev/null && ! command -v gnome-screenshot >/dev/null && ! command -v scrot >/dev/null; then
    printf 'Screenshot: installa uno strumento compatibile con il desktop (vedi COSA_SA_FARE.md).\n'
fi
