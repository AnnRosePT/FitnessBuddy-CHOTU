import os
import sys
import importlib.util

# Add physiovision directory to path for submodules (pose_engine, exercises, storage)
_pkg_dir = os.path.join(os.path.dirname(__file__), "physiovision")
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# Load physiovision/app.py without circular import name collision
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
