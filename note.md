# RNABagShow 工作记录

> 范围：2026-07-13 至 2026-07-15（+08:00）
> 依据：当前 Git 历史、检出代码和仓库文档；时间以 Git 提交时间为准，文件创建时间仅作为本机工作区参考。

## 2026-07-13｜真实推理闭环

- 从展示原型推进为可运行的 RNABag checkpoint 服务：前端上传 TSV，FastAPI 创建分析任务，后台单工作者处理并提供状态轮询和结果接口（`82444f7`、`cabd523`）。
- `backend/app/inference.py` 固化了当前预处理契约：UTF-8 TSV、前五行内识别 GeneID 表头、GeneID 必须是未四舍五入的 ASCII 整数字符串、重复 GeneID/模型 Symbol 按首次出现保留。
- 使用 GRCh38.p13 映射和有序 4096 HVG 列表，缺失基因补零后执行 `log1p`；`raw_sum` 与 `input_sum` 作为相同的 summary token 输入 checkpoint。
- 当前启用四个任务：组织癌症检测、组织来源识别（36 类）、血小板癌症检测、血小板肿瘤定位（5 类）。血浆任务仍保留 checkpoint 但禁用。
- 血小板癌症检测继续使用 legacy Healthy 概率阈值 `0.003955459`，其他任务使用 argmax；结果包含 `schema_version: 1`、输入摘要、样本级排序分数和科研用途警告。

## 2026-07-14｜持久化与受限部署

- 增加 PostgreSQL 分析状态/结果 JSONB 持久化与私有 MinIO/S3 原始 TSV 保存；以 SHA-256 复用相同原始对象，但每次分析保留独立分析记录（`3188f0b`）。
- 持久化启动会执行有序迁移、检查私有 bucket，并把中断的 `validating`/`running` 分析恢复为 `queued`；删除分析时保留最小化 `purged` tombstone，并在最后一个引用删除后清理对象。
- 默认内存模式保留一小时结果；两种模式都会在成功、失败、取消和关闭路径清理临时处理文件。上传采用流式写入并受大小限制，推理队列默认容量为 10。
- 增加 loopback CPU 应用服务、PostgreSQL/MinIO Compose 栈，以及按批准内网 CIDR `172.28.0.0/24` 限制访问的 Nginx gateway（`5ee4aeb`、`808f60a`、`fe9313a`、`573f089`、`b414fdf`）。
- 部署 checkout 只读挂载；数据库、对象存储、运行时文件、备份和凭据位于 checkout 外部。受控测试重置不会触碰 Git 工作区（`106c0a8`）。

## 2026-07-15｜展示流程与 Lab 工作台

- 11:15：主展示页重构为 Input → Task → Validate → Result 的引导式流程（`1d762a8`）。
- 13:18：采用 pinned scrollytelling 展示结构，左侧流程说明与右侧固定分析舞台同步切换（`bc63b7c`）；13:45 修复导航和 sticky stage 同步问题（`da7ace4`）。
- 恢复独立 `frontend/ranbag_lab.html` 单页工作台，使用 `frontend/rnabag-variant.js` 复用任务选择、基础预检、真实 API 上传、轮询和结果渲染逻辑（`f9971cd`）。主展示页和 Lab 会根据本地开发、`file://` 或 FastAPI 来源选择 API 地址。
- `README.md`、`backend/README.md` 和 `deploy/README.md` 已同步当前运行、预处理、持久化、部署和数据边界（`c56e279`）。

## 当前状态与边界

- 当前产品是面向生物、计算生物和医学领域专家的科研展示站，不是临床诊断系统；所有结果均必须标注为 research-use only。
- 本地开发入口为 `./run.sh`，前端默认 `http://127.0.0.1:5173/`，FastAPI 为 `http://127.0.0.1:8000/`。服务器通过 Compose 运行 loopback FastAPI，内网访问才经过受限 gateway。
- 当前没有登录、SSO、TLS、公网路由或限流能力，不能直接作为公网服务；这些属于后续独立部署和安全评审范围。
- 不记录上传表达数据，也不把原始数据、数据库文件、对象存储内容、运行日志或密钥写入 Git。持久化范围仅限已批准的分析元数据/结果和私有原始 TSV 对象。
