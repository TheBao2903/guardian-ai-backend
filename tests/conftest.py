"""Load domain modules without package initializers that eagerly create routers.

Those initializers construct production Firebase/model singletons at import
time. Unit tests exercise the real repository/service modules with fake I/O.
"""
from pathlib import Path
import sys
from types import ModuleType
import app.modules

MODULES = Path(__file__).resolve().parents[1] / 'app' / 'modules'
for directory in MODULES.iterdir():
    if directory.is_dir() and (directory / '__init__.py').exists():
        name = f'app.modules.{directory.name}'
        package = ModuleType(name)
        package.__path__ = [str(directory)]
        sys.modules.setdefault(name, package)
        setattr(app.modules, directory.name, sys.modules[name])
