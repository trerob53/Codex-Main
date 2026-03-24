"""
Cerasus Hub — Module Discovery
Finds and registers all hub modules by scanning subpackages.
"""

import importlib
import os

_module_dirs = [
    "attendance",
    "operations",
    "da_generator",
    "incidents",
    "overtime",
    "training",
    "uniforms",
]

REGISTERED_MODULES = []


def discover_modules() -> list:
    """Discover and instantiate all available hub modules.

    Each module subpackage must expose a ``get_module()`` function that
    returns a :class:`BaseModule` instance.
    """
    global REGISTERED_MODULES
    if REGISTERED_MODULES:
        return list(REGISTERED_MODULES)

    modules_dir = os.path.dirname(os.path.abspath(__file__))
    found = []

    for mod_name in _module_dirs:
        mod_path = os.path.join(modules_dir, mod_name)
        if not os.path.isdir(mod_path):
            continue
        init_file = os.path.join(mod_path, "__init__.py")
        if not os.path.isfile(init_file):
            continue
        try:
            pkg = importlib.import_module(f"src.modules.{mod_name}")
            if hasattr(pkg, "get_module"):
                instance = pkg.get_module()
                found.append(instance)
        except Exception as e:
            print(f"[Modules] Failed to load {mod_name}: {e}")

    REGISTERED_MODULES = found
    return list(REGISTERED_MODULES)
