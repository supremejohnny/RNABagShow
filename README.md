# RNABagShow

RNABag 的可运行展示站：前端提交转录组 TSV，FastAPI 后端完成预处理并运行项目 checkpoint。可选持久化模式使用 PostgreSQL 保存分析状态和结果 JSONB，使用私有 MinIO/S3 保存原始 TSV bytes。

## Frontend

展示页入口：

```text
frontend/index.html
```

主要部件：

- `frontend/index.html`: 自包含样式与脚本的主展示版，负责上传和结果交互
- `frontend/ranbag_lab.html`: 完整任务工作台入口
- `frontend/samples/`: 100 样本量的 FPKM TSV 示例文件
- `backend/`: FastAPI API、单工作者队列、TSV 预处理与 PyTorch 推理
- `backend/migrations/`: PostgreSQL schema migration
- `deploy/`: PostgreSQL/MinIO 测试部署、私有配置生成与安全重置脚本
- `RNABag/`: 4096 HVG、模型结构和 checkpoint
- `mapping/`: GRCh38.p13 GeneID/Symbol/Synonym 映射
- `index.html`: 根目录跳转入口

## Local run

```bash
./run.sh
```

打开 `http://127.0.0.1:5173/`。`run.sh` 会在同一终端中启动前端（5173）和后端（8000）；按 `Ctrl+C` 同时停止两者。详细 API、并发、临时数据删除和环境变量见 `backend/README.md`。

`run.sh` 只用于本地开发。服务器采用 Docker Compose：FastAPI 在同一个
8000 端口提供网页和 API，PostgreSQL 与私有 MinIO 保存已批准的测试数据，
所有端口默认仅绑定服务器回环地址。完整启动、SSH 隧道访问和测试命令见
[`deploy/README.md`](deploy/README.md)。

持久化测试栈的启动、迁移、查看和彻底删除方式见 `deploy/README.md`。
