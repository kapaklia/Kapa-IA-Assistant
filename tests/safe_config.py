"""Configurazione sintetica condivisa: nessun .env o cartella personale."""
import ast
import sys
import types
from pathlib import Path


def install():
    if getattr(sys.modules.get('kapa.config'), '__synthetic__', False):
        return
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import kapa
    config_path = root / 'kapa/config.py'
    module = types.ModuleType('kapa.config')
    module.__package__ = 'kapa'
    module.__file__ = str(config_path)
    module.__synthetic__ = True
    tree = ast.parse(config_path.read_text(encoding='utf-8'))
    body = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'dotenv':
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'load_dotenv':
            continue
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            replacements = {
                'GROQ_API_KEY': ast.Constant('test-key-not-a-secret'),
                'YOUTUBE_API_KEY': ast.Constant(None),
                'HOME': ast.parse("Path('/__ia_assistant_test__')", mode='eval').body,
                'CARTELLE_UTENTE': ast.parse("{name: HOME / name for name in ['scrivania','documenti','download','immagini','video','musica','home']}", mode='eval').body,
                'WHISPER_FILE_PERSONALE': ast.parse("HOME / 'personale.txt'", mode='eval').body,
            }
            for name in names:
                if name in replacements:
                    node.value = replacements[name]
        body.append(node)
    clean = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
    exec(compile(clean, str(config_path), 'exec'), module.__dict__)
    sys.modules['kapa.config'] = module
    kapa.config = module
