"""Operazioni amministrative controllate per Kapa.

L'IA può chiedere SOLO installazione pacchetti o aggiornamento sistema.
La password è richiesta dal programma di elevazione dentro un vero terminale:
non passa mai da Python, Groq, stdin catturato o file di log.
"""
import argparse
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from .app_paths import PROJECT_DIR

# Accetta un solo identificativo di pacchetto. Non accetta flag, comandi o shell.
PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]{0,99}$", re.ASCII)


def _os_release(path="/etc/os-release"):
    values = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def detect_distro(path="/etc/os-release"):
    data = _os_release(path)
    name = data.get("ID", "").lower()
    likes = set(data.get("ID_LIKE", "").lower().split())
    if name == "nobara" or name.startswith("nobara-"):
        return "nobara"
    if name in {"debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin"} or likes.intersection({"debian", "ubuntu"}):
        return "debian"
    if name in {"arch", "manjaro", "endeavouros", "garuda", "cachyos"} or "arch" in likes:
        return "arch"
    if name in {"fedora", "rhel", "centos", "rocky", "almalinux"} or likes.intersection({"fedora", "rhel"}):
        return "fedora"
    return "unsupported"


def build_command(action, package=None, distro=None):
    distro = distro or detect_distro()
    if distro == "unsupported":
        raise ValueError("Distribuzione non supportata: operazione interrotta.")
    if action == "install":
        if not isinstance(package, str) or not PACKAGE_RE.fullmatch(package):
            raise ValueError("Nome pacchetto non valido: specifica un solo nome, senza opzioni o comandi.")
        if distro in {"nobara", "fedora"}:
            return ["sudo", "dnf", "install", "--", package]
        if distro == "debian":
            return ["sudo", "apt", "install", "--", package]
        return ["sudo", "pacman", "-S", "--", package]
    if action == "update":
        return {
            "nobara": ["nobara-sync", "cli"],  # NON usare sudo
            "fedora": ["sudo", "dnf", "upgrade", "--refresh"],
            "debian": ["sudo", "apt", "update"],
            "arch": ["sudo", "pacman", "-Syu"],
        }[distro]
    raise ValueError("Operazione non autorizzata.")


def _terminal_args(script, action, package):
    """Ogni terminale riceve soltanto args generati localmente, mai shell utente."""
    argv = [sys.executable, str(script), "--run", action]
    if package is not None:
        argv.append(package)
    # Preferisce un emulatore disponibile; non installa nulla di nascosto.
    for term in ("xdg-terminal-exec", "konsole", "gnome-terminal", "xfce4-terminal", "mate-terminal", "xterm"):
        exe = shutil.which(term)
        if not exe:
            continue
        if term == "gnome-terminal":
            return [exe, "--", *argv]
        if term == "xfce4-terminal":
            # --execute accetta argv, a differenza di --command (stringa shell)
            return [exe, "--execute", *argv]
        if term == "mate-terminal":
            return [exe, "-x", *argv]
        return [exe, "-e", *argv]
    raise RuntimeError("Nessun terminale compatibile trovato (Konsole, GNOME Terminal, XFCE, MATE o xterm).")


def _launch(action, package=None):
    try:
        cmd = build_command(action, package)
        script = PROJECT_DIR / 'scripts/root_tools.py'
        terminal = _terminal_args(script, action, package)
        subprocess.Popen(terminal, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except (OSError, ValueError, RuntimeError) as exc:
        return f"Non posso avviare l'operazione: {exc}"
    summary = "Installazione di '" + package + "'" if action == "install" else "Aggiornamento del sistema"
    return f"{summary}: ho aperto un terminale per la conferma e l'eventuale password. Operazione non ancora completata."


def installa_applicazione(nome_app: str) -> str:
    """Avvia l'installazione di UN pacchetto in un terminale separato."""
    return _launch("install", nome_app)


def aggiorna_sistema() -> str:
    """Avvia il gestore aggiornamenti raccomandato dalla distribuzione."""
    return _launch("update")


def cerca_pacchetto(nome_app: str) -> str:
    """Cerca nomi di pacchetti nei repository senza privilegio amministrativo."""
    if not isinstance(nome_app, str) or not PACKAGE_RE.fullmatch(nome_app):
        return "Nome di ricerca non valido: usa una parola o un nome pacchetto, senza comandi."
    distro = detect_distro()
    commands = {
        "nobara": ["dnf", "search", nome_app],
        "fedora": ["dnf", "search", nome_app],
        "debian": ["apt-cache", "search", "--", nome_app],
        "arch": ["pacman", "-Ss", "--", nome_app],
    }
    if distro not in commands:
        return "Non conosco il gestore pacchetti della distribuzione."
    try:
        result = subprocess.run(commands[distro], capture_output=True, text=True, timeout=20,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Ricerca non riuscita: {exc}"
    output = (result.stdout or "").strip()
    if not output:
        return f"Nessun pacchetto trovato per '{nome_app}' oppure ricerca non riuscita."
    # Non inviare output potenzialmente enormi a Groq.
    return output[:1600] + ("\n… risultati troncati" if len(output) > 1600 else "")


def esegui_come_root(comando: str) -> str:
    """Compatibilità: disabilitata intenzionalmente anche se chiamata direttamente."""
    return "I comandi root arbitrari sono disabilitati. Sono consentiti solo installa_applicazione e aggiorna_sistema."


def _worker(action, package=None):
    try:
        distro = detect_distro()
        cmd = build_command(action, package, distro)
    except ValueError as exc:
        print(f"Operazione rifiutata: {exc}")
        return 2
    print("Kapa — operazione amministrativa")
    print("Sistema:", distro)
    print("Comando:", shlex.join(cmd))
    print("La password sarà richiesta dal sistema direttamente in questo terminale.")
    try:
        response = input("Procedere? [s/N]: ").strip().casefold()
        if response not in ("s", "si", "sì"):
            print("Operazione annullata.")
            return 0
        # Nessun sudo -S, niente lettura o salvataggio delle password.
        if distro == "debian" and action == "update":
            first = subprocess.run(cmd, check=False).returncode
            if first != 0:
                result = first
            else:
                result = subprocess.run(["sudo", "apt", "upgrade"], check=False).returncode
        else:
            result = subprocess.run(cmd, check=False).returncode
        print("Operazione terminata." if result == 0 else f"Operazione terminata con codice {result}.")
        return result
    except (EOFError, KeyboardInterrupt):
        print("\nOperazione annullata.")
        return 130
    except OSError as exc:
        print(f"Impossibile eseguire l'operazione: {exc}")
        return 1
    finally:
        try:
            input("Premi Invio per chiudere questo terminale...")
        except (EOFError, KeyboardInterrupt):
            pass


SCHEMA_CERCA_PACCHETTO = {
    "type": "function",
    "function": {"name": "cerca_pacchetto",
                 "description": "Cerca pacchetti disponibili nei repository della distribuzione, senza root e senza installarli.",
                 "parameters": {"type": "object", "properties": {"nome_app": {"type": "string", "description": "Parola o nome pacchetto da cercare."}}, "required": ["nome_app"]}},
}

SCHEMA_INSTALLA_APP = {
    "type": "function",
    "function": {"name": "installa_applicazione",
                 "description": "Installa un pacchetto esplicitamente richiesto dall'utente. Apre un terminale per conferma e password, senza gestirla nell'assistente.",
                 "parameters": {"type": "object", "properties": {"nome_app": {"type": "string", "description": "Nome preciso di UN pacchetto, per esempio gimp o vlc. Non passare comandi o opzioni."}}, "required": ["nome_app"]}},
}
SCHEMA_AGGIORNA_SISTEMA = {
    "type": "function",
    "function": {"name": "aggiorna_sistema",
                 "description": "Aggiorna il sistema su esplicita richiesta. Su Nobara usa nobara-sync cli, senza sudo. Apre terminale per conferma.",
                 "parameters": {"type": "object", "properties": {}, "required": []}},
}

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=("install", "update"))
    parser.add_argument("package", nargs="?")
    args = parser.parse_args(argv)
    return _worker(args.run, args.package)


if __name__ == "__main__":
    raise SystemExit(main())
