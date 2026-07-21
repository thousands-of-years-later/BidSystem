# Bid System Backend

## 本地基础设施

Docker Compose 提供：

- PostgreSQL 16 + pgvector，端口 `5432`
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

验证 MinIO bucket：

```powershell
docker compose run --rm minio-init
```

宿主机上的 Python 后端读取 `.env` 中的 `DATABASE_URL` 和 `MINIO_ENDPOINT`。若后端以后也作为 Compose 服务运行，应改用 `DATABASE_URL_DOCKER` 和 `MINIO_ENDPOINT_DOCKER`。

常用 Python 客户端依赖：

```powershell
pip install "sqlalchemy>=2" "psycopg[binary]>=3" minio
```

停止容器但保留数据：

```powershell
docker compose down
```

如需彻底清空开发数据，可执行 `docker compose down -v`。该命令会删除 PostgreSQL 和 MinIO 数据卷，已有数据无法从这些卷恢复。
