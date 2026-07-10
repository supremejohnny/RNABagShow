# RNABagShow

RNABag 的静态展示页，用于介绍转录组基础模型、数据处理流程和五个下游推理任务。

## Frontend

展示页入口：

```text
frontend/index.html
```

另外提供两个学术化版本：

```text
frontend/index2.html  # balanced academic view
frontend/index3.html  # dense academic model card
```

当前阶段是纯静态前端：

- `frontend/index.html`: 主展示版，保留可视化和任务交互
- `frontend/index2.html`: 平衡版，弱化 marketing，突出模型和任务结构
- `frontend/index3.html`: 学术版，集中展示参数、架构、标签和 checkpoint
- `frontend/styles.css`: 页面样式
- `frontend/app.js`: 任务切换、预置结果和推理流程动画
- `frontend/academic.css`: 两个学术化版本的样式
- `frontend/academic.js`: 两个学术化版本的轻量任务预览交互
- `index.html`: 根目录跳转入口

## Scope

第一阶段不需要后端。页面中的推理结果和日志是预置展示数据，用于说明 RNABag 的输入、任务选择、checkpoint 和输出形式。

如果后续需要让用户上传 RNA-seq / FPKM 数据并真实运行模型，再增加 FastAPI + PyTorch 推理服务。
