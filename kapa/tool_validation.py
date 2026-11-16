"""Validazione locale del sottoinsieme JSON Schema usato dagli strumenti."""
import math


def validate_arguments(schema, arguments):
    if not isinstance(arguments, dict):
        raise ValueError('Gli argomenti devono essere un oggetto JSON.')
    properties = schema.get('properties', {})
    if set(arguments) - set(properties):
        raise ValueError('Parametri non previsti per questa funzione.')
    if set(schema.get('required', [])) - set(arguments):
        raise ValueError('Mancano parametri obbligatori.')
    for name, value in arguments.items():
        spec = properties[name]
        kind = spec.get('type')
        checks = {
            'string': lambda: isinstance(value, str) and len(value) <= 20000,
            'number': lambda: type(value) in (int, float) and math.isfinite(value),
            'integer': lambda: type(value) is int,
            'boolean': lambda: type(value) is bool,
            'null': lambda: value is None,
        }
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(checks[k]() for k in kinds if isinstance(k, str) and k in checks):
            raise ValueError(f'Tipo o valore non valido per {name}.')
        if 'enum' in spec and value not in spec['enum']:
            raise ValueError(f'Valore non ammesso per {name}.')
    return arguments
