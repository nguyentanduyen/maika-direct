"""Load api.py/const.py without importing Home Assistant."""

import importlib.util
import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "maika_direct"

pkg = types.ModuleType("maika_direct_testpkg")
pkg.__path__ = [str(PKG)]
sys.modules["maika_direct_testpkg"] = pkg
for name in ("const", "api"):
    spec = importlib.util.spec_from_file_location(f"maika_direct_testpkg.{name}", PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
