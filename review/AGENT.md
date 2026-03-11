# 代码规范

* 禁止自动git提交
* 提交只包含git stage中的内容，comment使用英文书写，需要简明扼要，禁止把ai列为co-author
* 编码规范遵循PEP-8。
* 强制执行 Type Annotations。
* 公有函数应包含简洁的 Docstrings。不超过一行，注明函数中最重要的事。
* 环境使用uv管理
* 函数的McCabe复杂度尽量不要超过10。
* 使用 ruff 进行静态检查，配置 McCabe 复杂度阈值为 10。
* 测试和构建过程使用Makefile控制
* 每次修改源码后，如果需要，更新README.md。
* 删除无用代码，删除头部无效import
* 使用logging处理日志。
