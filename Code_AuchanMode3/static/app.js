document.addEventListener('DOMContentLoaded', () => {
    const dropFini = document.getElementById('drop-fini');
    const dropAssembla = document.getElementById('drop-assembla');
    const fileFini = document.getElementById('file-fini');
    const fileAssembla = document.getElementById('file-assembla');
    
    const btnSubmit = document.getElementById('btn-submit');
    const btnClearAll = document.getElementById('btn-clear-all');
    const filesListGrid = document.getElementById('files-list-grid');
    const listFini = document.getElementById('list-fini');
    const listAssembla = document.getElementById('list-assembla');

    const uploadSection = document.getElementById('upload-section');
    const processingSection = document.getElementById('processing-section');
    const resultsSection = document.getElementById('results-section');

    let uploadedFiniFiles = [];
    let uploadedAssemblaFiles = [];

    let lastResultsData = null;
    let currentMatchFilter = 'mismatches';

    // --- NEW UI LOGIC ---
    // Tabs
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    // View Toggles (Results Left Panel)
    const viewToggleBtns = document.querySelectorAll('.results-view-header .view-toggle-btn');
    viewToggleBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            viewToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const targetId = btn.dataset.target;
            if (targetId === 'matches-container') {
                document.getElementById('matches-container').classList.remove('hidden');
                document.getElementById('pdf-results-preview').classList.add('hidden');
            } else {
                document.getElementById('matches-container').classList.add('hidden');
                document.getElementById('pdf-results-preview').classList.remove('hidden');
            }
        });
    });

    // Match Filter Toggles (Results Right Panel)
    const filterToggleBtns = document.querySelectorAll('#match-filter-toggles .view-toggle-btn');
    filterToggleBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            filterToggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentMatchFilter = btn.dataset.filter;
            applyMatchFilter();
        });
    });

    function applyMatchFilter() {
        const cards = document.querySelectorAll('#matches-container .modern-match-card');
        let visibleCount = 0;
        cards.forEach(card => {
            const hasDiff = card.classList.contains('has-diff');
            const noDiff = card.classList.contains('no-diff');
            
            let show = false;
            if (currentMatchFilter === 'all') {
                show = true;
            } else if (currentMatchFilter === 'mismatches') {
                show = hasDiff;
            } else if (currentMatchFilter === 'correct') {
                show = noDiff;
            }
            
            if (show) {
                card.classList.remove('hidden');
                visibleCount++;
            } else {
                card.classList.add('hidden');
            }
        });
        
        let emptyMsg = document.getElementById('matches-empty-message');
        if (visibleCount === 0) {
            if (!emptyMsg) {
                emptyMsg = document.createElement('div');
                emptyMsg.id = 'matches-empty-message';
                emptyMsg.style.padding = '3rem';
                emptyMsg.style.textAlign = 'center';
                emptyMsg.style.color = 'var(--text-muted)';
                emptyMsg.style.fontSize = '1.1rem';
                emptyMsg.style.fontWeight = '500';
                emptyMsg.style.background = 'var(--bg-panel)';
                emptyMsg.style.border = '1px dashed var(--border-light)';
                emptyMsg.style.borderRadius = 'var(--radius)';
                document.getElementById('matches-container').appendChild(emptyMsg);
            }
            emptyMsg.classList.remove('hidden');
            if (currentMatchFilter === 'mismatches') {
                emptyMsg.innerHTML = '🎉 Không phát hiện cặp nào bị lệch! Tất cả đều trùng khớp.';
            } else if (currentMatchFilter === 'correct') {
                emptyMsg.innerHTML = '❌ Không có cặp nào trùng khớp hoàn toàn.';
            } else {
                emptyMsg.innerHTML = '📭 Không có dữ liệu so sánh.';
            }
        } else {
            if (emptyMsg) {
                emptyMsg.classList.add('hidden');
            }
        }
    }
    
    function switchTab(tabId) {
        tabBtns.forEach(btn => {
            if(btn.dataset.tab === tabId) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        tabContents.forEach(content => {
            if(content.id === 'tab-' + tabId) content.classList.add('active');
            else content.classList.remove('active');
        });
    }

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Zoom Cards
    const tierCards = document.querySelectorAll('.tier-card');
    const zoomSelect = document.getElementById('zoom-select');
    
    tierCards.forEach(card => {
        card.addEventListener('click', () => {
            tierCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            zoomSelect.value = card.dataset.zoom;
        });
    });
    // Fetch History
    async function loadHistoryList() {
        const container = document.getElementById('history-list-container');
        if (!container) return;
        try {
            const res = await fetch('/api/history');
            const data = await res.json();
            if (!data || data.length === 0) {
                container.innerHTML = '<div class="empty-state">No history available.</div>';
                return;
            }
            container.innerHTML = '';
            data.forEach(item => {
                const div = document.createElement('div');
                div.className = 'history-item';
                div.innerHTML = `
                    <div class="history-time">${item.timestamp}</div>
                    <div class="history-files">
                        <span>Fini: ${item.fini_files.join(', ')}</span>
                        <span>Asm: ${item.assembla_files.join(', ')}</span>
                    </div>
                `;
                div.addEventListener('click', () => {
                    // Re-render using saved payload
                    if(item.results) {
                        renderResults(item.results);
                    }
                });
                container.appendChild(div);
            });
        } catch (e) {
            console.error('Failed to load history', e);
            container.innerHTML = '<div class="empty-state" style="color:red;">Error loading history.</div>';
        }
    }

    const btnRefreshHistory = document.getElementById('btn-refresh-history');
    if (btnRefreshHistory) {
        btnRefreshHistory.addEventListener('click', loadHistoryList);
    }
    
    let serverFilesData = { fini: [], assembla: [] };

    // Fetch and render Server Files
    async function loadServerFiles() {
        try {
            const res = await fetch('/api/uploaded-files');
            if (res.ok) {
                serverFilesData = await res.json();
            }
        } catch (e) {
            console.error('Failed to load server files', e);
        }
        updateFileListsUI();
    }

    const btnRefreshServerFiles = document.getElementById('btn-refresh-server-files');
    if (btnRefreshServerFiles) {
        btnRefreshServerFiles.addEventListener('click', loadServerFiles);
    }

    function setupDropZone(dropZone, input, type) {
        if (!dropZone) return;
        dropZone.addEventListener('click', () => input.click());

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length) {
                handleUploadedFiles(files, type);
            }
        });
    }

    // Setup drop zones
    setupDropZone(dropFini, fileFini, 'fini');
    setupDropZone(dropAssembla, fileAssembla, 'assembla');

    fileFini.addEventListener('change', () => {
        if (fileFini.files.length) {
            handleUploadedFiles(fileFini.files, 'fini');
            fileFini.value = '';
        }
    });

    fileAssembla.addEventListener('change', () => {
        if (fileAssembla.files.length) {
            handleUploadedFiles(fileAssembla.files, 'assembla');
            fileAssembla.value = '';
        }
    });

    function handleUploadedFiles(files, type) {
        const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfs.length === 0) return;

        if (type === 'fini') {
            pdfs.forEach(pdf => {
                if (!uploadedFiniFiles.some(f => f.name === pdf.name && f.size === pdf.size)) {
                    uploadedFiniFiles.push(pdf);
                }
            });
        } else {
            pdfs.forEach(pdf => {
                if (!uploadedAssemblaFiles.some(f => f.name === pdf.name && f.size === pdf.size)) {
                    uploadedAssemblaFiles.push(pdf);
                }
            });
        }

        updateFileListsUI();
    }

    function renderServerListOnly(side, serverFiles, uploadedFiles, listElement) {
        listElement.innerHTML = '';

        if (!serverFiles || serverFiles.length === 0) {
            return;
        }

        serverFiles.forEach(item => {
            const isSelected = uploadedFiles.some(f => f.name === item.clean_name);
            const li = document.createElement('li');
            li.className = `server-file-li ${isSelected ? 'selected' : ''}`;
            li.dataset.filename = item.filename;
            li.dataset.clean = item.clean_name;
            li.title = `${item.clean_name}\n(Tải lên: ${item.time})`;
            
            li.innerHTML = `
                <span class="file-icon">${side === 'fini' ? '📄' : '📋'}</span>
                <span class="server-file-name">${item.clean_name}</span>
                ${isSelected ? '<span class="selected-badge" style="color: var(--primary); font-weight: bold; margin-left: 8px;">✓</span>' : ''}
            `;

            li.addEventListener('click', async (e) => {
                e.stopPropagation(); // Avoid triggering click on drop zone
                const idx = uploadedFiles.findIndex(f => f.name === item.clean_name);
                if (idx !== -1) {
                    uploadedFiles.splice(idx, 1);
                    updateFileListsUI();
                } else {
                    if (li.classList.contains('loading')) return;
                    li.classList.add('loading');
                    const nameSpan = li.querySelector('.server-file-name');
                    const originalText = nameSpan.textContent;
                    nameSpan.textContent = 'Đang tải file...';

                    try {
                        const fileUrl = `/static/uploads/${side}/${item.filename}`;
                        const response = await fetch(fileUrl);
                        if (!response.ok) throw new Error('Không tải được file từ server');
                        const blob = await response.blob();
                        const file = new File([blob], item.clean_name, { type: 'application/pdf' });
                        
                        uploadedFiles.push(file);
                        updateFileListsUI();
                    } catch (err) {
                        console.error(err);
                        alert('Không thể sử dụng file từ server: ' + err.message);
                        li.classList.remove('loading');
                        nameSpan.textContent = originalText;
                    }
                }
            });

            listElement.appendChild(li);
        });
    }

    function updateFileListsUI() {
        const listFini = document.getElementById('list-fini');
        const listAssembla = document.getElementById('list-assembla');
        const listFiniServer = document.getElementById('server-list-fini');
        const listAssemblaServer = document.getElementById('server-list-assembla');
        
        // 1. Render files selected in the dropzones
        if (listFini) {
            listFini.innerHTML = '';
            uploadedFiniFiles.forEach((file, index) => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <span class="file-li-name" title="${file.name}">📄 ${file.name}</span>
                    <span class="file-li-size">(${(file.size / 1024).toFixed(1)} KB)</span>
                    <button type="button" class="btn-remove-file" data-index="${index}" data-type="fini">✕</button>
                `;
                listFini.appendChild(li);
            });
        }
        if (listAssembla) {
            listAssembla.innerHTML = '';
            uploadedAssemblaFiles.forEach((file, index) => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <span class="file-li-name" title="${file.name}">📋 ${file.name}</span>
                    <span class="file-li-size">(${(file.size / 1024).toFixed(1)} KB)</span>
                    <button type="button" class="btn-remove-file" data-index="${index}" data-type="assembla">✕</button>
                `;
                listAssembla.appendChild(li);
            });
        }

        // Bind remove file events
        document.querySelectorAll('.btn-remove-file').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation(); // Avoid triggering click on drop zone
                const idx = parseInt(btn.getAttribute('data-index'));
                const type = btn.getAttribute('data-type');
                if (type === 'fini') {
                    uploadedFiniFiles.splice(idx, 1);
                } else {
                    uploadedAssemblaFiles.splice(idx, 1);
                }
                updateFileListsUI();
            });
        });

        // 2. Render server files checkmarks
        if (listFiniServer) {
            renderServerListOnly('fini', serverFilesData.fini, uploadedFiniFiles, listFiniServer);
        }
        if (listAssemblaServer) {
            renderServerListOnly('assembla', serverFilesData.assembla, uploadedAssemblaFiles, listAssemblaServer);
        }

        // Update dropzone styling classes
        if (dropFini) {
            if (uploadedFiniFiles.length > 0) dropFini.classList.add('has-files');
            else dropFini.classList.remove('has-files');
        }
        if (dropAssembla) {
            if (uploadedAssemblaFiles.length > 0) dropAssembla.classList.add('has-files');
            else dropAssembla.classList.remove('has-files');
        }

        // Show/Hide Clear All button
        const totalFilesCount = uploadedFiniFiles.length + uploadedAssemblaFiles.length;
        if (btnClearAll) {
            if (totalFilesCount > 0) btnClearAll.classList.remove('hidden');
            else btnClearAll.classList.add('hidden');
        }
    }

    // Initial load
    loadHistoryList();
    loadServerFiles();

    // Submit and compare PDFs
    btnSubmit.addEventListener('click', async () => {
        if (uploadedFiniFiles.length === 0 || uploadedAssemblaFiles.length === 0) {
            alert('Vui lòng chọn ít nhất 1 file Fini và 1 file Assembla để so sánh.');
            return;
        }

        // Show loading state
        btnSubmit.disabled = true;
        const btnLoader = document.getElementById('btn-loader') || document.createElement('span');
        btnLoader.classList.remove('hidden');
        
        processingSection.classList.remove('hidden');
        resultsSection.classList.add('hidden');

        // Hide stats while loading
        document.getElementById('widget-stats')?.classList.add('hidden');
        document.getElementById('widget-divider-1')?.classList.add('hidden');
        document.getElementById('pdv-divider')?.classList.add('hidden');
        document.getElementById('global-alert-badge')?.classList.add('hidden');

        const formData = new FormData();
        uploadedFiniFiles.forEach(file => {
            formData.append('fini_pdfs', file);
        });
        uploadedAssemblaFiles.forEach(file => {
            formData.append('assembla_pdfs', file);
        });

        const zoomSelect = document.getElementById('zoom-select');
        const zoomValue = zoomSelect ? zoomSelect.value : '2.0';

        const apiKeyInput = document.getElementById('openrouter-api-key');
        if (apiKeyInput && apiKeyInput.value) {
            formData.append('openrouter_api_key', apiKeyInput.value);
        }

        try {
            const response = await fetch(`/api/compare?zoom=${zoomValue}`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'So sánh thất bại');
            }

            const data = await response.json();
            renderResults(data);
            loadServerFiles();
            loadHistoryList();
        } catch (err) {
            console.error(err);
            alert('Lỗi: ' + err.message);
            // Reset UI on error
            uploadSection.classList.remove('hidden');
            processingSection.classList.add('hidden');
        } finally {
            btnSubmit.disabled = false;
            btnLoader.classList.add('hidden');
        }
    });

    // Clear all files & reset view
    function resetAndShowUpload() {
        uploadedFiniFiles = [];
        uploadedAssemblaFiles = [];
        lastResultsData = null;
        currentMatchFilter = 'mismatches';
        const filterToggleBtns = document.querySelectorAll('#match-filter-toggles .view-toggle-btn');
        filterToggleBtns.forEach(btn => {
            if (btn.dataset.filter === 'mismatches') btn.classList.add('active');
            else btn.classList.remove('active');
        });
        
        fileFini.value = '';
        fileAssembla.value = '';
        
        updateFileListsUI();

        uploadSection.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        document.getElementById('global-alert-badge')?.classList.add('hidden');
        document.getElementById('widget-stats')?.classList.add('hidden');
        document.getElementById('widget-divider-1')?.classList.add('hidden');
        document.getElementById('pdv-divider')?.classList.add('hidden');
        document.getElementById('unmatched-section')?.classList.add('hidden');
        
        const btnClear = document.getElementById('btn-clear-all');
        const btnNew = document.getElementById('btn-new-compare');
        if (btnClear) btnClear.style.display = 'inline-block';
        if (btnNew) btnNew.style.display = 'none';

        // Switch back to Config Tab
        switchTab('config');

        // Refresh the server uploaded files lists
        loadServerFiles();
    }

    btnClearAll.addEventListener('click', resetAndShowUpload);
    document.getElementById('btn-new-compare').addEventListener('click', resetAndShowUpload);

    function renderResults(data) {
        lastResultsData = data;
        processingSection.classList.add('hidden');
        uploadSection.classList.add('hidden'); // Hide upload section on success
        resultsSection.classList.remove('hidden');

        const btnClear = document.getElementById('btn-clear-all');
        const btnNew = document.getElementById('btn-new-compare');
        if (btnClear) btnClear.style.display = 'none';
        if (btnNew) btnNew.style.display = 'inline-block';

        // Switch to Results Tab
        switchTab('results');

        // Initialize Interactive Catalog Viewer with both raw PDFs
        if (data.raw_fini_url || data.raw_assembla_url) {
            initInteractiveCatalog(data.raw_fini_url, data.raw_assembla_url, data);
        }

        // Render Matches
        const container = document.getElementById('matches-container');
        container.innerHTML = '';
        
        // Global PDV Alert Banner
        const alertBadge = document.getElementById('global-alert-badge');
        if (alertBadge) {
            alertBadge.classList.remove('hidden');
            if (data.global_pdv_check.has_error) {
                alertBadge.className = 'pdv-badge-widget alert-error-badge';
                alertBadge.textContent = '❌ Lỗi chưa tắt PDV';
                
                // Add big banner in Match Cards container
                let pagesStr = data.global_pdv_check.sample_pages.join(', ');
                if (data.global_pdv_check.total_pages_with_error > 3) {
                    pagesStr += '...';
                }
                const pdvBanner = document.createElement('div');
                pdvBanner.className = 'global-pdv-banner';
                pdvBanner.innerHTML = `⚠️ <b>CẢNH BÁO LỖI TOÀN TRANG:</b> Phát hiện file Fini quên tắt layer PDV nền xanh (tại trang: <b>${pagesStr}</b>). Vui lòng kiểm tra lại!`;
                pdvBanner.style.backgroundColor = '#fef2f2';
                pdvBanner.style.border = '1px solid #fca5a5';
                pdvBanner.style.color = '#b91c1c';
                pdvBanner.style.padding = '15px';
                pdvBanner.style.borderRadius = '8px';
                pdvBanner.style.marginBottom = '20px';
                pdvBanner.style.fontWeight = '500';
                pdvBanner.style.fontSize = '1.1em';
                container.appendChild(pdvBanner);
            } else {
                alertBadge.className = 'pdv-badge-widget alert-success-badge';
                alertBadge.textContent = '✅ PDV OK';
            }
        }

        // Show widget stats
        const widgetStats = document.getElementById('widget-stats');
        const widgetDivider1 = document.getElementById('widget-divider-1');
        if (widgetStats) widgetStats.classList.remove('hidden');
        if (widgetDivider1) widgetDivider1.classList.remove('hidden');

        // Stats
        document.getElementById('stat-matched').textContent = data.stats.total_matched;

        const template = document.getElementById('match-card-template').content;

        let displayedCount = 0;
        let perfectMatchesCount = 0;
        data.matched.forEach((match, index) => {
            const clone = document.importNode(template, true);
            const card = clone.querySelector('.modern-match-card') || clone.querySelector('.match-card');
            
            // Pre-calculate text diff so we can use mismatch_boxes for image highlights
            if (!match._textDiff) {
                match._textDiff = getRichWordDiff(match.fini ? (match.fini.rich_text || []) : [], match.assembla ? (match.assembla.rich_text || []) : []);
            }
            
            // Render details first so we can check for differences
            renderBlockDetails(clone, 'fini', match.fini, match);
            renderBlockDetails(clone, 'assembla', match.assembla, match);

            // Comparative Table Rendering
            const fields = [
                {
                    key: 'text',
                    label: 'Nội dung chữ (Text & Style)',
                    getVal: (b) => b.text || 'N/A',
                    isEqual: (va, vb, match) => {
                        const cleanGarbage = (s) => {
                            let cleaned = (s || '').toLowerCase();
                            cleaned = cleaned.replace(/\b(o|i|ff|l|bl|h)\b/g, '');
                            return cleaned.replace(/\s+/g, ' ').trim();
                        };
                        if (cleanGarbage(va) !== cleanGarbage(vb)) return false;

                        if (!match._textDiff) {
                            match._textDiff = getRichWordDiff(match.fini.rich_text || [], match.assembla.rich_text || []);
                        }
                        const hasMismatch = match._textDiff.fini.includes('diff-mismatch-word') || 
                                            match._textDiff.fini.includes('background-color: rgba') ||
                                            match._textDiff.assembla.includes('diff-standard-word');
                        return !hasMismatch;
                    }
                },
                {
                    key: 'price',
                    label: 'Giá tiền (Price)',
                    getVal: (b) => b.price || 'N/A',
                    isEqual: (va, vb) => {
                        const clean = (s) => (s || '').replace(/\s+/g, '').trim().toLowerCase();
                        return clean(va) === clean(vb);
                    }
                },
                {
                    key: 'font_size',
                    label: 'Cỡ chữ (Font Size)',
                    getVal: (b) => b.font_size ? `${b.font_size}pt` : 'N/A'
                },

                {
                    key: 'classes',
                    label: 'Lớp (Classes)',
                    getVal: (b) => {
                        const classes = b.sub_classes || [];
                        return [...classes].sort().join(', ') || 'Không có';
                    },
                    isEqual: (va, vb) => {
                        const clean = (s) => (s || '').replace(/\s+/g, '').trim().toLowerCase();
                        return clean(va) === clean(vb);
                    }
                }
            ];

            const diffTbody = card.querySelector('.comparison-tbody');
            const identicalTbody = card.querySelector('.identical-tbody');
            const identicalCountSpan = card.querySelector('.identical-count');

            let identicalCount = 0;

            fields.forEach(field => {
                const valFini = field.getVal(match.fini);
                const valAssembla = field.getVal(match.assembla);

                const equal = field.isEqual ? field.isEqual(valFini, valAssembla, match) : (valFini === valAssembla);

                const tr = document.createElement('tr');
                
                let displayFini = valFini;
                let displayAssembla = valAssembla;

                if (!equal) {
                    if (field.key === 'classes') {
                        const diff = getClassesDiff(match.fini, match.assembla);
                        displayFini = diff.fini;
                        displayAssembla = diff.assembla;
                    } else if (field.key === 'text') {
                        let diff = match._textDiff || getRichWordDiff(match.fini.rich_text || [], match.assembla.rich_text || []);
                        const hasMismatch = diff.fini.includes('diff-mismatch-word') || 
                                            diff.fini.includes('background-color: rgba') ||
                                            diff.assembla.includes('diff-standard-word');
                        
                        const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                        if (!hasMismatch && clean(valFini) !== clean(valAssembla)) {
                            // rich_text failed to capture the difference (possibly empty or cached wrong), fallback to plain text word diff
                            diff = getPlainWordDiff(valFini, valAssembla);
                            displayFini = diff.fini;
                            displayAssembla = diff.assembla;
                        } else {
                            displayFini = diff.compact_fini;
                            displayAssembla = diff.compact_assembla;
                        }
                    } else if (field.key === 'price') {
                        const diff = getPlainWordDiff(match.fini.price, match.assembla.price);
                        displayFini = diff.fini;
                        displayAssembla = diff.assembla;
                    }
                }

                tr.innerHTML = `
                    <td class="prop-name">${field.label}</td>
                    <td class="fini-val">${displayFini}</td>
                    <td class="assembla-val">${displayAssembla}</td>
                `;

                if (!equal) {
                    tr.querySelector('.fini-val').classList.add('mismatch');
                    tr.querySelector('.assembla-val').classList.add('standard');
                    diffTbody.appendChild(tr);
                } else {
                    identicalTbody.appendChild(tr);
                    identicalCount++;
                }
            });

            identicalCountSpan.textContent = identicalCount;

            const hasAnyMismatch = match.has_diff || (diffTbody.children.length > 0);

            // Hide property table if perfectly matched (identical)
            if (!hasAnyMismatch) {
                const propTable = card.querySelector('.property-comparison');
                if (propTable) propTable.style.display = 'none';
                perfectMatchesCount++;
            }

            displayedCount++;
            if (card) card.style.animationDelay = `${displayedCount * 0.1}s`;
            
            if (match.method === "footer") {
                const titleEl = clone.querySelector('.match-title');
                const pageNum = match.fini ? (match.fini.page_idx + 1) : (match.assembla ? (match.assembla.page_idx + 1) : "?");
                titleEl.innerHTML = `Chân trang (Footer) - Trang ${pageNum}`;
            } else {
                clone.querySelector('.match-index').textContent = index + 1;
            }
            clone.querySelector('.badge-method').style.display = 'none';

            const statusBadge = clone.querySelector('.badge-status');
            if (!hasAnyMismatch) {
                card.classList.add('no-diff');
                statusBadge.classList.add('badge-success');
                statusBadge.textContent = 'V';
            } else {
                card.classList.add('has-diff');
                statusBadge.classList.add('badge-error');
                statusBadge.textContent = 'X';
            }

            if (diffTbody.children.length === 0) {
                const wrapper = card.querySelector('.comparison-table-wrapper');
                if (wrapper) {
                    wrapper.innerHTML = '<div style="padding: 1rem; text-align: center; color: #2ecc71; font-weight: 500;">✅ Tất cả thuộc tính trùng khớp!</div>';
                }
            }

            const btnToggle = card.querySelector('.btn-toggle-identical');
            const identicalContent = card.querySelector('.identical-content');
            if (btnToggle && identicalContent) {
                btnToggle.addEventListener('click', () => {
                    const isHidden = identicalContent.classList.contains('hidden');
                    if (isHidden) {
                        identicalContent.classList.remove('hidden');
                        btnToggle.querySelector('span').textContent = '👁️ Ẩn các thông tin trùng khớp';
                        btnToggle.classList.add('active');
                    } else {
                        identicalContent.classList.add('hidden');
                        btnToggle.querySelector('span').textContent = '👁️ Xem thêm các thông tin trùng khớp';
                        btnToggle.classList.remove('active');
                    }
                });
            }

            container.appendChild(clone);
        });

        // Apply selected filter to rendered matches
        applyMatchFilter();





        // Annotated PDFs are rendered directly in results preview iframes

        // Render Unmatched Blocks
        const unmatchedSection = document.getElementById('unmatched-section');
        const unmatchedFiniList = document.getElementById('unmatched-fini-list');
        const unmatchedFiniCount = document.getElementById('unmatched-fini-count');

        unmatchedFiniList.innerHTML = '';

        const unmatchedTemplate = document.getElementById('unmatched-card-template').content;

        const hasUnmatchedFini = data.unmatched_fini && data.unmatched_fini.length > 0;

        if (hasUnmatchedFini) {
            unmatchedSection.classList.remove('hidden');
            
            // Fini unmatched
            unmatchedFiniCount.textContent = data.unmatched_fini ? data.unmatched_fini.length : 0;
            if (data.unmatched_fini) {
                data.unmatched_fini.forEach(block => {
                    const clone = document.importNode(unmatchedTemplate, true);
                    renderUnmatchedBlockDetails(clone, block);
                    unmatchedFiniList.appendChild(clone);
                });
            }
        } else {
            unmatchedSection.classList.add('hidden');
        }
    }


    function escapeHTML(str) {
        return (str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function getPlainWordDiff(strFini, strAssembla) {
        const tokenize = (str) => {
            const tokens = (str || '').match(/\n|[ \t]+|[^\s]+/g) || [];
            return tokens.map(w => ({ text: w, size: 0, bold: false }));
        };
        return getRichWordDiff(tokenize(strFini), tokenize(strAssembla));
    }

    function getRichWordDiff(richFini, richAssembla) {
        if (!richFini || !richAssembla) return { fini: '', assembla: '' };

        const isBoilerplate = (wordObj) => {
            if (!wordObj || !wordObj.text) return false;
            let lower = wordObj.text.toLowerCase().trim();
            // Match standalone garbage words, or combinations like "o i"
            if (/^(o|i|ff|l|bl|h|o i|i o|\s)+$/.test(lower)) return true;
            return false;
        };

        const wordsFini = richFini.filter(w => w.text === '\n' || (!isBoilerplate(w) && w.text.trim().length > 0));
        const wordsAssembla = richAssembla.filter(w => w.text === '\n' || (!isBoilerplate(w) && w.text.trim().length > 0));

        const prepareText = (wordsArr) => {
            const textArr = [];
            const mapArr = [];
            wordsArr.forEach((w, idx) => {
                if (w.text === '\n') return;
                const parts = w.text.split('-');
                for (let i = 0; i < parts.length; i++) {
                    let p = parts[i];
                    if (i < parts.length - 1) p += '-';
                    if (p.trim()) {
                        textArr.push({ text: p, size: w.size, bold: w.bold });
                        mapArr.push([idx]);
                    }
                }
            });

            for (let i = 0; i < textArr.length - 1; i++) {
                const w1 = textArr[i].text;
                const w2 = textArr[i+1].text;
                if (/^[\d€.,]+$/.test(w1) && /^[\d€.,]+$/.test(w2)) {
                    textArr[i].text = w1 + w2;
                    mapArr[i].push(...mapArr[i+1]);
                    textArr.splice(i + 1, 1);
                    mapArr.splice(i + 1, 1);
                    i--; // recheck
                }
            }
            return { textArr, mapArr };
        };

        const alignSubWords = (indicesA, indicesB, wordsA, wordsB, matchIndicesA, matchIndicesB) => {
            if (!indicesA || !indicesB || indicesA.length === 0 || indicesB.length === 0) return;
            if (indicesA.length === 1 && indicesB.length === 1) {
                matchIndicesA[indicesA[0]] = indicesB[0];
                matchIndicesB[indicesB[0]] = indicesA[0];
                return;
            }
            if (indicesA.length === indicesB.length) {
                for (let k = 0; k < indicesA.length; k++) {
                    matchIndicesA[indicesA[k]] = indicesB[k];
                    matchIndicesB[indicesB[k]] = indicesA[k];
                }
                return;
            }
            let offsetA = 0;
            const rangesA = indicesA.map(idx => {
                const len = (wordsA[idx] && wordsA[idx].text ? wordsA[idx].text.length : 0);
                const start = offsetA;
                offsetA += len;
                return { idx, start, end: offsetA };
            });

            let offsetB = 0;
            const rangesB = indicesB.map(idx => {
                const len = (wordsB[idx] && wordsB[idx].text ? wordsB[idx].text.length : 0);
                const start = offsetB;
                offsetB += len;
                return { idx, start, end: offsetB };
            });

            rangesA.forEach(rA => {
                let bestB = indicesB[0];
                let maxOverlap = -1;
                rangesB.forEach(rB => {
                    const overlap = Math.max(0, Math.min(rA.end, rB.end) - Math.max(rA.start, rB.start));
                    if (overlap > maxOverlap) {
                        maxOverlap = overlap;
                        bestB = rB.idx;
                    }
                });
                matchIndicesA[rA.idx] = bestB;
            });

            rangesB.forEach(rB => {
                let bestA = indicesA[0];
                let maxOverlap = -1;
                rangesA.forEach(rA => {
                    const overlap = Math.max(0, Math.min(rA.end, rB.end) - Math.max(rA.start, rB.start));
                    if (overlap > maxOverlap) {
                        maxOverlap = overlap;
                        bestA = rA.idx;
                    }
                });
                matchIndicesB[rB.idx] = bestA;
            });
        };

        const { textArr: textFini, mapArr: mapFini } = prepareText(wordsFini);
        const { textArr: textAssembla, mapArr: mapAssembla } = prepareText(wordsAssembla);

        const m = textFini.length;
        const n = textAssembla.length;
        
        const normalize = (str) => (str || '').normalize('NFC').toLowerCase();

        const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
        for (let i = 1; i <= m; i++) {
            for (let j = 1; j <= n; j++) {
                if (normalize(textFini[i-1].text) === normalize(textAssembla[j-1].text)) {
                    dp[i][j] = dp[i-1][j-1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i-1][j], dp[i][j-1]);
                }
            }
        }

        const matchIndicesFini = Array(wordsFini.length).fill(-1);
        const matchIndicesAssembla = Array(wordsAssembla.length).fill(-1);

        let i = m, j = n;
        while (i > 0 && j > 0) {
            if (normalize(textFini[i-1].text) === normalize(textAssembla[j-1].text)) {
                const origIndicesI = mapFini[i-1];
                const origIndicesJ = mapAssembla[j-1];
                alignSubWords(origIndicesI, origIndicesJ, wordsFini, wordsAssembla, matchIndicesFini, matchIndicesAssembla);
                i--; j--;
            } else if (dp[i-1][j] >= dp[i][j-1]) {
                i--;
            } else {
                j--;
            }
        }

        const renderRichMismatches = (words, matchIndices, otherWords, isFini) => {
            let html = [];
            let compactHtml = [];
            let htmlBoxes = [];
            for (let k = 0; k < words.length; k++) {
                const w = words[k];
                if (w.text === '\n') {
                    html.push('<br>');
                    continue;
                }
                
                let wordHTML = escapeHTML(w.text);
                const mappedIdx = matchIndices[k];
                
                if (mappedIdx === -1) {
                    // Mismatch in text itself (extra/missing word)
                    const tagClass = isFini ? 'diff-mismatch-word' : 'diff-standard-word';
                    let diffText = w.size > 0 ? `<span style="font-size: 0.75em; opacity: 0.9; margin-left: 2px;"> (${w.size}pt)</span>` : '';
                    let el = `<span class="${tagClass}">${wordHTML}${diffText}</span>`;
                    html.push(el);
                    compactHtml.push(el);
                    if (w.xyxy) htmlBoxes.push(w.xyxy);
                } else {
                    // Text matched, check style with the corresponding word
                    const otherW = otherWords[mappedIdx];
                    const sizeDiff = w.size !== otherW.size;
                    const boldDiff = !!w.bold !== !!otherW.bold;
                    
                    let styleStr = w.size > 0 ? `font-size: ${w.size}pt;` : '';
                    if (w.bold) styleStr += ` font-weight: bold;`;
                    
                    if (sizeDiff || boldDiff) {
                        let diffText = "";
                        if (sizeDiff) diffText += ` (${w.size}pt)`;
                        if (boldDiff) diffText += ` (${w.bold ? 'Đậm' : 'Thường'})`;
                        
                        let el = `<span style="${styleStr} background-color: rgba(234, 179, 8, 0.3); border-radius: 3px; padding: 0 2px;">${wordHTML}<span style="font-size: 0.8em; color: #b45309; font-weight: bold; margin-left: 4px;">${diffText}</span></span>`;
                        html.push(el);
                        compactHtml.push(el);
                        if (w.xyxy) htmlBoxes.push(w.xyxy);
                    } else {
                        if (styleStr) {
                            html.push(`<span style="${styleStr}">${wordHTML}</span>`);
                        } else {
                            html.push(`<span>${wordHTML}</span>`);
                        }
                    }
                }
            }
            return {
                html: html.join(' ').replace(/ <br> /g, '<br>').replace(/<br> /g, '<br>'),
                compactHtml: compactHtml.join(' <span style="color:#94a3b8; font-size:0.8em;">...</span> '),
                boxes: htmlBoxes
            };
        };
        const finiResult = renderRichMismatches(wordsFini, matchIndicesFini, wordsAssembla, true);
        const assemblaResult = renderRichMismatches(wordsAssembla, matchIndicesAssembla, wordsFini, false);

        return {
            fini: finiResult.html || '<span class="diff-empty">(Trống)</span>',
            assembla: assemblaResult.html || '<span class="diff-empty">(Trống)</span>',
            compact_fini: finiResult.compactHtml || '<span style="color: #64748b; font-style: italic;">(Lỗi nằm ở phần ảnh/cấu trúc)</span>',
            compact_assembla: assemblaResult.compactHtml || '<span style="color: #64748b; font-style: italic;">(Lỗi nằm ở phần ảnh/cấu trúc)</span>',
            mismatch_boxes: finiResult.boxes,
            assembla_mismatch_boxes: assemblaResult.boxes
        };
    }
    function getClassesDiff(finiBlock, assemblaBlock) {
        const classesFini = finiBlock.sub_classes || [];
        const classesAssembla = assemblaBlock.sub_classes || [];
        const subsFini = finiBlock.sub_elements || [];
        const subsAssembla = assemblaBlock.sub_elements || [];
        
        const countFini = {};
        classesFini.forEach(c => countFini[c] = (countFini[c] || 0) + 1);
        
        const countAssembla = {};
        classesAssembla.forEach(c => countAssembla[c] = (countAssembla[c] || 0) + 1);
        
        const allKeys = Array.from(new Set([...Object.keys(countFini), ...Object.keys(countAssembla)])).sort();
        
        let finiParts = [];
        let assemblaParts = [];
        
        allKeys.forEach(cls => {
            const numFini = countFini[cls] || 0;
            const numAssembla = countAssembla[cls] || 0;
            
            const elsFini = subsFini.filter(s => s.name === cls);
            const elsAssembla = subsAssembla.filter(s => s.name === cls);
            
            if (numFini === numAssembla) {
                for (let i = 0; i < numFini; i++) {
                    finiParts.push(`<span>${escapeHTML(cls)}</span>`);
                    assemblaParts.push(`<span>${escapeHTML(cls)}</span>`);
                }
            } else {
                for (let i = 0; i < numFini; i++) {
                    const el = elsFini[i];
                    const cropHtml = el && el.crop_base64 ? `<br><img src="data:image/png;base64,${el.crop_base64}" style="max-height: 40px; border: 1px solid #ccc; margin-top: 4px; border-radius: 4px;">` : '';
                    if (numFini > numAssembla && i >= numAssembla) {
                        finiParts.push(`<div class="diff-mismatch-word" title="Lớp thừa không có trong Assembla" style="display: inline-block; text-align: center; margin: 2px;">Thừa: ${escapeHTML(cls)}${cropHtml}</div>`);
                    } else {
                        finiParts.push(`<div style="display: inline-block; text-align: center; margin: 2px;"><span>${escapeHTML(cls)}</span>${cropHtml}</div>`);
                    }
                }
                
                if (numFini < numAssembla) {
                    for (let i = numFini; i < numAssembla; i++) {
                        const el = elsAssembla[i];
                        const cropHtml = el && el.crop_base64 ? `<br><img src="data:image/png;base64,${el.crop_base64}" style="max-height: 40px; opacity: 0.5; margin-top: 4px; border: 1px dashed #ef4444; border-radius: 4px;">` : '';
                        finiParts.push(`<div class="diff-mismatch-word" style="background: rgba(239, 68, 68, 0.25); display: inline-block; text-align: center; margin: 2px;" title="Fini thiếu lớp này">Thiếu: ${escapeHTML(cls)}${cropHtml}</div>`);
                    }
                }
                
                for (let i = 0; i < numAssembla; i++) {
                    const el = elsAssembla[i];
                    const cropHtml = el && el.crop_base64 ? `<br><img src="data:image/png;base64,${el.crop_base64}" style="max-height: 40px; border: 1px solid #ccc; margin-top: 4px; border-radius: 4px;">` : '';
                    if (numAssembla > numFini && i >= numFini) {
                        assemblaParts.push(`<div class="diff-standard-word" title="Cần phải có lớp này" style="display: inline-block; text-align: center; margin: 2px;">${escapeHTML(cls)}${cropHtml}</div>`);
                    } else {
                        assemblaParts.push(`<div style="display: inline-block; text-align: center; margin: 2px;"><span>${escapeHTML(cls)}</span>${cropHtml}</div>`);
                    }
                }
            }
        });
        
        return {
            fini: finiParts.join(' ') || '<span class="diff-empty">(Trống)</span>',
            assembla: assemblaParts.join(' ') || '<span class="diff-empty">(Trống)</span>'
        };
    }

    function renderBlockDetails(context, prefix, data, matchObj) {
        if (!data) return;
        context.querySelector(`.${prefix}-page`).textContent = data.page_idx + 1;
        if(data.image_base64) {
            const img = context.querySelector(`.${prefix}-img`);
            img.src = `data:image/jpeg;base64,${data.image_base64}`;
            
            let boxesToDraw = null;
            let borderColor = '';
            let bgColor = '';
            
            if (prefix === 'fini' && matchObj && matchObj._textDiff && matchObj._textDiff.mismatch_boxes && matchObj._textDiff.mismatch_boxes.length > 0) {
                boxesToDraw = matchObj._textDiff.mismatch_boxes;
                borderColor = 'rgb(239, 68, 68)'; // red-500
                bgColor = 'rgba(239, 68, 68, 0.4)';
            } else if (prefix === 'assembla' && matchObj && matchObj._textDiff && matchObj._textDiff.assembla_mismatch_boxes && matchObj._textDiff.assembla_mismatch_boxes.length > 0) {
                boxesToDraw = matchObj._textDiff.assembla_mismatch_boxes;
                borderColor = 'rgb(34, 197, 94)'; // green-500
                bgColor = 'rgba(34, 197, 94, 0.4)';
            }
            
            if (boxesToDraw) {
                const wrapper = document.createElement('div');
                wrapper.style.position = 'relative';
                wrapper.style.display = 'inline-block';
                wrapper.style.maxWidth = '100%';
                img.parentNode.insertBefore(wrapper, img);
                wrapper.appendChild(img);
                
                const [X1, Y1, X2, Y2] = data.xyxy;
                const blockWidth = X2 - X1;
                const blockHeight = Y2 - Y1;
                
                boxesToDraw.forEach(box => {
                    const [bx1, by1, bx2, by2] = box;
                    const leftPct = ((bx1 - X1) / blockWidth) * 100;
                    const topPct = ((by1 - Y1) / blockHeight) * 100;
                    const widthPct = ((bx2 - bx1) / blockWidth) * 100;
                    const heightPct = ((by2 - by1) / blockHeight) * 100;
                    
                    const hl = document.createElement('div');
                    hl.className = 'word-highlight-modal';
                    hl.style.position = 'absolute';
                    hl.style.left = `${leftPct}%`;
                    hl.style.top = `${topPct}%`;
                    hl.style.width = `${widthPct}%`;
                    hl.style.height = `${heightPct}%`;
                    hl.style.backgroundColor = bgColor;
                    hl.style.border = `2px solid ${borderColor}`;
                    hl.style.borderRadius = '2px';
                    hl.style.pointerEvents = 'none';
                    wrapper.appendChild(hl);
                });
            }
        }
    }

    function renderUnmatchedBlockDetails(context, data) {
        context.querySelector('.unmatched-page').textContent = data.page_idx + 1;
        if(data.image_base64) {
            context.querySelector('.unmatched-img').src = `data:image/jpeg;base64,${data.image_base64}`;
        }
        context.querySelector('.unmatched-text').textContent = data.text || 'N/A';
        context.querySelector('.unmatched-price').textContent = data.price || 'N/A';
        context.querySelector('.unmatched-pdv').textContent = data.pdv_code || 'N/A';
    }

    // --- Single-View Interactive Catalog Logic ---
    let catalogFiniDoc = null;
    let catalogErrorPages = [];
    let currentErrorPageIndex = 0;
    let catalogZoom = 1.0;
    let catalogData = null;

    async function initInteractiveCatalog(finiUrl, assemblaUrl, data) {
        catalogData = data;
        
        let errorPagesSet = new Set();
        let pagesWithMatches = new Set();
        
        data.matched.forEach(match => {
            if (match.fini) {
                pagesWithMatches.add(match.fini.page_idx + 1);
                let computedHasDiff = match.has_diff;
                if (match.assembla) {
                    const textDiff = match._textDiff || getRichWordDiff(match.fini.rich_text || [], match.assembla.rich_text || []);
                    match._textDiff = textDiff;
                    const hasTextMismatch = textDiff.fini.includes('diff-mismatch-word') || textDiff.fini.includes('background-color: rgba') || textDiff.assembla.includes('diff-standard-word');
                    const clean = (s) => (s || '').replace(/\s+/g, '').trim().toLowerCase();
                    const hasPriceMismatch = clean(match.fini.price) !== clean(match.assembla.price);
                    
                    if (hasTextMismatch || hasPriceMismatch) {
                        computedHasDiff = true;
                    }
                }
                if (computedHasDiff) {
                    errorPagesSet.add(match.fini.page_idx + 1); // 1-based page index
                }
            }
        });
        
        if (data.unmatched_fini) {
            data.unmatched_fini.forEach(un => {
                if (pagesWithMatches.has(un.page_idx + 1)) {
                    errorPagesSet.add(un.page_idx + 1);
                }
            });
        }
        
        catalogErrorPages = Array.from(errorPagesSet).sort((a,b) => a - b);
        
        if (catalogErrorPages.length === 0) {
            catalogErrorPages = [1]; // Fallback if no errors exist at all
        }
        
        currentErrorPageIndex = 0;

        try {
            if (finiUrl) {
                catalogFiniDoc = await pdfjsLib.getDocument(finiUrl).promise;
                renderCatalogPage(catalogErrorPages[currentErrorPageIndex]);
            }
        } catch (e) {
            console.error("Error loading PDF.js catalog:", e);
        }
    }

    window.initInteractiveCatalog = initInteractiveCatalog;

    document.getElementById('catalog-prev-btn').addEventListener('click', () => {
        if (currentErrorPageIndex <= 0) return;
        currentErrorPageIndex--;
        renderCatalogPage(catalogErrorPages[currentErrorPageIndex]);
    });

    document.getElementById('catalog-next-btn').addEventListener('click', () => {
        if (currentErrorPageIndex >= catalogErrorPages.length - 1) return;
        currentErrorPageIndex++;
        renderCatalogPage(catalogErrorPages[currentErrorPageIndex]);
    });

    async function renderCatalogPage(num) {
        if (!catalogFiniDoc) return;
        
        document.getElementById('catalog-page-info').textContent = `Trang ${num} (Lỗi: ${currentErrorPageIndex + 1}/${catalogErrorPages.length} trang)`;
        document.getElementById('catalog-prev-btn').disabled = currentErrorPageIndex <= 0;
        document.getElementById('catalog-next-btn').disabled = currentErrorPageIndex >= catalogErrorPages.length - 1;

        await renderSinglePdfPage(catalogFiniDoc, num, 'fini-canvas', 'fini-overlay-layer');
        renderFiniOverlays(num);
        renderAssemblaUnmatchedSidebar(num);
    }

    async function renderSinglePdfPage(doc, num, canvasId, overlayId) {
        const page = await doc.getPage(num);
        const canvas = document.getElementById(canvasId);
        const ctx = canvas.getContext('2d');

        let unscaledViewport = page.getViewport({ scale: 1.0 });
        // Single view means canvas takes most of the width (minus sidebar 350px)
        const panelWidth = Math.min(1200, window.innerWidth - 450); 
        catalogZoom = panelWidth / unscaledViewport.width;
        if (catalogZoom > 2.5) catalogZoom = 2.5;

        const viewport = page.getViewport({ scale: catalogZoom });
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        const overlayLayer = document.getElementById(overlayId);
        overlayLayer.style.width = `${viewport.width}px`;
        overlayLayer.style.height = `${viewport.height}px`;

        const renderContext = { canvasContext: ctx, viewport: viewport };
        await page.render(renderContext).promise;
    }

    function renderFiniOverlays(pageNum) {
        const finiOverlay = document.getElementById('fini-overlay-layer');
        finiOverlay.innerHTML = '';
        
        const engineZoom = catalogData.engine_zoom || 2.0;
        const scaleFactor = catalogZoom / engineZoom;
        const pageIndex = pageNum - 1; 
        
        // Draw matched items (errors and correct ones)
        catalogData.matched.forEach((match, idx) => {
            if (match.fini && match.fini.page_idx === pageIndex) {
                let computedHasDiff = match.has_diff;
                let computedErrors = computedHasDiff ? match.differences.map(d => d.label).join(' | ') : "";
                
                // Also check text/price mismatches frontend-side (same logic as Match Modal)
                if (match.assembla) {
                    const textDiff = match._textDiff || getRichWordDiff(match.fini.rich_text || [], match.assembla.rich_text || []);
                    match._textDiff = textDiff;
                    const hasTextMismatch = textDiff.fini.includes('diff-mismatch-word') || textDiff.fini.includes('background-color: rgba') || textDiff.assembla.includes('diff-standard-word');
                    
                    const clean = (s) => (s || '').replace(/\\s+/g, '').trim().toLowerCase();
                    const hasPriceMismatch = clean(match.fini.price) !== clean(match.assembla.price);
                    
                    if (hasTextMismatch || hasPriceMismatch) {
                        computedHasDiff = true;
                        if (!computedErrors) computedErrors = "Nội dung/Giá tiền không khớp";
                    }
                }
                
                if (!computedHasDiff) {
                    computedErrors = "✅ Khớp hoàn toàn";
                }

                const assemblaImgBase64 = match.assembla ? match.assembla.image_base64 : '';
                
                drawFiniBox(finiOverlay, match.fini.xyxy, scaleFactor, idx, false, computedErrors, computedHasDiff, assemblaImgBase64, match);
            }
        });
        
        // Unmatched Fini (Thiếu bên Assembla)
        if (catalogData.unmatched_fini) {
            catalogData.unmatched_fini.forEach((un, idx) => {
                if (un.page_idx === pageIndex) {
                    drawFiniBox(finiOverlay, un.xyxy, scaleFactor, idx, 'fini_unmatched', "Thiếu bên Assembla", true, '', null);
                }
            });
        }
    }

    function drawFiniBox(container, coords, scaleFactor, idx, unmatchedType, errorText, hasDiff, assemblaImgBase64, matchObj) {
        const [x1, y1, x2, y2] = coords;
        const div = document.createElement('div');
        div.className = 'interactive-box';
        if (hasDiff) {
            div.classList.add('error-box'); // this will show red border on hover
        }
        
        div.style.left = `${x1 * scaleFactor}px`;
        div.style.top = `${y1 * scaleFactor}px`;
        div.style.width = `${(x2 - x1) * scaleFactor}px`;
        div.style.height = `${(y2 - y1) * scaleFactor}px`;
        
        let finiHighlightsHtml = '';
        let assemblaHighlightsHtml = '';
        
        if (hasDiff && matchObj && matchObj.assembla) {
            const textDiff = matchObj._textDiff || getRichWordDiff(matchObj.fini.rich_text || [], matchObj.assembla.rich_text || []);
            matchObj._textDiff = textDiff;
            
            let finiBoxes = textDiff.mismatch_boxes ? [...textDiff.mismatch_boxes] : [];
            let assemblaBoxes = textDiff.assembla_mismatch_boxes ? [...textDiff.assembla_mismatch_boxes] : [];
            
            // Check Price Mismatch to add price boxes
            const clean = (s) => (s || '').replace(/\s+/g, '').trim().toLowerCase();
            const checkSubElementDiff = (finiVal, assemblaVal, subElementName) => {
                if (clean(finiVal) !== clean(assemblaVal)) {
                    if (matchObj.fini.sub_elements) {
                        const subF = matchObj.fini.sub_elements.find(s => s.name === subElementName);
                        if (subF && subF.xyxy) finiBoxes.push(subF.xyxy);
                    }
                    if (matchObj.assembla.sub_elements) {
                        const subA = matchObj.assembla.sub_elements.find(s => s.name === subElementName);
                        if (subA && subA.xyxy) assemblaBoxes.push(subA.xyxy);
                    }
                }
            };
            
            checkSubElementDiff(matchObj.fini.price, matchObj.assembla.price, 'price');
            checkSubElementDiff(matchObj.fini.promo_text, matchObj.assembla.promo_text, 'promo_fidelite');
            
            // Draw Fini Boxes
            finiBoxes.forEach(box => {
                const [bx1, by1, bx2, by2] = box;
                finiHighlightsHtml += `<div class="word-highlight" style="left:${(bx1 - x1)*scaleFactor}px; top:${(by1 - y1)*scaleFactor}px; width:${(bx2 - bx1)*scaleFactor}px; height:${(by2 - by1)*scaleFactor}px;"></div>`;
            });
            
            // Draw Assembla Boxes
            const [Ax1, Ay1, Ax2, Ay2] = matchObj.assembla.xyxy || [0,0,1,1];
            const blockW = Ax2 - Ax1;
            const blockH = Ay2 - Ay1;
            assemblaBoxes.forEach(box => {
                const [bx1, by1, bx2, by2] = box;
                if (blockW > 0 && blockH > 0) {
                    const l = ((bx1 - Ax1) / blockW) * 100;
                    const t = ((by1 - Ay1) / blockH) * 100;
                    const w = ((bx2 - bx1) / blockW) * 100;
                    const h = ((by2 - by1) / blockH) * 100;
                    assemblaHighlightsHtml += `<div class="assembla-highlight" style="left:${l}%; top:${t}%; width:${w}%; height:${h}%;"></div>`;
                }
            });
        }
        
        if (finiHighlightsHtml) {
            div.innerHTML = finiHighlightsHtml; // Add highlights to the main Fini overlay box
        }
        
        // Create the Assembla Preview Popup
        const popup = document.createElement('div');
        popup.className = 'assembla-preview-popup';
        
        const headerClass = hasDiff ? 'error' : 'success';
        const headerTitle = hasDiff ? 'Lỗi đối chiếu:' : 'Trạng thái:';
        
        let popupHtml = `
            <div class="popup-header ${headerClass}">${headerTitle} ${errorText}</div>
        `;
        
        if (assemblaImgBase64) {
            popupHtml += `
                <div class="popup-img-container">
                    <div style="position: relative; display: inline-block;">
                        <img src="data:image/jpeg;base64,${assemblaImgBase64}" alt="Assembla Crop" style="max-width:100%; display:block;" />
                        ${assemblaHighlightsHtml}
                    </div>
                </div>
                <div style="padding:8px; font-size:0.8rem; text-align:center; color:#64748b; background:#fffaf0; border-top:1px solid #fcd34d;">(Click chuột vào ảnh để xem chi tiết toàn bộ lỗi)</div>
            `;
        } else if (unmatchedType === 'fini_unmatched') {
            popupHtml += `<div class="popup-error-details" style="text-align:center; padding: 20px;">Không có dữ liệu bên Assembla</div>`;
        }
        
        popup.innerHTML = popupHtml;
        // Do NOT append to div directly, handle it dynamically on hover
        
        // Use fixed positioning relative to viewport
        div.addEventListener('mouseenter', () => {
            const rect = div.getBoundingClientRect();
            
            // Set fixed coordinates based on the hovered box
            popup.style.top = `${rect.top}px`;
            popup.style.left = `${rect.right + 10}px`;
            // Reset right/margin if it was flipped previously
            popup.style.right = 'auto';
            popup.style.marginLeft = '0';
            popup.style.marginRight = '0';
            popup.style.transform = 'translateX(0)';
            
            document.body.appendChild(popup);
            
            // Allow a tiny delay for browser to render and get actual width
            requestAnimationFrame(() => {
                popup.classList.add('show-popup');
            });
        });
        
        div.addEventListener('mouseleave', () => {
            popup.classList.remove('show-popup');
            if (popup.parentNode) {
                // Short timeout to allow CSS fade out before removing from DOM
                setTimeout(() => {
                    if (!popup.classList.contains('show-popup') && popup.parentNode) {
                        popup.parentNode.removeChild(popup);
                    }
                }, 200);
            }
        });
        
        // Click to open Modal for full detail
        div.addEventListener('click', () => {
            showMatchModal(idx, unmatchedType);
        });
        
        container.appendChild(div);
    }

    function renderAssemblaUnmatchedSidebar(pageNum) {
        const sidebarList = document.getElementById('assembla-unmatched-list');
        sidebarList.innerHTML = '';
        
        const pageIndex = pageNum - 1;
        let count = 0;
        
        if (catalogData.unmatched_assembla) {
            catalogData.unmatched_assembla.forEach((un, idx) => {
                if (un.page_idx === pageIndex) {
                    count++;
                    const card = document.createElement('div');
                    card.className = 'unmatched-sidebar-card';
                    card.innerHTML = `
                        <div class="desc">Khối bị dư thừa (chỉ có bên Assembla):</div>
                        <img src="data:image/jpeg;base64,${un.image_base64}" alt="Unmatched Assembla" />
                    `;
                    sidebarList.appendChild(card);
                }
            });
        }
        
        if (count === 0) {
            sidebarList.innerHTML = `<div class="empty-unmatched">Không có sản phẩm nào bị dư thừa trên trang này.</div>`;
        }
    }

    // Modal Logic
    const modal = document.getElementById('match-detail-modal');
    const modalBody = document.getElementById('modal-detail-body');
    const btnCloseModal = document.getElementById('btn-close-modal');

    btnCloseModal.addEventListener('click', () => {
        modal.classList.add('hidden');
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });

    function showMatchModal(matchIdx, unmatchedType) {
        modalBody.innerHTML = '';
        
        if (unmatchedType === 'fini_unmatched') {
            modalBody.innerHTML = `<div style="text-align:center; padding: 2rem;"><h4>Thiếu bên Assembla</h4><p>Khối này có trong thiết kế Fini nhưng không tìm thấy bên bản dàn trang Assembla.</p></div>`;
        } else if (unmatchedType === 'assembla_unmatched') {
            modalBody.innerHTML = `<div style="text-align:center; padding: 2rem;"><h4>Dư thừa bên Assembla</h4><p>Khối này bị dư thừa bên bản dàn trang Assembla (không có trong thiết kế Fini).</p></div>`;
        } else {
            // Lấy lại thẻ Match Card từ tab Results
            const allCards = document.querySelectorAll('#matches-container .modern-match-card');
            if (matchIdx >= 0 && matchIdx < allCards.length) {
                const originalCard = allCards[matchIdx];
                const clonedCard = originalCard.cloneNode(true);
                clonedCard.style.animationDelay = '0s'; // reset animation
                modalBody.appendChild(clonedCard);
                
                // Re-bind identical content toggle
                const btnToggle = clonedCard.querySelector('.btn-toggle-identical');
                const identicalContent = clonedCard.querySelector('.identical-content');
                if (btnToggle && identicalContent) {
                    btnToggle.addEventListener('click', () => {
                        const isHidden = identicalContent.classList.contains('hidden');
                        if (isHidden) {
                            identicalContent.classList.remove('hidden');
                            btnToggle.querySelector('span').textContent = '👁️ Ẩn các thông tin trùng khớp';
                            btnToggle.classList.add('active');
                        } else {
                            identicalContent.classList.add('hidden');
                            btnToggle.querySelector('span').textContent = '👁️ Xem thêm các thông tin trùng khớp';
                            btnToggle.classList.remove('active');
                        }
                    });
                }
            }
        }
        
        modal.classList.remove('hidden');
    }

});
