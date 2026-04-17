# all2txt 需求文档

## 目标

构建一个命令行工具，从任意格式文件中抽取纯文本，供后续向量搜索引擎（RAG pipeline）使用。

## 核心需求

1. **文件类型自动识别**：使用系统 `file --mime-type` 命令检测文件 MIME 类型，无需依赖扩展名。

2. **多后端注册**：每种 MIME 类型可注册多个后端（extractor）。后端通过类装饰器方式注册，新增后端只需新增一个文件。

3. **优先级与配置**：
   - 后端具有默认优先级（数字越小越优先）。
   - 可通过 `all2txt.toml` 配置文件按 MIME 类型覆盖后端顺序。
   - 运行时自动按优先级尝试，失败则 fallback 到下一个。

4. **胶水模式**：实现以调用外部工具（CLI）为主，Python 为粘合层。不强依赖任何特定外部工具，后端缺失时跳过。

5. **典型支持格式**（不限于）：
   - 文档类：PDF、Word、Excel、PowerPoint、ODT、EPUB
   - 标记类：HTML、Markdown、LaTeX（.tex）
   - Unix 文档类：man page（troff）、GNU Info
   - 纯文本、CSV
   - 图片（通过 OCR 后端）

6. **CLI 接口**：`all2txt [--config FILE] [--mime MIME] [--debug] FILE...`

## 非目标

- 不做格式转换，只输出纯文本。
- 不内置 OCR 引擎，OCR 通过可选后端（如 unstructured）支持。
- 不做文本后处理（分段、去重等）。
