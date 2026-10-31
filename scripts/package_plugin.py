"""打包插件为可安装 zip。

用法：python scripts/package_plugin.py
输出：dist/astrbot_plugin_special_days-<version>.zip
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXCLUDE_DIRS = {"tests", "scripts", "dist", "__pycache__", ".git"}
EXCLUDE_FILES = {"audit.log", "special_days.db", ".gitignore", ".gitattributes"}


def read_version() -> str:
    for line in (ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "dev"


def main() -> None:
    version = read_version()
    DIST.mkdir(exist_ok=True)
    target = DIST / f"astrbot_plugin_special_days-{version}.zip"
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if path.name in EXCLUDE_FILES or path.suffix == ".pyc":
                continue
            zf.write(path, rel.as_posix())
            count += 1
    print(f"打包完成: {target} ({count} files)")


if __name__ == "__main__":
    main()
