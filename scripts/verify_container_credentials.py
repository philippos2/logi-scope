"""Check filesystem and environment boundaries without displaying credentials."""

import argparse
import os
from pathlib import Path


def verify(service: str) -> None:
    root = Path('/home/developer/work/logi-scope')
    if list(root.glob('.env')) or list(root.glob('.env.*')) != [root / '.env.example']:
        raise RuntimeError('Unexpected environment file exposed in container')
    if (root / '.git').exists():
        raise RuntimeError('Host Git metadata exposed in container')
    allowed = {
        'app': {'DATABASE_PASSWORD'},
        'ingest': {'INGEST_DATABASE_PASSWORD'},
        'manage': {'DATABASE_PASSWORD', 'INGEST_DATABASE_PASSWORD', 'ADMIN_DATABASE_PASSWORD', 'UPDATE_DATABASE_PASSWORD'},
        'updates': {'UPDATE_DATABASE_PASSWORD'},
    }[service]
    actual = {key for key in os.environ if key.endswith('_PASSWORD')}
    if actual != allowed:
        raise RuntimeError('Unexpected credential environment variables')
    for name in ('src', 'seed', 'tests', 'scripts', 'pyproject.toml', 'uv.lock'):
        if not (root / name).exists():
            raise RuntimeError('Required development input is missing')
    print(f'{service}: credential isolation and development mounts verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('service', choices=('app', 'ingest', 'manage', 'updates'))
    verify(parser.parse_args().service)
