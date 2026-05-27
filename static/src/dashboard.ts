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
  const modalOverlay=document.getElementById('modalOverlay') as HTMLDivElement | null;
  const jsonOutput = document.getElementById('jsonOutput') as HTMLElement | null;

  // Form controls inputs
  const modelSelect     = document.getElementById('modelSelect') as HTMLSelectElement | null;
  const customThreshold = document.getElementById('customThreshold') as HTMLInputElement | null;

  let selectedFile: File | null = null;
  let pdfB64: string | null     = null;

  if (!uploadZone || !imageInput || !predictBtn || !resetBtn || !fileNameEl || !loadingEl || !resultsEl || !errorBox || !downloadBtn || !modalOverlay) {
    console.error("Required dashboard DOM elements are missing.");
    return;
  }

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
      const previewEl = document.getElementById('imgOriginalPreview') as HTMLImageElement | null;
      if (previewEl && e.target?.result) {
        previewEl.src = e.target.result as string;
      }
    };
    reader.readAsDataURL(file);
  }

  // ── Run Analysis Pipeline ──────────────────────────────────────────
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

    try {
      const res = await fetch('/api/predict/', { method: 'POST', body: formData });
      const data = await res.json();
      
      // Trace JSON payload to dashboard contrast panel
      if (jsonOutput) {
        jsonOutput.textContent = JSON.stringify(data, null, 2);
      }

      if (!res.ok) {
        showError(data.error || 'Prediction failed.');
        return;
      }
      renderResults(data);
    } catch (err) {
      showError('Network error. Is the server running?');
    } finally {
      loadingEl.classList.add('hidden');
      predictBtn.disabled = false;
    }
  });

  // ── Animate Loading Steps ─────────────────────────────────────────
  function animateSteps() {
    const steps = ['step1', 'step2', 'step3', 'step4', 'step5'];
    const delays = [0, 1200, 2400, 3600, 5000];
    steps.forEach((id, i) => {
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) {
          el.classList.add('active');
          const dot = el.querySelector('.dot');
          if (dot) dot.classList.add('active');
        }
      }, delays[i]);
    });
  }

  // ── Render Results ────────────────────────────────────────────────
  function renderResults(data: APIResponse) {
    const abn  = data.abnormality;
    const path = data.pathology;
    const seg  = data.segmentation;
    const rep  = data.clinical_report;

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

  // ── Download Report Modal ─────────────────────────────────────────
  downloadBtn.addEventListener('click', () => {
    const examDate = document.getElementById('examDate') as HTMLInputElement | null;
    if (examDate) {
      examDate.value = new Date().toISOString().split('T')[0];
    }
    modalOverlay.classList.remove('hidden');
  });

  const skipBtn = document.getElementById('skipBtn');
  if (skipBtn) {
    skipBtn.addEventListener('click', () => {
      modalOverlay.classList.add('hidden');
      if (pdfB64) triggerDownload(pdfB64);
    });
  }

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
        if (pdfB64) triggerDownload(pdfB64);
        return;
      }

      // Rebuild PDF with custom metadata
      const formData = new FormData();
      if (selectedFile) {
        formData.append('image', selectedFile);
      }
      formData.append('patient_info', JSON.stringify(patientInfo));

      try {
        const res = await fetch('/api/predict/', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok && data.pdf_b64) {
          triggerDownload(data.pdf_b64);
        } else {
          console.warn("Could not regenerate report. Falling back to default PDF.");
          if (pdfB64) triggerDownload(pdfB64);
        }
      } catch {
        if (pdfB64) triggerDownload(pdfB64);
      }
    });
  }

  // Close modal on background overlay clicks
  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) modalOverlay.classList.add('hidden');
  });

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

    // Reset local preview image
    const previewEl = document.getElementById('imgOriginalPreview') as HTMLImageElement | null;
    if (previewEl) previewEl.src = '';

    // Clear JSON code block
    if (jsonOutput) {
      jsonOutput.textContent = '{\n  "status": "200 OK",\n  "waiting": "API Request has not been sent yet."\n}';
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
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // ── UI Helper Logic ────────────────────────────────────────────────
  function pct(val: number) {
    return (val * 100).toFixed(1) + '%';
  }

  function setLabel(id: string, text: string, cls: string) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = text.charAt(0).toUpperCase() + text.slice(1);
      el.className = `badge ${cls}`;
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
