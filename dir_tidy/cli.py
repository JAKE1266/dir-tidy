"""命令行入口：``python -m dir_tidy`` 或安装后 ``dirtidy``。

用法：
    dirtidy <dir>                    预览整理计划（默认 dry-run，不动任何文件）
    dirtidy <dir> --apply            执行整理（写入 .dir-tidy/undo-*.json 回滚清单）
    dirtidy <dir> --undo             撤销最近一次整理
    dirtidy <dir> --rules my.json    追加自定义规则（用户规则优先于内置规则）
    dirtidy <dir> --recursive        连子目录一起整理
    dirtidy <dir> --move-others 其他  未命中规则的文件也移入指定目录
    dirtidy rules                    查看内置规则
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .planner import apply, latest_manifest, plan, undo
from .rules import builtin_rules


def _load_user_rules(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    rules = data.get("rules", data) if isinstance(data, dict) else data
    if not isinstance(rules, list):
        raise ValueError("规则文件应为 {\"rules\": [...]} 或规则数组")
    return rules


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dirtidy",
        description="规则驱动的目录整理器：预览 → 应用 → 可回滚",
    )
    ap.add_argument("--version", action="version", version=f"dir-tidy {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("tidy", help="整理一个目录")
    sp.add_argument("dir", help="要整理的目录")
    sp.add_argument("--apply", action="store_true", help="真正执行移动（默认只预览）")
    sp.add_argument("--undo", action="store_true", help="撤销该目录最近一次整理")
    sp.add_argument("--rules", help="自定义规则 JSON 文件")
    sp.add_argument("--recursive", action="store_true", help="包含子目录")
    sp.add_argument("--move-others", metavar="DIRNAME", help="未命中规则的文件也移入该子目录")
    sp.add_argument("--exclude", default="", help="逗号分隔的排除 glob，如 *.tmp,*.crdownload")

    sub.add_parser("rules", help="查看内置规则")

    args = ap.parse_args(argv)

    if args.cmd == "rules":
        print("内置规则（扩展名 → 子目录）：")
        for r in builtin_rules():
            print(f"  {r.dest:<8} {r.match}")
        return 0

    root = Path(args.dir)
    try:
        if args.undo:
            m = latest_manifest(root)
            if not m:
                print(f"未找到回滚清单（{root}/.dir-tidy/ 为空）", file=sys.stderr)
                return 1
            n = undo(m)
            print(f"已撤销最近一次整理：恢复 {n} 个文件（清单 {m.name}）")
            return 0

        user_rules = _load_user_rules(args.rules) if args.rules else None
        p = plan(root, user_rules=user_rules, recursive=args.recursive,
                 move_unmatched=args.move_others, exclude=args.exclude)

        if not p.moves:
            print("没有需要移动的文件。")
            for path, why in p.skipped:
                print(f"  跳过 {path.name}（{why}）")
            return 0

        print(f"{'将移动' if args.apply else '计划移动'} {p.total} 个文件：")
        for it in p.moves:
            rel_src = it.src.relative_to(root)
            print(f"  [{it.rule}] {rel_src}  →  {it.dest}/{it.dst.name}")
        for path, why in p.skipped:
            print(f"  跳过 {path.name}（{why}）")

        if args.apply:
            manifest = apply(p)
            print(f"完成：移动 {p.total} 个文件；回滚清单 {manifest}")
        else:
            print("预览模式，未做任何改动。加 --apply 执行；执行后可用 --undo 回滚。")
        return 0
    except (NotADirectoryError, FileNotFoundError):
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:  # 注意：JSONDecodeError 是 ValueError 子类，须在前
        print(f"规则文件不是合法 JSON：{e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
