import os
import subprocess
import sys
import tempfile
from importlib.metadata import distribution
from pathlib import Path

import dir_tidy

ROOT = Path(__file__).resolve().parents[1]


def run_cli(console, *args, cwd):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env.pop("PYTHONUTF8", None)
    result = subprocess.run([str(console), *args], cwd=cwd, capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("utf-8")


def main():
    module_path = Path(dir_tidy.__file__).resolve()
    if module_path == (ROOT / "dir_tidy" / "__init__.py").resolve():
        raise RuntimeError(f"dir_tidy 仍从源码目录导入：{module_path}")

    package = distribution("dir-tidy")
    if package.version != "0.1.1":
        raise RuntimeError(f"版本不符：{package.version}")

    scripts_dir = Path(sys.executable).parent
    console = scripts_dir / ("dirtidy.exe" if os.name == "nt" else "dirtidy")
    if not console.exists():
        raise RuntimeError(f"控制台脚本不存在：{console}")

    version = run_cli(console, "--version", cwd=ROOT)
    if "dir-tidy 0.1.1" not in version:
        raise RuntimeError(f"控制台脚本版本检查失败：{version!r}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        root = work / "messy"
        for folder, content in (("one", "first"), ("two", "second")):
            source = root / folder / "report.pdf"
            source.parent.mkdir(parents=True)
            source.write_text(content, encoding="utf-8")

        output = run_cli(console, "tidy", str(root), "--recursive", "--apply", cwd=work)
        if "完成" not in output:
            raise RuntimeError(f"CLI 整理失败：{output!r}")
        targets = sorted((root / "文档").glob("report*.pdf"))
        contents = {path.read_text(encoding="utf-8") for path in targets}
        if len(targets) != 2 or contents != {"first", "second"}:
            raise RuntimeError(f"同名文件未安全保留：{[path.name for path in targets]}")

        output = run_cli(console, "tidy", str(root), "--undo", cwd=work)
        if "恢复 2 个文件" not in output:
            raise RuntimeError(f"CLI 回滚失败：{output!r}")
        if (root / "one" / "report.pdf").read_text(encoding="utf-8") != "first":
            raise RuntimeError("第一个文件回滚内容不符")
        if (root / "two" / "report.pdf").read_text(encoding="utf-8") != "second":
            raise RuntimeError("第二个文件回滚内容不符")

    print("Installed wheel smoke test passed")


if __name__ == "__main__":
    main()
