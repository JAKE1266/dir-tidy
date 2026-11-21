"""规则定义与匹配：内置分类规则 + 用户自定义规则（glob / regex）。"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

# 内置规则：按扩展名归类。顺序即优先级（先匹配先赢）。
BUILTIN_RULES: list[dict] = [
    {"name": "图片", "ext": "jpg jpeg png gif webp bmp svg heic avif"},
    {"name": "视频", "ext": "mp4 mkv mov avi webm flv m4v"},
    {"name": "音频", "ext": "mp3 wav flac aac m4a ogg"},
    {"name": "文档", "ext": "pdf doc docx xls xlsx ppt pptx txt md csv"},
    {"name": "压缩包", "ext": "zip rar 7z tar gz bz2"},
    {"name": "程序与代码", "ext": "exe msi bat ps1 sh py js ts html css ipynb"},
    {"name": "字体", "ext": "ttf otf woff woff2"},
]


@dataclass(frozen=True)
class Rule:
    """一条归类规则。

    match  形如 ``*.jpg,*.png``（glob，逗号分隔，大小写不敏感）或 ``regex:^发票.*\\.pdf$``
    dest   目标子目录名
    name   规则名（用于计划展示与用户规则覆盖内置规则）
    """

    match: str
    dest: str
    name: str = ""

    def __post_init__(self) -> None:
        if not self.match or not self.dest:
            raise ValueError("规则必须包含 match 与 dest")
        if self.match.lower().startswith("regex:"):
            try:
                object.__setattr__(self, "_regex", re.compile(self.match[6:]))
            except re.error as e:
                raise ValueError(f"无效正则 {self.match!r}: {e}") from None
            object.__setattr__(self, "_globs", None)
        else:
            globs = [g.strip().lower() for g in self.match.split(",") if g.strip()]
            if not globs:
                raise ValueError(f"规则 match 为空: {self.match!r}")
            object.__setattr__(self, "_globs", globs)
            object.__setattr__(self, "_regex", None)

    def matches(self, filename: str) -> bool:
        if self._regex is not None:
            return bool(self._regex.search(filename))
        low = filename.lower()
        return any(fnmatch.fnmatchcase(low, g) for g in self._globs)


def builtin_rules() -> list[Rule]:
    """内置规则列表（按扩展名 → 目录）。"""
    return [Rule(match=", ".join(f"*.{e}" for e in r["ext"].split()),
                 dest=r["name"], name=r["name"]) for r in BUILTIN_RULES]


def load_rules(user_rules: list[dict] | None = None,
               include_builtin: bool = True) -> list[Rule]:
    """合并规则：用户规则在前（优先），内置规则在后。"""
    rules: list[Rule] = []
    for r in user_rules or []:
        rules.append(Rule(match=str(r["match"]), dest=str(r["dest"]),
                          name=str(r.get("name", "自定义"))))
    if include_builtin:
        rules.extend(builtin_rules())
    return rules


def match_first(filename: str, rules: list[Rule]) -> Rule | None:
    """返回第一条命中的规则；都不命中返回 None。"""
    for r in rules:
        if r.matches(filename):
            return r
    return None
