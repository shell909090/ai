# 项目核心定位

功能：总结各种信息。
技术栈：Python, langchain, litellm, uv (包管理)。

# 代码规范

* 禁止自动git提交
* 编码规范遵循PEP-8。
* 强制执行 Type Annotations。
* 公有函数必须包含详尽的 Docstrings (Args, Returns, Raises)。
* 环境使用uv管理
* 函数的McCabe复杂度尽量不要超过10。
* 使用 ruff 进行静态检查，配置 McCabe 复杂度阈值为 10。
* 测试和构建过程使用Makefile控制
* 每次修改源码后，如果需要，更新README.md。
* 删除无用代码，删除头部无效import
* 使用logging处理日志。

# read_nyt

使用llm自动阅读new york time新闻，生成摘要。

llm的选择原则参考../CLAUDE.md。

支持多种供应商。
