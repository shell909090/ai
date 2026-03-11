# review tools

`gen_callgraph.py` 是一个 Python 项目静态调用图与符号摘要生成工具。

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
python3 gen_callgraph.py /path/to/python/project --out docs/python_analysis --output all
```

也可以先赋予可执行权限后直接运行：

```bash
chmod +x gen_callgraph.py
./gen_callgraph.py /path/to/python/project --out docs/python_analysis --output all
```

## 输出文件

- `callgraph.dot`
- `callgraph.svg`
- `signatures.md`

`signatures.md` 当前仅按文件分组（`By File`）输出。

## 把 SVG 转成 JPG

如果系统还没有 ImageMagick，可以先安装：

```bash
sudo apt-get update
sudo apt-get install -y imagemagick
convert --version
```

安装后，直接使用 ImageMagick 的 `convert`：

```bash
convert -density 120 docs/python_analysis/callgraph.svg -background white -alpha remove -alpha off -quality 90 docs/python_analysis/callgraph.jpg
```

如果输出目录不同，把命令里的路径替换成对应文件即可。`-density 120` 通常足够预览，也能避免直接生成过大的位图导致转换变慢。
