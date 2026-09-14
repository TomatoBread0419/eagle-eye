# 🐳 Docker 部署

## 概述

Eagle Eye 可以运行在 Docker 容器中，适合部署到云服务器或 NAS 设备。当前主运行环境是 Android Termux，Docker 版本作为备选部署方案。

---

## 系统要求

| 组件 | 要求 |
|------|------|
| Docker | 24.0+ |
| Docker Compose | 2.20+ |
| CPU | x86_64 / ARM64 |
| 内存 | ≥ 2GB（推荐 4GB） |
| 存储 | ≥ 10GB |
| 网络 | 可访问 Alpaca API + DeepSeek API |

---

## 项目结构

```
eagle-eye/
├── Dockerfile
├── docker-compose.yml
├── .env                  # 环境变量（Alpaca API Key 等）
├── .dockerignore
├── main.py
├── core/
├── strategy/
├── execution/
├── risk/
├── portfolio/
├── broker/
├── monitoring/
├── ops/
├── scheduler/
├── data/
├── storage/
└── logs/
```

---

## Dockerfile

```dockerfile
# ─── Builder Stage ──────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Runtime Stage ──────────────────────────
FROM python:3.13-slim

WORKDIR /app

# 从 builder 阶段复制虚拟环境
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /data /logs

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python main.py health || exit 1

# 默认入口
CMD ["python", "main.py", "status"]
```

---

## Docker Compose

```yaml
version: "3.8"

services:
  eagle-eye:
    build: .
    container_name: eagle-eye
    restart: unless-stopped
    environment:
      - ALPACA_API_KEY=${ALPACA_API_KEY}
      - ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY}
      - ALPACA_BASE_URL=https://paper-api.alpaca.markets
      - EAGLE_LOG_LEVEL=INFO
      - EAGLE_TARGET_ALLOCATION=0.85
      - TZ=Asia/Shanghai
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./storage:/app/storage
    ports:
      - "9090:9090"   # 可选：健康检查端口
    networks:
      - eagle-net
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  eagle-net:
    driver: bridge
```

---

## .env 配置

```bash
# 🦅 Eagle Eye — Docker 环境变量

# Alpaca API（必须）
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here

# 日志
EAGLE_LOG_LEVEL=INFO

# 交易参数
EAGLE_TARGET_ALLOCATION=0.85
EAGLE_MAX_SINGLE_POSITION=0.20
EAGLE_DRAWDOWN_PAUSE=0.12

# 通知（可选）
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## .dockerignore

```
.git/
.gitignore
__pycache__/
*.pyc
.env.local
logs/*
!logs/.gitkeep
data/*
!data/.gitkeep
.DS_Store
*.md
docs/
```

---

## 快速启动

```bash
# 1. 克隆仓库
git clone https://github.com/TomatoBread0419/eagle-eye-trading.git
cd eagle-eye-trading

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 Alpaca API Key

# 3. 构建镜像
docker compose build

# 4. 启动
docker compose up -d

# 5. 检查状态
docker compose logs -f

# 6. 运行命令
docker exec eagle-eye python main.py status
docker exec eagle-eye python main.py report
docker exec eagle-eye python main.py scan
```

---

## 常用命令

```bash
# 查看运行状态
docker compose ps

# 查看实时日志
docker compose logs -f

# 运行市场扫描
docker exec eagle-eye python main.py scan

# 生成决策报告
docker exec eagle-eye python main.py report

# 检查系统健康
docker exec eagle-eye python main.py health

# 执行交易（谨慎使用）
docker exec eagle-eye python main.py execute

# 停止服务
docker compose down

# 重建并重启（代码更新后）
docker compose up -d --build
```

---

## 数据持久化

Docker 使用 volume 挂载持久化数据：

| Volume | 挂载路径 | 用途 |
|--------|---------|------|
| `./data` | `/app/data` | 市场数据、行情缓存 |
| `./logs` | `/app/logs` | 审计日志、运行日志 |
| `./storage` | `/app/storage` | SQLite 数据库、状态文件 |

这些目录在容器删除后数据依然保留。

---

## 在 Termux 中运行 Docker

> **注意**：Android Termux 原生不支持 Docker。以下方案供参考：

### 方案 A：Termux + proot-distro

```bash
# 安装 Ubuntu 发行版
pkg install proot-distro
proot-distro install ubuntu

# 进入 Ubuntu
proot-distro login ubuntu

# 安装 Docker（需要 Ubuntu 22.04+）
apt update && apt install docker.io
```

### 方案 B：直接运行（推荐）

Eagle Eye 设计为可直接在 Termux 中运行，无需 Docker：

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 运行
python main.py status
```

---

## 性能建议

| 部署方式 | 优缺点 | 推荐场景 |
|----------|--------|----------|
| **Termux（当前）** | 7×24 低功耗运行，无需云服务 | ✅ 日常交易 |
| **Docker (x86 VPS)** | 稳定、可扩展、支持集群 | 生产环境 |
| **Docker (ARM NAS)** | 低功耗、家庭部署 | 备用节点 |

---

## 故障排查

### 容器启动失败

```bash
# 查看详细日志
docker compose logs

# 检查环境变量是否设置
docker compose config

# 手动执行入口脚本
docker run --rm -it eagle-eye sh
# 在容器内：python main.py status
```

### 网络访问问题

```bash
# 测试 Alpaca 连接
docker exec eagle-eye python -c "
import urllib.request
resp = urllib.request.urlopen('https://paper-api.alpaca.markets/v2/account')
print(resp.status)
"
```

### 数据库问题

```bash
# 检查 SQLite
docker exec eagle-eye python -c "
import sqlite3
conn = sqlite3.connect('/app/storage/eagle.db')
print(conn.execute('SELECT COUNT(*) FROM trades').fetchone())
"
```
