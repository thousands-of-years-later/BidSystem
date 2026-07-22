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

首次启动前在仓库根目录复制环境变量，并按需修改开发账号和密码：

```powershell
Copy-Item backend/.env.example backend/.env
docker compose --env-file backend/.env -f deploy/compose.yaml up -d
docker compose --env-file backend/.env -f deploy/compose.yaml ps -a
```

MinIO 控制台地址为 <http://localhost:9001>，默认开发账号和密码来自 `.env`：

```text
账号：bid_system
密码：bid_system_dev_secret
```

验证 PostgreSQL 与 pgvector：

```powershell
docker compose --env-file backend/.env -f deploy/compose.yaml exec postgres psql -U bid_system -d bid_system -c "SELECT version();"
docker compose --env-file backend/.env -f deploy/compose.yaml exec postgres psql -U bid_system -d bid_system -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
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
docker compose --env-file backend/.env -f deploy/compose.yaml run --rm minio-init
```

宿主机上的 Python 后端读取 `backend/.env`。系统环境变量优先于 `.env`；若后端以后也作为 Compose 服务运行，应将数据库、Redis和MinIO地址改为对应的 `*_DOCKER` 值。

`APP_ENV` 支持 `dev`、`test` 和 `prod`。PostgreSQL、Redis和MinIO是关键启动依赖，连接失败会阻止应用启动；LLM和OCR默认延迟连接，启用时必须通过环境变量或外部密钥系统注入凭据。配置和日志不会输出密钥原文。

## 日志与可观测性

运行日志输出到 stderr，运行时审计事件输出到独立的 stdout 通道。JSON日志统一包含服务、环境、事件名以及可用的 `request_id`、`trace_id`、`span_id`；消息、异常和结构化字段在写入前都会脱敏。运行时审计日志只用于运维检索，不能代替未来由 `reviews` 业务模块事务化保存的权威审计记录。

OpenTelemetry默认关闭。启用Trace或指标时，必须配置Collector的OTLP HTTP基础地址（不要包含 `/v1/traces` 或 `/v1/metrics`）：

```text
TRACING_ENABLED=true
METRICS_ENABLED=true
TRACING_SERVICE_NAME=bid-system
TRACING_OTLP_ENDPOINT=http://localhost:4318
METRICS_EXPORT_INTERVAL_SECONDS=60
```

已直接接入HTTP请求耗时、错误率和SQLAlchemy连接池快照。Worker任务、队列积压以及LLM请求、Token和成本通过 `platform.telemetry.metrics` 的类型化 recorder 接入；LLM成本只有在上游提供确定的金额与币种时才会上报。

## Celery Worker

异步任务使用Celery 5.6和Redis broker。PostgreSQL中的
`platform.task_execution` 是任务状态、幂等和死信的权威数据源；未配置Celery
result backend，Redis不保存正式业务状态。

当前仅定义了 `documents.parse` 的类型化消息契约。由于文档模块和解析工作流尚未
落地，该任务不会注册到生产Worker，避免把未实现的解析流程报告为成功。

在Linux或Docker中独立启动Worker：

```text
bid-system-worker
```

`bid-system-worker-health` 会探测Worker依赖的PostgreSQL、Redis和MinIO；Compose
健康检查随后再通过定向Celery ping确认目标Worker仍能响应控制命令。

API与Worker使用同一镜像、不同进程入口：

```powershell
docker compose --env-file backend/.env -f deploy/compose.yaml up -d --build api worker
docker compose --env-file backend/.env -f deploy/compose.yaml ps
```

Worker采用late acknowledgement、单次预取、有上限任务超时和Redis visibility
timeout。收到 `TERM` 时Celery执行warm shutdown，在途任务可在Compose配置的停止
宽限期内完成。

常用 Python 客户端依赖：

```powershell
pip install -e ".[dev]"
```

停止容器但保留数据：

```powershell
docker compose --env-file backend/.env -f deploy/compose.yaml down
```

如需彻底清空开发数据，可执行 `docker compose --env-file backend/.env -f deploy/compose.yaml down -v`。该命令会删除 PostgreSQL 和 MinIO 数据卷，已有数据无法从这些卷恢复。
