const CONTACT_EMAIL = "lingshumaa@gmail.com";

const sampleFiles = [
  {
    file: "rnabag_demo_fpkm_tissue_100.tsv",
    path: "samples/rnabag_demo_fpkm_tissue_100.tsv"
  },
  {
    file: "rnabag_demo_fpkm_plasma_100.tsv",
    path: "samples/rnabag_demo_fpkm_plasma_100.tsv"
  },
  {
    file: "rnabag_demo_fpkm_platelet_100.tsv",
    path: "samples/rnabag_demo_fpkm_platelet_100.tsv"
  }
];

const taskData = {
  tissueCancer: {
    modality: "Tissue biopsy",
    title: "Tissue Cancer Detection",
    description: "基于组织来源的 FPKM 表达矩阵判断样本是否呈现癌症信号，输出 Healthy 或 Cancer。",
    detail: "输入文件需要是以 GeneID 为第一列、样本为后续列的 TSV。RNABag 后续会完成基因映射、4096 HVG 过滤、log1p 转换，并加载 Tissue_cancer_detect.ckpt 进行二分类。",
    output: "Cancer",
    quickRows: [
      ["DEMO_TISSUE_001", "Cancer", "0.91"],
      ["DEMO_TISSUE_002", "Healthy", "0.86"]
    ]
  },
  tissueOrigin: {
    modality: "Tissue biopsy",
    title: "Tissue Origin Identification",
    description: "在 36 个组织来源标签中识别样本所属组织，用于跨组织来源追踪和样本来源确认。",
    detail: "该任务仍然使用同样的 FPKM TSV 输入格式，但预测头会切换到 Tissue_origin.ckpt，输出 36 类组织来源标签，例如 Pancreas、Stomach、Lung 等。",
    output: "Pancreas",
    quickRows: [
      ["DEMO_TISSUE_001", "Pancreas", "0.67"],
      ["DEMO_TISSUE_002", "Stomach", "0.59"]
    ]
  },
  plasmaCancer: {
    modality: "Plasma biopsy",
    title: "Plasma Cancer Detection",
    description: "面向血浆样本的 FPKM 表达矩阵进行癌症二分类，适合液体活检展示场景。",
    detail: "用户上传的 plasma TSV 仍需是 FPKM 标准化后的表达矩阵。页面只做格式接收与展示，真实接入时会使用 Plasma_cancer_detect.ckpt 运行推理。",
    output: "Healthy",
    quickRows: [
      ["DEMO_PLASMA_001", "Healthy", "0.78"],
      ["DEMO_PLASMA_002", "Cancer", "0.74"]
    ]
  },
  plateletCancer: {
    modality: "Platelet biopsy",
    title: "Platelet Cancer Detection",
    description: "利用血小板转录组 FPKM 信号检测癌症状态，输出 Healthy 或 Cancer。",
    detail: "血小板癌症检测任务在推理逻辑中包含任务特定阈值。真实接入时，上传 TSV 会经过同样的数据整理流程后进入 Platelet_cancer_detect.ckpt。",
    output: "Cancer",
    quickRows: [
      ["DEMO_PLATELET_001", "Cancer", "0.83"],
      ["DEMO_PLATELET_002", "Healthy", "0.69"]
    ]
  },
  plateletLocal: {
    modality: "Platelet biopsy",
    title: "Platelet Tumor Localization",
    description: "在 HNSC、NSCLC、Glioma、PAAD、OV 五个标签中定位肿瘤来源。",
    detail: "该任务使用 Platelet_tumor_local.ckpt。输入仍是 FPKM TSV，网页端快速展示只返回预置结果，避免让用户误以为本地浏览器已经运行真实模型。",
    output: "NSCLC",
    quickRows: [
      ["DEMO_PLATELET_001", "NSCLC", "0.58"],
      ["DEMO_PLATELET_002", "PAAD", "0.51"]
    ]
  }
};

const taskTabs = document.querySelectorAll(".task-chip");
const taskModality = document.querySelector("#task-modality");
const taskTitle = document.querySelector("#task-title");
const taskDescription = document.querySelector("#task-description");
const taskDetail = document.querySelector("#task-detail");
const outputLabel = document.querySelector("#output-label");
const outputCore = document.querySelector("#output-core");
const outputChart = document.querySelector("#output-chart");
const sampleCards = document.querySelector("#sample-cards");
const uploadInput = document.querySelector("#tsv-upload");
const uploadStatus = document.querySelector("#upload-status");
const quickResults = document.querySelector("#quick-results");
const runDemo = document.querySelector("#run-demo");
const fileDialog = document.querySelector("#file-dialog");
const dialogSummary = document.querySelector("#file-dialog-summary");
const dialogPreview = document.querySelector("#file-dialog-preview");
const emailFile = document.querySelector("#email-file");
const downloadFile = document.querySelector("#download-file");
const canvas = document.querySelector("#expression-canvas");
const ctx = canvas.getContext("2d");

let activeTask = "tissueCancer";
let heatmapFrame = 0;
let selectedFileAction = null;

function renderTask(taskKey) {
  const task = taskData[taskKey];
  activeTask = taskKey;

  taskTabs.forEach((tab) => {
    const isActive = tab.dataset.task === taskKey;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  });

  taskModality.textContent = task.modality;
  taskTitle.textContent = task.title;
  taskDescription.textContent = task.description;
  taskDetail.textContent = task.detail;
  outputLabel.textContent = task.output;
  outputCore.textContent = task.modality.split(" ")[0];
  renderQuickPlaceholder();
}

function renderSampleCards() {
  sampleCards.innerHTML = sampleFiles.map((sample) => `
    <a class="sample-link" href="${sample.path}" download="${sample.file}">
      ${sample.file}
    </a>
  `).join("");
}

async function handleUpload(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  if (!file.name.toLowerCase().endsWith(".tsv")) {
    uploadStatus.textContent = "当前只接受 .tsv 文件。请上传已经完成 FPKM 标准化的 TSV。";
    return;
  }

  const previewText = await file.slice(0, 96000).text();
  const lines = previewText.split(/\r?\n/).filter(Boolean);
  const header = lines[0] || "";
  const columns = header.split("\t");
  const firstColumn = (columns[0] || "").trim().toLowerCase();
  const sampleCount = Math.max(0, columns.length - 1);
  const hasTabStructure = columns.length > 1;
  const hasGeneColumn = firstColumn === "geneid" || firstColumn === "gene_id" || firstColumn === "gene";

  const status = [];
  status.push(`${file.name}`);
  status.push(hasTabStructure ? `${sampleCount} sample columns detected` : "未检测到 tab 分隔列");
  if (!hasGeneColumn) status.push("建议第一列命名为 GeneID");
  uploadStatus.textContent = status.join(" · ");

  selectedFileAction = { type: "upload", file: file.name, blob: file };
  openFileDialog({
    title: `用户文件：${file.name}`,
    meta: `${formatBytes(file.size)} · ${sampleCount} 个样本列 · ${hasGeneColumn ? "GeneID column detected" : "GeneID column not detected"}`,
    preview: lines.slice(0, 5).join("\n")
  });
}

function openFileDialog({ title, meta, preview }) {
  dialogSummary.textContent = `${title}。${meta}`;
  dialogPreview.textContent = preview;
  if (typeof fileDialog.showModal === "function") {
    fileDialog.showModal();
  } else {
    fileDialog.setAttribute("open", "");
  }
}

function emailSelectedFile() {
  if (!selectedFileAction) return;
  const subject = `RNABag FPKM TSV: ${selectedFileAction.file}`;
  const body = [
    "您好，",
    "",
    "我希望提交或咨询以下 RNABag FPKM TSV 文件：",
    `文件名：${selectedFileAction.file}`,
    `来源：${selectedFileAction.type === "sample" ? "RNABag showcase 100-sample demo" : "user uploaded local TSV"}`,
    "",
    "说明：浏览器无法通过 mailto 自动附加本地文件，请在邮件客户端中手动添加 TSV 附件。",
    "",
    "RNABag showcase"
  ].join("\n");

  window.location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

function downloadSelectedFile() {
  if (!selectedFileAction) return;
  const link = document.createElement("a");

  if (selectedFileAction.type === "sample") {
    link.href = selectedFileAction.path;
  } else {
    link.href = URL.createObjectURL(selectedFileAction.blob);
  }

  link.download = selectedFileAction.file;
  document.body.appendChild(link);
  link.click();
  link.remove();

  if (selectedFileAction.type === "upload") {
    URL.revokeObjectURL(link.href);
  }
}

function renderQuickPlaceholder() {
  quickResults.className = "quick-results empty";
  quickResults.textContent = "点击运行快速展示后，这里会显示 2 个内置样本的预置结果。";
  outputChart.innerHTML = `
    <div class="chart-empty">
      <strong>${taskData[activeTask].modality.split(" ")[0]}</strong>
      <span>运行快速展示后，图形会根据 1-2 个样本的预置结果更新。</span>
    </div>
  `;
}

function runQuickDemo() {
  const rows = taskData[activeTask].quickRows;
  quickResults.className = "quick-results";
  quickResults.innerHTML = `
    <table class="quick-table">
      <thead>
        <tr>
          <th>Sample</th>
          <th>Prediction</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${row[0]}</td>
            <td>${row[1]}</td>
            <td>${row[2]}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  renderOutputChart(rows);
}

function renderOutputChart(rows) {
  const maxConfidence = Math.max(...rows.map((row) => Number(row[2])));
  outputChart.innerHTML = `
    <div class="result-bars">
      ${rows.map((row, index) => {
        const confidence = Number(row[2]);
        const width = `${Math.max(8, Math.round((confidence / maxConfidence) * 100))}%`;
        return `
          <div class="result-bar-row">
            <div class="bar-meta">
              <strong>${row[0]}</strong>
              <span>${row[1]} · ${row[2]}</span>
            </div>
            <div class="bar-track">
              <span style="--bar-width: ${width}; --bar-color: ${index === 0 ? "#2458d3" : "#14796f"};"></span>
            </div>
          </div>
        `;
      }).join("")}
    </div>
    <div class="result-flow">
      <span>FPKM TSV</span>
      <span>4096 HVGs</span>
      <span>${taskData[activeTask].title}</span>
    </div>
  `;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawExpressionCanvas() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);

  const left = 36;
  const top = 42;
  const gap = 4;
  const cols = 24;
  const rows = 17;
  const targetMatrixWidth = Math.min(width * 0.56, 390);
  const cell = Math.max(8, Math.min(13, Math.floor((targetMatrixWidth - (cols - 1) * gap) / cols)));

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  ctx.font = "12px SFMono-Regular, Consolas, monospace";
  ctx.fillStyle = "#79869a";
  ctx.fillText("expression matrix", left, top - 16);

  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const wave = Math.sin((x * 0.72) + (y * 0.45) + heatmapFrame * 0.026);
      const value = (wave + 1) / 2;
      const blue = Math.floor(72 + value * 128);
      const green = Math.floor(112 + value * 90);
      const red = Math.floor(34 + value * 54);
      ctx.fillStyle = `rgb(${red}, ${green}, ${blue})`;
      ctx.fillRect(left + x * (cell + gap), top + y * (cell + gap), cell, cell);
    }
  }

  const matrixWidth = cols * cell + (cols - 1) * gap;
  const matrixHeight = rows * cell + (rows - 1) * gap;
  const centerY = top + matrixHeight / 2;
  const matrixRight = left + matrixWidth;
  const nodeX = Math.max(matrixRight + 42, Math.floor(width * 0.68));
  const nodeW = Math.max(144, Math.min(190, width - nodeX - 34));
  const geneY = top + 4;
  const encoderY = top + 112;
  const headY = Math.min(height - 126, top + 238);

  ctx.strokeStyle = "#b8c3d3";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(matrixRight + 14, centerY);
  ctx.lineTo(nodeX - 18, centerY);
  ctx.lineTo(nodeX - 18, geneY + 32);
  ctx.lineTo(nodeX, geneY + 32);
  ctx.stroke();

  drawNode(nodeX, geneY, nodeW, 64, "Gene tokens", "4096 HVGs", "#eef3f8");
  drawNode(nodeX, encoderY, nodeW, 72, "RNABag", "8-layer encoder", "#f5fbfa");
  drawNode(nodeX, headY, nodeW, 72, "Task heads", "5 downstream tasks", "#fff8ee");

  ctx.strokeStyle = "#2458d3";
  ctx.beginPath();
  ctx.moveTo(nodeX + nodeW / 2, geneY + 64);
  ctx.lineTo(nodeX + nodeW / 2, encoderY);
  ctx.stroke();

  ctx.strokeStyle = "#14796f";
  ctx.beginPath();
  ctx.moveTo(nodeX + nodeW / 2, encoderY + 72);
  ctx.lineTo(nodeX + nodeW / 2, headY);
  ctx.stroke();

  heatmapFrame += 1;
  window.requestAnimationFrame(drawExpressionCanvas);
}

function drawNode(x, y, width, height, title, subtitle, fill) {
  ctx.fillStyle = fill;
  ctx.strokeStyle = "#dbe2ec";
  ctx.lineWidth = 1;
  roundRect(x, y, width, height, 8);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "#18212f";
  ctx.font = "700 14px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillText(title, x + 16, y + 30);
  ctx.fillStyle = "#536174";
  ctx.font = "12px SFMono-Regular, Consolas, monospace";
  ctx.fillText(subtitle, x + 16, y + 54);
}

function roundRect(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

taskTabs.forEach((tab) => {
  tab.addEventListener("click", () => renderTask(tab.dataset.task));
});

uploadInput.addEventListener("change", handleUpload);
runDemo.addEventListener("click", runQuickDemo);
emailFile.addEventListener("click", emailSelectedFile);
downloadFile.addEventListener("click", downloadSelectedFile);
window.addEventListener("resize", resizeCanvas);

renderSampleCards();
renderTask(activeTask);
resizeCanvas();
drawExpressionCanvas();
