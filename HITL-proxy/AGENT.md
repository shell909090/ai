# 代码规范

* 禁止自动git提交
* 提交只包含git stage中的内容，comment使用英文书写，需要简明扼要，禁止把ai列为co-author
* 每次修改源码后，如果需要，更新README.md。
* README.md使用英文，README.cn.md使用中文。
* docs是用户文档区域，修改之前需要和用户确认。
  * docs/req.md是原始需求文档。涉及需求变更需要同步确认文档是否需要更新。
* 测试和构建过程使用Makefile控制
* golang代码，文件必须用gofmt格式化，导入分组用goimports
* golang代码，提交前需要通过go test和golangci-lint
* Python代码编码规范遵循PEP-8。
* Python代码强制执行 Type Annotations。
* Python代码公有函数应包含简洁的 Docstrings。不超过一行，注明函数中最重要的事。
* Python代码环境使用uv管理
* Python代码函数的McCabe复杂度尽量不要超过10。
* Python代码使用 ruff 进行静态检查，配置 McCabe 复杂度阈值为 10。
* Python代码删除无用代码，删除头部无效import
* Python代码使用logging处理日志。
