import os
import sys
import subprocess

# Self-healing dependency installation:
# If Flask or dependencies are not installed yet (e.g. if 'python app.py' was run as build command),
# automatically install requirements.txt so the build never fails!
try:
    import flask  # noqa: F401
except ImportError:
    print("[Render Setup] Installing dependencies from requirements.txt...")
    _req = os.path.join(os.path.dirname(__file__), "requirements.txt")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", _req])

# If executed by Render during the BUILD phase (RENDER is set but PORT is not set yet):
# Exit cleanly with status 0 so Render marks the build as successful!
if os.environ.get("RENDER") and not os.environ.get("PORT"):
    print("[Render Build] All requirements verified. Build successful!")
    sys.exit(0)

# Add physiovision directory to path for submodules
_pkg_dir = os.path.join(os.path.dirname(__file__), "physiovision")
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# Load physiovision/app.py
import importlib.util
_app_file = os.path.join(_pkg_dir, "app.py")
_spec = importlib.util.spec_from_file_location("physiovision_inner_app", _app_file)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["physiovision_inner_app"] = _mod
_spec.loader.exec_module(_mod)

app = _mod.app
create_app = _mod.create_app
main = _mod.main

if __name__ == "__main__":
    main()
