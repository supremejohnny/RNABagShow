# RNABagShow 工作记录

> 范围：2026-07-14 至 2026-07-15（+08:00）  
> 依据：Git 提交记录及当前检出文件的创建时间；后者仅代表本机工作区证据。

## 2026-07-14｜持久化与受限部署

- 增加 PostgreSQL 分析状态/结果持久化与私有 MinIO/S3 原始 TSV 保存，并补充迁移、容器化测试和受控重置路径。
- 增加 loopback CPU 应用服务，以及按批准内网 CIDR 限制访问的 Nginx gateway。
- 相关提交：`3188f0b` 至 `b414fdf`。

## 2026-07-15｜展示流程与 Lab 工作台

- 11:15：重构为 Input → Task → Validate → Result 的引导式流程（`1d762a8`）。
- 13:18：采用 pinned scrollytelling 展示结构（`bc63b7c`）；13:45 修复导航和 sticky stage 同步问题（`da7ace4`）。
- 后续完成独立 `frontend/ranbag_lab.html` 工作台，并在 `frontend/rnabag-variant.js` 中补足 `data-variant="lab"` 的导航和滚动兼容逻辑。
- 本机创建时间：`rnabag-variant.js` 11:54:53、`frontend/index.html` 11:57:48、`ranbag_lab.html` 13:55:05。

当前展示页与 Lab 工作台复用同一分析逻辑；所有输出均限科研用途，不用于临床诊断。
