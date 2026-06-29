# task 结构

- card id
- session id
- proj
- agent
- workdir
- abort
- summary

# 容量管理

- 维护总 task 数和每种 proj 的 task 数。
- 容量计数器只做启动限制，不做 abort 依据。已经启动 session 并不因为容量限制而终止。
- 另一方面说，按照算法正常执行的话， kanban 管理的 task 不应超出容量限制。

# timer

1. 对所有 task 通过 agent driver 做 session 状态检查，看 session 是否仍在执行、正常结束或异常结束。
2. 做 doing 检查。
3. 做 timeout 检查。
    - 如果有 task 满足 now > task.abort+timeout，那么给 card 标 attention。增加 comment 说明 abort 超时。销毁 task，总 task 计数-1，对应 proj task 计数-1。
    - 如果有 task 满足 now > task.summary+timeout，那么把 card 拖去 done，并标 attention。追加 comment 说执行完成但总结超时。销毁 task，总 task 计数-1，对应 proj task 计数-1。
4. 如果 task 容量限制未满，去拉 todo list。过滤掉没有标 proj 的 card。检查第一条 card 对应的 proj 是否满足容量限制要求。如果满足，拖去 doing。随后走 doing.in 流程。如果不满足，继续向下检查。agent 不影响容量，只影响启动 session 时选择的 driver 和配置。

# session 状态

session 状态由对应 agent driver 返回。协调器只识别三类状态：running、finished、failed。driver 负责把底层工具状态映射成这三类。例如 opencode driver 可以把缺失 info.finish 和 tool-calls 映射成 running，把 stop 映射成 finished，把 length、content-filter、error、unknown 映射成 failed。

1. 如果状态是 running，那么跳过当前 session。当前 session 还在活跃。
2. 检查 task.abort。 如果有，给 card 增加 comment 说明 abort 成功。运行abort钩子。销毁 task，总 task 计数-1，对应 proj task 计数-1。（此条隐含默认，如果有task.abort，那么当前card不在doing，且用户不在乎任务是否成功）
3. 如果没有 task.abort，检查状态。如果状态是 failed，把对应 card 拖去 done，增加attention标签。追加 comment，说任务执行异常结束。销毁 task，总 task 计数-1，对应 proj task 计数-1。（此条隐含，即使在summary途中出了错，也属于任务执行出错）
4. 如果状态是 finished，检查 task.summary 属性。如果有，追加 comment 说执行完成，并把 agent driver 返回的最后文本一起写到 comments 里。同步执行 session.finish 钩子。无论是否成功，把对应 card 拖去 done。销毁 task，总 task 计数-1，对应 proj task 计数-1。
5. 如果没有 task.summary，给 session 发 summary prompt。并设置 task.summary = time。

# doing 检查

1. 过滤 card。判定card是否有 proj 标签。如果没有的话忽略，这张卡不该AI管。
2. task 结构和 doing list 做差。只在 task 结构里的是 doing.out。只在 card list 里的是 doing.in。注意先做 out 再做 in，不然会有错误的容量限制。

# doing.in

1. 拿 proj 信息。没有 proj:* label 时跳过卡片。
2. 拿 agent 信息。没有 agent:* label 时用 kanban.default_agent；多个 agent:*、未知 agent 或默认 agent 配置错误时，把 card 转去 done，标 attention，追加 comment。其他 label 透传给 agent driver 解释。
3. 做容量检查。如果容量超了，把 card 转去 todo。
4. 如果容量没超。建立 task 结构追踪并立刻占用容量，总 task 计数+1，对应 proj task 计数+1。运行 session.new 钩子。session.new 钩子运行结束且成功之后，使用指定 agent 建立对应 session；如果钩子失败，销毁 task 并释放容量，把 card 转去 done，标 attention，追加 comment。

# doing.out

1. 向对应session发abort信号。
2. task.abort = time。
3. 追加 comment 说开始 abort。
