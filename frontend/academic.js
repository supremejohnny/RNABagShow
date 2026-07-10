const academicTasks = {
  tissue_cancer_detect: {
    title: "tissue_cancer_detect",
    modality: "Tissue",
    labels: "2",
    checkpoint: "Tissue_cancer_detect.ckpt",
    result: "Cancer",
    output: "Healthy / Cancer",
    command: "python infer_code/main.py --task tissue_cancer_detect --device cuda"
  },
  tissue_origin: {
    title: "tissue_origin",
    modality: "Tissue",
    labels: "36",
    checkpoint: "Tissue_origin.ckpt",
    result: "Pancreas",
    output: "36 tissue-origin classes",
    command: "python infer_code/main.py --task tissue_origin --device cuda"
  },
  plasma_cancer_detect: {
    title: "plasma_cancer_detect",
    modality: "Plasma",
    labels: "2",
    checkpoint: "Plasma_cancer_detect.ckpt",
    result: "Healthy",
    output: "Healthy / Cancer",
    command: "python infer_code/main.py --task plasma_cancer_detect --device cuda"
  },
  platelet_cancer_detect: {
    title: "platelet_cancer_detect",
    modality: "Platelet",
    labels: "2",
    checkpoint: "Platelet_cancer_detect.ckpt",
    result: "Cancer",
    output: "Healthy / Cancer, threshold=0.003955459",
    command: "python infer_code/main.py --task platelet_cancer_detect --device cuda"
  },
  platelet_tumor_local: {
    title: "platelet_tumor_local",
    modality: "Platelet",
    labels: "5",
    checkpoint: "Platelet_tumor_local.ckpt",
    result: "NSCLC",
    output: "HNSC / NSCLC / Glioma / PAAD / OV",
    command: "python infer_code/main.py --task platelet_tumor_local --device cuda"
  }
};

function setText(root, selector, value) {
  const node = root.querySelector(selector);
  if (node) node.textContent = value;
}

function renderAcademicTask(root, taskKey) {
  const task = academicTasks[taskKey] || academicTasks.tissue_cancer_detect;

  root.querySelectorAll("[data-academic-task]").forEach((button) => {
    const isActive = button.dataset.academicTask === taskKey;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  setText(root, "[data-demo-title]", task.title);
  setText(root, "[data-demo-modality]", task.modality);
  setText(root, "[data-demo-labels]", task.labels);
  setText(root, "[data-demo-checkpoint]", task.checkpoint);
  setText(root, "[data-demo-result]", task.result);
  setText(root, "[data-demo-output]", task.output);
  setText(root, "[data-demo-command]", task.command);

  document.querySelectorAll("[data-task-row]").forEach((row) => {
    row.classList.toggle("is-highlighted", row.dataset.taskRow === taskKey);
  });
}

document.querySelectorAll("[data-academic-demo]").forEach((root) => {
  root.querySelectorAll("[data-academic-task]").forEach((button) => {
    button.addEventListener("click", () => renderAcademicTask(root, button.dataset.academicTask));
  });

  const activeButton = root.querySelector("[data-academic-task].is-active") || root.querySelector("[data-academic-task]");
  if (activeButton) renderAcademicTask(root, activeButton.dataset.academicTask);
});
