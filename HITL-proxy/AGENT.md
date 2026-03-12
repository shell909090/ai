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
