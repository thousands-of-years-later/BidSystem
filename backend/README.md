# Bid System Backend

## Python 环境

后端统一使用 Python 3.13（支持范围为 `>=3.13,<3.14`）。建议从仓库根目录创建独立虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 本地基础设施

Docker Compose 提供：

- PostgreSQL 16 + pgvector，端口 `5432`
- Redis，端口 `6379`
- MinIO S3 兼容对象存储，API 端口 `9000`、管理控制台端口 `9001`
- `minio-init` 一次性任务，自动创建默认 bucket `bid-system`

首次启动前复制环境变量，并按需修改开发账号和密码：

```powershell
Copy-Item .env.example .env
docker compose up -d
docker compose ps -a
```

MinIO 控制台地址为 <http://localhost:9001>，默认开发账号和密码来自 `.env`：

```text
账号：bid_system
密码：bid_system_dev_secret
```

验证 PostgreSQL 与 pgvector：

```powershell
docker compose exec postgres psql -U bid_system -d bid_system -c "SELECT version();"
docker compose exec postgres psql -U bid_system -d bid_system -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
```

## 数据库迁移与所有权

数据库结构只通过 Alembic 迁移管理，应用启动时不会自动执行 `create_all()`。在仓库根目录运行：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://bid_system:bid_system_dev@localhost:5432/bid_system"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

首期按 PostgreSQL schema 划分数据所有权；`platform` schema 仅保存通用基础设施表。每张业务表只能由所属模块仓储写入，跨模块同步调用经过目标模块 `public.py` 并返回 DTO，禁止返回 ORM 对象或直接修改其他模块的表。

`platform.outbox_event` 与业务状态在同一事务写入，发布端采用 `FOR UPDATE SKIP LOCKED`、租约和有上限指数退避实现至少一次投递。消费者必须以 `event_id` 建立幂等约束或等价的持久化去重记录，成功提交消费结果后才能确认消息。

集成测试必须使用独立 `TEST_DATABASE_URL`；不得把开发库或生产库作为事务回滚测试目标。

验证 MinIO bucket：

```powershell
docker compose run --rm minio-init
```

宿主机上的 Python 后端读取 `backend/.env`。系统环境变量优先于 `.env`；若后端以后也作为 Compose 服务运行，应将数据库、Redis和MinIO地址改为对应的 `*_DOCKER` 值。

`APP_ENV` 支持 `dev`、`test` 和 `prod`。PostgreSQL、Redis和MinIO是关键启动依赖，连接失败会阻止应用启动；LLM和OCR默认延迟连接，启用时必须通过环境变量或外部密钥系统注入凭据。配置和日志不会输出密钥原文。

常用 Python 客户端依赖：

```powershell
pip install -e ".[dev]"
```

停止容器但保留数据：

```powershell
docker compose down
```

如需彻底清空开发数据，可执行 `docker compose down -v`。该命令会删除 PostgreSQL 和 MinIO 数据卷，已有数据无法从这些卷恢复。
