// ── TypeScript Dashboard Controller for DeepMammo-API ────────────────

interface APIResponse {
  abnormality: {
    label: string;
    confidence: number;
    probabilities: {
      mass: number;
      calcification: number;
    };
  };
  pathology: {
    label: string;
    confidence: number;
    probabilities: {
      benign: number;
      malignant: number;
    };
  };
  segmentation: {
    mask_b64: string;
    overlay_b64: string;
    coverage_pct: number;
  };
  gradcam_b64: string;
  clinical_report: {
    model_used: string;
    sections: Record<string, string>;
  };
  pdf_b64: string;
}

interface PatientInfo {
  patient_name?: string;
  patient_id?: string;
  referring_physician?: string;
  exam_date?: string;
  clinical_notes?: string;
}

document.addEventListener('DOMContentLoaded', () => {
  const uploadZone = document.getElementById('uploadZone') as HTMLDivElement | null;
  const imageInput = document.getElementById('imageInput') as HTMLInputElement | null;
  const predictBtn = document.getElementById('predictBtn') as HTMLButtonElement | null;
  const resetBtn   = document.getElementById('resetBtn') as HTMLButtonElement | null;
  const fileNameEl = document.getElementById('fileName') as HTMLDivElement | null;
  const loadingEl  = document.getElementById('loadingState') as HTMLDivElement | null;
  const resultsEl  = document.getElementById('resultsSection') as HTMLDivElement | null;
  const errorBox   = document.getElementById('errorBox') as HTMLDivElement | null;
  const downloadBtn= document.getElementById('downloadBtn') as HTMLButtonElement | null;
  const previewQuickBtn = document.getElementById('previewQuickBtn') as HTMLButtonElement | null;
  const modalOverlay=document.getElementById('modalOverlay') as HTMLDivElement | null;
  const jsonOutput = document.getElementById('jsonOutput') as HTMLElement | null;
  const pdfPreviewOverlay = document.getElementById('pdfPreviewOverlay') as HTMLDivElement | null;
  const pdfPreviewIframe = document.getElementById('pdfPreviewIframe') as HTMLIFrameElement | null;
  const btnDownloadFromPreview = document.getElementById('btnDownloadFromPreview') as HTMLButtonElement | null;
  const btnClosePreview = document.getElementById('btnClosePreview') as HTMLButtonElement | null;
  const btnOpenNewTab = document.getElementById('btnOpenNewTab') as HTMLButtonElement | null;

  // Form controls inputs
  const modelSelect     = document.getElementById('modelSelect') as HTMLSelectElement | null;
  const customThreshold = document.getElementById('customThreshold') as HTMLInputElement | null;

  // Upload visual helpers
  const uploadIcon = uploadZone?.querySelector('.upload-icon') as HTMLDivElement | null;
  const uploadHelperText = document.getElementById('uploadHelperText') as HTMLElement | null;
  const uploadPreviewContainer = document.getElementById('uploadPreviewContainer') as HTMLDivElement | null;
  const imgUploadPreview = document.getElementById('imgUploadPreview') as HTMLImageElement | null;

  // Telemetry element selections
  const telemetryTotalRequests = document.getElementById('telemetryTotalRequests');
  const telemetryAvgLatency = document.getElementById('telemetryAvgLatency');
  const telemetrySuccessRate = document.getElementById('telemetrySuccessRate');
  const telemetryCredits = document.getElementById('telemetryCredits');
  const analyticsTableBody = document.getElementById('analyticsTableBody');

  let selectedFile: File | null = null;
  let pdfB64: string | null     = null;

  interface Transaction {
    timestamp: string;
    endpoint: string;
    status: string;
    latency: number;
    model: string;
  }

  function getTransactions(): Transaction[] {
    const raw = localStorage.getItem('deepmammo_session_transactions');
    if (raw) return JSON.parse(raw);
    const defaults: Transaction[] = [
      { timestamp: '2026-05-27 19:04:12', endpoint: 'POST /api/predict/', status: '200 OK', latency: 2.31, model: 'deepmammo-v1-resnet' },
      { timestamp: '2026-05-27 18:59:04', endpoint: 'POST /api/predict/', status: '200 OK', latency: 2.45, model: 'deepmammo-v1-resnet' },
      { timestamp: '2026-05-27 18:44:31', endpoint: 'POST /api/predict/', status: '500 Server Error', latency: 0.12, model: 'deepmammo-v2-vit' }
    ];
    localStorage.setItem('deepmammo_session_transactions', JSON.stringify(defaults));
    return defaults;
  }

  function addTransaction(tx: Transaction) {
    const list = getTransactions();
    list.unshift(tx);
    localStorage.setItem('deepmammo_session_transactions', JSON.stringify(list));
    updateAnalyticsTelemetry();
  }

  function updateAnalyticsTelemetry() {
    const list = getTransactions();
    if (telemetryTotalRequests) {
      telemetryTotalRequests.textContent = (14204 + list.length - 3).toLocaleString();
    }
    
    if (list.length > 0) {
      const avg = list.reduce((acc, tx) => acc + tx.latency, 0) / list.length;
      if (telemetryAvgLatency) {
        telemetryAvgLatency.textContent = avg.toFixed(2) + 's';
      }
      
      const successes = list.filter(tx => tx.status.includes('200')).length;
      const rate = (successes / list.length) * 100;
      if (telemetrySuccessRate) {
        telemetrySuccessRate.textContent = rate.toFixed(2) + '%';
      }
    }

    if (telemetryCredits) {
      const actualCalls = list.length - 3;
      const cost = Math.max(0, actualCalls * 0.05);
      telemetryCredits.textContent = '$' + (48.50 - cost).toFixed(2);
    }

    if (analyticsTableBody) {
      analyticsTableBody.innerHTML = '';
      list.forEach(tx => {
        const isOk = tx.status.includes('200');
        const statusClass = isOk ? 'status-ok' : 'status-error';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${tx.timestamp}</td>
          <td><code>${tx.endpoint}</code></td>
          <td><span class="status-pill ${statusClass}">${tx.status}</span></td>
          <td>${tx.latency.toFixed(2)}s</td>
          <td><code>${tx.model}</code></td>
        `;
        analyticsTableBody.appendChild(tr);
      });
    }
  }

  // Populate dynamic telemetry cards on start
  updateAnalyticsTelemetry();

  if (!uploadZone || !imageInput || !predictBtn || !resetBtn || !fileNameEl || !loadingEl || !resultsEl || !errorBox || !downloadBtn || !modalOverlay) {
    console.error("Required dashboard DOM elements are missing.");
    return;
  }

  // ── Tab State Manager ──────────────────────────────────────────────
  const navPlayground = document.getElementById('nav-playground');
  const navAnalytics  = document.getElementById('nav-analytics');
  const navKeys       = document.getElementById('nav-keys');
  const navDocs       = document.getElementById('nav-docs');

  const workspacePlayground = document.getElementById('workspace-playground');
  const workspaceAnalytics  = document.getElementById('workspace-analytics');
  const workspaceKeys       = document.getElementById('workspace-keys');
  const workspaceDocs       = document.getElementById('workspace-docs');

  const tabs = [
    { nav: navPlayground, ws: workspacePlayground },
    { nav: navAnalytics,  ws: workspaceAnalytics },
    { nav: navKeys,       ws: workspaceKeys },
    { nav: navDocs,       ws: workspaceDocs }
  ];

  tabs.forEach(tab => {
    if (tab.nav && tab.ws) {
      tab.nav.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Remove active class from all navs and hide all workspaces
        tabs.forEach(t => {
          t.nav?.classList.remove('active');
          t.ws?.classList.remove('active-tab');
        });

        // Activate the clicked tab
        tab.nav.classList.add('active');
        tab.ws.classList.add('active-tab');
      });
    }
  });

  // ── File Handling & Specimen Previews ──────────────────────────────

  uploadZone.addEventListener('click', () => imageInput.click());
  imageInput.addEventListener('change', (e: Event) => {
    const target = e.target as HTMLInputElement;
    if (target.files && target.files[0]) {
      setFile(target.files[0]);
    }
  });

  uploadZone.addEventListener('dragover', (e: DragEvent) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
  });

  uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
  });

  uploadZone.addEventListener('drop', (e: DragEvent) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  });

  function setFile(file: File) {
    selectedFile = file;
    if (fileNameEl) {
      fileNameEl.textContent = file.name;
      fileNameEl.classList.remove('hidden');
    }
    if (predictBtn) {
      predictBtn.disabled = false;
    }
    hideError();

    // Render local preview of original scan
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        const previewEl = document.getElementById('imgOriginalPreview') as HTMLImageElement | null;
        if (previewEl) {
          previewEl.src = e.target.result as string;
        }
        if (imgUploadPreview) {
          imgUploadPreview.src = e.target.result as string;
        }
        if (uploadPreviewContainer) {
          uploadPreviewContainer.classList.remove('hidden');
        }
        if (uploadIcon) {
          uploadIcon.classList.add('hidden');
        }
        if (uploadHelperText) {
          uploadHelperText.classList.add('hidden');
        }
      }
    };
    reader.readAsDataURL(file);
  }

  function truncateBase64InJson(obj: any): any {
    const clone = JSON.parse(JSON.stringify(obj));
    const truncate = (val: any) => {
      if (typeof val === 'string' && val.length > 100) {
        return val.substring(0, 50) + `... [truncated base64, total ${val.length.toLocaleString()} chars] ...`;
      }
      return val;
    };
    
    if (clone.segmentation) {
      if (clone.segmentation.mask_b64) clone.segmentation.mask_b64 = truncate(clone.segmentation.mask_b64);
      if (clone.segmentation.overlay_b64) clone.segmentation.overlay_b64 = truncate(clone.segmentation.overlay_b64);
    }
    if (clone.gradcam_b64) clone.gradcam_b64 = truncate(clone.gradcam_b64);
    if (clone.pdf_b64) clone.pdf_b64 = truncate(clone.pdf_b64);
    
    return clone;
  }

  // ── Run Analysis Pipeline ──────────────────────────────────────────
  let stepTimeouts: number[] = [];
  let elapsedTimerInterval: number | undefined;

  function clearLoadingAnimation() {
    stepTimeouts.forEach(t => clearTimeout(t));
    stepTimeouts = [];
    if (elapsedTimerInterval !== undefined) {
      clearInterval(elapsedTimerInterval);
      elapsedTimerInterval = undefined;
    }
    const steps = ['step1', 'step2', 'step3', 'step4', 'step5'];
    steps.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('active');
        const dot = el.querySelector('.dot');
        if (dot) dot.classList.remove('active');
      }
    });
    const elapsedEl = document.getElementById('elapsedTimer');
    if (elapsedEl) {
      elapsedEl.textContent = '0.0s';
    }
  }

  predictBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    predictBtn.disabled = true;
    resetBtn.classList.remove('hidden');
    loadingEl.classList.remove('hidden');
    resultsEl.classList.add('hidden');
    hideError();
    animateSteps();

    const formData = new FormData();
    formData.append('image', selectedFile);
    
    // Append customization configurations
    if (modelSelect) {
      formData.append('model_routing', modelSelect.value);
    }
    if (customThreshold) {
      formData.append('confidence_threshold', (parseFloat(customThreshold.value) / 100).toString());
    }

    const activeTriage = document.querySelector('input[name="triageOverride"]:checked') as HTMLInputElement | null;
    if (activeTriage) {
      formData.append('triage_override', activeTriage.value);
    }

    const startTime = performance.now();
    let statusText = '200 OK';

    try {
      const res = await fetch('/api/predict/', { method: 'POST', body: formData });
      const durationSeconds = (performance.now() - startTime) / 1000;
      
      const data = await res.json();
      
      // Trace JSON payload to dashboard contrast panel
      if (jsonOutput) {
        const truncatedData = truncateBase64InJson(data);
        jsonOutput.textContent = JSON.stringify(truncatedData, null, 2);
      }

      if (!res.ok) {
        statusText = `${res.status} Error`;
        addTransaction({
          timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
          endpoint: 'POST /api/predict/',
          status: statusText,
          latency: durationSeconds,
          model: modelSelect ? modelSelect.value : 'deepmammo-v1-resnet'
        });
        showError(data.error || 'Prediction failed.');
        return;
      }

      addTransaction({
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        endpoint: 'POST /api/predict/',
        status: '200 OK',
        latency: durationSeconds,
        model: modelSelect ? modelSelect.value : 'deepmammo-v1-resnet'
      });
      renderResults(data);
    } catch (err) {
      const durationSeconds = (performance.now() - startTime) / 1000;
      addTransaction({
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        endpoint: 'POST /api/predict/',
        status: '500 Net Error',
        latency: durationSeconds,
        model: modelSelect ? modelSelect.value : 'deepmammo-v1-resnet'
      });
      showError('Network error. Is the server running?');
    } finally {
      if (elapsedTimerInterval !== undefined) {
        clearInterval(elapsedTimerInterval);
        elapsedTimerInterval = undefined;
      }
      loadingEl.classList.add('hidden');
      predictBtn.disabled = false;
    }
  });

  // ── Animate Loading Steps ─────────────────────────────────────────
  function animateSteps() {
    clearLoadingAnimation();
    const steps = ['step1', 'step2', 'step3', 'step4', 'step5'];
    const delays = [0, 1200, 2400, 3600, 5000];
    steps.forEach((id, i) => {
      const t = setTimeout(() => {
        const el = document.getElementById(id);
        if (el) {
          el.classList.add('active');
          const dot = el.querySelector('.dot');
          if (dot) dot.classList.add('active');
        }
      }, delays[i]);
      stepTimeouts.push(t as any);
    });

    const elapsedEl = document.getElementById('elapsedTimer');
    const timerStart = performance.now();
    elapsedTimerInterval = setInterval(() => {
      const elapsed = (performance.now() - timerStart) / 1000;
      if (elapsedEl) {
        elapsedEl.textContent = elapsed.toFixed(1) + 's';
      }
    }, 100) as any;
  }

  // ── Render Results ────────────────────────────────────────────────
  function renderResults(data: APIResponse) {
    const abn  = data.abnormality;
    const path = data.pathology;
    const seg  = data.segmentation;
    const rep  = data.clinical_report;

    // Add glow classes based on prediction labels
    const abnCard = document.getElementById('abnCard');
    const pathCard = document.getElementById('pathCard');

    if (abnCard) {
      abnCard.classList.remove('glow-mass', 'glow-calcification');
      if (abn.label.toLowerCase() === 'mass') {
        abnCard.classList.add('glow-mass');
      } else if (abn.label.toLowerCase() === 'calcification') {
        abnCard.classList.add('glow-calcification');
      }
    }

    if (pathCard) {
      pathCard.classList.remove('glow-benign', 'glow-malignant');
      if (path.label.toLowerCase() === 'benign') {
        pathCard.classList.add('glow-benign');
      } else if (path.label.toLowerCase() === 'malignant') {
        pathCard.classList.add('glow-malignant');
      }
    }

    setLabel('abnLabel', abn.label, `badge-${abn.label}`);
    
    const abnConfEl = document.getElementById('abnConf');
    if (abnConfEl) abnConfEl.textContent = pct(abn.confidence);

    const abnBar = document.getElementById('abnBar');
    if (abnBar) abnBar.style.width = pct(abn.confidence);

    const probMass = document.getElementById('probMass');
    if (probMass) probMass.textContent = pct(abn.probabilities.mass);

    const probCalc = document.getElementById('probCalc');
    if (probCalc) probCalc.textContent = pct(abn.probabilities.calcification);

    setLabel('pathLabel', path.label, `badge-${path.label}`);

    const pathConfEl = document.getElementById('pathConf');
    if (pathConfEl) pathConfEl.textContent = pct(path.confidence);

    const pathBar = document.getElementById('pathBar');
    if (pathBar) pathBar.style.width = pct(path.confidence);

    const probBenign = document.getElementById('probBenign');
    if (probBenign) probBenign.textContent = pct(path.probabilities.benign);

    const probMalignant = document.getElementById('probMalignant');
    if (probMalignant) probMalignant.textContent = pct(path.probabilities.malignant);

    // Set visualization matrices image sources
    const imgMask = document.getElementById('imgMask') as HTMLImageElement | null;
    if (imgMask) imgMask.src = `data:image/png;base64,${seg.mask_b64}`;

    const imgOverlay = document.getElementById('imgOverlay') as HTMLImageElement | null;
    if (imgOverlay) imgOverlay.src = `data:image/png;base64,${seg.overlay_b64}`;

    const imgGradcam = document.getElementById('imgGradcam') as HTMLImageElement | null;
    if (imgGradcam) imgGradcam.src = `data:image/png;base64,${data.gradcam_b64}`;

    const coverage = document.getElementById('coverage');
    if (coverage) coverage.textContent = `${seg.coverage_pct}%`;

    const sectionTitles: Record<string, string> = {
      'clinical indication': 'Clinical Indication',
      'technique': 'Technique',
      'findings': 'Findings',
      'impression': 'Impression',
      'recommendation': 'Recommendation',
      'disclaimer': 'Disclaimer',
      'full_report': 'Report'
    };

    const reportDiv = document.getElementById('reportSections');
    if (reportDiv) {
      reportDiv.innerHTML = '';
      for (const [key, title] of Object.entries(sectionTitles)) {
        const text = rep.sections[key];
        if (text) {
          reportDiv.innerHTML += `<div class="report-section"><h4>${title}</h4><p>${text}</p></div>`;
        }
      }
    }

    const reportModel = document.getElementById('reportModel');
    if (reportModel) reportModel.textContent = rep.model_used;

    pdfB64 = data.pdf_b64;
    resultsEl.classList.remove('hidden');
    resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ── Download / Preview Report Modal ──────────────────────────────
  // "Download PDF" button → opens patient info modal first
  downloadBtn.addEventListener('click', () => {
    const examDate = document.getElementById('examDate') as HTMLInputElement | null;
    if (examDate) {
      examDate.value = new Date().toISOString().split('T')[0];
    }
    modalOverlay.classList.remove('hidden');
  });

  // "Preview" quick button → open preview immediately with current PDF
  if (previewQuickBtn) {
    previewQuickBtn.addEventListener('click', () => {
      if (pdfB64) openPdfPreview(pdfB64);
    });
  }

  // "Skip & Preview" → show current PDF in preview without regenerating
  const skipBtn = document.getElementById('skipBtn');
  if (skipBtn) {
    skipBtn.addEventListener('click', () => {
      modalOverlay.classList.add('hidden');
      if (pdfB64) openPdfPreview(pdfB64);
    });
  }

  // "Generate & Preview" → rebuild PDF with patient info then preview it
  const confirmBtn = document.getElementById('confirmBtn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', async () => {
      const patientName = (document.getElementById('patientName') as HTMLInputElement | null)?.value.trim();
      const patientId = (document.getElementById('patientId') as HTMLInputElement | null)?.value.trim();
      const referringPhysician = (document.getElementById('referringPhysician') as HTMLInputElement | null)?.value.trim();
      const examDate = (document.getElementById('examDate') as HTMLInputElement | null)?.value;
      const clinicalNotes = (document.getElementById('clinicalNotes') as HTMLTextAreaElement | null)?.value.trim();

      const patientInfo: PatientInfo = {
        patient_name: patientName,
        patient_id: patientId,
        referring_physician: referringPhysician,
        exam_date: examDate,
        clinical_notes: clinicalNotes,
      };

      modalOverlay.classList.add('hidden');

      const hasData = Object.values(patientInfo).some(v => v);
      if (!hasData) {
        if (pdfB64) openPdfPreview(pdfB64);
        return;
      }

      // Rebuild PDF with custom patient metadata
      const formData = new FormData();
      if (selectedFile) {
        formData.append('image', selectedFile);
      }
      formData.append('patient_info', JSON.stringify(patientInfo));

      // Show a lightweight in-bar loading state
      const confirmBtnEl = document.getElementById('confirmBtn') as HTMLButtonElement | null;
      if (confirmBtnEl) { confirmBtnEl.disabled = true; confirmBtnEl.textContent = 'Building…'; }

      try {
        const res = await fetch('/api/predict/', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok && data.pdf_b64) {
          pdfB64 = data.pdf_b64; // update cached copy
          openPdfPreview(data.pdf_b64);
        } else {
          console.warn("Could not regenerate report. Falling back to default PDF.");
          if (pdfB64) openPdfPreview(pdfB64);
        }
      } catch {
        if (pdfB64) openPdfPreview(pdfB64);
      } finally {
        if (confirmBtnEl) { confirmBtnEl.disabled = false; confirmBtnEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg> Generate &amp; Preview'; }
      }
    });
  }

  // Close modal on background overlay clicks
  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) modalOverlay.classList.add('hidden');
  });

  // PDF preview overlay controls
  if (btnClosePreview) {
    btnClosePreview.addEventListener('click', () => closePdfPreview());
  }
  if (btnOpenNewTab) {
    btnOpenNewTab.addEventListener('click', () => {
      if (currentPreviewBlobUrl) {
        window.open(currentPreviewBlobUrl, '_blank');
      }
    });
  }
  if (btnDownloadFromPreview) {
    btnDownloadFromPreview.addEventListener('click', () => {
      if (pdfB64) triggerDownload(pdfB64);
    });
  }

  function triggerDownload(b64: string) {
    if (!b64) return;
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) {
      arr[i] = bytes.charCodeAt(i);
    }
    const blob = new Blob([arr], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'deepmammo_report.pdf';
    link.click();
    URL.revokeObjectURL(url);
  }

  // ── PDF Preview Helper ────────────────────────────────────────────
  let currentPreviewBlobUrl: string | null = null;

  function openPdfPreview(b64: string) {
    if (!b64 || !pdfPreviewOverlay || !pdfPreviewIframe) return;
    // Revoke previous blob URL to avoid memory leaks
    if (currentPreviewBlobUrl) {
      URL.revokeObjectURL(currentPreviewBlobUrl);
      currentPreviewBlobUrl = null;
    }
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: 'application/pdf' });
    currentPreviewBlobUrl = URL.createObjectURL(blob);
    pdfPreviewIframe.src = currentPreviewBlobUrl;
    pdfPreviewOverlay.classList.remove('hidden');
  }

  function closePdfPreview() {
    if (!pdfPreviewOverlay || !pdfPreviewIframe) return;
    pdfPreviewOverlay.classList.add('hidden');
    pdfPreviewIframe.src = '';
    if (currentPreviewBlobUrl) {
      URL.revokeObjectURL(currentPreviewBlobUrl);
      currentPreviewBlobUrl = null;
    }
  }

  // ── Reset Interactive Playground ──────────────────────────────────
  resetBtn.addEventListener('click', () => {
    selectedFile = null;
    pdfB64 = null;
    if (imageInput) imageInput.value = '';
    fileNameEl.classList.add('hidden');
    predictBtn.disabled = true;
    resetBtn.classList.add('hidden');
    resultsEl.classList.add('hidden');
    hideError();

    // Reset upload preview
    if (imgUploadPreview) imgUploadPreview.src = '';
    if (uploadPreviewContainer) uploadPreviewContainer.classList.add('hidden');
    if (uploadIcon) uploadIcon.classList.remove('hidden');
    if (uploadHelperText) uploadHelperText.classList.remove('hidden');

    // Reset local preview image
    const previewEl = document.getElementById('imgOriginalPreview') as HTMLImageElement | null;
    if (previewEl) previewEl.src = '';

    // Clear JSON code block
    if (jsonOutput) {
      jsonOutput.textContent = '{\n  "status": "200 OK",\n  "waiting": "API Request has not been sent yet."\n}';
    }
    const abnCard = document.getElementById('abnCard');
    const pathCard = document.getElementById('pathCard');
    if (abnCard) {
      abnCard.classList.remove('glow-mass', 'glow-calcification');
    }
    if (pathCard) {
      pathCard.classList.remove('glow-benign', 'glow-malignant');
    }
    clearLoadingAnimation();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // ── API Keys Management ───────────────────────────────────────────
  interface ApiKey {
    id: string;
    name: string;
    key: string;
    created: string;
    scope: string;
  }

  const newKeyInput = document.getElementById('newKeyName') as HTMLInputElement | null;
  const btnCreateKey = document.getElementById('btnCreateKey') as HTMLButtonElement | null;
  const apiKeysTableBody = document.getElementById('apiKeysTableBody') as HTMLTableSectionElement | null;

  function getKeys(): ApiKey[] {
    const keysRaw = localStorage.getItem('deepmammo_api_keys');
    if (keysRaw) {
      return JSON.parse(keysRaw);
    }
    // Default initial mock keys
    const defaults: ApiKey[] = [
      { id: '1', name: 'Default Developer Key', key: 'sk_live_dev_8f2d4e9a1b7c093f12', created: '2026-05-24', scope: 'Read/Write' },
      { id: '2', name: 'Staging Analytics', key: 'sk_live_stg_09c3a2f8b5e7d14f77', created: '2026-05-26', scope: 'Read Only' }
    ];
    localStorage.setItem('deepmammo_api_keys', JSON.stringify(defaults));
    return defaults;
  }

  function saveKeys(keys: ApiKey[]) {
    localStorage.setItem('deepmammo_api_keys', JSON.stringify(keys));
  }

  function renderKeys() {
    if (!apiKeysTableBody) return;
    const keys = getKeys();
    apiKeysTableBody.innerHTML = '';
    keys.forEach(key => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${key.name}</strong></td>
        <td>${key.created}</td>
        <td>
          <code class="key-display" data-full-key="${key.key}">••••••••••••••••</code>
        </td>
        <td><span class="badge badge-benign" style="font-size: 0.7rem; background:#E2F8E8; color:#10B981;">${key.scope}</span></td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn-action btn-reveal" style="background:#F1F5F9; border:none; padding:4px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer; font-weight:600; color:var(--brand-navy);">Reveal</button>
            <button class="btn-action btn-copy" style="background:#F1F5F9; border:none; padding:4px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer; font-weight:600; color:var(--brand-navy);">Copy</button>
            <button class="btn-action btn-revoke" style="background:rgba(216, 90, 48, 0.1); border:none; padding:4px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer; font-weight:600; color:var(--rose-coral);">Revoke</button>
          </div>
        </td>
      `;

      const revealBtn = tr.querySelector('.btn-reveal') as HTMLButtonElement;
      const copyBtn = tr.querySelector('.btn-copy') as HTMLButtonElement;
      const revokeBtn = tr.querySelector('.btn-revoke') as HTMLButtonElement;
      const codeEl = tr.querySelector('.key-display') as HTMLElement;

      revealBtn.addEventListener('click', () => {
        if (codeEl.textContent?.includes('•')) {
          codeEl.textContent = codeEl.getAttribute('data-full-key');
          revealBtn.textContent = 'Hide';
        } else {
          codeEl.textContent = '••••••••••••••••';
          revealBtn.textContent = 'Reveal';
        }
      });

      copyBtn.addEventListener('click', () => {
        const fullKey = codeEl.getAttribute('data-full-key') || '';
        navigator.clipboard.writeText(fullKey);
        alert(`Copied key "${key.name}" to clipboard!`);
      });

      revokeBtn.addEventListener('click', () => {
        if (confirm(`Are you absolutely sure you want to revoke the credential "${key.name}"? This action cannot be undone.`)) {
          const freshKeys = getKeys().filter(k => k.id !== key.id);
          saveKeys(freshKeys);
          renderKeys();
        }
      });

      apiKeysTableBody.appendChild(tr);
    });
  }

  if (btnCreateKey && newKeyInput) {
    btnCreateKey.addEventListener('click', () => {
      const name = newKeyInput.value.trim();
      if (!name) {
        alert('Please provide a descriptive name for your API key.');
        return;
      }
      const randomHex = Array.from({ length: 24 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
      const newKey: ApiKey = {
        id: Date.now().toString(),
        name: name,
        key: `sk_live_${randomHex}`,
        created: new Date().toISOString().split('T')[0],
        scope: 'Read/Write'
      };
      const keys = getKeys();
      keys.push(newKey);
      saveKeys(keys);
      renderKeys();
      updateDocsCodeSnippet();
      newKeyInput.value = '';
      alert(`API Key "${name}" successfully generated!`);
    });
  }

  // ── Interactive API Docs Code Switcher ──────────────────────────────
  const docsCodeBlock = document.getElementById('docsCodeBlock') as HTMLElement | null;
  const btnCopyDocsCode = document.getElementById('btnCopyDocsCode') as HTMLButtonElement | null;
  const codeTabButtons = document.querySelectorAll('.code-tab-btn');

  function getActiveApiKey(): string {
    const keys = getKeys();
    if (keys.length > 0) {
      return keys[keys.length - 1].key;
    }
    return 'sk_live_dev_8f2d4e9a1b7c093f12';
  }

  function getRecipes(): Record<string, string> {
    const key = getActiveApiKey();
    return {
      curl: `curl -X POST http://127.0.0.1:8000/api/predict/ \\
  -H "Authorization: Bearer ${key}" \\
  -F "image=@scan.png" \\
  -F "model_routing=deepmammo-v1-resnet" \\
  -F "confidence_threshold=0.85"`,
      python: `import requests

url = "http://127.0.0.1:8000/api/predict/"
headers = {
    "Authorization": "Bearer ${key}"
}
files = {
    "image": open("scan.png", "rb")
}
data = {
    "model_routing": "deepmammo-v1-resnet",
    "confidence_threshold": "0.85"
}

response = requests.post(url, headers=headers, files=files, data=data)
print(response.json())`,
      javascript: `const formData = new FormData();
formData.append("image", fileInput.files[0]);
formData.append("model_routing", "deepmammo-v1-resnet");
formData.append("confidence_threshold", "0.85");

fetch("http://127.0.0.1:8000/api/predict/", {
  method: "POST",
  headers: {
    "Authorization": "Bearer ${key}"
  },
  body: formData
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error("Error:", error));`
    };
  }

  function updateDocsCodeSnippet() {
    if (!docsCodeBlock) return;
    const activeBtn = document.querySelector('.code-tab-btn.active') as HTMLButtonElement | null;
    const lang = activeBtn?.getAttribute('data-lang') || 'curl';
    const recipesList = getRecipes();
    if (recipesList[lang]) {
      docsCodeBlock.textContent = recipesList[lang];
    }
  }

  codeTabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      // Remove active class from all buttons
      codeTabButtons.forEach(b => b.classList.remove('active'));
      // Add active to current
      btn.classList.add('active');
      updateDocsCodeSnippet();
    });
  });

  if (btnCopyDocsCode) {
    btnCopyDocsCode.addEventListener('click', () => {
      if (docsCodeBlock) {
        navigator.clipboard.writeText(docsCodeBlock.textContent || '');
        alert('Copied Code Recipe to clipboard!');
      }
    });
  }

  // Populate docs code recipe on start
  updateDocsCodeSnippet();

  // Initial keys render
  renderKeys();

  // ── UI Helper Logic ────────────────────────────────────────────────

  function pct(val: number) {
    return (val * 100).toFixed(1) + '%';
  }

  function setLabel(id: string, text: string, cls: string) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = text.charAt(0).toUpperCase() + text.slice(1);
      let classList = `badge ${cls}`;
      if (text.toLowerCase() === 'malignant') {
        classList += ' badge-malignant-pulse';
      }
      el.className = classList;
    }
  }

  function showError(msg: string) {
    if (errorBox) {
      errorBox.textContent = '⚠ ' + msg;
      errorBox.classList.remove('hidden');
    }
  }

  function hideError() {
    if (errorBox) {
      errorBox.classList.add('hidden');
    }
  }
});
