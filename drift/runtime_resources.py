"""Resolve checkout assets or resources bundled in a release wheel."""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent


def config_path(package=PACKAGE_ROOT):
    checkout = package.parent / 'config.yaml'
    return checkout if checkout.is_file() else package / 'resources' / 'config.yaml'


def frontend_directory(package=PACKAGE_ROOT):
    checkout = package.parent / 'frontend' / 'dist'
    return checkout if (checkout / 'index.html').is_file() else package / 'resources' / 'frontend'


def workspace_root(package=PACKAGE_ROOT):
    return package.parent if (package.parent / 'config.yaml').is_file() else Path.cwd()
