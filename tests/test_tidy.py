import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dir_tidy.planner import apply, latest_manifest, plan, undo
from dir_tidy.rules import Rule, builtin_rules, load_rules, match_first


def touch(dir_path: Path, name: str, content: str = "x") -> Path:
    p = dir_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestRules(unittest.TestCase):
    def test_builtin_covers_common(self):
        rules = builtin_rules()
        self.assertEqual(match_first("photo.JPG", rules).dest, "图片")
        self.assertEqual(match_first("clip.mp4", rules).dest, "视频")
        self.assertEqual(match_first("报告.PDF", rules).dest, "文档")
        self.assertIsNone(match_first("unknown.xyz123", rules))

    def test_user_rule_priority_and_regex(self):
        user = [{"name": "发票", "match": "regex:^发票.*\\.pdf$", "dest": "报销"}]
        rules = load_rules(user)
        self.assertEqual(rules[0].name, "发票")
        self.assertEqual(match_first("发票2026.pdf", rules).dest, "报销")
        self.assertEqual(match_first("报告.pdf", rules).dest, "文档")  # 回落内置

    def test_invalid_rule(self):
        with self.assertRaises(ValueError):
            Rule(match="", dest="x")
        with self.assertRaises(ValueError):
            Rule(match="regex:[", dest="x")


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        touch(self.root, "a.jpg")
        touch(self.root, "movie.mp4")
        touch(self.root, "whatever.abc")
        touch(self.root, "temp file.tmp")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_plan(self):
        p = plan(self.root)
        dests = {m.dst.parent.name for m in p.moves}
        self.assertEqual(dests, {"图片", "视频"})
        self.assertEqual([s[0].name for s in p.skipped], ["temp file.tmp", "whatever.abc"])

    def test_apply_moves_and_undo_restores(self):
        names_before = sorted(x.name for x in self.root.iterdir() if x.is_file())
        p = plan(self.root)
        manifest = apply(p)
        self.assertTrue((self.root / "图片" / "a.jpg").exists())
        self.assertTrue((self.root / "视频" / "movie.mp4").exists())
        self.assertFalse((self.root / "a.jpg").exists())
        # 状态目录里应有回滚清单
        self.assertEqual(latest_manifest(self.root), manifest)
        n = undo(manifest)
        self.assertEqual(n, 2)
        names_after = sorted(x.name for x in self.root.iterdir() if x.is_file())
        self.assertEqual(names_before, names_after)
        # 回滚后清掉空分类目录
        self.assertFalse((self.root / "图片").exists())
        self.assertFalse((self.root / "视频").exists())

    def test_collision_renames(self):
        (self.root / "图片").mkdir()
        (self.root / "图片" / "a.jpg").write_text("old", encoding="utf-8")
        p = plan(self.root)
        item = next(m for m in p.moves if m.src.name == "a.jpg")
        self.assertEqual(item.dst.name, "a (1).jpg")
        apply(p)
        self.assertEqual((self.root / "图片" / "a.jpg").read_text(encoding="utf-8"), "old")
        self.assertNotEqual((self.root / "图片" / "a (1).jpg").read_text(encoding="utf-8"), "old")

    def test_recursive_same_name_files_get_unique_targets(self):
        touch(self.root, "one/report.pdf", "first")
        touch(self.root, "two/report.pdf", "second")
        p = plan(self.root, recursive=True)
        moves = [m for m in p.moves if m.src.name == "report.pdf"]
        self.assertEqual(len(moves), 2)
        self.assertEqual(len({m.dst for m in moves}), 2)
        apply(p)
        contents = {
            path.read_text(encoding="utf-8")
            for path in (self.root / "文档").glob("report*.pdf")
        }
        self.assertEqual(contents, {"first", "second"})

    def test_move_unmatched_same_name_files_get_unique_targets(self):
        touch(self.root, "one/same.bin", "first")
        touch(self.root, "two/same.bin", "second")
        p = plan(self.root, recursive=True, move_unmatched="其他")
        moves = [m for m in p.moves if m.src.name == "same.bin"]
        self.assertEqual(len(moves), 2)
        self.assertEqual(len({m.dst for m in moves}), 2)
        apply(p)
        contents = {
            path.read_text(encoding="utf-8")
            for path in (self.root / "其他").glob("same*.bin")
        }
        self.assertEqual(contents, {"first", "second"})

    def test_apply_refuses_destination_created_after_plan(self):
        p = plan(self.root)
        target = self.root / "图片" / "a.jpg"
        target.parent.mkdir()
        target.write_text("new", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            apply(p)
        self.assertEqual((self.root / "a.jpg").read_text(encoding="utf-8"), "x")
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertFalse((self.root / ".dir-tidy").exists())

    def test_recursive_skips_dest_and_hidden(self):
        touch(self.root, "子目录/nested.png")
        touch(self.root, ".隐藏/secret.jpg")
        (self.root / "图片").mkdir()
        touch(self.root, "图片/already.jpg")
        p = plan(self.root, recursive=True)
        moved_names = [m.src.name for m in p.moves]
        self.assertIn("nested.png", moved_names)
        self.assertNotIn("secret.jpg", moved_names)
        self.assertNotIn("already.jpg", moved_names)

    def test_move_unmatched(self):
        p = plan(self.root, move_unmatched="其他")
        dsts = {m.src.name: m.dst.parent.name for m in p.moves}
        self.assertEqual(dsts["whatever.abc"], "其他")

    def test_exclude(self):
        p = plan(self.root, exclude="*.tmp")
        # 排除的文件不移动，但会以“命中排除规则”出现在跳过清单里，便于确认
        self.assertNotIn("temp file.tmp", [m.src.name for m in p.moves])
        self.assertIn(("命中排除规则"), [why for _, why in p.skipped])

    def test_user_rules_file_shape(self):
        p = plan(self.root, user_rules=[{"match": "*.jpg", "dest": "照片库", "name": "照片"}])
        item = next(m for m in p.moves if m.src.name == "a.jpg")
        self.assertEqual(item.dest, "照片库")

    def test_missing_dir_raises(self):
        with self.assertRaises(NotADirectoryError):
            plan(self.root / "no-such-dir")

    def test_undo_manifest_json_shape(self):
        p = plan(self.root)
        manifest = apply(p)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"root", "at", "moves"})


if __name__ == "__main__":
    unittest.main()
