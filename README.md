# dir-tidy

规则驱动的目录整理器 —— 专治乱成一锅粥的「下载」/「桌面」/微信接收目录。

- **默认 dry-run**：先看计划再动手，不指定 `--apply` 绝不移动任何文件
- **内置分类规则**：图片 / 视频 / 音频 / 文档 / 压缩包 / 程序与代码 / 字体，按扩展名归类
- **自定义规则**：JSON 文件定义 glob 或正则规则（如 `regex:^发票.*\.pdf$ → 报销/`），用户规则永远优先于内置规则
- **冲突安全**：目标重名自动加序号（`报告.pdf → 报告 (1).pdf`），绝不覆盖
- **一键回滚**：每次应用写入 `.dir-tidy/undo-*.json` 清单，`--undo` 完整还原（含清理空分类目录）
- **递归 / 排除 / 兜底**：`--recursive` 连子目录一起整理（自动跳过隐藏目录），`--exclude` 排除下载临时文件，`--move-others` 给未命中文件一个去处

零第三方依赖，Python ≥ 3.8。

## 安装

```bash
pip install .     # 获得 dirtidy 命令
python -m dir_tidy --help    # 或免安装直接运行
```

## 真实运行示例

某个乱目录（含自定义规则 `*.psd → 设计稿/`，排除 `*.tmp`）：

```console
$ python -m dir_tidy tidy ./messy --rules rules.json --exclude "*.tmp"
计划移动 8 个文件：
  [音频] demo_song.mp3  →  音频/demo_song.mp3
  [图片] IMG_20260101_101010.jpg  →  图片/IMG_20260101_101010.jpg
  [程序与代码] setup.exe  →  程序与代码/setup.exe
  [压缩包] 下载 (3).zip  →  压缩包/下载 (3).zip
  [文档] 会议纪要.docx  →  文档/会议纪要.docx
  [文档] 发票20260101.pdf  →  文档/发票20260101.pdf
  [视频] 旅行视频剪辑_v1.mp4  →  视频/旅行视频剪辑_v1.mp4
  [设计稿] 未命名设计稿_final_v2.psd  →  设计稿/未命名设计稿_final_v2.psd
  跳过 rules.json（未命中任何规则）
  跳过 临时缓存.tmp（命中排除规则）
预览模式，未做任何改动。加 --apply 执行；执行后可用 --undo 回滚。
```

执行与回滚：

```console
$ python -m dir_tidy tidy ./messy --apply --rules rules.json --exclude "*.tmp"
将移动 8 个文件：
  ...
完成：移动 8 个文件；回滚清单 messy\.dir-tidy\undo-20261121-125229.json

$ python -m dir_tidy tidy ./messy --undo
已撤销最近一次整理：恢复 8 个文件（清单 undo-20261121-125229.json）
```

## 自定义规则

```json
{
  "rules": [
    {"name": "设计稿", "match": "*.psd,*.ai", "dest": "设计稿"},
    {"name": "发票", "match": "regex:^发票.*\\.pdf$", "dest": "报销"}
  ]
}
```

- `match` 写 `*.psd,*.ai` 这样的 glob（逗号分隔、大小写不敏感），或加 `regex:` 前缀写正则
- 规则按顺序匹配，先命中先赢；用户规则排在全部内置规则之前

## 设计取舍

- **计划/执行分离**：`plan()` 是纯函数（只读目录），`apply()` 才落盘，两者可独立测试
- **回滚清单即真相**：只记录 `src → dst`，撤销时逆序还原；空分类目录一并清理
- **永不覆盖**：所有目标冲突都走 `_collision_free` 加序号，源文件与回滚都不可能丢
- **零依赖**：`pip install dir-tidy` 不拉任何包

## 运行测试

```bash
python -m unittest discover -s tests
# Ran 18 tests ... OK
```

## License

MIT
