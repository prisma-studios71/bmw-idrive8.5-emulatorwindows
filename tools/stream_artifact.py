"""Write one verified artifact from a package container to stdout (used by import.sh)."""
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from find_packages import Container  # noqa: E402

path, kind, sgbm, version, artifact = sys.argv[1:6]
with Container(pathlib.Path(path), kind, sgbm, version).open(artifact) as stream:
    shutil.copyfileobj(stream, sys.stdout.buffer, 8 << 20)
