(() => {
  const params = new URLSearchParams(window.location.search);
  const variant = document.body.dataset.variant || "two";
  const isLab = params.get("mode") === "lab" || variant === "lab";
  document.body.classList.toggle("lab-mode", isLab);

  const backendOrigin = "http://127.0.0.1:8000";
  const localHostname = ["127.0.0.1", "localhost"].includes(window.location.hostname);
  let apiBaseUrl = window.location.protocol === "file:" ? backendOrigin : "";
  const apiUrl = path => `${apiBaseUrl}${path}`;
  const apiBaseReady = window.location.protocol !== "file:" && localHostname ? fetch("/api/v1/health/live", { cache: "no-store" })
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
        origin: { title: "Tissue Origin Identification", apiTask: "tissue_origin_identification", sampleKey: "tissue", description: "根据全转录组表达特征推断样本最可能的组织来源，用于跨组织来源追踪、样本注释与 provenance confirmation。", specs: ["Input: tissue-derived bulk RNA-seq", "Head: 36-class classification", "Labels: tissue-origin ontology", "Representation: 4096 HVGs", "Output: ranked probabilities"], expected: "36 tissue classes", type: "rank" }
      }
    },
    plasma: {
      label: "plasma", subtitle: "血浆 RNA", icon: "PL", enabled: false,
      tasks: { cancer: { title: "Plasma Cancer Detection", apiTask: "plasma_cancer_detection", sampleKey: "plasma", description: "识别 plasma-derived RNA expression matrix 中的癌症相关信号，为 minimally invasive liquid-biopsy 研究提供分层依据。", specs: ["Input: plasma-derived RNA", "Status: coming soon"], expected: "Coming soon", type: "binary" } }
    },
    platelet: {
      label: "platelet", subtitle: "血小板 RNA", icon: "PT", enabled: true,
      tasks: {
        cancer: { title: "Platelet Cancer Detection", apiTask: "platelet_cancer_detection", sampleKey: "platelet", description: "利用 tumor-educated platelet 的转录组重编程信号评估癌症状态，捕捉循环系统中的肿瘤相关分子响应。", specs: ["Input: platelet-derived RNA", "Head: thresholded binary classifier", "Labels: Healthy / Cancer", "Biology: tumor-educated platelets", "Output: class probability"], expected: "Healthy / Cancer", type: "binary" },
        location: { title: "Tumor Localization", apiTask: "platelet_tumor_localization", sampleKey: "platelet", description: "基于血小板转录组特征定位最可能的肿瘤来源，为后续组织学验证提供候选器官或癌种假设。", specs: ["Input: platelet-derived RNA", "Head: 5-class classification", "Labels: HNSC / NSCLC / Glioma / PAAD / OV", "Biology: tumor-educated platelets", "Output: ranked probabilities"], expected: "HNSC / NSCLC / Glioma / PAAD / OV", type: "rank" }
      }
    }
  };
  if (!isLab) {
    inputs.tissue.tasks = { cancer: inputs.tissue.tasks.cancer };
    inputs.platelet.tasks = { cancer: inputs.platelet.tasks.cancer };
  }
  const taskLabels = { cancer: "Cancer detection", origin: "Tissue origin · 36 classes", location: "Tumor localization · 5 classes" };
  const state = { activeInput: "tissue", activeTask: "cancer", selectedFile: null, runToken: 0, analysisId: null, status: "ready", lastStatus: "" };
  let programmaticStep = null;
  let programmaticSettleTimer = 0;

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" })[character]);
  }
  function currentTask() { return inputs[state.activeInput].tasks[state.activeTask]; }
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
    $$(".js-sample-description").forEach(node => { node.textContent = `${task.title} 使用已验证的 ${sample.label} ${sample.sampleCount}-sample FPKM matrix，可用于检查数据结构与快速演示。`; });
    $$(".js-sample-link").forEach(link => { link.href = apiUrl(sample.apiPath); link.download = sample.filename; });
    $$(".js-demo-run").forEach(button => { button.setAttribute("aria-label", `Use Demo Data for ${task.title}`); });
    clearFile(false);
    resetResult();
    updateContext();
  }
  function selectInput(key) {
    state.activeInput = key;
    state.activeTask = Object.keys(inputs[key].tasks)[0];
    state.runToken += 1;
    renderInputs(); renderTasks(); renderTaskDetail();
    scrollToStep("step-task");
  }
  function selectTask(key) {
    state.activeTask = key;
    state.runToken += 1;
    renderTasks(); renderTaskDetail();
    scrollToStep("step-validate");
  }
  function setValidation(message, kind = "") {
    $$(".js-validation").forEach(box => { box.className = `validation ${kind ? `show ${kind}` : ""}`; box.textContent = message; });
  }
  function clearFile(announce = true) {
    state.selectedFile = null;
    state.analysisId = null;
    $$(".js-file-input").forEach(input => { input.value = ""; });
    if (announce) setValidation("");
    setStepStates();
  }
  function resetResult() {
    state.status = "ready";
    $$(".js-result-title").forEach(node => { node.textContent = "Prediction preview"; });
    $$(".js-result-badge").forEach(node => { node.textContent = "RNABAG CHECKPOINT"; });
    $$(".js-chart").forEach(chart => { chart.innerHTML = `<div class="empty-chart"><div class="empty-orbit"></div><p>选择 TSV 并提交本地分析，查看完整预处理与 checkpoint 输出。</p></div>`; });
    $$(".js-result-summary").forEach(box => { box.innerHTML = `<small>Expected output</small><strong>${escapeHtml(currentTask().expected)}</strong>`; });
    $$(".js-run").forEach(button => { button.disabled = false; button.textContent = "提交本地分析"; });
    $$(".js-demo-run").forEach(button => { button.disabled = false; button.textContent = "Use Demo Data"; });
    updateContext(); setStepStates();
  }
  function setRunState(running, label = "提交本地分析") {
    $$(".js-run").forEach(button => { button.disabled = running; button.textContent = label; });
    $$(".js-demo-run").forEach(button => { button.disabled = running; });
  }
  function setDemoRunState(running, label = "Use Demo Data") {
    $$(".js-demo-run").forEach(button => { button.disabled = running; button.textContent = label; });
  }
  function showProgress(message) {
    $$(".js-result-title").forEach(node => { node.textContent = "Local analysis"; });
    $$(".js-chart").forEach(chart => { chart.innerHTML = `<div class="empty-chart"><div class="empty-orbit"></div><p>${escapeHtml(message)}</p></div>`; });
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
    const prediction = result.predictions[0];
    const rows = prediction.scores.slice(0, task.type === "binary" ? 2 : 5).map(item => ({ label: escapeHtml(item.label), value: Math.round(item.score * 1000) / 10 }));
    $$(".js-chart").forEach(chart => {
      chart.innerHTML = task.type === "binary" ? rows.map((row, index) => `<div class="probability ${index ? "secondary" : ""}"><div class="prob-meta"><strong>${row.label}</strong><span>${row.value}%</span></div><div class="bar"><i data-width="${row.value}"></i></div></div>`).join("") : `<div>${rows.map(row => `<div class="rank-row"><strong>${row.label}</strong><div class="bar"><i data-width="${row.value}"></i></div><span>${row.value}%</span></div>`).join("")}</div>`;
    });
    const predicted = prediction.scores.find(item => item.label === prediction.predicted_label) || prediction.scores[0];
    const predictedValue = Math.round(predicted.score * 1000) / 10;
    const extra = result.predictions.length > 1 ? ` · 共 ${result.predictions.length} 个样本，当前展示第 1 个` : "";
    $$(".js-result-title").forEach(node => { node.textContent = "RNABag prediction"; });
    $$(".js-result-badge").forEach(node => { node.textContent = "CHECKPOINT"; });
    $$(".js-result-summary").forEach(box => { box.innerHTML = `<small>Predicted class · ${escapeHtml(prediction.sample_id)}${extra}</small><strong>${escapeHtml(prediction.predicted_label)} · ${predictedValue}%</strong>`; });
    requestAnimationFrame(() => $$("[data-width]").forEach(bar => { bar.style.width = `${bar.dataset.width}%`; }));
    const summary = result.input_summary;
    const duplicateText = summary.duplicate_gene_rows ? `；检出 ${summary.duplicate_gene_rows} 个重复 GeneID 行，按输入顺序保留第一次出现并丢弃后续重复行` : "";
    setValidation(`✓ 服务端完整校验 · ${summary.gene_rows} 个基因行 · ${summary.sample_count} 个样本 · GeneID 映射 ${summary.mapped_unique_gene_ids}/${summary.unique_gene_ids} · HVG ${summary.model_hvg_found}/${summary.model_hvg_total}${duplicateText}`, summary.duplicate_gene_rows ? "warn" : "ok");
    state.status = "succeeded";
    updateContext(); setStepStates();
  }
  async function runAnalysis() {
    if (!state.selectedFile) { setValidation("请先选择一个通过基础预检的 .tsv 文件。", "warn"); scrollToStep("step-validate"); return; }
    const task = currentTask();
    const token = ++state.runToken;
    state.status = "queued";
    setRunState(true, "正在上传…");
    showProgress("正在将 TSV 发送给本地 RNABag API…");
    scrollToStep("step-result");
    try {
      await apiBaseReady;
      const created = await readJson(await fetch(apiUrl(`/api/v1/analyses?task=${encodeURIComponent(task.apiTask)}`), { method: "POST", headers: { "Content-Type": "text/tab-separated-values", "X-RNABag-Filename": encodeURIComponent(state.selectedFile.name) }, body: state.selectedFile }));
      state.analysisId = created.analysis_id;
      while (token === state.runToken) {
        const job = await readJson(await fetch(apiUrl(`/api/v1/analyses/${created.analysis_id}`)));
        state.status = job.status;
        if (job.status === "succeeded") { renderResult(await readJson(await fetch(apiUrl(`/api/v1/analyses/${created.analysis_id}/result`)))); return; }
        if (job.status === "failed") throw new Error(job.error?.message || "Local analysis failed.");
        setRunState(true, job.status === "validating" ? "正在完整校验…" : "已进入队列…");
        showProgress(job.status === "validating" ? "正在校验基因、生成 4096 HVG 矩阵并运行 RNABag checkpoint…" : "分析已进入本地单工作者队列…");
        await new Promise(resolve => setTimeout(resolve, 450));
      }
    } catch (error) {
      if (token !== state.runToken) return;
      state.status = "failed";
      setValidation(`分析未完成：${error.message}`, "warn");
      showProgress("本地分析失败。请返回 Validate 步骤检查文件或 API 状态。");
      setStepStates(); updateContext();
    } finally { if (token === state.runToken) setRunState(false); }
  }
  async function runDemoAnalysis() {
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
      showProgress("Demo Data 加载或分析失败，请检查本地 API 状态。");
      setRunState(false);
      setStepStates(); updateContext();
    } finally {
      setDemoRunState(false);
    }
  }
  async function validateFile(file, { navigate = true } = {}) {
    if (!file) return false;
    state.selectedFile = null;
    if (!file.name.toLowerCase().endsWith(".tsv")) { setValidation("格式不匹配：请选择 .tsv 文件，而不是 CSV 或 Excel 文件。", "warn"); return false; }
    const text = await file.slice(0, 160000).text();
    const lines = text.split(/\r?\n/).filter(line => line.trim());
    const headerIndex = lines.slice(0, 5).findIndex(line => ["geneid", "gene_id", "gene"].includes(((line.split("\t")[0] || "").replace(/^\uFEFF/, "").trim().toLowerCase())));
    const headers = (lines[headerIndex >= 0 ? headerIndex : 0] || "").split("\t");
    const hasGene = ["geneid", "gene_id", "gene"].includes((headers[0] || "").replace(/^\uFEFF/, "").trim().toLowerCase());
    const tabular = headers.length > 1;
    let numeric = true;
    const dataStart = headerIndex >= 0 ? headerIndex + 1 : 1;
    lines.slice(dataStart, dataStart + 20).forEach(line => line.split("\t").slice(1).forEach(value => { if (value !== "" && (!Number.isFinite(Number(value)) || Number(value) < 0)) numeric = false; }));
    const issues = [];
    if (!tabular) issues.push("未检测到 Tab 分隔的样本列");
    if (!hasGene) issues.push("第一列建议命名为 GeneID");
    if (!numeric) issues.push("检测到非数值或负表达值");
    if (issues.length) { setValidation(`${file.name} · ${issues.join("；")}`, "warn"); return false; }
    state.selectedFile = file;
    setValidation(`✓ 基础格式通过 · ${headers.length - 1} 个样本列 · 已检查前 ${Math.min(20, Math.max(0, lines.length - dataStart))} 个基因行 · 提交后将完整校验`, "ok");
    setStepStates(); updateContext();
    if (navigate) scrollToStep("step-result");
    return true;
  }
  function updateContext(extraStatus = "") {
    const task = currentTask();
    $$(".js-context-input").forEach(node => { node.textContent = inputs[state.activeInput].label; });
    $$(".js-context-task").forEach(node => { node.textContent = task.title; });
    $$(".js-context-file").forEach(node => { node.textContent = state.selectedFile?.name || "Not selected"; });
    $$(".js-context-analysis").forEach(node => { node.textContent = state.analysisId || "Not created"; });
    $$(".js-context-status").forEach(node => { node.textContent = extraStatus || (state.status === "ready" ? "Ready for input" : state.status); });
    $$(".js-context-output").forEach(node => { node.textContent = task.expected; });
  }
  function bindFileControls() {
    $$(".js-file-input").forEach(input => input.addEventListener("change", event => validateFile(event.target.files[0])));
    $$(".js-dropzone").forEach(dropzone => {
      ["dragenter", "dragover"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add("drag"); }));
      ["dragleave", "drop"].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove("drag"); }));
      dropzone.addEventListener("drop", event => validateFile(event.dataTransfer.files[0]));
    });
  }
  function ensureDemoControls() {
    $$(".js-dropzone").forEach(dropzone => {
      if ($(".demo-hint", dropzone)) return;
      const hint = document.createElement("span");
      hint.className = "demo-hint";
      hint.textContent = "（没有文件？试试我们的 demo data↓）";
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
    $$("[data-restart]").forEach(button => button.addEventListener("click", () => { state.activeInput = "tissue"; state.activeTask = "cancer"; state.runToken += 1; renderInputs(); renderTasks(); renderTaskDetail(); scrollToStep("step-input"); }));
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

  ensureDemoControls();
  apiBaseReady.then(() => {
    const sample = sampleData[currentTask().sampleKey];
    $$(".js-sample-link").forEach(link => { link.href = apiUrl(sample.apiPath); });
    if (apiBaseUrl && $(".status")) $(".status").textContent = "Local API · 127.0.0.1:8000";
  });
  $$(".js-run").forEach(button => button.addEventListener("click", runAnalysis));
  $$(".js-demo-run").forEach(button => button.addEventListener("click", runDemoAnalysis));
  renderInputs(); renderTasks(); renderTaskDetail(); bindFileControls(); bindNavigation(); bindScrollState(); bindOverviewLightbox();
  const initialStep = /^#step-(input|task|validate|result)$/.test(window.location.hash) ? window.location.hash.slice(1) : "step-input";
  setActiveStep(initialStep, "programmatic");
  if (window.location.hash && variant !== "lab") {
    const alignInitialStep = () => window.setTimeout(() => scrollToStep(initialStep), 0);
    if (document.readyState === "complete") alignInitialStep();
    else window.addEventListener("load", alignInitialStep, { once: true });
  }
  window.addEventListener("resize", () => { if (variant === "two") setActivePanel(document.body.dataset.activeStep || "step-input"); });
})();
