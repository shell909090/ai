# DKAI - AI Development Container

基于 Debian 13 的 Docker 容器，通过 ttyd 提供 Web 终端访问，适合在远程设备上持续使用 agent 工具。

## 快速开始

### 1. 构建镜像

```bash
make build
# 或
docker build -t dkai .
```

### 2. 创建 profile 配置

统一配置目录：`~/.config/dkai`

每个 profile 由两个文件组成：
- `~/.config/dkai/<profile>.env`：传给容器的 env 文件
- `~/.config/dkai/<profile>.root`：软链接，指向要挂载到容器的主目录

示例（profile 名称为 `ai`）：

```bash
mkdir -p ~/.config/dkai

cat > ~/.config/dkai/ai.env <<'ENV'
PASSWORD=your-secure-password
LANG=en_US.UTF-8

# Optional API keys
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ENV

ln -s /path/to/your/workspace ~/.config/dkai/ai.root
```

### 3. 启动容器

```bash
./dkai start ai
```

### 4. 访问

浏览器打开: `http://localhost:<host-port>`（默认 `8484`）
- 用户名: `shell`
- 密码: 对应 profile 的 `.env` 文件中的 `PASSWORD`

## 重要说明

### 路径脱敏策略

- 仓库不保存你的真实宿主机路径。
- 真实路径通过 `~/.config/dkai/<profile>.root` 注入。
- 真实密钥与运行参数通过 `~/.config/dkai/<profile>.env` 注入。

### 权限模型与风险（重要）

- 容器内 `shell` 用户默认可通过 `sudo` 提权到 root（设计如此，便于 agent 自行安装/调整组件）。
- 这意味着容器内环境被改乱、被误操作或被恶意命令执行的风险由使用者自行承担。
- 风险通常主要落在挂载进容器的目录及其内容。

### Docker 隔离边界（重要）

- Docker 提供的是“隔离”而不是“绝对安全边界”。
- 不应把容器当作强隔离沙箱；内核漏洞、错误配置、高权限运行方式都可能扩大影响面。
- 若暴露到公网，建议额外使用反向代理、TLS、访问控制与最小权限挂载策略。

## 组件清单

容器内安装内容请直接查看 `packages.txt` 与 `Dockerfile`。

## 常用命令

```bash
# 启动某个 profile
./dkai start ai

# 停止某个 profile
./dkai stop ai

# 查看日志
docker logs -f dkai-ai

# 进入容器
docker exec -it dkai-ai bash
```

## 架构说明

- 基础镜像: debian:13-slim
- ttyd: 1.7.7 (从 GitHub 下载预编译版本)
- 运行用户: shell (sudo 免密)
- 入口脚本: `/usr/bin/run_agent`

## 高级配置

### 容器内环境变量

`run_agent` 会尝试加载容器内工作目录下的 `.env`（如果存在）。

### 自定义启动参数

通过 profile 的 `.env` 传入额外参数：

```bash
TMUX_ARGS=-f /home/shell/.tmux.conf
TTYD_ARGS=--client-option fontSize=16
```

注意：`docker run --env-file` 建议使用 `KEY=value` 原始格式，不要给值再包一层引号。

### dkai 脚本可调参数

- `DKAI_HOST_PORT`：宿主机映射端口（默认 `8484`）
- `DKAI_IMAGE`：镜像名（默认 `dkai`）
- `DKAI_NAME_PREFIX`：容器名前缀（默认 `dkai`）
- `DKAI_CONFIG_HOME`：profile 配置目录（默认 `~/.config/dkai`）

说明：
- 容器内端口固定为 `8484`（与镜像入口约定一致）。
- 容器内挂载目标固定为 `/home/shell`。

## 自定义

- 添加系统包: 编辑 `packages.txt`
- 修改 sudo 配置: 编辑 `sudoers`
- 调整启动行为: 编辑 `run_agent`
