/**
 * PDF Comparison Tool – Frontend Application
 * Vanilla JS with i18n, SSE progress, and API calls.
 */

// ============================================================
//  i18n Translations
// ============================================================
const I18N = {
    vi: {
        appTitle: 'Công cụ So sánh PDF',
        appDesc: 'So sánh tự động PDF Brief và Produit Fini',
        // Step 1
        step1Title: 'Chọn PDF A (Brief)',
        optUpload: 'Upload file mới',
        optExisting: 'Chọn từ danh sách',
        uploadHint: 'Kéo thả file PDF hoặc nhấn để chọn',
        uploadHintSub: 'Chỉ chấp nhận file .pdf',
        noProcessed: 'Chưa có PDF nào đã xử lý.',
        selectPdf: 'Chọn PDF đã xử lý:',
        btnStep1: 'Chạy Step 1 (Detect Bbox)',
        btnStep23: 'Chạy Step 2 & 3 (Detect ID + OCR)',
        pdfAReady: 'PDF A đã sẵn sàng',
        bboxCount: '{0} bbox',
        idCount: '{0} ID',
        alreadyProcessed: 'PDF này đã có dữ liệu bbox + ID.',
        deleteBtn: 'Xóa dữ liệu',
        deleteConfirm: 'Bạn có chắc muốn xóa toàn bộ dữ liệu của PDF này?',
        deleteWarning: 'Hành động này không thể hoàn tác!',
        confirmBtn: 'Xác nhận xóa',
        cancelBtn: 'Hủy',
        // Step 2
        step2Title: 'Chọn PDF B (Produit Fini)',
        uploadBHint: 'Kéo thả file PDF B (có thể nhiều file)',
        // Step 3
        step3Title: 'Chạy So sánh YOLO',
        btnRunYolo: 'So sánh thực thể (YOLO)',
        // Progress
        processing: 'Đang xử lý...',
        // Results
        resultsTitle: 'Kết quả so sánh thực thể',
        metricMatched: 'Cặp matched',
        metricDiff: 'Có sai khác',
        metricUnmatched: 'Brief chưa match',
        metricExtraFinal: 'Final dư',
        labelMissing: '❌ Thiếu trong Final',
        labelExtra: '➕ Thừa trong Final',
        labelMatch: '✅ Khớp',
        labelNoPI: '(fallback: full block)',
        downloadBtn: 'Tải JSON',
        success: 'Thành công',
        failed: 'Thất bại',
        uploadFirst: 'Vui lòng chọn file trước',
        modelNotFound: 'Không tìm thấy model YOLO',
        selectedFiles: 'Đã chọn {0} file:',
        noResults: 'Không có kết quả',
        unmatchedFinal: 'Block Final chưa match',
    },
    en: {
        appTitle: 'PDF Comparison Tool',
        appDesc: 'Automatically compare Brief vs. Produit Fini PDFs',
        step1Title: 'Select PDF A (Brief)',
        optUpload: 'Upload new file',
        optExisting: 'Choose from list',
        uploadHint: 'Drag & drop PDF or click to select',
        uploadHintSub: 'Only .pdf files accepted',
        noProcessed: 'No processed PDFs yet.',
        selectPdf: 'Select a processed PDF:',
        btnStep1: 'Run Step 1 (Detect Bbox)',
        btnStep23: 'Run Step 2 & 3 (Detect ID + OCR)',
        pdfAReady: 'PDF A is ready',
        bboxCount: '{0} bbox',
        idCount: '{0} IDs',
        alreadyProcessed: 'This PDF already has bbox + ID data.',
        deleteBtn: 'Delete data',
        deleteConfirm: 'Are you sure you want to delete all data for this PDF?',
        deleteWarning: 'This action cannot be undone!',
        confirmBtn: 'Confirm delete',
        cancelBtn: 'Cancel',
        step2Title: 'Select PDF B (Produit Fini)',
        uploadBHint: 'Drag & drop PDF B files (multiple allowed)',
        step3Title: 'Run YOLO Comparison',
        btnRunYolo: 'Compare Entities (YOLO)',
        processing: 'Processing...',
        resultsTitle: 'Entity Comparison Results',
        metricMatched: 'Matched pairs',
        metricDiff: 'With diff',
        metricUnmatched: 'Unmatched brief',
        metricExtraFinal: 'Extra in final',
        labelMissing: '❌ Missing in Final',
        labelExtra: '➕ Extra in Final',
        labelMatch: '✅ Matching',
        labelNoPI: '(fallback: full block)',
        downloadBtn: 'Download JSON',
        success: 'Success',
        failed: 'Failed',
        uploadFirst: 'Please select a file first',
        modelNotFound: 'YOLO model not found',
        selectedFiles: 'Selected {0} file(s):',
        noResults: 'No results',
        unmatchedFinal: 'Unmatched Final blocks',
    },
    fr: {
        appTitle: 'Outil de Comparaison PDF',
        appDesc: 'Comparer automatiquement les PDF Brief et Produit Fini',
        step1Title: 'Sélectionner PDF A (Brief)',
        optUpload: 'Importer un nouveau fichier',
        optExisting: 'Choisir dans la liste',
        uploadHint: 'Glisser-déposer le PDF ou cliquer pour sélectionner',
        uploadHintSub: 'Fichiers .pdf uniquement',
        noProcessed: 'Aucun PDF traité.',
        selectPdf: 'Sélectionner un PDF traité :',
        btnStep1: 'Lancer Étape 1 (Detect Bbox)',
        btnStep23: 'Lancer Étapes 2 & 3 (Detect ID + OCR)',
        pdfAReady: 'PDF A est prêt',
        bboxCount: '{0} bbox',
        idCount: '{0} ID',
        alreadyProcessed: 'Ce PDF possède déjà des données bbox + ID.',
        deleteBtn: 'Supprimer les données',
        deleteConfirm: 'Êtes-vous sûr de vouloir supprimer toutes les données de ce PDF ?',
        deleteWarning: 'Cette action est irréversible !',
        confirmBtn: 'Confirmer la suppression',
        cancelBtn: 'Annuler',
        step2Title: 'Sélectionner PDF B (Produit Fini)',
        uploadBHint: 'Glisser-déposer les PDF B (multiples autorisés)',
        step3Title: 'Comparaison YOLO',
        btnRunYolo: 'Comparer les entités (YOLO)',
        processing: 'Traitement en cours...',
        resultsTitle: 'Résultats de comparaison',
        metricMatched: 'Paires matchées',
        metricDiff: 'Avec différences',
        metricUnmatched: 'Brief sans match',
        metricExtraFinal: 'Extra dans Final',
        labelMissing: '❌ Absent dans Final',
        labelExtra: '➕ En trop dans Final',
        labelMatch: '✅ Correspondance',
        labelNoPI: '(repli: bloc entier)',
        downloadBtn: 'Télécharger JSON',
        success: 'Succès',
        failed: 'Échoué',
        uploadFirst: 'Veuillez d\'abord sélectionner un fichier',
        modelNotFound: 'Modèle YOLO introuvable',
        selectedFiles: '{0} fichier(s) sélectionné(s) :',
        noResults: 'Aucun résultat',
        unmatchedFinal: 'Blocs Final sans correspondance',
    },
};

// ============================================================
//  App State
// ============================================================
const state = {
    lang: localStorage.getItem('pdf_tool_lang') || 'vi',
    sessionId: null,
    pdfAName: null,
    pdfAFile: null, // Track selected file A
    pdfAReady: false,
    pdfBFiles: [],
    running: false,
};

// ============================================================
//  Helpers
// ============================================================
function t(key, ...args) {
    let text = (I18N[state.lang] || I18N.vi)[key] || key;
    args.forEach((arg, i) => { text = text.replace(`{${i}}`, arg); });
    return text;
}

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function showAlert(container, type, msg) {
    const icons = { info: 'info', success: 'check-circle', warning: 'alert-triangle', error: 'x-circle' };
    const el = document.createElement('div');
    el.className = `alert alert-${type}`;
    el.innerHTML = `<i data-lucide="${icons[type] || 'info'}"></i><span>${msg}</span>`;
    container.prepend(el);
    if (window.lucide) lucide.createIcons();
    setTimeout(() => el.remove(), 8000);
}

async function api(method, url, data = null, isForm = true) {
    const opts = { method };
    if (data) {
        if (isForm && !(data instanceof FormData)) {
            const fd = new FormData();
            Object.entries(data).forEach(([k, v]) => fd.append(k, v));
            opts.body = fd;
        } else {
            opts.body = data;
        }
    }
    const res = await fetch(`/api/${url}`, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API error');
    }
    return res.json();
}

// ============================================================
//  Render Functions
// ============================================================
function renderApp() {
    const app = $('#app');
    app.innerHTML = `
        <div class="app-header">
            <h1><i data-lucide="layers" class="icon-lg"></i> ${t('appTitle')}</h1>
            <p>${t('appDesc')}</p>
            <div class="header-controls">
                <div class="lang-switcher">
                    <button class="lang-btn ${state.lang === 'vi' ? 'active' : ''}" data-lang="vi">VN</button>
                    <button class="lang-btn ${state.lang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
                    <button class="lang-btn ${state.lang === 'fr' ? 'active' : ''}" data-lang="fr">FR</button>
                </div>
            </div>
        </div>

        <div class="main-layout">
            <!-- Top Left: PDF A -->
            <div class="card" id="card-step1">
                <div class="card-title">
                    <span class="step-badge">1</span>
                    <i data-lucide="file-text"></i>
                    <span>${t('step1Title')}</span>
                </div>
                <div class="radio-group" id="pdf-a-mode">
                    <div class="radio-option">
                        <input type="radio" name="pdfAMode" id="modeUpload" value="upload" checked>
                        <label for="modeUpload"><i data-lucide="upload-cloud"></i> ${t('optUpload')}</label>
                    </div>
                    <div class="radio-option">
                        <input type="radio" name="pdfAMode" id="modeExisting" value="existing">
                        <label for="modeExisting"><i data-lucide="folder-open"></i> ${t('optExisting')}</label>
                    </div>
                </div>

                <div id="upload-a-section" style="margin-top:18px;">
                    <div class="upload-zone" id="dropzone-a">
                        <div class="upload-icon"><i data-lucide="file-up"></i></div>
                        <div class="upload-title">${t('uploadHint')}</div>
                        <div class="upload-hint">${t('uploadHintSub')}</div>
                        <input type="file" accept=".pdf" id="file-a-input">
                    </div>
                    <div id="file-a-info"></div>
                </div>

                <div id="existing-a-section" class="hidden" style="margin-top:18px;">
                    <div id="processed-list"></div>
                </div>

                <div id="pdf-a-status" style="margin-top:14px;"></div>
                <div id="pdf-a-actions" style="margin-top:14px;"></div>
            </div>

            <!-- Top Right: PDF B & Run -->
            <div id="card-step2-wrapper">
                <div class="card" id="card-step2">
                    <div class="card-title">
                        <span class="step-badge">2</span>
                        <i data-lucide="files"></i>
                        <span>${t('step2Title')}</span>
                    </div>
                    <div class="upload-zone" id="dropzone-b">
                        <div class="upload-icon"><i data-lucide="file-plus-2"></i></div>
                        <div class="upload-title">${t('uploadBHint')}</div>
                        <div class="upload-hint">${t('uploadHintSub')}</div>
                        <input type="file" accept=".pdf" multiple id="file-b-input">
                    </div>
                    <div id="file-b-list" class="file-list"></div>
                </div>

                <div class="card" id="card-step3" style="margin-top:20px;">
                    <div class="card-title">
                        <span class="step-badge">3</span>
                        <i data-lucide="scan-search"></i>
                        <span>${t('step3Title')}</span>
                    </div>
                    <button class="btn btn-primary btn-full" id="btn-run-pipeline" disabled>
                        <i data-lucide="play"></i> ${t('btnRunYolo')}
                    </button>
                </div>
            </div>

            <!-- Bottom: Progress & Results -->
            <div id="result-section-wrapper">
                <div class="card ${!state.running && !state.sessionId ? 'hidden' : ''}" id="card-progress">
                    <div class="card-title">
                        <i data-lucide="refresh-cw" class="spinner-icon"></i>
                        <span>${t('processing')}</span>
                    </div>
                    <div id="pipeline-progress">
                        <div class="progress-wrapper">
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill" id="progress-fill" style="width:0%"></div>
                            </div>
                            <div class="progress-text">
                                <span id="progress-label">${t('processing')}</span>
                                <span id="progress-pct">0%</span>
                            </div>
                        </div>
                        <div class="log-container" id="progress-log"></div>
                    </div>
                </div>

                <!-- Results -->
                <div class="card hidden" id="card-results">
                    <div class="card-title">
                        <i data-lucide="bar-chart-3"></i>
                        <span>${t('resultsTitle')}</span>
                    </div>
                    <div id="results-container"></div>
                </div>
            </div>
        </div>

        <!-- Dialog -->
        <div id="dialog-overlay" class="dialog-overlay hidden"></div>
    `;

    bindEvents();
    if (window.lucide) lucide.createIcons();
}

function bindEvents() {
    // Language switcher
    $$('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            state.lang = btn.dataset.lang;
            localStorage.setItem('pdf_tool_lang', state.lang);
            renderApp();
            // Restore state
            if (state.pdfAReady) {
                const info = { bbox_count: 0, id_count: 0 }; // Placeholder, will be refreshed
                api('GET', `pdf-info/${state.pdfAName}`).then(showPdfAStatus);
            } else if (state.pdfAFile) {
                preparePdfA(state.pdfAFile);
            }
        });
    });

    // PDF A mode toggle
    $$('#pdf-a-mode input').forEach(radio => {
        radio.addEventListener('change', () => {
            const mode = radio.value;
            if (mode === 'upload') {
                $('#upload-a-section').classList.remove('hidden');
                $('#existing-a-section').classList.add('hidden');
            } else {
                $('#upload-a-section').classList.add('hidden');
                $('#existing-a-section').classList.remove('hidden');
                loadProcessedPdfs();
            }
        });
    });

    // Upload PDF A
    const fileAInput = $('#file-a-input');
    const dropzoneA = $('#dropzone-a');

    fileAInput.addEventListener('change', () => {
        if (fileAInput.files.length > 0) preparePdfA(fileAInput.files[0]);
    });

    ['dragover', 'dragenter'].forEach(ev => {
        dropzoneA.addEventListener(ev, e => { e.preventDefault(); dropzoneA.classList.add('dragover'); });
    });
    ['dragleave', 'drop'].forEach(ev => {
        dropzoneA.addEventListener(ev, e => { e.preventDefault(); dropzoneA.classList.remove('dragover'); });
    });
    dropzoneA.addEventListener('drop', e => {
        if (e.dataTransfer.files.length > 0) preparePdfA(e.dataTransfer.files[0]);
    });

    // Upload PDF B
    const fileBInput = $('#file-b-input');
    const dropzoneB = $('#dropzone-b');

    if (fileBInput) {
        fileBInput.addEventListener('change', () => {
            if (fileBInput.files.length > 0) handlePdfBUpload(fileBInput.files);
        });

        ['dragover', 'dragenter'].forEach(ev => {
            dropzoneB.addEventListener(ev, e => { e.preventDefault(); dropzoneB.classList.add('dragover'); });
        });
        ['dragleave', 'drop'].forEach(ev => {
            dropzoneB.addEventListener(ev, e => { e.preventDefault(); dropzoneB.classList.remove('dragover'); });
        });
        dropzoneB.addEventListener('drop', e => {
            if (e.dataTransfer.files.length > 0) handlePdfBUpload(e.dataTransfer.files);
        });
    }

    // Run YOLO compare
    const btnRun = $('#btn-run-pipeline');
    if (btnRun) {
        btnRun.addEventListener('click', runYoloCompare);
    }
}

// ============================================================
//  PDF A Handlers
// ============================================================
function preparePdfA(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showAlert($('#pdf-a-status'), 'error', t('uploadFirst'));
        return;
    }
    state.pdfAFile = file;
    state.pdfAName = file.name.replace('.pdf', '');
    state.pdfAReady = false; // Not yet processed

    const statusEl = $('#pdf-a-status');
    const objectUrl = URL.createObjectURL(file);
    statusEl.innerHTML = `
        <div class="file-item">
            <i data-lucide="file"></i>
            <span class="file-name">${file.name}</span>
        </div>
        <div class="pdf-preview" style="height: 400px; margin-top: 10px;">
            <iframe src="${objectUrl}"></iframe>
        </div>
    `;
    if (window.lucide) lucide.createIcons();
    
    // Enable run button if PDF B files are also present
    const runBtn = $('#btn-run-pipeline');
    if (runBtn) runBtn.disabled = state.pdfBFiles.length === 0;

    // Thu gọn khu vực chọn/upload
    $('#pdf-a-mode').classList.add('hidden');
    $('#upload-a-section').classList.add('hidden');
}

async function handlePdfAUpload() {
    if (!state.pdfAFile) return;

    const statusEl = $('#pdf-a-status');
    statusEl.innerHTML = `<div class="alert alert-info"><span class="spinner"></span> Uploading PDF A...</div>`;

    const fd = new FormData();
    fd.append('file', state.pdfAFile);
    const res = await api('POST', 'upload-pdf-a', fd, false);

    state.sessionId = res.session_id;
    state.pdfAName = res.pdf_name;

    if (res.already_processed) {
        state.pdfAReady = true;
        const previewUrl = `/api/pdf-a/${res.pdf_name}`;
        showPdfAStatus(res, previewUrl);
        return true;
    } else {
        // Need to run step 1 and 2&3
        appendLog('PDF A uploaded, starting analysis...');
        await runStep1();
        await runStep23();
        // Since we now have results, show the status with a preview
        const previewUrl = `/api/pdf-a/${res.pdf_name}`;
        showPdfAStatus({ ...res, bbox_count: state.bboxCount, id_count: state.idCount }, previewUrl);
        return true;
    }
}

async function selectExistingPdf(name) {
    const statusEl = $('#pdf-a-status');
    statusEl.innerHTML = `<div class="alert alert-info"><span class="spinner"></span> Loading...</div>`;

    try {
        const res = await api('POST', 'select-pdf-a', { name });
        state.sessionId = res.session_id;
        state.pdfAName = res.pdf_name;
        state.pdfAReady = true;
        state.pdfAFile = null;

        // Highlight selected
        $$('.pdf-list-item').forEach(el => el.classList.remove('selected'));
        const selectedEl = document.querySelector(`.pdf-list-item[data-name="${name}"]`);
        if (selectedEl) selectedEl.classList.add('selected');

        const previewUrl = `/api/pdf-a/${res.pdf_name}`;
        showPdfAStatus(res, previewUrl);
        
        // Enable run button if PDF B files are also present
        const runBtn = $('#btn-run-pipeline');
        if (runBtn) runBtn.disabled = state.pdfBFiles.length === 0;

        // Thu gọn khu vực chọn/existing
        $('#pdf-a-mode').classList.add('hidden');
        $('#existing-a-section').classList.add('hidden');
    } catch (err) {
        statusEl.innerHTML = '';
        showAlert(statusEl, 'error', err.message);
    }
}

function showPdfAStatus(data, previewUrl = null) {
    const statusEl = $('#pdf-a-status');
    const info = data || {};
    let finalUrl = previewUrl;
    if (!finalUrl && state.pdfAFile) {
        finalUrl = URL.createObjectURL(state.pdfAFile);
    } else if (!finalUrl && state.pdfAName) {
        finalUrl = `/api/pdf-a/${state.pdfAName}`;
    }

    statusEl.innerHTML = `
        <div class="alert alert-success">
            <i data-lucide="check"></i>
            <div>
                <strong>${t('pdfAReady')}: ${state.pdfAName}</strong><br>
                <div style="margin-top: 5px;">
                    <span class="status-chip chip-success">${t('bboxCount', info.bbox_count || '...')}</span>
                    <span class="status-chip chip-info">${t('idCount', info.id_count || '...')}</span>
                </div>
            </div>
        </div>
        ${finalUrl ? `<div class="pdf-preview" style="height: 400px; margin-top: 10px;"><iframe src="${finalUrl}"></iframe></div>` : ''}
    `;
    if (window.lucide) lucide.createIcons();

    // Thu gọn toàn bộ khu vực chọn PDF A
    $('#pdf-a-mode').classList.add('hidden');
    $('#upload-a-section').classList.add('hidden');
    $('#existing-a-section').classList.add('hidden');

    // Delete button
    const actionsEl = $('#pdf-a-actions');
    actionsEl.innerHTML = `
        <button class="btn btn-danger btn-sm" id="btn-delete-a">${t('deleteBtn')}</button>
    `;
    $('#btn-delete-a').addEventListener('click', () => showDeleteDialog());
}

function showPdfAStepButtons(data) {
    const statusEl = $('#pdf-a-status');
    statusEl.innerHTML = `
        <div class="file-item">
            <i data-lucide="file"></i>
            <span class="file-name">${state.pdfAName}.pdf</span>
        </div>
    `;
    if (window.lucide) lucide.createIcons();

    const actionsEl = $('#pdf-a-actions');
    const needStep1 = !data.already_processed && data.bbox_count === 0;
    const needStep23 = data.bbox_count > 0 && data.id_count === 0;

    if (needStep1) {
        actionsEl.innerHTML = `<button class="btn btn-primary" id="btn-step1">${t('btnStep1')}</button>`;
        $('#btn-step1').addEventListener('click', runStep1);
    } else if (needStep23) {
        actionsEl.innerHTML = `<button class="btn btn-primary" id="btn-step23">${t('btnStep23')}</button>`;
        $('#btn-step23').addEventListener('click', runStep23);
    }
}

async function runStep1() {
    const btn = $('#btn-step1');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> Processing...`;
    }

    const statusEl = $('#pdf-a-status');

    try {
        const res = await api('POST', 'run-step1', {
            session_id: state.sessionId,
            pdf_name: state.pdfAName,
        });
        showAlert(statusEl, 'success', t('step1Done', res.total_bbox));

        // Now show step23 button if it's manual mode
        const actionsEl = $('#pdf-a-actions');
        if (actionsEl && !state.running) {
            actionsEl.innerHTML = `<button class="btn btn-primary" id="btn-step23">${t('btnStep23')}</button>`;
            $('#btn-step23').addEventListener('click', runStep23);
        }
    } catch (err) {
        if (statusEl) showAlert(statusEl, 'error', err.message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = t('btnStep1');
        }
    }
}

async function runStep23() {
    const btn = $('#btn-step23');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> Processing...`;
    }

    const statusEl = $('#pdf-a-status');

    try {
        const res = await api('POST', 'run-step23', {
            session_id: state.sessionId,
            pdf_name: state.pdfAName,
        });
        if (statusEl) showAlert(statusEl, 'success', t('step23Done', res.step2_saved, res.step3_renamed));

        state.pdfAReady = true;
        const info = await api('GET', `pdf-info/${state.pdfAName}`);
        showPdfAStatus(info);
    } catch (err) {
        if (statusEl) showAlert(statusEl, 'error', err.message);
        if (btn) {
            btn.disabled = false;
            btn.textContent = t('btnStep23');
        }
    }
}

async function loadProcessedPdfs() {
    const container = $('#processed-list');
    container.innerHTML = `<div class="alert alert-info"><span class="spinner"></span> Loading...</div>`;

    try {
        const res = await api('GET', 'processed-pdfs');
        if (res.pdfs.length === 0) {
            container.innerHTML = `<div class="alert alert-warning">${t('noProcessed')}</div>`;
            return;
        }

        container.innerHTML = `<div class="pdf-list">${res.pdfs.map(p => `
            <div class="pdf-list-item" data-name="${p.name}">
                <i data-lucide="file-check" class="pdf-icon"></i>
                <div class="pdf-details">
                    <div class="pdf-name">${p.name}</div>
                    <div class="pdf-meta">${t('bboxCount', p.bbox_count)} · ${t('idCount', p.id_count)}</div>
                </div>
                <span class="status-chip ${p.has_bbox && p.has_id ? 'chip-success' : 'chip-warning'}">
                    <i data-lucide="${p.has_bbox && p.has_id ? 'check' : 'alert-circle'}"></i>
                </span>
            </div>
        `).join('')}</div>`;

        if (window.lucide) lucide.createIcons();

        $$('.pdf-list-item').forEach(item => {
            item.addEventListener('click', () => selectExistingPdf(item.dataset.name));
        });
    } catch (err) {
        container.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
    }
}

// ============================================================
//  PDF B Handlers
// ============================================================
async function handlePdfBUpload(files) {
    state.pdfBFiles = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    renderPdfBList();

    const btnRun = $('#btn-run-pipeline');
    if (btnRun) {
        btnRun.disabled = state.pdfBFiles.length === 0 || (!state.pdfAName && !state.pdfAFile);
    }
}

function renderPdfBList() {
    const container = $('#file-b-list');
    if (state.pdfBFiles.length === 0) {
        container.innerHTML = '';
        $('#dropzone-b').classList.remove('hidden');
        return;
    }
    $('#dropzone-b').classList.add('hidden');
    container.innerHTML = state.pdfBFiles.map((f, i) => {
        const objectUrl = URL.createObjectURL(f);
        return `
            <div class="file-item-wrapper" style="margin-bottom: 20px;">
                <div class="file-item">
                    <i data-lucide="file-text"></i>
                    <span class="file-name">${f.name}</span>
                    <span class="file-remove" onclick="removePdfB(${i})"><i data-lucide="x"></i></span>
                </div>
                <div class="pdf-preview" style="height: 300px; margin-top: 8px;">
                    <iframe src="${objectUrl}"></iframe>
                </div>
            </div>
        `;
    }).join('');

    if (window.lucide) lucide.createIcons();

    $$('.file-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            state.pdfBFiles.splice(parseInt(btn.dataset.idx), 1);
            renderPdfBList();
            const runBtn = $('#btn-run-pipeline');
            if (runBtn) runBtn.disabled = state.pdfBFiles.length === 0;
        });
    });
}



// ============================================================
//  YOLO Compare Execution
// ============================================================
async function runYoloCompare() {
    if (state.pdfBFiles.length === 0 || state.running) return;
    if (!state.pdfAName && !state.pdfAFile) return;

    state.running = true;

    const btn = $('#btn-run-pipeline');
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${t('processing')}`;

    const progressCard = $('#card-progress');
    if (progressCard) progressCard.classList.remove('hidden');
    $('#progress-log').innerHTML = '';
    updateProgress(0, t('processing'));

    try {
        // 1) Upload PDF A if not yet done
        if (!state.pdfAReady && state.pdfAFile) {
            appendLog('Uploading PDF A...');
            const fd = new FormData();
            fd.append('file', state.pdfAFile);
            const res = await api('POST', 'upload-pdf-a', fd, false);
            state.sessionId = res.session_id;
            state.pdfAName = res.pdf_name;
            state.pdfAReady = true;
        }

        // 2) Upload PDF B files
        appendLog('Uploading PDF B files...');
        const uploadFd = new FormData();
        uploadFd.append('session_id', state.sessionId);
        state.pdfBFiles.forEach(f => uploadFd.append('files', f));
        await api('POST', 'upload-pdf-b', uploadFd, false);
        updateProgress(10, 'PDFs uploaded, starting YOLO analysis...');

        // 3) Listen SSE for progress
        const sseUrl = `/api/stream-progress/${state.sessionId}`;
        const eventSource = new EventSource(sseUrl);
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                appendLog(data.detail, data.status);
                updateProgress(data.progress, data.detail);
                if (data.step === 'complete') {
                    eventSource.close();
                    // data.data is the full result from run_yolo_comparison
                    renderYoloResults(data.data?.results || []);
                    state.running = false;
                    btn.disabled = false;
                    btn.innerHTML = `<i data-lucide="play"></i> ${t('btnRunYolo')}`;
                    if (window.lucide) lucide.createIcons();
                }
            } catch (e) { /* ignore */ }
        };
        eventSource.onerror = () => eventSource.close();

        // 4) Trigger YOLO compare
        appendLog('Running 3-model YOLO detection on both PDFs...');
        await api('POST', 'run-yolo-compare', {
            session_id: state.sessionId,
            pdf_a_name: state.pdfAName,
        });

    } catch (err) {
        showAlert($('#card-step3'), 'error', err.message);
        state.running = false;
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="scan-search"></i> ${t('btnRunYolo')}`;
        if (window.lucide) lucide.createIcons();
    }
}

function updateProgress(pct, label) {
    const fill = $('#progress-fill');
    const pctLabel = $('#progress-pct');
    const textLabel = $('#progress-label');
    if (fill) fill.style.width = `${pct}%`;
    if (pctLabel) pctLabel.textContent = `${pct}%`;
    if (textLabel) textLabel.textContent = label;
}

function appendLog(msg, status) {
    const log = $('#progress-log');
    if (!log || !msg) return;
    const line = document.createElement('div');
    line.className = `log-line log-${status || 'running'}`;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}

// ============================================================
//  Render YOLO Comparison Results
// ============================================================
function renderYoloResults(resultsArray) {
    const card = $('#card-results');
    if (card) card.classList.remove('hidden');

    const container = $('#results-container');
    if (!resultsArray || resultsArray.length === 0) {
        container.innerHTML = `<div class="alert alert-warning">${t('noResults')}</div>`;
        return;
    }

    let html = '';
    for (const item of resultsArray) {
        if (item.error) {
            html += `<div class="result-card"><div class="alert alert-error">${item.file}: ${item.error}</div></div>`;
            continue;
        }
        const r = item.result;

        // Summary metrics
        html += `
        <div class="result-card">
            <div class="result-header">
                <div class="result-title"><i data-lucide="layers"></i>
                    ${r.brief_pdf} <span style="opacity:.5; margin:0 6px;">vs</span> ${r.final_pdf}
                </div>
                <span class="status-chip ${r.pairs_with_difference > 0 ? 'chip-warning' : 'chip-success'}">
                    ${r.pairs_with_difference > 0 ? r.pairs_with_difference + ' diff' : '✓ OK'}
                </span>
            </div>
            <div class="metrics-grid">
                <div class="metric-card"><div class="metric-value">${r.matched_pairs}</div><div class="metric-label">${t('metricMatched')}</div></div>
                <div class="metric-card ${r.pairs_with_difference > 0 ? 'metric-warning' : ''}"><div class="metric-value">${r.pairs_with_difference}</div><div class="metric-label">${t('metricDiff')}</div></div>
                <div class="metric-card" style="opacity:.55" title="Bình thường — Brief có thể có block mà Final không cần"><div class="metric-value">${r.brief_blocks_not_in_final ?? 0}</div><div class="metric-label">Brief chỉ có</div></div>
                <div class="metric-card" style="opacity:.55" title="Final có thêm block không có trong Brief"><div class="metric-value">${r.final_blocks_not_in_brief ?? 0}</div><div class="metric-label">Final thêm</div></div>
            </div>`;

        // Per-pair breakdown
        if (r.pairs && r.pairs.length > 0) {
            html += `<div style="margin-top:16px;">`;
            for (const pair of r.pairs) {
                const hasDiff = pair.has_difference;
                const borderColor = hasDiff ? '#f59e0b' : '#22c55e';
                const usedPIBrief = pair.brief_used_product_inf ? '' : ` <small style="opacity:.5">${t('labelNoPI')}</small>`;

                // Build crop image URLs
                function cropUrl(cropPath) {
                    if (!cropPath) return null;
                    const parts = cropPath.replace(/\\/g, '/').split('/');
                    const fname = parts.pop();
                    const folder = parts.pop();
                    return `/api/yolo-preview/${state.sessionId}/${folder}/${fname}`;
                }
                const briefCrop = cropUrl(pair.brief_crop_path);
                const finalCrop = cropUrl(pair.final_crop_path);

                html += `
                <div style="border-left: 3px solid ${borderColor}; padding: 10px 14px; margin-bottom:10px; background: rgba(255,255,255,0.03); border-radius: 6px;">
                    <div style="font-size:0.78rem; opacity:.55; margin-bottom:4px;">
                        Brief p${pair.brief_page} → Final p${pair.final_page}
                        &nbsp;<span style="opacity:.5;">match: ${(pair.match_score * 100).toFixed(0)}%</span>
                    </div>
                    <div style="font-size:0.7rem; opacity:.4; margin-bottom:8px; font-style:italic; white-space:pre-wrap;">
                        📝 Brief key: "${escHtml((pair.brief_match_text||'').replace(/\n/g,' ').slice(0,80))}"<br>
                        📝 Final key: "${escHtml((pair.final_match_text||'').replace(/\n/g,' ').slice(0,80))}"
                    </div>`;


                // Side-by-side crop images
                if (briefCrop || finalCrop) {
                    html += `<div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px;">`;
                    html += `<div style="text-align:center;">
                        <div style="font-size:0.7rem; opacity:.45; margin-bottom:3px;">Brief</div>
                        ${briefCrop ? `<img src="${briefCrop}" loading="lazy" style="width:100%; border-radius:5px; border:1px solid rgba(255,255,255,0.1);" alt="Brief block">` : '<div style="opacity:.3; font-size:.75rem;">no crop</div>'}
                    </div>`;
                    html += `<div style="text-align:center;">
                        <div style="font-size:0.7rem; opacity:.45; margin-bottom:3px;">Final</div>
                        ${finalCrop ? `<img src="${finalCrop}" loading="lazy" style="width:100%; border-radius:5px; border:1px solid rgba(255,255,255,0.1);" alt="Final block">` : '<div style="opacity:.3; font-size:.75rem;">no crop</div>'}
                    </div>`;
                    html += `</div>`;
                }

                // Entity diff text
                if (pair.delta) {
                    if (pair.delta.missing_in_final.length > 0)
                        html += `<div style="color:#f87171; font-size:0.8rem;">${t('labelMissing')}: ${pair.delta.missing_in_final.join(', ')}</div>`;
                    if (pair.delta.extra_in_final.length > 0)
                        html += `<div style="color:#fb923c; font-size:0.8rem;">${t('labelExtra')}: ${pair.delta.extra_in_final.join(', ')}</div>`;
                    if (pair.delta.matching.length > 0)
                        html += `<div style="color:#86efac; font-size:0.8rem;">${t('labelMatch')}: ${pair.delta.matching.join(', ')}</div>`;
                }
                html += `</div>`;
            }
            html += `</div>`;
        }

        // Unmatched final blocks (reference only)
        if (r.unmatched_final_blocks && r.unmatched_final_blocks.length > 0) {
            html += `<div style="margin-top:12px; font-size:0.8rem; opacity:.6">${t('unmatchedFinal')}:`;
            for (const ub of r.unmatched_final_blocks) {
                html += `<div style="margin-left:12px;">p${ub.page} — ${escHtml(ub.match_preview)} [${Object.keys(ub.entities).join(', ')}]</div>`;
            }
            html += `</div>`;
        }

        // ── YOLO Preview Images ───────────────────────────────────────────
        const hasPreviews = (r.brief_previews?.length > 0) || (r.final_previews?.length > 0);
        if (hasPreviews) {
            html += `
            <div style="margin-top:20px;">
                <div style="font-size:0.78rem; opacity:.5; letter-spacing:.05em; margin-bottom:10px; text-transform:uppercase;">
                    🖼 YOLO Detection Preview
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px;">
                    <div>
                        <div style="font-size:0.75rem; opacity:.55; margin-bottom:6px; text-align:center;">📄 Brief</div>
                        ${(r.brief_previews || []).map(p => {
                            const parts = p.replace(/\\/g,'/').split('/');
                            const fname = parts.pop();
                            const folder = parts.pop();
                            return `<img src="/api/yolo-preview/${state.sessionId}/${folder}/${fname}"
                                style="width:100%; border-radius:6px; margin-bottom:8px; border:1px solid rgba(255,255,255,0.1);"
                                loading="lazy" alt="Brief preview">`;
                        }).join('')}
                    </div>
                    <div>
                        <div style="font-size:0.75rem; opacity:.55; margin-bottom:6px; text-align:center;">📄 Final</div>
                        ${(r.final_previews || []).map(p => {
                            const parts = p.replace(/\\/g,'/').split('/');
                            const fname = parts.pop();
                            const folder = parts.pop();
                            return `<img src="/api/yolo-preview/${state.sessionId}/${folder}/${fname}"
                                style="width:100%; border-radius:6px; margin-bottom:8px; border:1px solid rgba(255,255,255,0.1);"
                                loading="lazy" alt="Final preview">`;
                        }).join('')}
                    </div>
                </div>
            </div>`;
        }

        html += `</div>`; // end result-card
    }

    container.innerHTML = html;
    if (window.lucide) lucide.createIcons();
}

function escHtml(str) {
    return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Keep old showResults for backward compat (not called anymore)
function showResults(results) { renderYoloResults(results); }

// ============================================================
//  Delete Dialog
// ============================================================
function showDeleteDialog() {
    const overlay = $('#dialog-overlay');
    overlay.classList.remove('hidden');
    overlay.innerHTML = `
        <div class="dialog-box">
            <div class="dialog-title"><i data-lucide="alert-triangle" class="icon-danger"></i> ${t('deleteConfirm')}</div>
            <div class="dialog-body">
                <strong>${state.pdfAName}</strong><br>
                ${t('deleteWarning')}
            </div>
            <div class="dialog-actions">
                <button class="btn btn-secondary btn-sm" id="dialog-cancel">${t('cancelBtn')}</button>
                <button class="btn btn-danger btn-sm" id="dialog-confirm">${t('confirmBtn')}</button>
            </div>
        </div>
    `;
    if (window.lucide) lucide.createIcons();

    $('#dialog-cancel').addEventListener('click', () => overlay.classList.add('hidden'));
    $('#dialog-confirm').addEventListener('click', async () => {
        try {
            await api('DELETE', `delete-pdf-a/${state.pdfAName}`);
            state.pdfAReady = false;
            state.pdfAName = null;
            overlay.classList.add('hidden');
            renderApp();
        } catch (err) {
            showAlert($('#pdf-a-status'), 'error', err.message);
            overlay.classList.add('hidden');
        }
    });
}

// ============================================================
//  Init
// ============================================================
async function init() {
    renderApp();

    // Health check
    try {
        const health = await api('GET', 'health');
        if (!health.model_found) {
            showAlert($('#card-step1'), 'error', t('modelNotFound'));
        }
    } catch (err) {
        showAlert($('#card-step1'), 'error', 'Cannot connect to server: ' + err.message);
    }
}

document.addEventListener('DOMContentLoaded', init);
