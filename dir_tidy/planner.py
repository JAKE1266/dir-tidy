"""计划生成与执行：扫描目录 → MoveItem 列表 → 应用移动 → 可回滚清单。"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .rules import Rule, load_rules, match_first

STATE_DIR = ".dir-tidy"


@dataclass
class MoveItem:
    src: Path
    dst: Path
    rule: str   # 规则名
    dest: str   # 目标子目录


@dataclass
class Plan:
    root: Path
    moves: list[MoveItem] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)  # (路径, 原因)

    @property
    def total(self) -> int:
        return len(self.moves)


def _collision_free(dst_dir: Path, name: str, reserved: set[Path] | None = None) -> Path:
    """目标重名时自动加序号：报告.pdf → 报告 (1).pdf。"""
    reserved = reserved or set()
    candidate = dst_dir / name
    if not candidate.exists() and candidate not in reserved:
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    m = re.match(r"^(.*) \((\d+)\)$", stem)
    base, n = (m.group(1), int(m.group(2))) if m else (stem, 0)
    while True:
        n += 1
        candidate = dst_dir / f"{base} ({n}){suffix}"
        if not candidate.exists() and candidate not in reserved:
            return candidate


def plan(
    root: Path,
    user_rules: list[dict] | None = None,
    recursive: bool = False,
    move_unmatched: str | None = None,
    exclude: str = "",
) -> Plan:
    """扫描目录生成整理计划（不落盘）。

    recursive     是否包含子目录（始终跳过目标子目录、隐藏目录与 .dir-tidy）
    move_unmatched 未命中任何规则的文件移到哪里；None 表示原地保留
    exclude       逗号分隔的 glob，命中的文件跳过
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    rules: list[Rule] = load_rules(user_rules)
    excl = [e.strip().lower() for e in exclude.split(",") if e.strip()]
    p = Plan(root=root)
    reserved: set[Path] = set()
    dest_names = {r.dest for r in rules} | ({move_unmatched} if move_unmatched else set())

    candidates = list(root.iterdir())
    if recursive:
        candidates = [
            x for d in root.iterdir() if d.is_dir()
            and d.name not in dest_names and not d.name.startswith(".")
            for x in d.rglob("*")
        ] + candidates

    for path in sorted(candidates, key=lambda x: x.name.lower()):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts[:-1]):
            continue  # 任何层级的隐藏目录都不碰（含 .dir-tidy）
        if path.parent.name in dest_names and path.parent != root:
            continue  # 已在归类目录里的不再重复处理
        low = path.name.lower()
        if any(fnmatch_like(low, e) for e in excl):
            p.skipped.append((path, "命中排除规则"))
            continue
        rule = match_first(path.name, rules)
        if rule is None:
            if move_unmatched:
                dst = _collision_free(root / move_unmatched, path.name, reserved)
                reserved.add(dst)
                p.moves.append(MoveItem(path, dst, "未命中", move_unmatched))
            else:
                p.skipped.append((path, "未命中任何规则"))
            continue
        if path.parent == root / rule.dest:
            continue  # 已在目标位置
        dst = _collision_free(root / rule.dest, path.name, reserved)
        reserved.add(dst)
        p.moves.append(MoveItem(path, dst, rule.name, rule.dest))
    return p


def fnmatch_like(name: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatchcase(name, pattern)


def apply(p: Plan) -> Path:
    """执行计划：移动文件并写入回滚清单。返回清单路径。"""
    destinations: set[Path] = set()
    for item in p.moves:
        if item.src.resolve() == item.dst.resolve():
            continue
        if not item.src.exists():
            raise FileNotFoundError(str(item.src))
        if item.dst in destinations:
            raise FileExistsError(f"目标重复：{item.dst}")
        if item.dst.exists():
            raise FileExistsError(f"目标已存在：{item.dst}")
        destinations.add(item.dst)

    p.root.mkdir(parents=True, exist_ok=True)
    state = p.root / STATE_DIR
    state.mkdir(exist_ok=True)
    manifest_path = state / f"undo-{datetime.now():%Y%m%d-%H%M%S}.json"
    records: list[dict] = []
    for item in p.moves:
        if item.src.resolve() == item.dst.resolve():
            continue  # 目标与源相同（极端边界），跳过避免报错
        item.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.src), str(item.dst))
        records.append({"src": str(item.src), "dst": str(item.dst)})
    manifest_path.write_text(
        json.dumps({"root": str(p.root), "at": datetime.now().isoformat(timespec="seconds"),
                    "moves": records}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return manifest_path


def undo(manifest_path: Path) -> int:
    """按清单把文件移回原位，返回恢复条数；顺带清掉因此产生的空分类目录。"""
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    root = Path(data["root"])
    n = 0
    dest_dirs: set[Path] = set()
    for rec in reversed(data["moves"]):  # 逆序撤销，保证重名序号还原正确
        src, dst = Path(rec["src"]), Path(rec["dst"])
        dest_dirs.add(dst.parent)
        if dst.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(_collision_free(src.parent, src.name)))
            n += 1
    # 清理空目录（深度优先，只删空的，安全）
    for d in sorted(dest_dirs, key=lambda x: len(x.parts), reverse=True):
        while d != root and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
    return n


def latest_manifest(root: Path) -> Path | None:
    state = Path(root) / STATE_DIR
    if not state.is_dir():
        return None
    files = sorted(state.glob("undo-*.json"))
    return files[-1] if files else None
