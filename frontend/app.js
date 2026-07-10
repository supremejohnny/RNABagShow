const taskData = {
  tissueCancer: {
    modality: "Tissue biopsy",
    title: "Tissue Cancer Detection",
    description: "基于组织 RNA 表达谱判断样本是否呈现癌症信号，输出 Healthy 或 Cancer。",
    command: "python infer_code/main.py --task tissue_cancer_detect --device cuda",
    input: "log1p_tissue.npy | 4096 genes | batch size 8",
    checkpoint: "Tissue_cancer_detect.ckpt",
    result: "Cancer",
    scores: [
      { label: "Cancer", value: 0.91, color: "#2458d3" },
      { label: "Healthy", value: 0.09, color: "#14796f" }
    ],
    logs: [
      ["info", "load config: task=tissue_cancer_detect, n_labels=2"],
      ["ok", "read processed matrix: log1p_tissue.npy"],
      ["info", "load checkpoint: Tissue_cancer_detect.ckpt"],
      ["ok", "softmax logits -> Cancer"]
    ]
  },
  tissueOrigin: {
    modality: "Tissue biopsy",
    title: "Tissue Origin Identification",
    description: "在 36 个组织来源标签中识别样本所属组织，用于跨癌种和来源追踪场景。",
    command: "python infer_code/main.py --task tissue_origin --device cuda",
    input: "log1p_tissue.npy | tissue metadata | 36 candidate labels",
    checkpoint: "Tissue_origin.ckpt",
    result: "Pancreas",
    scores: [
      { label: "Pancreas", value: 0.67, color: "#2458d3" },
      { label: "Stomach", value: 0.16, color: "#9b6b12" },
      { label: "Colon", value: 0.10, color: "#14796f" },
      { label: "Liver", value: 0.07, color: "#b63a55" }
    ],
    logs: [
      ["info", "load config: task=tissue_origin, n_labels=36"],
      ["ok", "map prediction ids with key_to_tissue_origin"],
      ["info", "load checkpoint: Tissue_origin.ckpt"],
      ["ok", "top class -> Pancreas"]
    ]
  },
  plasmaCancer: {
    modality: "Plasma biopsy",
    title: "Plasma Cancer Detection",
    description: "面向血浆来源的转录组信号进行癌症二分类，适合液体活检展示场景。",
    command: "python infer_code/main.py --task plasma_cancer_detect --device cuda",
    input: "log1p_plasma.npy | 4096 genes | normalized expression",
    checkpoint: "Plasma_cancer_detect.ckpt",
    result: "Healthy",
    scores: [
      { label: "Healthy", value: 0.78, color: "#14796f" },
      { label: "Cancer", value: 0.22, color: "#2458d3" }
    ],
    logs: [
      ["info", "load config: task=plasma_cancer_detect, n_labels=2"],
      ["ok", "read plasma expression features"],
      ["info", "load checkpoint: Plasma_cancer_detect.ckpt"],
      ["ok", "softmax logits -> Healthy"]
    ]
  },
  plateletCancer: {
    modality: "Platelet biopsy",
    title: "Platelet Cancer Detection",
    description: "利用血小板 RNA 表达谱检测癌症信号，推理逻辑中包含任务特定阈值判定。",
    command: "python infer_code/main.py --task platelet_cancer_detect --device cuda",
    input: "log1p_platelet.npy | platelet transcriptome | thresholded probability",
    checkpoint: "Platelet_cancer_detect.ckpt",
    result: "Cancer",
    scores: [
      { label: "Cancer", value: 0.83, color: "#2458d3" },
      { label: "Healthy", value: 0.17, color: "#14796f" }
    ],
    logs: [
      ["info", "load config: task=platelet_cancer_detect, n_labels=2"],
      ["ok", "apply platelet threshold: 0.003955459"],
      ["info", "load checkpoint: Platelet_cancer_detect.ckpt"],
      ["ok", "thresholded output -> Cancer"]
    ]
  },
  plateletLocal: {
    modality: "Platelet biopsy",
    title: "Platelet Tumor Localization",
    description: "在 HNSC、NSCLC、Glioma、PAAD、OV 五个标签中定位肿瘤来源。",
    command: "python infer_code/main.py --task platelet_tumor_local --device cuda",
    input: "log1p_platelet.npy | 5 candidate tumor locations",
    checkpoint: "Platelet_tumor_local.ckpt",
    result: "NSCLC",
    scores: [
      { label: "NSCLC", value: 0.58, color: "#2458d3" },
      { label: "PAAD", value: 0.18, color: "#9b6b12" },
      { label: "HNSC", value: 0.13, color: "#14796f" },
      { label: "OV", value: 0.07, color: "#b63a55" },
      { label: "Glioma", value: 0.04, color: "#536174" }
    ],
    logs: [
      ["info", "load config: task=platelet_tumor_local, n_labels=5"],
      ["ok", "map prediction ids with key_to_platelet_tumor_local"],
      ["info", "load checkpoint: Platelet_tumor_local.ckpt"],
      ["ok", "top class -> NSCLC"]
    ]
  }
};

const taskTabs = document.querySelectorAll(".task-tab");
const taskModality = document.querySelector("#task-modality");
const taskTitle = document.querySelector("#task-title");
const taskDescription = document.querySelector("#task-description");
const taskCommand = document.querySelector("#task-command");
const sampleInput = document.querySelector("#sample-input");
const checkpoint = document.querySelector("#checkpoint");
const resultLabel = document.querySelector("#result-label");
const scoreList = document.querySelector("#score-list");
const consoleLog = document.querySelector("#console-log");
const runDemo = document.querySelector("#run-demo");
const resetDemo = document.querySelector("#reset-demo");
const canvas = document.querySelector("#expression-canvas");
const ctx = canvas.getContext("2d");

let activeTask = "tissueCancer";
let logTimer = null;
let heatmapFrame = 0;

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
  taskCommand.textContent = task.command;
  sampleInput.textContent = task.input;
  checkpoint.textContent = task.checkpoint;
  resultLabel.textContent = task.result;

  scoreList.innerHTML = task.scores.map((score) => {
    const width = `${Math.round(score.value * 100)}%`;
    return `
      <div class="score-row">
        <span>${score.label}</span>
        <span class="score-bar" aria-hidden="true">
          <span style="--score: ${width}; --bar-color: ${score.color};"></span>
        </span>
        <span>${width}</span>
      </div>
    `;
  }).join("");

  resetConsole();
}

function resetConsole() {
  window.clearInterval(logTimer);
  logTimer = null;
  consoleLog.innerHTML = '<div class="console-line">ready: static showcase mode</div>';
  runDemo.disabled = false;
}

function runTaskDemo() {
  const task = taskData[activeTask];
  let index = 0;
  consoleLog.innerHTML = "";
  runDemo.disabled = true;

  logTimer = window.setInterval(() => {
    const entry = task.logs[index];
    if (!entry) {
      window.clearInterval(logTimer);
      logTimer = null;
      runDemo.disabled = false;
      return;
    }

    const line = document.createElement("div");
    line.className = `console-line ${entry[0]}`;
    line.textContent = entry[1];
    consoleLog.appendChild(line);
    consoleLog.scrollTop = consoleLog.scrollHeight;
    index += 1;
  }, 430);
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

runDemo.addEventListener("click", runTaskDemo);
resetDemo.addEventListener("click", resetConsole);
window.addEventListener("resize", resizeCanvas);

renderTask(activeTask);
resizeCanvas();
drawExpressionCanvas();
