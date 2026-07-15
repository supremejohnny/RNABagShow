# RNABagShow

RNABag 的可运行科研展示站：前端上传表达矩阵 TSV，FastAPI 后端按 GeneID 映射并构造有序 4096 HVG 特征，随后运行项目 checkpoint 并返回样本级预测。结果仅用于科研展示，**不构成临床诊断**。

默认模式在内存中管理分析任务；可选持久化模式使用 PostgreSQL 保存分析状态和结果 JSONB，并把原始 TSV bytes 存入私有 MinIO/S3 对象存储。

## 页面与分析流程

- 根 `index.html` 仅跳转到 `frontend/index.html`。
- `frontend/index.html` 是主展示页，样式内置，交互由 `frontend/rnabag-variant.js` 提供。页面采用 **Input → Task → Validate → Result** 四步 pinned scrollytelling：左侧说明研究步骤，右侧固定分析舞台随滚动同步切换。
- `frontend/ranbag_lab.html` 是独立的 RNABag Lab 单页工作台，与主展示页复用同一份分析交互逻辑；适合直接完成输入、任务选择、校验和结果查看。
- `frontend/samples/` 提供 100 样本 FPKM TSV 示例。

当前启用的任务：

1. 组织 RNA 癌症检测
2. 组织来源识别（36 类）
3. 血小板 RNA 癌症检测
4. 血小板 RNA 肿瘤定位（5 类）

血浆癌症检测的 checkpoint 已随项目保留，但工作流仍禁用，等待其输入与样本约定确认。

## 目录说明

- `backend/app/main.py`：FastAPI、上传流式写入、单工作者队列、内存/持久化任务路由和静态文件服务。
- `backend/app/inference.py`：TSV 校验、GeneID 映射、4096 HVG 矩阵构造、checkpoint 加载与预测格式化。
- `backend/app/catalog.py`：API 任务、模态和标签顺序。
- `backend/migrations/`：PostgreSQL schema migrations。
- `RNABag/`：模型结构、4096 HVG 列表与 checkpoint。
- `mapping/`：GRCh38.p13 GeneID / Symbol / Synonym 映射。
- `deploy/`：私有持久化、CPU 应用和受限内网 gateway 的 Compose 部署与运维脚本。

## 本地运行

首次使用请在仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
./run.sh
```

打开 <http://127.0.0.1:5173/>。`run.sh` 会在同一终端启动前端静态服务（5173）和 FastAPI（8000）；按 `Ctrl+C` 同时停止两者。每个任务的首次请求会加载并缓存对应 checkpoint，因此通常比后续请求更慢。

详细 API、预处理约定、队列策略、临时数据删除和环境变量见 [backend/README.md](backend/README.md)。

## 验证

常规代码检查可在仓库根目录运行：

```bash
python3 -m py_compile backend/app/main.py backend/app/inference.py
python3 -m unittest discover -s backend/tests -v
node --check frontend/rnabag-variant.js
bash -n deploy/*.sh
```

如本机具备 Docker 与部署配置，可按 [AGENTS.md](AGENTS.md) 中的 Compose `config --quiet` 命令继续验证部署文件。完整的持久化初始化、测试、CPU 应用启动、SSH 隧道和受限内网 gateway 操作见 [deploy/README.md](deploy/README.md)。

## 部署与数据边界

`run.sh` 仅用于本地开发。服务器部署由 Docker Compose 管理：FastAPI 在 loopback 端口同时提供网页和 API，PostgreSQL 与 MinIO 保持私有；需要团队内网访问时，才可按批准的 CIDR 启动独立 Nginx gateway。

当前应用没有登录能力，不能直接作为公网服务。公网开放前必须完成独立的 TLS、身份认证、限流与网络安全评审。不要将上传的表达数据、数据库文件、对象存储内容、日志或密钥写入 Git 仓库。
