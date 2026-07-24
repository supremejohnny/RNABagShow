(() => {
  const runtimeConfig = window.RNABAG_RUNTIME_CONFIG || {};
  const publicPreview = runtimeConfig.mode === "public-preview";
  const localHostname = ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
  const publicHosts = Array.isArray(runtimeConfig.publicHosts) ? runtimeConfig.publicHosts : [];
  const publicApp = runtimeConfig.mode === "full" && ["http:", "https:"].includes(window.location.protocol) && publicHosts.includes(window.location.hostname);
  const params = new URLSearchParams(window.location.search);
  const variant = document.body.dataset.variant || "two";
  const isLab = params.get("mode") === "lab" || variant === "lab";
  document.body.classList.toggle("lab-mode", isLab);
  document.body.classList.toggle("public-preview", publicPreview);
  document.body.classList.toggle("public-app", publicApp);

  const backendOrigin = "http://127.0.0.1:8000";
  let apiBaseUrl = publicPreview ? "" : window.location.protocol === "file:" ? backendOrigin : "";
  const apiUrl = path => `${apiBaseUrl}${path}`;
  const apiBaseReady = publicPreview ? Promise.resolve() : window.location.protocol !== "file:" && localHostname ? fetch("/api/v1/health/live", { cache: "no-store" })
    .then(async response => {
      const payload = await response.json().catch(() => ({}));
      apiBaseUrl = response.ok && payload.status === "ok" && payload.mode === "checkpoint" ? "" : backendOrigin;
    })
    .catch(() => { apiBaseUrl = backendOrigin; }) : Promise.resolve();
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const sampleData = {
    tissue: { apiPath: "/api/v1/demo-data/tissue", filename: "tissue_sample_fpkm_to_joh.tsv", label: "tissue RNA", sampleCount: 12 },
    platelet: { apiPath: "/api/v1/demo-data/platelet", filename: "Platelet_sample_to_joh.tsv", label: "platelet RNA", sampleCount: 3 }
  };
  const inputs = {
    tissue: {
      label: "tissue", subtitle: "组织 RNA", icon: "TI", enabled: true,
      tasks: {
        cancer: { title: "Tissue Cancer Detection", apiTask: "tissue_cancer_detection", sampleKey: "tissue", description: "评估组织来源的 bulk RNA expression profile 是否呈现癌症相关转录信号，适用于研究队列中的癌症状态分层。", specs: ["Input: tissue-derived bulk RNA-seq", "Head: binary classification", "Labels: Healthy / Cancer", "Representation: 4096 HVGs", "Output: class probability"], expected: "Healthy / Cancer", type: "binary" },
        origin: { title: "Tissue Origin Identification", apiTask: "tissue_origin_identification", sampleKey: "tissue", description: "根据全转录组表达特征推断样本最可能的组织来源，用于跨组织来源追踪、样本注释与 provenance confirmation。", specs: ["Input: tissue-derived bulk RNA-seq", "Head: 36-class classification", "Labels: tissue-origin ontology", "Representation: 4096 HVGs", "Output: ranked probabilities"], expected: "36 tissue classes", type: "rank" },
        originDetect: { title: "Origin and Detect", apiTask: "tissue_origin_and_cancer_detection", sampleKey: "tissue", description: "对每个 tissue 样本先使用 Tissue_origin checkpoint 溯源，再使用 Tissue_cancer_detect checkpoint 输出 Healthy / Cancer，同时保留两个阶段的概率。", specs: ["Input: tissue-derived bulk RNA-seq", "Stage 1: 36-class tissue origin", "Stage 2: binary cancer detection", "Checkpoints: Tissue_origin → Tissue_cancer_detect", "Output: paired sample-level predictions"], expected: "Tissue origin + Healthy / Cancer", type: "workflow" }
      }
    },
    plasma: {
      label: "plasma", subtitle: "血浆 RNA", icon: "PL", enabled: true,
      tasks: { cancer: { title: "Plasma Cancer Detection", apiTask: "plasma_cancer_detection", sampleKey: "plasma", description: "识别 plasma-derived RNA expression matrix 中的癌症相关信号，为 minimally invasive liquid-biopsy 研究提供分层依据。本任务仅供研究使用，不用于临床诊断，且当前无内置示例数据。", specs: ["Input: plasma-derived RNA", "Head: binary classification", "Labels: Healthy / Cancer", "Representation: 4096 HVGs", "Output: class probability"], expected: "Healthy / Cancer", type: "binary" } }
    },
    platelet: {
      label: "platelet", subtitle: "血小板 RNA", icon: "PT", enabled: true,
      tasks: {
        cancer: { title: "Platelet Cancer Detection", apiTask: "platelet_cancer_detection", sampleKey: "platelet", description: "利用 tumor-educated platelet 的转录组重编程信号评估癌症状态，捕捉循环系统中的肿瘤相关分子响应。", specs: ["Input: platelet-derived RNA", "Head: thresholded binary classifier", "Labels: Healthy / Cancer", "Biology: tumor-educated platelets", "Output: class probability"], expected: "Healthy / Cancer", type: "binary" },
        location: { title: "Tumor Localization", apiTask: "platelet_tumor_localization", sampleKey: "platelet", description: "基于血小板转录组特征定位最可能的肿瘤来源，为后续组织学验证提供候选器官或癌种假设。", specs: ["Input: platelet-derived RNA", "Head: 5-class classification", "Labels: HNSC / NSCLC / Glioma / PAAD / OV", "Biology: tumor-educated platelets", "Output: ranked probabilities"], expected: "HNSC / NSCLC / Glioma / PAAD / OV", type: "rank" }
      }
    }
  };
  const taskLabels = { cancer: "Cancer detection", origin: "Tissue origin · 36 classes", originDetect: "Origin and Detect", location: "Tumor localization · 5 classes" };
  const defaultTasks = { tissue: "originDetect", platelet: "cancer" };
  const state = { activeInput: "tissue", activeTask: defaultTasks.tissue, selectedFile: null, runToken: 0, preflightToken: 0, analysisId: null, status: "ready", lastStatus: "" };
  let programmaticStep = null;
  let programmaticSettleTimer = 0;

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" })[character]);
  }
  function currentTask() { return inputs[state.activeInput].tasks[state.activeTask]; }
  function currentTaskHasDemo() { return Boolean(sampleData[currentTask().sampleKey]); }
  function stepNode(step) { return document.getElementById(step); }
  function panelNode(step) { return $(`[data-panel-step="${step}"]`); }
  function ui(step, selector) { return $(selector, panelNode(step) || document); }
  function workflowSteps() { return $$("[data-workflow-step]"); }
  function compactLayout() { return window.matchMedia("(max-width: 759px)").matches; }
  function scrollNodeForStep(step) { return compactLayout() ? panelNode(step) : stepNode(step); }
  function scrollStepNodes() { return compactLayout() ? $$('[data-panel-step]') : workflowSteps(); }
  function stepForScrollNode(node) { return node?.dataset.panelStep || node?.id || "step-input"; }
  function workflowOffset() {
    return (isLab ? 0 : ($(".nav")?.offsetHeight || 0)) + ($(".workflow-nav")?.offsetHeight || 0);
  }
  function setStepStates() {
    const states = {
      "step-input": "complete",
      "step-task": "complete",
      "step-validate": state.selectedFile ? "complete" : "available",
      "step-result": state.status === "succeeded" ? "complete" : state.status === "failed" ? "needs-attention" : "available"
    };
    $$('[data-step-state]').forEach(node => {
      const value = states[node.dataset.stepState] || "available";
      node.dataset.state = value;
      node.textContent = value === "complete" ? "Complete" : value === "needs-attention" ? "Needs attention" : "Open";
    });
  }
  function setActiveStep(step, source = "scroll") {
    $$('[data-step-target]').forEach(link => {
      const active = link.dataset.stepTarget === step;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "step");
      else link.removeAttribute("aria-current");
    });
    $$('[data-workflow-step]').forEach(node => node.classList.toggle("active", node.id === step));
    if (variant === "two") setActivePanel(step);
    document.body.dataset.activeStep = step;
    if (source === "natural") history.replaceState(null, "", `#${step}`);
  }
  function setActivePanel(step) {
    const compact = compactLayout();
    $$('[data-panel-step]').forEach(panel => {
      const active = panel.dataset.panelStep === step;
      panel.classList.toggle("active", active);
      panel.classList.toggle("compact-visible", compact);
      panel.setAttribute("aria-hidden", compact ? "false" : String(!active));
      panel.inert = compact ? false : !active;
    });
  }
  function naturalStepAtProbe(nodes = scrollStepNodes()) {
    const probe = workflowOffset() + Math.min(innerHeight * .3, 220);
    let active = nodes[0];
    nodes.forEach(node => { if (node.getBoundingClientRect().top <= probe) active = node; });
    return stepForScrollNode(active);
  }
  function settleProgrammaticScroll() {
    window.clearTimeout(programmaticSettleTimer);
    programmaticSettleTimer = window.setTimeout(() => {
      const intendedStep = programmaticStep;
      programmaticStep = null;
      if (!intendedStep) return;
      const target = scrollNodeForStep(intendedStep);
      const reachedTarget = target && Math.abs(target.getBoundingClientRect().top - workflowOffset()) <= 24;
      setActiveStep(reachedTarget ? intendedStep : naturalStepAtProbe(), reachedTarget ? "programmatic" : "natural");
    }, reducedMotion.matches ? 40 : 160);
  }
  function scrollToStep(step, mode = "replace") {
    if (variant === "lab") {
      if (mode === "push") history.pushState(null, "", `#${step}`);
      else history.replaceState(null, "", `#${step}`);
      programmaticStep = null;
      setActiveStep(step, "programmatic");
      return;
    }
    const target = scrollNodeForStep(step);
    if (!target) return;
    if (mode === "replace") history.replaceState(null, "", `#${step}`);
    else if (mode === "push") history.pushState(null, "", `#${step}`);
    programmaticStep = step;
    setActiveStep(step, "programmatic");
    const top = window.scrollY + target.getBoundingClientRect().top - workflowOffset();
    window.scrollTo({ top: Math.max(0, top), behavior: reducedMotion.matches ? "auto" : "smooth" });
    settleProgrammaticScroll();
  }
  window.rnabagScrollToStep = scrollToStep;

  function renderInputs() {
    $$(".js-input-list").forEach(list => {
      list.innerHTML = Object.entries(inputs).map(([key, item]) => `<button class="input-card ${key === state.activeInput ? "active" : ""}" data-input="${key}" type="button" ${item.enabled ? "" : "disabled"}><span class="input-icon">${item.icon}</span><span class="input-name"><strong>${item.label}</strong><span>${item.subtitle}</span></span><span class="input-count">${item.enabled ? `${Object.keys(item.tasks).length} task${Object.keys(item.tasks).length > 1 ? "s" : ""}` : "Coming soon"}</span></button>`).join("");
      $$('[data-input]', list).forEach(button => button.addEventListener("click", () => selectInput(button.dataset.input)));
    });
  }
  function renderTasks() {
    const tasks = inputs[state.activeInput].tasks;
    if (!tasks[state.activeTask]) state.activeTask = Object.keys(tasks)[0];
    $$(".js-task-list").forEach(list => {
      list.innerHTML = Object.keys(tasks).map(key => `<button class="task-choice ${key === state.activeTask ? "active" : ""}" data-task="${key}" type="button"><strong>${taskLabels[key]}</strong><span>${tasks[key].specs[1] || "Prediction head"}</span></button>`).join("");
      $$('[data-task]', list).forEach(button => button.addEventListener("click", () => selectTask(button.dataset.task)));
    });
  }
  function renderTaskDetail() {
    const input = inputs[state.activeInput];
    const task = currentTask();
    $$(".js-task-modality").forEach(node => { node.textContent = input.subtitle; });
    $$(".js-task-title").forEach(node => { node.textContent = task.title; });
    $$(".js-task-description").forEach(node => { node.textContent = task.description; });
    $$(".js-task-specs").forEach(list => { list.innerHTML = task.specs.map(item => `<li>${escapeHtml(item)}</li>`).join(""); });
    $$(".js-api-key").forEach(node => { node.textContent = `input: ${state.activeInput}`; });
    $$(".js-modality-rule").forEach(node => { node.textContent = `样本模态：${state.activeInput} only`; });
    $$(".js-modality-help").forEach(node => { node.textContent = `一个文件中请勿混入其他模态；该任务只接受 ${input.subtitle}。`; });
    $$(".js-expected-output").forEach(node => { node.textContent = task.expected; });
    const sample = sampleData[task.sampleKey];
    if (sample) {
      $$(".js-sample-description").forEach(node => { node.textContent = publicPreview ? "公网预览阶段不提供示例数据下载或推理。" : `${task.title} 使用已验证的 ${sample.label} ${sample.sampleCount}-sample FPKM matrix，可用于检查数据结构与快速演示。`; });
      $$(".js-sample-link").forEach(link => {
        if (publicPreview) {
          link.removeAttribute("href");
          link.removeAttribute("download");
          link.setAttribute("aria-disabled", "true");
          const label = $("span", link);
          if (label) label.textContent = "Example dataset 暂未开放";
        } else {
          link.href = apiUrl(sample.apiPath);
          link.download = sample.filename;
          link.removeAttribute("aria-disabled");
        }
      });
      $$(".js-demo-run").forEach(button => { button.disabled = publicPreview; button.textContent = publicPreview ? "Demo 暂未开放" : "Use Demo Data"; button.setAttribute("aria-label", `Use Demo Data for ${task.title}`); });
    } else {
      $$(".js-sample-description").forEach(node => { node.textContent = "Plasma 示例数据暂未提供，请使用自有 FPKM TSV 文件进行分析。"; });
      $$(".js-sample-link").forEach(link => {
        link.removeAttribute("href");
        link.removeAttribute("download");
        link.setAttribute("aria-disabled", "true");
        const label = $("span", link);
        if (label) label.textContent = "示例数据暂未开放";
      });
      $$(".js-demo-run").forEach(button => { button.disabled = true; button.textContent = "Demo 暂未提供"; button.setAttribute("aria-label", "Plasma 示例数据暂未提供"); });
    }
    $$(".js-demo-hint").forEach(hint => { hint.textContent = sample ? (publicPreview ? "（公网预览不接收文件）" : "（没有文件？试试我们的 demo data↓）") : "（请使用自有 FPKM TSV 文件进行分析）"; });
    clearFile(false);
    resetResult();
    updateContext();
  }
  function selectInput(key) {
    state.activeInput = key;
    state.activeTask = inputs[key].tasks[defaultTasks[key]] ? defaultTasks[key] : Object.keys(inputs[key].tasks)[0];
    state.runToken += 1;
    renderInputs(); renderTasks(); renderTaskDetail();
    scrollToStep("step-task");
  }
  function selectTask(key) {
    state.activeTask = key;
    state.runToken += 1;
    renderTasks(); renderTaskDetail();
  }
  function confirmTask() {
    scrollToStep("step-validate");
  }
  function setValidation(message, kind = "") {
    $$(".js-validation").forEach(box => { box.className = `validation ${kind ? `show ${kind}` : ""}`; box.textContent = message; });
  }
  function updateFileUploadUI() {
    const hasFile = !!state.selectedFile;
    $$(".js-validate-submit").forEach(box => {
      box.style.display = (hasFile && !publicPreview) ? "" : "none";
    });
    $$(".js-run").forEach(button => {
      button.disabled = publicPreview || !hasFile;
      button.textContent = publicPreview ? "推理服务暂未开放" : publicApp ? "提交公共分析" : "提交本地分析";
    });
    $$(".js-dropzone").forEach(dz => {
      dz.classList.toggle("has-file", hasFile);
      const icon = $(".drop-icon", dz);
      const title = $("strong", dz);
      const hint = $(".js-dropzone-hint", dz);
      if (hasFile && state.selectedFile) {
        if (icon) icon.textContent = "✓";
        if (title) title.textContent = "文件格式验证完成";
        if (hint) hint.textContent = `${state.selectedFile.name} · 可提交${publicApp ? "公共分析" : "本地分析"}`;
      } else {
        const def = dropzoneDefaultContent();
        if (icon) icon.textContent = def.icon;
        if (title) title.textContent = def.title;
        if (hint) hint.textContent = def.hint;
      }
    });
  }
  function dropzoneDefaultContent() {
    if (publicPreview) return { icon: "↑", title: "文件上传暂未开放", hint: "（公网预览不接收文件）" };
    if (publicApp) return { icon: "↑", title: "拖入或选择 FPKM .tsv", hint: "浏览器先预检；提交后由 RNABag API 完整校验" };
    return { icon: "↑", title: "拖入或选择 FPKM .tsv", hint: "浏览器先预检；提交后由本地 API 完整校验" };
  }
  function clearFile(announce = true) {
    state.preflightToken += 1;
    state.selectedFile = null;
    state.analysisId = null;
    $$(".js-file-input").forEach(input => { input.value = ""; });
    if (announce) setValidation("");
    setStepStates();
    updateFileUploadUI();
  }
  function resetResult() {
    state.status = "ready";
    $$(".js-result-title").forEach(node => { node.textContent = publicPreview ? "Public preview" : "Prediction preview"; });
    $$(".js-result-badge").forEach(node => { node.textContent = publicPreview ? "INFERENCE OFFLINE" : "RNABAG CHECKPOINT"; });
    $$(".js-chart").forEach(chart => {
      chart.classList.remove("has-results");
      chart.innerHTML = `<div class="empty-chart"><div class="empty-orbit"></div><p>${publicPreview ? "公网预览仅展示产品与任务界面，暂不接收文件或运行推理。" : publicApp ? "选择 TSV 并提交临时公共分析，查看完整预处理与 checkpoint 输出。" : "选择 TSV 并提交本地分析，查看完整预处理与 checkpoint 输出。"}</p></div>`;
    });
    $$(".js-result-summary").forEach(box => { box.innerHTML = `<small>Expected output</small><strong>${escapeHtml(currentTask().expected)}</strong>`; });
    const hasDemo = currentTaskHasDemo();
    $$(".js-demo-run").forEach(button => { button.disabled = publicPreview || !hasDemo; button.textContent = publicPreview ? "Demo 暂未开放" : (!hasDemo ? "Demo 暂未提供" : "Use Demo Data"); });
    updateContext(); setStepStates(); updateFileUploadUI();
  }
  function setRunState(running, label = publicApp ? "提交公共分析" : "提交本地分析") {
    $$(".js-run").forEach(button => { button.disabled = publicPreview || running; button.textContent = publicPreview ? "推理服务暂未开放" : label; });
    $$(".js-demo-run").forEach(button => { button.disabled = publicPreview || running || !currentTaskHasDemo(); });
  }
  function setDemoRunState(running, label = "Use Demo Data") {
    $$(".js-demo-run").forEach(button => { button.disabled = running || !currentTaskHasDemo(); button.textContent = label; });
  }
  function showProgress(message) {
    $$(".js-result-title").forEach(node => { node.textContent = publicApp ? "Public analysis" : "Local analysis"; });
    $$(".js-chart").forEach(chart => {
      chart.classList.remove("has-results");
      chart.innerHTML = `<div class="empty-chart"><div class="empty-orbit"></div><p>${escapeHtml(message)}</p></div>`;
    });
    updateContext(message);
  }
  function apiErrorMessage(payload, fallback) {
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
    if (payload?.message) return payload.message;
    return fallback;
  }
  async function readJson(response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiErrorMessage(payload, `API request failed (${response.status})`));
    return payload;
  }
  function renderResult(result) {
    const task = currentTask();
    const predictions = Array.isArray(result.predictions) ? result.predictions : [];
    if (!predictions.length) throw new Error("API returned no sample predictions.");
    const sampleResults = predictions.map((prediction, sampleIndex) => {
      if (task.type === "workflow") {
        const origin = prediction.origin || {};
        const cancer = prediction.cancer_detection || {};
        const originScores = Array.isArray(origin.scores) ? origin.scores : [];
        const cancerScores = Array.isArray(cancer.scores) ? cancer.scores : [];
        if (!originScores.length || !cancerScores.length) throw new Error("API returned an incomplete workflow prediction.");
        const originRows = originScores.slice(0, 5).map(item => ({ label: escapeHtml(item.label), value: Math.round(item.score * 1000) / 10 }));
        const cancerRows = cancerScores.slice(0, 2).map(item => ({ label: escapeHtml(item.label), value: Math.round(item.score * 1000) / 10 }));
        const originWinner = originScores.find(item => item.label === origin.predicted_label) || originScores[0];
        const cancerWinner = cancerScores.find(item => item.label === cancer.predicted_label) || cancerScores[0];
        const originValue = Math.round(originWinner.score * 1000) / 10;
        const cancerValue = Math.round(cancerWinner.score * 1000) / 10;
        const originChart = originRows.map(row => `<div class="rank-row"><strong>${row.label}</strong><div class="bar"><i data-width="${row.value}"></i></div><span>${row.value}%</span></div>`).join("");
        const cancerChart = cancerRows.map((row, index) => `<div class="probability ${index ? "secondary" : ""}"><div class="prob-meta"><strong>${row.label}</strong><span>${row.value}%</span></div><div class="bar"><i data-width="${row.value}"></i></div></div>`).join("");
        return `<section class="sample-result" role="listitem"><header class="sample-result-head"><div><small>Sample ${sampleIndex + 1} / ${predictions.length}</small><strong>${escapeHtml(prediction.sample_id)}</strong></div><span>${escapeHtml(origin.predicted_label)} → ${escapeHtml(cancer.predicted_label)}</span></header><div class="sample-score-list"><div class="workflow-stage"><div class="workflow-stage-head"><small>01 · Origin</small><strong>${escapeHtml(origin.predicted_label)} · ${originValue}%</strong></div>${originChart}</div><div class="workflow-stage"><div class="workflow-stage-head"><small>02 · Detect</small><strong>${escapeHtml(cancer.predicted_label)} · ${cancerValue}%</strong></div>${cancerChart}</div></div></section>`;
      }
      const scores = Array.isArray(prediction.scores) ? prediction.scores : [];
      const rows = scores.slice(0, task.type === "binary" ? 2 : 5).map(item => ({ label: escapeHtml(item.label), value: Math.round(item.score * 1000) / 10 }));
      const predicted = scores.find(item => item.label === prediction.predicted_label) || scores[0];
      const predictedValue = predicted ? Math.round(predicted.score * 1000) / 10 : 0;
      const chartRows = task.type === "binary"
        ? rows.map((row, index) => `<div class="probability ${index ? "secondary" : ""}"><div class="prob-meta"><strong>${row.label}</strong><span>${row.value}%</span></div><div class="bar"><i data-width="${row.value}"></i></div></div>`).join("")
        : rows.map(row => `<div class="rank-row"><strong>${row.label}</strong><div class="bar"><i data-width="${row.value}"></i></div><span>${row.value}%</span></div>`).join("");
      return `<section class="sample-result" role="listitem"><header class="sample-result-head"><div><small>Sample ${sampleIndex + 1} / ${predictions.length}</small><strong>${escapeHtml(prediction.sample_id)}</strong></div><span>${escapeHtml(prediction.predicted_label)} · ${predictedValue}%</span></header><div class="sample-score-list">${chartRows}</div></section>`;
    }).join("");
    $$(".js-chart").forEach(chart => {
      chart.classList.add("has-results");
      chart.innerHTML = `<div class="sample-results" role="list" aria-label="${predictions.length} sample predictions">${sampleResults}</div>`;
    });
    $$(".js-result-title").forEach(node => { node.textContent = "RNABag sample predictions"; });
    $$(".js-result-badge").forEach(node => { node.textContent = "CHECKPOINT"; });
    $$(".js-result-summary").forEach(box => { box.innerHTML = `<small>Sample-level predictions</small><strong>${predictions.length} / ${result.input_summary.sample_count} samples completed</strong>`; });
    requestAnimationFrame(() => $$("[data-width]").forEach(bar => { bar.style.width = `${bar.dataset.width}%`; }));
    const summary = result.input_summary;
    const duplicateText = summary.duplicate_gene_rows ? `；检出 ${summary.duplicate_gene_rows} 个重复 GeneID 行，按输入顺序保留第一次出现并丢弃后续重复行` : "";
    setValidation(`✓ 服务端完整校验 · ${summary.gene_rows} 个基因行 · ${summary.sample_count} 个样本 · GeneID 映射 ${summary.mapped_unique_gene_ids}/${summary.unique_gene_ids} · HVG ${summary.model_hvg_found}/${summary.model_hvg_total}${duplicateText}`, summary.duplicate_gene_rows ? "warn" : "ok");
    state.status = "succeeded";
    updateContext(); setStepStates();
  }
  async function runAnalysis() {
    if (publicPreview) return;
    if (!state.selectedFile) { setValidation("请先选择一个通过基础预检的 .tsv 文件。", "warn"); scrollToStep("step-validate"); return; }
    const task = currentTask();
    const token = ++state.runToken;
    state.status = "queued";
    setRunState(true, "正在上传…");
    showProgress(`正在将 TSV 发送给 ${publicApp ? "RNABag 公共 API" : "本地 RNABag API"}…`);
    scrollToStep("step-result");
    try {
      await apiBaseReady;
      const created = await readJson(await fetch(apiUrl(`/api/v1/analyses?task=${encodeURIComponent(task.apiTask)}`), { method: "POST", headers: { "Content-Type": "text/tab-separated-values", "X-RNABag-Filename": encodeURIComponent(state.selectedFile.name) }, body: state.selectedFile }));
      state.analysisId = created.analysis_id;
      while (token === state.runToken) {
        const job = await readJson(await fetch(apiUrl(`/api/v1/analyses/${created.analysis_id}`)));
        state.status = job.status;
        if (job.status === "succeeded") { renderResult(await readJson(await fetch(apiUrl(`/api/v1/analyses/${created.analysis_id}/result`)))); return; }
        if (job.status === "failed") throw new Error(job.error?.message || `${publicApp ? "Public" : "Local"} analysis failed.`);
        setRunState(true, job.status === "validating" ? "正在完整校验…" : "已进入队列…");
        showProgress(job.status === "validating" ? "正在校验基因、生成 4096 HVG 矩阵并运行 RNABag checkpoint…" : `分析已进入${publicApp ? "公共" : "本地"}单工作者队列…`);
        await new Promise(resolve => setTimeout(resolve, 450));
      }
    } catch (error) {
      if (token !== state.runToken) return;
      state.status = "failed";
      setValidation(`分析未完成：${error.message}`, "warn");
      showProgress(`${publicApp ? "公共" : "本地"}分析失败。请返回 Validate 步骤检查文件或 API 状态。`);
      setStepStates(); updateContext();
    } finally { if (token === state.runToken) setRunState(false); }
  }
  async function runDemoAnalysis() {
    if (publicPreview) return;
    const task = currentTask();
    const sample = sampleData[task.sampleKey];
    if (!sample) {
      setValidation("当前任务暂未配置 Demo Data。", "warn");
      return;
    }
    const loadToken = state.runToken;
    state.status = "loading-demo";
    setRunState(true, "正在载入示例数据…");
    setDemoRunState(true, "Loading Demo…");
    setValidation(`正在读取 ${sample.filename}…`);
    showProgress("正在读取内置 Demo Data，随后将自动提交分析…");
    scrollToStep("step-result");
    try {
      await apiBaseReady;
      const response = await fetch(apiUrl(sample.apiPath));
      if (!response.ok) throw new Error(`Demo Data request failed (${response.status})`);
      const blob = await response.blob();
      if (loadToken !== state.runToken) return;
      const file = new File([blob], sample.filename, { type: "text/tab-separated-values" });
      const valid = await validateFile(file, { navigate: false });
      if (!valid) throw new Error("内置 Demo Data 未通过基础预检。");
      if (loadToken !== state.runToken) return;
      await runAnalysis();
    } catch (error) {
      if (loadToken !== state.runToken) return;
      state.status = "failed";
      setValidation(`Demo Data 无法运行：${error.message}`, "warn");
      showProgress(`Demo Data 加载或分析失败，请检查${publicApp ? "公共" : "本地"} API 状态。`);
      setRunState(false);
      setStepStates(); updateContext();
    } finally {
      setDemoRunState(false);
    }
  }
  async function validateFile(file, { navigate = false } = {}) {
    if (publicPreview) return false;
    if (!file) return false;
    const preflightToken = ++state.preflightToken;
    state.selectedFile = null;
    setValidation("");
    setStepStates(); updateFileUploadUI();
    if (!file.name.toLowerCase().endsWith(".tsv")) { setValidation("格式不匹配：请选择 .tsv 文件，而不是 CSV 或 Excel 文件。", "warn"); return false; }
    const text = await file.slice(0, 160000).text();
    if (preflightToken !== state.preflightToken) return false;
    const lines = text.split(/\r?\n/).filter(line => line.trim());
    const headerIndex = lines.slice(0, 5).findIndex(line => ["geneid", "gene_id", "gene"].includes(((line.split("\t")[0] || "").replace(/^\uFEFF/, "").trim().toLowerCase())));
    const headers = (lines[headerIndex >= 0 ? headerIndex : 0] || "").split("\t");
    const sampleCount = headers.slice(1).filter(header => header.trim()).length;
    const hasGene = ["geneid", "gene_id", "gene"].includes((headers[0] || "").replace(/^\uFEFF/, "").trim().toLowerCase());
    const tabular = sampleCount > 0;
    let numeric = true;
    const dataStart = headerIndex >= 0 ? headerIndex + 1 : 1;
    lines.slice(dataStart, dataStart + 20).forEach(line => line.split("\t").slice(1).forEach(value => { if (value !== "" && (!Number.isFinite(Number(value)) || Number(value) < 0)) numeric = false; }));
    const issues = [];
    if (!tabular) issues.push("未检测到 Tab 分隔的样本列");
    if (!hasGene) issues.push("第一列建议命名为 GeneID");
    if (!numeric) issues.push("检测到非数值或负表达值");
    if (issues.length) { setValidation(`${file.name} · ${issues.join("；")}`, "warn"); return false; }
    state.selectedFile = file;
    setValidation(`✓ 基础格式通过 · ${sampleCount} 个样本列 · 已检查前 ${Math.min(20, Math.max(0, lines.length - dataStart))} 个基因行 · 提交后将完整校验`, "ok");
    setStepStates(); updateContext(); updateFileUploadUI();
    if (navigate) scrollToStep("step-result");
    return true;
  }
  function updateContext(extraStatus = "") {
    const task = currentTask();
    $$(".js-context-input").forEach(node => { node.textContent = inputs[state.activeInput].label; });
    $$(".js-context-task").forEach(node => { node.textContent = task.title; });
    $$(".js-context-file").forEach(node => { node.textContent = publicPreview ? "Uploads disabled" : state.selectedFile?.name || "Not selected"; });
    $$(".js-context-analysis").forEach(node => { node.textContent = publicPreview ? "Not available" : state.analysisId || "Not created"; });
    $$(".js-context-status").forEach(node => { node.textContent = publicPreview ? "Public preview" : publicApp && !extraStatus ? "Public app" : extraStatus || (state.status === "ready" ? "Ready for input" : state.status); });
    $$(".js-context-output").forEach(node => { node.textContent = task.expected; });
  }
  function bindFileControls() {
    if (publicPreview) {
      $$(".js-file-input").forEach(input => { input.disabled = true; });
      $$(".js-dropzone").forEach(dropzone => {
        dropzone.setAttribute("aria-disabled", "true");
        ["click", "dragenter", "dragover", "dragleave", "drop"].forEach(name => dropzone.addEventListener(name, event => event.preventDefault()));
      });
      return;
    }
    $$(".js-file-input").forEach(input => input.addEventListener("change", event => validateFile(event.target.files[0])));
    $$(".js-dropzone").forEach(dropzone => {
      ["dragenter", "dragover"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add("drag"); }));
      ["dragleave", "drop"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove("drag"); }));
      dropzone.addEventListener("drop", event => validateFile(event.dataTransfer.files[0]));
    });
  }
  function ensureDemoControls() {
    $$(".js-dropzone").forEach(dropzone => {
      const existingHint = $(".demo-hint", dropzone);
      if (existingHint) {
        existingHint.classList.add("js-demo-hint");
        return;
      }
      const hint = document.createElement("span");
      hint.className = "demo-hint js-demo-hint";
      hint.textContent = publicPreview ? "（公网预览不接收文件）" : "（没有文件？试试我们的 demo data↓）";
      dropzone.append(hint);
    });
    $$(".sample-options").forEach(options => {
      if (options.previousElementSibling?.classList.contains("demo-action")) return;
      const section = document.createElement("section");
      section.className = "demo-action";
      section.setAttribute("aria-label", "Demo data");
      section.innerHTML = '<button class="demo-run js-demo-run" type="button">Use Demo Data</button>';
      options.before(section);
    });
  }
  function bindNavigation() {
    $$('a[href^="#step-"]').forEach(link => link.addEventListener("click", event => {
      event.preventDefault();
      scrollToStep(link.dataset.stepTarget || link.getAttribute("href").slice(1), "replace");
    }));
    $$("[data-restart]").forEach(button => button.addEventListener("click", () => { state.activeInput = "tissue"; state.activeTask = defaultTasks.tissue; state.runToken += 1; renderInputs(); renderTasks(); renderTaskDetail(); scrollToStep("step-input"); }));
  }
  function bindScrollState() {
    if (variant === "lab") return;
    const observedSteps = scrollStepNodes();
    const observer = "IntersectionObserver" in window ? new IntersectionObserver(() => {
      if (programmaticStep) return;
      setActiveStep(naturalStepAtProbe(observedSteps), "natural");
    }, { rootMargin: `-${workflowOffset()}px 0px -52% 0px`, threshold: [0, .2, .5, .8] }) : null;
    observedSteps.forEach(step => observer ? observer.observe(step) : null);
    let frame = 0;
    window.addEventListener("scroll", () => {
      if (programmaticStep) { settleProgrammaticScroll(); return; }
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (observer) return;
        setActiveStep(naturalStepAtProbe(observedSteps), "natural");
      });
    }, { passive: true });
  }
  function bindOverviewLightbox() {
    const figure = $(".overview-figure");
    const lightbox = $(".overview-lightbox");
    if (!figure || !lightbox) return;
    const open = () => {
      lightbox.classList.add("is-open");
      lightbox.setAttribute("aria-hidden", "false");
      document.body.classList.add("overview-lightbox-open");
    };
    const close = () => {
      lightbox.classList.remove("is-open");
      lightbox.setAttribute("aria-hidden", "true");
      document.body.classList.remove("overview-lightbox-open");
      figure.focus({ preventScroll: true });
    };
    figure.addEventListener("click", open);
    figure.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
    });
    lightbox.addEventListener("click", close);
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && lightbox.classList.contains("is-open")) close();
    });
  }

  function applyPublicPreview() {
    if (!publicPreview) return;
    const style = document.createElement("style");
    style.textContent = ".public-preview-banner{padding:10px 20px;color:#503b08;background:#fff3c4;border-bottom:1px solid #ead58a;text-align:center;font-size:13px;font-weight:700}.public-preview .status::before{background:#d69b13;box-shadow:0 0 0 4px rgba(214,155,19,.14)}.public-preview .js-dropzone{opacity:.62;cursor:not-allowed}.public-preview .js-dropzone:hover{background:#fbfcfe;border-color:#aeb9c9}.public-preview .js-sample-link[aria-disabled=true]{opacity:.58;cursor:not-allowed}.public-preview .js-run:disabled,.public-preview .js-demo-run:disabled{cursor:not-allowed}.pong-indicator[data-state=checking]{color:#7c4b16}.pong-indicator[data-state=ok]{color:#2ca66f}.pong-indicator[data-state=unavailable]{color:#c0392b}";
    document.head.append(style);
    const banner = document.createElement("div");
    banner.className = "public-preview-banner";
    banner.setAttribute("role", "status");
    banner.textContent = "公网预览 · 当前仅展示页面与任务设计，不接收文件，不运行推理。";
    const anchor = isLab ? $(".lab-bar") : $(".nav");
    if (anchor) anchor.insertAdjacentElement("afterend", banner);
    else document.body.prepend(banner);
    $$(".status").forEach(node => { node.textContent = "Public preview"; });
    $$(".disclaimer").forEach(node => { node.textContent = "公网预览不接收或保存任何样本数据；页面内容仅限研究展示，不用于临床诊断。"; });
    $$(".stage-subtitle").forEach(node => {
      node.textContent = node.textContent.replace("本地 API", "后续推理服务").replace("提交后", "服务开放后");
    });
    const probePath = runtimeConfig.probePath;
    if (probePath) {
      const indicator = document.createElement("span");
      indicator.className = "pong-indicator";
      indicator.setAttribute("aria-live", "polite");
      indicator.dataset.state = "checking";
      indicator.textContent = "Connectivity: checking...";
      const banner = $(".public-preview-banner");
      if (banner) banner.append(document.createTextNode(" · "), indicator);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      fetch(probePath, { cache: "no-store", signal: controller.signal })
        .then(response => {
          if (!response.ok) throw new Error();
          return response.text();
        })
        .then(text => {
          const ok = text.trim() === "pong";
          indicator.textContent = ok ? "Connectivity: pong" : "Connectivity: unavailable";
          indicator.dataset.state = ok ? "ok" : "unavailable";
        })
        .catch(() => {
          indicator.textContent = "Connectivity: unavailable";
          indicator.dataset.state = "unavailable";
        })
        .finally(() => clearTimeout(timer));
    }
    updateFileUploadUI();
  }

  function applyPublicApp() {
    if (!publicApp) return;
    const style = document.createElement("style");
    style.textContent = ".public-app-banner{padding:10px 20px;color:#173d34;background:#e5f4ec;border-bottom:1px solid #a9d8c2;text-align:center;font-size:13px;font-weight:700}.public-app .status::before{background:#2c8f78;box-shadow:0 0 0 4px rgba(44,143,120,.14)}.public-app .js-dropzone{border-color:#79b9aa}";
    document.head.append(style);
    const banner = document.createElement("div");
    banner.className = "public-app-banner";
    banner.setAttribute("role", "status");
    banner.textContent = "临时公共上传已开放：TSV 字节将按批准的分析生命周期私密保存在 tang3；当前无登录或 TLS。请勿上传 PHI 或其他敏感数据。仅限研究使用，不用于临床诊断。";
    const anchor = isLab ? $(".lab-bar") : $(".nav");
    if (anchor) anchor.insertAdjacentElement("afterend", banner);
    else document.body.prepend(banner);
    $$(".status").forEach(node => { node.textContent = "Temporary public app · HTTP"; });
    $$(".disclaimer").forEach(node => { node.textContent = "当前结果由 RNABag checkpoint 生成，仅限研究展示，不用于临床诊断。"; });
    $$(".stage-subtitle, .js-dropzone span, .story-chapter p").forEach(node => {
      node.textContent = node.textContent.replace("本地 API", "RNABag API").replace("本地 checkpoint", "RNABag checkpoint");
    });
    updateFileUploadUI();
  }

  ensureDemoControls();
  if (!publicPreview) apiBaseReady.then(() => {
    const task = currentTask();
    const sample = sampleData[task.sampleKey];
    if (sample) {
      $$(".js-sample-link").forEach(link => { link.href = apiUrl(sample.apiPath); });
    }
    if (apiBaseUrl && $(".status")) $(".status").textContent = "Local API · 127.0.0.1:8000";
  });
  if (!publicPreview) {
    $$(".js-run").forEach(button => button.addEventListener("click", runAnalysis));
    $$(".js-demo-run").forEach(button => button.addEventListener("click", runDemoAnalysis));
  }
  $$(".js-task-confirm").forEach(button => button.addEventListener("click", confirmTask));
  renderInputs(); renderTasks(); renderTaskDetail(); bindFileControls(); bindNavigation(); bindScrollState(); bindOverviewLightbox();
  applyPublicApp();
  applyPublicPreview();
  const initialStep = /^#step-(input|task|validate|result)$/.test(window.location.hash) ? window.location.hash.slice(1) : "step-input";
  setActiveStep(initialStep, "programmatic");
  if (window.location.hash && variant !== "lab") {
    const alignInitialStep = () => window.setTimeout(() => scrollToStep(initialStep), 0);
    if (document.readyState === "complete") alignInitialStep();
    else window.addEventListener("load", alignInitialStep, { once: true });
  }
  window.addEventListener("resize", () => { if (variant === "two") setActivePanel(document.body.dataset.activeStep || "step-input"); });
})();
