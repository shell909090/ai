# review tools

`gen-sign.py` 是一个 Python 项目符号摘要与内部调用图生成工具。

## 依赖

运行脚本只依赖：

- Python 3.10+
- 系统级 Graphviz（`dot` 命令）

在 Debian/Ubuntu 上安装 `dot`：

```bash
sudo apt-get update
sudo apt-get install -y graphviz
dot -V
```

## 使用

在当前目录执行：

```bash
python3 gen-sign.py /path/to/python/project --out docs/python_analysis
```

如果还想额外生成“每个文件一张图”的内部调用图：

```bash
python3 gen-sign.py /path/to/python/project --out docs/python_analysis --per-file-internal
```

也可以先赋予可执行权限后直接运行：

```bash
chmod +x gen-sign.py
./gen-sign.py /path/to/python/project --out docs/python_analysis
```

## 输出文件

- `signatures.md`
- `internal_callgraphs/*.dot`
- `internal_callgraphs/*.svg`

默认只生成 `signatures.md`。

`internal_callgraphs/` 在启用 `--per-file-internal` 时生成：当前文件内部调用会展开，跨文件调用只显示为外部叶子节点，不继续展开目标模块。
