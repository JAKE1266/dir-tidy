import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run_cli(*args, cwd=None, expect=0):
    r = subprocess.run([PY, "-m", "dir_tidy", *args], capture_output=True,
                       text=True, cwd=cwd or ROOT, encoding="utf-8")
    if r.returncode != expect:
        raise AssertionError(f"exit={r.returncode} (expect {expect})\n"
                             f"stdout={r.stdout}\nstderr={r.stderr}")
    return r


def touch(root: Path, name: str) -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    return p


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        touch(self.root, "a.jpg")
        touch(self.root, "movie.mp4")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rules_command(self):
        r = run_cli("rules")
        self.assertIn("内置规则", r.stdout)
        self.assertIn("图片", r.stdout)

    def test_tidy_dry_run_and_apply_undo(self):
        r = run_cli("tidy", str(self.root))
        self.assertIn("计划移动 2 个文件", r.stdout)
        self.assertIn("预览模式", r.stdout)
        # dry-run 不落盘
        self.assertTrue((self.root / "a.jpg").exists())
        self.assertFalse((self.root / ".dir-tidy").exists())

        r = run_cli("tidy", str(self.root), "--apply")
        self.assertIn("回滚清单", r.stdout)
        self.assertTrue((self.root / "图片" / "a.jpg").exists())

        r = run_cli("tidy", str(self.root), "--undo")
        self.assertIn("恢复 2 个文件", r.stdout)
        self.assertTrue((self.root / "a.jpg").exists())
        self.assertFalse((self.root / "图片" / "a.jpg").exists())

    def test_custom_rules_file(self):
        rules = self.root / "rules.json"
        rules.write_text(json.dumps({"rules": [{"name": "设计稿", "match": "*.psd", "dest": "PSD"}]},
                                    ensure_ascii=False), encoding="utf-8")
        touch(self.root, "banner.psd")
        r = run_cli("tidy", str(self.root), "--rules", str(rules))
        self.assertIn("[设计稿]", r.stdout)

    def test_missing_dir(self):
        r = run_cli("tidy", str(self.root / "gone"), expect=1)
        self.assertIn("目录不存在", r.stderr)

    def test_bad_rules_json(self):
        bad = self.root / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        r = run_cli("tidy", str(self.root), "--rules", str(bad), expect=2)
        self.assertIn("JSON", r.stderr)

    def test_version(self):
        r = subprocess.run([PY, "-m", "dir_tidy", "--version"],
                           capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
        self.assertIn("dir-tidy", r.stdout)


if __name__ == "__main__":
    unittest.main()
