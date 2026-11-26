from __future__ import annotations

import html
import json


def _js_safe(value: str) -> str:
    """Serialize a Python value for safe inline <script> injection."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


_BASE_CSS = """
:root {
    --bg-ground: #F4F5F7;
    --bg-surface: #FFFFFF;
    --bg-subtle: #E9ECEF;
    --text-primary: #111827;
    --text-secondary: #475569;
    --border-control: #64748B;
    --border-divider: #CBD5E1;
    --accent: #0F4C81;
    --accent-hover: #0B3A63;
    --success-text: #166534;
    --success-bg: #DCFCE7;
    --success-border: #15803D;
    --warn-text: #92400E;
    --warn-bg: #FEF3C7;
    --warn-border: #B45309;
    --err-text: #991B1B;
    --err-bg: #FEE2E2;
    --err-border: #B91C1C;
    --radius-control: 6px;
    --radius-panel: 10px;
}

* {
    box-sizing: border-box;
}

html {
    font-size: 16px;
    max-width: 100%;
    overflow-x: clip;
}

body {
    margin: 0;
    max-width: 100%;
    overflow-x: clip;
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: var(--bg-ground);
    color: var(--text-primary);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}

.mono {
    font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
}

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}

:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
}

.topbar {
    background-color: var(--bg-surface);
    border-top: 4px solid var(--accent);
    border-bottom: 1px solid var(--border-divider);
    padding: 12px 16px;
}

.topbar-inner {
    max-width: 1440px;
    margin: 0 auto;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.topbar-left {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    min-width: 0;
    max-width: 100%;
    flex: 1 1 280px;
}

.topbar-title-group {
    min-width: 0;
    max-width: 100%;
}

.topbar h1 {
    margin: 0;
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    word-break: break-word;
}

.topbar-sub {
    font-size: 0.875rem;
    color: var(--text-secondary);
}

.topbar-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
}

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 44px;
    padding: 10px 16px;
    font-family: inherit;
    font-size: 0.9375rem;
    font-weight: 600;
    line-height: 1.2;
    border-radius: var(--radius-control);
    border: 1px solid var(--border-control);
    background-color: var(--bg-surface);
    color: var(--text-primary);
    text-decoration: none;
    cursor: pointer;
    transition: background-color 120ms ease, border-color 120ms ease;
}

.btn:hover:not(:disabled) {
    background-color: var(--bg-subtle);
}

.btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
}

.btn-primary {
    background-color: var(--accent);
    border-color: var(--accent);
    color: #FFFFFF;
}

.btn-primary:hover:not(:disabled) {
    background-color: var(--accent-hover);
    border-color: var(--accent-hover);
}

.btn-danger {
    color: var(--err-text);
    border-color: var(--err-border);
    background-color: var(--bg-surface);
}

.btn-danger:hover:not(:disabled) {
    background-color: var(--err-bg);
}

.btn-sm {
    min-height: 44px;
    padding: 8px 12px;
    font-size: 0.875rem;
}

.tag {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: var(--radius-control);
    font-size: 0.8125rem;
    font-weight: 600;
    border: 1px solid var(--border-control);
    background-color: var(--bg-subtle);
    color: var(--text-primary);
}

.tag-success {
    background-color: var(--success-bg);
    color: var(--success-text);
    border-color: var(--success-border);
}

.tag-warn {
    background-color: var(--warn-bg);
    color: var(--warn-text);
    border-color: var(--warn-border);
}

.tag-error {
    background-color: var(--err-bg);
    color: var(--err-text);
    border-color: var(--err-border);
}

.panel {
    background-color: var(--bg-surface);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-panel);
    padding: 16px;
}

.banner {
    border-radius: var(--radius-panel);
    padding: 14px 16px;
    border: 1px solid var(--border-control);
    background-color: var(--bg-surface);
    margin-bottom: 16px;
}

.banner-title {
    font-weight: 700;
    font-size: 0.95rem;
    margin: 0 0 6px 0;
}

.banner p, .banner ul {
    margin: 0;
    font-size: 0.92rem;
}

.banner ul {
    margin-top: 6px;
    padding-left: 20px;
}

.banner-success {
    background-color: var(--success-bg);
    color: var(--success-text);
    border-color: var(--success-border);
}

.banner-warn {
    background-color: var(--warn-bg);
    color: var(--warn-text);
    border-color: var(--warn-border);
}

.banner-error {
    background-color: var(--err-bg);
    color: var(--err-text);
    border-color: var(--err-border);
}

.field-label {
    display: block;
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
}

.input, .select {
    width: 100%;
    min-width: 0;
    max-width: 100%;
    min-height: 44px;
    padding: 9px 10px;
    font-family: inherit;
    font-size: 1rem;
    color: var(--text-primary);
    background-color: var(--bg-surface);
    border: 1px solid var(--border-control);
    border-radius: var(--radius-control);
    transition: border-color 120ms ease;
}

.input-mono {
    font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
}

input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
}

input[type="number"] {
    -moz-appearance: textfield;
}

.input[readonly] {
    background-color: var(--bg-subtle);
    color: var(--text-primary);
}

.state-box {
    max-width: 720px;
    margin: 32px auto;
    padding: 24px;
    background-color: var(--bg-surface);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-panel);
}

.state-box h2 {
    margin: 0 0 8px 0;
    font-size: 1.15rem;
}

.state-box p {
    margin: 0 0 16px 0;
    color: var(--text-secondary);
}

.hidden {
    display: none !important;
}
"""


def render_forbidden_page_html(message: str) -> str:
    safe_msg = html.escape(message or "Link tidak valid atau sudah kedaluwarsa.")
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Akses Ditolak - AIS-VISTA</title>
    <style>{_BASE_CSS}</style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-inner">
            <div class="topbar-title-group">
                <h1>AIS-VISTA Opname Editor</h1>
                <div class="topbar-sub">Validasi akses tautan</div>
            </div>
            <a class="btn" href="/">Buka Konsol Utama</a>
        </div>
    </header>
    <main style="padding: 16px;">
        <section class="state-box banner-error" role="alert">
            <h2>ERROR: Akses Halaman Ditolak</h2>
            <p style="color: var(--err-text);">{safe_msg}</p>
            <p style="color: var(--err-text);">Minta tautan review terbaru dari bot WhatsApp AIS-VISTA atau buka Konsol Utama.</p>
            <a class="btn" href="/">Kembali ke Konsol Utama</a>
        </section>
    </main>
</body>
</html>"""


def render_review_page_html(record_id: str, token: str, dashboard_url: str) -> str:
    safe_id_html = html.escape(record_id)
    safe_dash_html = html.escape(dashboard_url)
    js_id = _js_safe(record_id)
    js_token = _js_safe(token)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review Opname {safe_id_html} - AIS-VISTA</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
{_BASE_CSS}

main.review-main {{
    max-width: 1440px;
    margin: 0 auto;
    padding: 16px 16px 140px 16px;
}}

.workspace {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    align-items: start;
}}

.workspace > * {{
    min-width: 0;
}}

.workspace.no-media {{
    max-width: 1280px;
    margin: 0 auto;
}}

.scan-panel {{
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
}}

.scan-header-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}}

.scan-header-row h2 {{
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
}}

.scan-toolbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
}}

.scan-viewport {{
    width: 100%;
    max-height: 46vh;
    overflow: auto;
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-control);
    background-color: var(--bg-subtle);
    padding: 8px;
    text-align: center;
}}

.scan-viewport img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
    transform-origin: center center;
    transition: transform 140ms ease;
    border-radius: 4px;
}}

.scan-body.is-collapsed {{
    display: none;
}}

.header-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
}}

.header-grid > *, .row-fields > *, .dims-grid > * {{
    min-width: 0;
}}

.slot-preview-note {{
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border-divider);
    font-size: 0.875rem;
    color: var(--text-secondary);
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
}}

.section-header {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin: 18px 0 12px 0;
}}

.section-header h2 {{
    margin: 0;
    font-size: 1.05rem;
    font-weight: 700;
}}

.rows-list {{
    display: flex;
    flex-direction: column;
    gap: 12px;
}}

.row-card {{
    background-color: var(--bg-surface);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-panel);
    padding: 14px;
}}

.row-card.has-error {{
    border-color: var(--err-border);
}}

.row-card-top {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding-bottom: 10px;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--border-divider);
}}

.row-card-title {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    font-size: 0.95rem;
}}

.row-card-actions {{
    display: flex;
    gap: 8px;
}}

.row-fields {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}}

.f-tanggal,
.f-boq,
.f-vol,
.f-ket,
.dims-wrap {{
    grid-column: span 2;
}}

.dims-wrap {{
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-control);
    padding: 10px;
    background-color: var(--bg-ground);
}}

.dims-toggle {{
    width: 100%;
    min-height: 44px;
    padding: 8px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background-color: var(--bg-surface);
    border: 1px solid var(--border-control);
    border-radius: var(--radius-control);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
}}

.dims-grid {{
    display: none;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 10px;
}}

.dims-wrap.is-open .dims-grid {{
    display: grid;
}}

.vol-row-group {{
    display: flex;
    align-items: stretch;
    gap: 6px;
}}

.unit-pill {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 56px;
    padding: 0 10px;
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-control);
    background-color: var(--bg-subtle);
    color: var(--text-primary);
    font-weight: 600;
    font-size: 0.875rem;
}}

.calc-hint {{
    margin-top: 4px;
    font-size: 0.8125rem;
    color: var(--text-secondary);
}}

.summary-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
}}

.summary-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-control);
    background-color: var(--bg-ground);
}}

.action-bar {{
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 20;
    background-color: var(--bg-surface);
    border-top: 1px solid var(--border-divider);
    padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
    box-shadow: 0 -2px 8px rgba(17, 24, 39, 0.08);
}}

.action-bar-inner {{
    max-width: 1440px;
    margin: 0 auto;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
}}

.action-bar-buttons {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    flex: 1 1 100%;
    justify-content: stretch;
}}

.action-bar-buttons .btn {{
    flex: 1 1 auto;
    padding: 8px 12px;
    font-size: 0.875rem;
}}

.modal-backdrop {{
    position: fixed;
    inset: 0;
    z-index: 50;
    background-color: rgba(17, 24, 39, 0.85);
    display: flex;
    flex-direction: column;
    padding: 12px;
}}

.modal-toolbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: space-between;
    align-items: center;
    background-color: var(--bg-surface);
    padding: 10px 12px;
    border-radius: var(--radius-panel) var(--radius-panel) 0 0;
}}

.modal-canvas {{
    flex: 1 1 auto;
    overflow: auto;
    background-color: var(--bg-subtle);
    border-radius: 0 0 var(--radius-panel) var(--radius-panel);
    padding: 16px;
    text-align: center;
}}

.modal-canvas img {{
    max-width: 100%;
    height: auto;
    transform-origin: top center;
    transition: transform 140ms ease;
}}

@media (min-width: 960px) {{
    main.review-main {{
        padding: 20px 24px 48px 24px;
    }}

    .workspace.has-media {{
        grid-template-columns: minmax(340px, 40%) 1fr;
        gap: 20px;
    }}

    .scan-panel {{
        position: sticky;
        top: 16px;
    }}

    .scan-body.is-collapsed {{
        display: block;
    }}

    .scan-toggle-btn {{
        display: none;
    }}

    .scan-viewport {{
        max-height: 76vh;
    }}

    .header-grid {{
        grid-template-columns: repeat(4, minmax(0, 1fr));
    }}

    .row-fields {{
        grid-template-columns: repeat(24, minmax(0, 1fr));
        gap: 8px;
        align-items: start;
    }}

    .f-tanggal {{ grid-column: span 5; }}
    .f-kode {{ grid-column: span 4; }}
    .f-lokasi {{ grid-column: span 4; }}
    .f-jalur {{ grid-column: span 2; }}
    .f-lajur {{ grid-column: span 2; }}
    .f-boq {{ grid-column: span 7; }}

    .dims-wrap {{
        display: contents;
        grid-column: auto;
        border: 0;
        padding: 0;
        background: transparent;
    }}

    .dims-toggle {{
        display: none;
    }}

    .dims-grid,
    .dims-wrap.is-open .dims-grid {{
        display: contents;
    }}

    .f-dim {{ grid-column: span 2; }}
    .f-vol {{ grid-column: span 6; }}
    .f-ket {{ grid-column: span 10; }}

    .input, .select {{
        font-size: 0.9375rem;
        padding: 8px 10px;
    }}

    .summary-grid {{
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }}

    .action-bar {{
        position: static;
        margin-top: 20px;
        border: 1px solid var(--border-divider);
        border-radius: var(--radius-panel);
        box-shadow: none;
        padding: 14px 16px;
    }}

    .action-bar-buttons {{
        flex: 0 0 auto;
    }}

    .action-bar-buttons .btn {{
        flex: 0 0 auto;
        font-size: 0.9375rem;
        padding: 10px 16px;
    }}
}}
    </style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-inner">
            <div class="topbar-left">
                <a class="btn btn-sm" href="{safe_dash_html}">&larr; Daftar Slot</a>
                <div class="topbar-title-group">
                    <h1 id="pageTitle">Review Opname <span class="mono">{safe_id_html}</span></h1>
                    <div class="topbar-sub" id="pageSub">Memuat detail formulir...</div>
                </div>
            </div>
            <div class="topbar-meta" id="topMetaTags"></div>
        </div>
    </header>

    <main class="review-main">
        <div id="loadingState" class="state-box" role="status" aria-live="polite">
            <h2>Memuat Data Opname</h2>
            <p>Mengambil data baris pekerjaan dan lampiran scan untuk <span class="mono">{safe_id_html}</span>...</p>
        </div>

        <div id="errorState" class="state-box banner-error hidden" role="alert">
            <h2>ERROR: Gagal Memuat Data Opname</h2>
            <p id="errorStateMsg" style="color: var(--err-text);">Terjadi kesalahan saat membaca data dari server.</p>
            <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                <button type="button" class="btn" id="retryLoadBtn">Muat Ulang</button>
                <a class="btn" href="{safe_dash_html}">Buka Daftar Slot</a>
            </div>
        </div>

        <form id="editorForm" class="hidden" novalidate>
            <div id="statusBanner" class="banner hidden" role="status" aria-live="polite"></div>
            <div id="rosterBanner" class="banner banner-warn hidden" role="status"></div>

            <div id="workspaceGrid" class="workspace no-media">
                <aside id="scanPanel" class="panel scan-panel hidden" aria-label="Lampiran Scan Opname">
                    <div class="scan-header-row">
                        <h2>Lampiran Scan</h2>
                        <button type="button" class="btn btn-sm scan-toggle-btn" id="scanToggleBtn" aria-expanded="true">Sembunyikan Scan</button>
                    </div>
                    <div id="scanBody" class="scan-body">
                        <div class="scan-toolbar" style="margin-bottom: 10px;">
                            <button type="button" class="btn btn-sm" id="zoomOutBtn">Zoom -</button>
                            <span class="tag mono" id="zoomLevelLabel">100%</span>
                            <button type="button" class="btn btn-sm" id="zoomInBtn">Zoom +</button>
                            <button type="button" class="btn btn-sm" id="rotateBtn">Putar 90</button>
                            <button type="button" class="btn btn-sm" id="openLightboxBtn">Layar Penuh</button>
                            <a class="btn btn-sm" id="rawMediaLink" href="#" target="_blank" rel="noopener">File Asli</a>
                        </div>
                        <div id="pdfPager" class="scan-toolbar hidden" style="margin-bottom: 10px;">
                            <button type="button" class="btn btn-sm" id="prevPageBtn">Hal Sebelumnya</button>
                            <span class="tag mono" id="pdfPageLabel">Hal 1 / 1</span>
                            <button type="button" class="btn btn-sm" id="nextPageBtn">Hal Berikutnya</button>
                        </div>
                        <div class="scan-viewport">
                            <img id="scanPreviewImg" src="" alt="Lampiran form opname yang ditandatangani" />
                        </div>
                    </div>
                </aside>

                <div class="editor-column">
                    <section class="panel" aria-labelledby="headerMetaTitle">
                        <h2 id="headerMetaTitle" style="margin: 0 0 12px 0; font-size: 1rem;">Informasi Header Formulir</h2>
                        <div class="header-grid">
                            <div>
                                <label class="field-label" for="asetDisplay">Aset Pekerjaan</label>
                                <input id="asetDisplay" class="input" type="text" readonly />
                            </div>
                            <div>
                                <label class="field-label" for="wilayahSelect">Wilayah</label>
                                <select id="wilayahSelect" class="select">
                                    <option value="W1">W1 (Wilayah 1)</option>
                                    <option value="W2">W2 (Wilayah 2)</option>
                                </select>
                            </div>
                            <div>
                                <label class="field-label" for="vendorSelect">Vendor</label>
                                <select id="vendorSelect" class="select"></select>
                            </div>
                            <div>
                                <label class="field-label" for="mingguSelect">Minggu</label>
                                <select id="mingguSelect" class="select">
                                    <option value="M1">M1</option>
                                    <option value="M2">M2</option>
                                    <option value="M3">M3</option>
                                    <option value="M4">M4</option>
                                    <option value="M5">M5</option>
                                </select>
                            </div>
                        </div>
                        <div class="slot-preview-note">
                            <span>Target Slot ID: <strong id="slotIdPreview" class="mono">-</strong></span>
                            <span id="xlsxArchiveLinkWrap"></span>
                        </div>
                    </section>

                    <div class="section-header">
                        <h2>Daftar Baris Pekerjaan (<span id="rowCountLabel" class="mono">0</span>)</h2>
                        <button type="button" class="btn btn-sm" id="addRowTopBtn">+ Tambah Baris</button>
                    </div>

                    <div id="rowsContainer" class="rows-list"></div>

                    <section class="panel" style="margin-top: 16px;" aria-labelledby="summaryTitle">
                        <h2 id="summaryTitle" style="margin: 0 0 10px 0; font-size: 1rem;">Ringkasan Volume per Item BOQ</h2>
                        <div id="summaryGrid" class="summary-grid"></div>
                    </section>

                    <div class="action-bar" id="actionBar">
                        <div class="action-bar-inner">
                            <div style="font-size: 0.875rem; color: var(--text-secondary);" id="dirtyIndicator">Semua perubahan dimuat</div>
                            <div class="action-bar-buttons">
                                <button type="button" class="btn" id="addRowBtn">+ Tambah Baris</button>
                                <button type="submit" class="btn btn-primary" id="saveBtn">Simpan ke DATA UNTUK VOL</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </form>
    </main>

    <div id="lightboxModal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="lightboxTitle">
        <div class="modal-toolbar">
            <strong id="lightboxTitle">Pratinjau Scan</strong>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
                <button type="button" class="btn btn-sm" id="modalZoomOutBtn">Zoom -</button>
                <span class="tag mono" id="modalZoomLabel">100%</span>
                <button type="button" class="btn btn-sm" id="modalZoomInBtn">Zoom +</button>
                <button type="button" class="btn btn-sm" id="modalRotateBtn">Putar 90</button>
                <button type="button" class="btn btn-sm" id="closeLightboxBtn">Tutup (Esc)</button>
            </div>
        </div>
        <div class="modal-canvas">
            <img id="lightboxImg" src="" alt="Lampiran form opname diperbesar" />
        </div>
    </div>

    <script>
    (function() {{
        const RECORD_ID = {js_id};
        const TOKEN = {js_token};

        const loadingEl = document.getElementById("loadingState");
        const errorEl = document.getElementById("errorState");
        const errorMsgEl = document.getElementById("errorStateMsg");
        const retryBtn = document.getElementById("retryLoadBtn");
        const formEl = document.getElementById("editorForm");
        const statusBanner = document.getElementById("statusBanner");
        const rosterBanner = document.getElementById("rosterBanner");
        const workspaceGrid = document.getElementById("workspaceGrid");
        const topMetaTags = document.getElementById("topMetaTags");
        const pageSubEl = document.getElementById("pageSub");

        const scanPanel = document.getElementById("scanPanel");
        const scanBody = document.getElementById("scanBody");
        const scanToggleBtn = document.getElementById("scanToggleBtn");
        const scanImg = document.getElementById("scanPreviewImg");
        const zoomOutBtn = document.getElementById("zoomOutBtn");
        const zoomInBtn = document.getElementById("zoomInBtn");
        const zoomLevelLabel = document.getElementById("zoomLevelLabel");
        const rotateBtn = document.getElementById("rotateBtn");
        const openLightboxBtn = document.getElementById("openLightboxBtn");
        const rawMediaLink = document.getElementById("rawMediaLink");
        const pdfPager = document.getElementById("pdfPager");
        const prevPageBtn = document.getElementById("prevPageBtn");
        const nextPageBtn = document.getElementById("nextPageBtn");
        const pdfPageLabel = document.getElementById("pdfPageLabel");

        const lightboxModal = document.getElementById("lightboxModal");
        const lightboxImg = document.getElementById("lightboxImg");
        const modalZoomOutBtn = document.getElementById("modalZoomOutBtn");
        const modalZoomInBtn = document.getElementById("modalZoomInBtn");
        const modalZoomLabel = document.getElementById("modalZoomLabel");
        const modalRotateBtn = document.getElementById("modalRotateBtn");
        const closeLightboxBtn = document.getElementById("closeLightboxBtn");

        const asetDisplay = document.getElementById("asetDisplay");
        const wilayahSelect = document.getElementById("wilayahSelect");
        const vendorSelect = document.getElementById("vendorSelect");
        const mingguSelect = document.getElementById("mingguSelect");
        const slotIdPreview = document.getElementById("slotIdPreview");
        const xlsxArchiveLinkWrap = document.getElementById("xlsxArchiveLinkWrap");
        const rowsContainer = document.getElementById("rowsContainer");
        const rowCountLabel = document.getElementById("rowCountLabel");
        const summaryGrid = document.getElementById("summaryGrid");
        const addRowTopBtn = document.getElementById("addRowTopBtn");
        const addRowBtn = document.getElementById("addRowBtn");
        const saveBtn = document.getElementById("saveBtn");
        const dirtyIndicator = document.getElementById("dirtyIndicator");

        const state = {{
            data: null,
            rows: [],
            dirty: false,
            saving: false,
            zoom: 1,
            rotate: 0,
            page: 0,
            totalPages: 1,
            rowErrors: {{}},
            lastFocusedEl: null,
            modalZoom: 1,
            modalRotate: 0,
        }};

        function esc(str) {{
            return String(str == null ? "" : str)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }}

        function markDirty() {{
            state.dirty = true;
            dirtyIndicator.textContent = "Ada perubahan belum disimpan";
        }}

        window.addEventListener("beforeunload", function(e) {{
            if (state.dirty && !state.saving) {{
                e.preventDefault();
                e.returnValue = "";
            }}
        }});

        formEl.addEventListener("focusin", function(e) {{
            if (window.innerWidth < 960 && (e.target.tagName === "INPUT" || e.target.tagName === "SELECT")) {{
                setTimeout(function() {{
                    e.target.scrollIntoView({{ block: "center", behavior: "smooth" }});
                }}, 180);
            }}
        }});

        function computeBillingYYMM(dateStr) {{
            const parts = String(dateStr || "").split("-");
            if (parts.length !== 3) return "2601";
            let y = parseInt(parts[0], 10);
            let m = parseInt(parts[1], 10);
            const d = parseInt(parts[2], 10);
            if (!y || !m || !d) return "2601";
            if (d >= 26) {{
                m += 1;
                if (m > 12) {{ m = 1; y += 1; }}
            }}
            return String(y % 100).padStart(2, "0") + String(m).padStart(2, "0");
        }}

        function updateRosterWarning() {{
            if (!state.data) return;
            const aset = state.data.aset;
            const wil = wilayahSelect.value;
            const vend = vendorSelect.value;
            const roster = state.data.official_roster || [];
            const match = roster.some(function(item) {{
                return item[0] === aset && item[1] === vend && item[2] === wil;
            }});
            if (!match && vend && wil) {{
                const officialForSlot = roster.filter(function(item) {{
                    return item[0] === aset && item[2] === wil;
                }}).map(function(item) {{ return item[1]; }});
                const hint = officialForSlot.length
                    ? "Vendor resmi untuk " + aset + " " + wil + ": " + officialForSlot.join(", ") + "."
                    : "Kombinasi ini tidak tercantum pada roster 21 slot resmi.";
                rosterBanner.innerHTML = '<div class="banner-title">PERHATIAN: Roster Berbeda dari Daftar Resmi</div><p>' +
                    esc(aset + " / " + wil + " / " + vend + ". " + hint + " Anda tetap dapat menyimpan bila penugasan ini disetujui.") + '</p>';
                rosterBanner.classList.remove("hidden");
            }} else if ((state.data.warnings || []).length > 0 && !state.dirty) {{
                rosterBanner.innerHTML = '<div class="banner-title">PERHATIAN: Catatan Sistem</div><ul>' +
                    state.data.warnings.map(function(w) {{ return "<li>" + esc(w.replace(/\\*/g, "")) + "</li>"; }}).join("") +
                    "</ul>";
                rosterBanner.classList.remove("hidden");
            }} else {{
                rosterBanner.classList.add("hidden");
            }}
        }}

        function updateSlotPreview() {{
            if (!state.data) return;
            const firstDate = (state.rows[0] && state.rows[0].tanggal) || state.data.default_date || "";
            const yymm = computeBillingYYMM(firstDate);
            slotIdPreview.textContent = "XLS-" + yymm + "-" + state.data.aset + "-" + wilayahSelect.value + "-" + vendorSelect.value + "-" + mingguSelect.value;
            updateRosterWarning();
        }}

        function applyScanTransform() {{
            scanImg.style.transform = "scale(" + state.zoom + ") rotate(" + state.rotate + "deg)";
            zoomLevelLabel.textContent = Math.round(state.zoom * 100) + "%";
        }}

        function applyModalTransform() {{
            lightboxImg.style.transform = "scale(" + state.modalZoom + ") rotate(" + state.modalRotate + "deg)";
            modalZoomLabel.textContent = Math.round(state.modalZoom * 100) + "%";
        }}

        function loadMediaPage(pageNum) {{
            if (!state.data || !state.data.media_url) return;
            state.page = Math.max(0, pageNum);
            const url = state.data.media_url + "&page=" + state.page;
            fetch(url).then(function(resp) {{
                if (!resp.ok) throw new Error("Lampiran tidak dapat dimuat (HTTP " + resp.status + ")");
                const pagesHeader = parseInt(resp.headers.get("X-PDF-Pages") || "1", 10);
                if (!isNaN(pagesHeader) && pagesHeader >= 1) {{
                    state.totalPages = pagesHeader;
                }}
                return resp.blob();
            }}).then(function(blob) {{
                const objUrl = URL.createObjectURL(blob);
                scanImg.src = objUrl;
                lightboxImg.src = objUrl;
                if (state.totalPages > 1) {{
                    pdfPager.classList.remove("hidden");
                    pdfPageLabel.textContent = "Hal " + (state.page + 1) + " / " + state.totalPages;
                    prevPageBtn.disabled = state.page <= 0;
                    nextPageBtn.disabled = state.page >= state.totalPages - 1;
                }}
            }}).catch(function(err) {{
                scanImg.alt = err.message;
            }});
        }}

        function splitJalurLajur(jalurLajur) {{
            const txt = String(jalurLajur || "").trim();
            if (!txt || txt === "-") return ["", ""];
            const parts = txt.split(/\\s+/);
            return [parts[0] || "", parts.slice(1).join(" ")];
        }}

        function getBoqByKey(key) {{
            const opts = (state.data && state.data.boq_options) || [];
            return opts.find(function(o) {{ return o.item_key === key; }}) || null;
        }}

        function renderSummary() {{
            const totals = new Map();
            state.rows.forEach(function(r) {{
                const vol = parseFloat(r.volume);
                if (!r.item_key || isNaN(vol) || vol <= 0) return;
                const boq = getBoqByKey(r.item_key);
                const label = (boq ? boq.keyword : r.item_key) + " (" + r.item_key + ")";
                const sat = (boq && boq.satuan) || r.satuan || "";
                const mapKey = r.item_key + "::" + sat;
                if (!totals.has(mapKey)) {{
                    totals.set(mapKey, {{ label: label, sat: sat, vol: 0 }});
                }}
                totals.get(mapKey).vol += vol;
            }});

            if (totals.size === 0) {{
                summaryGrid.innerHTML = '<div class="topbar-sub">Belum ada volume valid untuk diringkas.</div>';
                return;
            }}
            const htmlParts = [];
            totals.forEach(function(item) {{
                const fmtVol = Number(item.vol.toFixed(4));
                htmlParts.push(
                    '<div class="summary-row">' +
                    '<span style="font-weight: 600;">' + esc(item.label) + '</span>' +
                    '<span class="mono" style="font-weight: 700;">' + esc(fmtVol + " " + item.sat) + '</span>' +
                    '</div>'
                );
            }});
            summaryGrid.innerHTML = htmlParts.join("");
        }}

        function calcDimVolume(row) {{
            const dims = [row.p, row.l, row.t, row.jml].map(function(v) {{
                if (v === "" || v == null) return null;
                const n = parseFloat(String(v).replace(",", "."));
                return isNaN(n) ? null : n;
            }}).filter(function(n) {{ return n !== null; }});
            if (dims.length === 0) return null;
            let prod = 1;
            dims.forEach(function(n) {{ prod *= n; }});
            return Number(prod.toFixed(4));
        }}

        function renderRows() {{
            rowCountLabel.textContent = String(state.rows.length);
            if (state.rows.length === 0) {{
                rowsContainer.innerHTML =
                    '<div class="panel" style="text-align: center; padding: 24px;">' +
                    '<p style="margin: 0 0 12px 0; color: var(--text-secondary);">Belum ada baris pekerjaan. Tambahkan minimal 1 baris untuk disimpan.</p>' +
                    '<button type="button" class="btn" id="emptyAddBtn">+ Tambah Baris Pertama</button>' +
                    '</div>';
                document.getElementById("emptyAddBtn").addEventListener("click", addNewRow);
                renderSummary();
                updateSlotPreview();
                return;
            }}

            const boqOpts = (state.data && state.data.boq_options) || [];
            rowsContainer.innerHTML = "";

            state.rows.forEach(function(row, idx) {{
                const card = document.createElement("div");
                const rowErr = state.rowErrors[idx];
                card.className = "row-card" + (rowErr ? " has-error" : "");
                card.dataset.index = String(idx);

                const [jalurVal, lajurVal] = row.jalur !== undefined ? [row.jalur, row.lajur || ""] : splitJalurLajur(row.jalur_lajur);
                row.jalur = jalurVal;
                row.lajur = lajurVal;

                const boqOptionsHtml = boqOpts.map(function(opt) {{
                    const sel = opt.item_key === row.item_key ? " selected" : "";
                    return '<option value="' + esc(opt.item_key) + '"' + sel + '>' +
                        esc(opt.keyword + " [" + opt.item_key + "] (" + opt.satuan + ")") +
                        '</option>';
                }}).join("");

                const hasAnyDim = [row.p, row.l, row.t, row.jml].some(function(v) {{ return v !== "" && v != null; }});
                const dimText = hasAnyDim
                    ? "Dimensi terisi (" + [row.p, row.l, row.t, row.jml].filter(function(v) {{ return v !== "" && v != null; }}).join(" x ") + ")"
                    : "Dimensi (P x L x T x Jml) - Opsional";
                const autoHint = row._autoCalc ? "Auto dari P x L x T x Jml" : "";
                const errHtml = rowErr
                    ? '<div class="banner banner-error" style="margin-bottom: 10px; padding: 8px 10px;" role="alert">' + esc(rowErr) + '</div>'
                    : "";

                card.innerHTML =
                    '<div class="row-card-top">' +
                        '<div class="row-card-title">' +
                            '<span class="mono">Baris #' + (idx + 1) + '</span>' +
                            (row.handwritten_edited ? '<span class="tag tag-warn">Revisi Tangan OCR</span>' : '') +
                        '</div>' +
                        '<div class="row-card-actions">' +
                            '<button type="button" class="btn btn-sm dup-row-btn" aria-label="Duplikat baris ' + (idx + 1) + '">Duplikat</button>' +
                            '<button type="button" class="btn btn-sm btn-danger del-row-btn" aria-label="Hapus baris ' + (idx + 1) + '">Hapus</button>' +
                        '</div>' +
                    '</div>' +
                    errHtml +
                    '<div class="row-fields">' +
                        '<div class="f-tanggal">' +
                            '<label class="field-label" for="tgl_' + idx + '">Tanggal</label>' +
                            '<input id="tgl_' + idx + '" class="input input-mono" type="date" value="' + esc(row.tanggal || "") + '" data-field="tanggal" />' +
                        '</div>' +
                        '<div class="f-kode">' +
                            '<label class="field-label" for="kode_' + idx + '">Kode Temuan</label>' +
                            '<input id="kode_' + idx + '" class="input input-mono" type="text" placeholder="Contoh: 181126PV001" value="' + esc(row.kode_temuan === "-" ? "" : (row.kode_temuan || "")) + '" data-field="kode_temuan" />' +
                        '</div>' +
                        '<div class="f-lokasi">' +
                            '<label class="field-label" for="loc_' + idx + '">STA / KM</label>' +
                            '<input id="loc_' + idx + '" class="input" type="text" placeholder="KM 45+200" value="' + esc(row.lokasi || "") + '" data-field="lokasi" />' +
                        '</div>' +
                        '<div class="f-jalur">' +
                            '<label class="field-label" for="jal_' + idx + '">Jalur</label>' +
                            '<input id="jal_' + idx + '" class="input" type="text" placeholder="A / B" value="' + esc(row.jalur || "") + '" data-field="jalur" />' +
                        '</div>' +
                        '<div class="f-lajur">' +
                            '<label class="field-label" for="laj_' + idx + '">Lajur</label>' +
                            '<input id="laj_' + idx + '" class="input" type="text" placeholder="L1 / Bahu" value="' + esc(row.lajur || "") + '" data-field="lajur" />' +
                        '</div>' +
                        '<div class="f-boq">' +
                            '<label class="field-label" for="boq_' + idx + '">Item Pekerjaan (BOQ)</label>' +
                            '<select id="boq_' + idx + '" class="select" data-field="item_key">' + boqOptionsHtml + '</select>' +
                        '</div>' +
                        '<div class="dims-wrap' + (hasAnyDim ? ' is-open' : '') + '">' +
                            '<button type="button" class="dims-toggle" aria-expanded="' + (hasAnyDim ? 'true' : 'false') + '">' +
                                '<span>' + esc(dimText) + '</span><span>Ubah</span>' +
                            '</button>' +
                            '<div class="dims-grid">' +
                                '<div class="f-dim"><label class="field-label" for="p_' + idx + '">P</label><input id="p_' + idx + '" class="input input-mono" type="number" step="any" inputmode="decimal" value="' + esc(row.p == null ? "" : row.p) + '" data-field="p" /></div>' +
                                '<div class="f-dim"><label class="field-label" for="l_' + idx + '">L</label><input id="l_' + idx + '" class="input input-mono" type="number" step="any" inputmode="decimal" value="' + esc(row.l == null ? "" : row.l) + '" data-field="l" /></div>' +
                                '<div class="f-dim"><label class="field-label" for="t_' + idx + '">T</label><input id="t_' + idx + '" class="input input-mono" type="number" step="any" inputmode="decimal" value="' + esc(row.t == null ? "" : row.t) + '" data-field="t" /></div>' +
                                '<div class="f-dim"><label class="field-label" for="jml_' + idx + '">Jml</label><input id="jml_' + idx + '" class="input input-mono" type="number" step="any" inputmode="decimal" value="' + esc(row.jml == null ? "" : row.jml) + '" data-field="jml" /></div>' +
                            '</div>' +
                        '</div>' +
                        '<div class="f-vol">' +
                            '<label class="field-label" for="vol_' + idx + '">Vol. Opname</label>' +
                            '<div class="vol-row-group">' +
                                '<input id="vol_' + idx + '" class="input input-mono" type="number" step="any" min="0" inputmode="decimal" value="' + esc(row.volume == null ? "" : row.volume) + '" data-field="volume" />' +
                                '<span class="unit-pill" id="unit_' + idx + '">' + esc(row.satuan || "-") + '</span>' +
                            '</div>' +
                            '<div class="calc-hint" id="hint_' + idx + '">' + esc(autoHint) + '</div>' +
                        '</div>' +
                        '<div class="f-ket">' +
                            '<label class="field-label" for="ket_' + idx + '">Keterangan</label>' +
                            '<input id="ket_' + idx + '" class="input" type="text" placeholder="Catatan lapangan (opsional)" value="' + esc(row.keterangan || "") + '" data-field="keterangan" />' +
                        '</div>' +
                    '</div>';

                card.querySelector(".dup-row-btn").addEventListener("click", function() {{
                    const copy = Object.assign({{}}, row, {{ handwritten_edited: false }});
                    state.rows.splice(idx + 1, 0, copy);
                    state.rowErrors = {{}};
                    markDirty();
                    renderRows();
                }});

                card.querySelector(".del-row-btn").addEventListener("click", function() {{
                    state.rows.splice(idx, 1);
                    state.rowErrors = {{}};
                    markDirty();
                    renderRows();
                }});

                const dimToggleBtn = card.querySelector(".dims-toggle");
                const dimsWrapEl = card.querySelector(".dims-wrap");
                dimToggleBtn.addEventListener("click", function() {{
                    const open = dimsWrapEl.classList.toggle("is-open");
                    dimToggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
                }});

                card.querySelectorAll("[data-field]").forEach(function(el) {{
                    const field = el.dataset.field;
                    el.addEventListener("input", function() {{
                        state.rowErrors = {{}};
                        card.classList.remove("has-error");
                        markDirty();
                        if (field === "p" || field === "l" || field === "t" || field === "jml") {{
                            row[field] = el.value === "" ? null : el.value;
                            const computed = calcDimVolume(row);
                            if (computed !== null && computed > 0) {{
                                row.volume = computed;
                                row._autoCalc = true;
                                card.querySelector("#vol_" + idx).value = String(computed);
                                card.querySelector("#hint_" + idx).textContent = "Auto dari P x L x T x Jml";
                            }}
                        }} else if (field === "volume") {{
                            row.volume = el.value === "" ? null : el.value;
                            row._autoCalc = false;
                            card.querySelector("#hint_" + idx).textContent = "";
                        }} else if (field === "tanggal") {{
                            row.tanggal = el.value;
                            updateSlotPreview();
                        }} else {{
                            row[field] = el.value;
                        }}
                        renderSummary();
                    }});

                    if (field === "item_key") {{
                        el.addEventListener("change", function() {{
                            row.item_key = el.value;
                            const chosen = getBoqByKey(el.value);
                            if (chosen) {{
                                row.keyword = chosen.keyword;
                                row.uraian = chosen.uraian;
                                row.satuan = chosen.satuan;
                                card.querySelector("#unit_" + idx).textContent = chosen.satuan;
                            }}
                            markDirty();
                            renderSummary();
                        }});
                    }}
                }});

                rowsContainer.appendChild(card);
            }});

            renderSummary();
            updateSlotPreview();
        }}

        function addNewRow() {{
            const last = state.rows[state.rows.length - 1] || {{}};
            const firstBoq = (state.data && state.data.boq_options && state.data.boq_options[0]) || {{}};
            state.rows.push({{
                tanggal: last.tanggal || (state.data && state.data.default_date) || "",
                kode_temuan: "",
                lokasi: last.lokasi || "",
                jalur: last.jalur || "",
                lajur: last.lajur || "",
                item_key: last.item_key || firstBoq.item_key || "",
                keyword: last.keyword || firstBoq.keyword || "",
                uraian: last.uraian || firstBoq.uraian || "",
                satuan: last.satuan || firstBoq.satuan || "",
                p: null,
                l: null,
                t: null,
                jml: null,
                volume: null,
                keterangan: "",
                _autoCalc: false,
            }});
            markDirty();
            renderRows();
        }}

        function populatePage(data) {{
            state.data = data;
            state.rows = (data.entries || []).map(function(e) {{
                const [jal, laj] = splitJalurLajur(e.jalur_lajur);
                return Object.assign({{}}, e, {{ jalur: jal, lajur: laj, _autoCalc: false }});
            }});
            state.dirty = false;
            state.rowErrors = {{}};

            const isPending = data.record_type === "PENDING";
            pageSubEl.textContent = isPending
                ? "Periksa hasil pembacaan sebelum menyimpan ke DATA_UNTUK_VOL"
                : "Edit slot tersimpan dan perbarui baris DATA_UNTUK_VOL secara otomatis";

            const statusLabel = data.status === "CONFIRMED" || data.status === "ACTIVE"
                ? '<span class="tag tag-success">TERSIMPAN</span>'
                : '<span class="tag tag-warn">MENUNGGU KONFIRMASI</span>';
            topMetaTags.innerHTML =
                '<span class="tag">' + esc(data.aset + " - " + data.aset_title) + '</span>' +
                statusLabel;

            asetDisplay.value = data.aset + " - " + data.aset_title;
            wilayahSelect.value = data.wilayah || "W1";
            mingguSelect.value = data.minggu || "M1";

            const vendors = Array.from(new Set([].concat(data.vendor_options || [], [data.vendor || ""]).filter(Boolean)));
            vendorSelect.innerHTML = vendors.map(function(v) {{
                return '<option value="' + esc(v) + '"' + (v === data.vendor ? " selected" : "") + '>' + esc(v) + '</option>';
            }}).join("");

            if (data.xlsx_web_url) {{
                xlsxArchiveLinkWrap.innerHTML = '<a class="btn btn-sm" href="' + esc(data.xlsx_web_url) + '" target="_blank" rel="noopener">Buka Arsip Excel</a>';
            }} else {{
                xlsxArchiveLinkWrap.innerHTML = "";
            }}

            if (data.has_media && data.media_url) {{
                workspaceGrid.classList.remove("no-media");
                workspaceGrid.classList.add("has-media");
                scanPanel.classList.remove("hidden");
                rawMediaLink.href = data.media_url + "&raw=1";
                loadMediaPage(0);
            }} else {{
                workspaceGrid.classList.remove("has-media");
                workspaceGrid.classList.add("no-media");
                scanPanel.classList.add("hidden");
            }}

            renderRows();
            dirtyIndicator.textContent = "Data siap diperiksa";
            loadingEl.classList.add("hidden");
            errorEl.classList.add("hidden");
            formEl.classList.remove("hidden");
        }}

        function fetchRecord() {{
            loadingEl.classList.remove("hidden");
            errorEl.classList.add("hidden");
            formEl.classList.add("hidden");

            fetch("/api/opname/review/" + encodeURIComponent(RECORD_ID) + "?token=" + encodeURIComponent(TOKEN))
                .then(function(resp) {{
                    return resp.json().then(function(body) {{
                        if (!resp.ok) {{
                            throw new Error(body.detail || ("Server mengembalikan status " + resp.status));
                        }}
                        return body;
                    }});
                }})
                .then(populatePage)
                .catch(function(err) {{
                    loadingEl.classList.add("hidden");
                    errorMsgEl.textContent = err.message || "Gagal memuat data opname.";
                    errorEl.classList.remove("hidden");
                }});
        }}

        function showBanner(type, title, lines) {{
            statusBanner.className = "banner " + (type === "success" ? "banner-success" : (type === "warn" ? "banner-warn" : "banner-error"));
            const itemsHtml = lines && lines.length
                ? "<ul>" + lines.map(function(l) {{ return "<li>" + esc(l) + "</li>"; }}).join("") + "</ul>"
                : "";
            statusBanner.innerHTML = '<div class="banner-title">' + esc(title) + '</div>' + itemsHtml;
            statusBanner.classList.remove("hidden");
            statusBanner.scrollIntoView({{ block: "nearest", behavior: "smooth" }});
        }}

        formEl.addEventListener("submit", function(e) {{
            e.preventDefault();
            if (state.saving) return;

            statusBanner.classList.add("hidden");
            state.rowErrors = {{}};

            if (state.rows.length === 0) {{
                showBanner("error", "ERROR: Belum Ada Baris Pekerjaan", ["Tambahkan minimal 1 baris pekerjaan sebelum menyimpan."]);
                return;
            }}

            state.saving = true;
            saveBtn.disabled = true;
            saveBtn.textContent = "Menyimpan ke OneDrive...";

            const payload = {{
                aset: state.data.aset,
                wilayah: wilayahSelect.value,
                vendor: vendorSelect.value,
                minggu: mingguSelect.value,
                entries: state.rows.map(function(r) {{
                    return {{
                        tanggal: r.tanggal || "",
                        kode_temuan: r.kode_temuan || "-",
                        lokasi: r.lokasi || "",
                        jalur: r.jalur || "",
                        lajur: r.lajur || "",
                        item_key: r.item_key || "",
                        p: r.p === "" || r.p == null ? null : Number(String(r.p).replace(",", ".")),
                        l: r.l === "" || r.l == null ? null : Number(String(r.l).replace(",", ".")),
                        t: r.t === "" || r.t == null ? null : Number(String(r.t).replace(",", ".")),
                        jml: r.jml === "" || r.jml == null ? null : Number(String(r.jml).replace(",", ".")),
                        vol_vendor: r.vol_vendor == null ? null : Number(r.vol_vendor),
                        volume: r.volume === "" || r.volume == null ? 0 : Number(String(r.volume).replace(",", ".")),
                        material_status: r.material_status || "",
                        keterangan: r.keterangan || "",
                    }};
                }}),
            }};

            fetch("/api/opname/review/" + encodeURIComponent(RECORD_ID) + "/save?token=" + encodeURIComponent(TOKEN), {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify(payload),
            }})
            .then(function(resp) {{
                return resp.json().then(function(body) {{
                    return {{ status: resp.status, ok: resp.ok, body: body }};
                }});
            }})
            .then(function(res) {{
                if (!res.ok) {{
                    const errList = (res.body && res.body.errors) || [];
                    const msgLines = [];
                    errList.forEach(function(it) {{
                        const msg = "Baris " + it.row + ": " + it.message;
                        msgLines.push(msg);
                        if (typeof it.row === "number" && it.row >= 1) {{
                            state.rowErrors[it.row - 1] = it.message;
                        }}
                    }});
                    if (msgLines.length === 0) {{
                        msgLines.push((res.body && res.body.detail) || "Terjadi kesalahan validasi saat menyimpan.");
                    }}
                    renderRows();
                    showBanner("error", "ERROR: Simpan Dibatalkan, Perbaiki Baris Berikut", msgLines);
                    return;
                }}

                state.dirty = false;
                dirtyIndicator.textContent = "Tersimpan ke DATA_UNTUK_VOL";
                const b = res.body;
                const slotIds = (b.results || []).map(function(s) {{ return s.slot_id + " (" + s.appended + " baris)"; }});
                const infoLines = ["Slot diperbarui: " + slotIds.join(", ")];
                if (b.whatsapp_notified) {{
                    infoLines.push("Notifikasi konfirmasi telah dikirim ke WhatsApp.");
                }}
                if (b.xlsx_url) {{
                    xlsxArchiveLinkWrap.innerHTML = '<a class="btn btn-sm" href="' + esc(b.xlsx_url) + '" target="_blank" rel="noopener">Buka Arsip Excel Baru</a>';
                }}
                showBanner("success", "OK: Data Berhasil Disimpan ke DATA_UNTUK_VOL", infoLines);

                const firstUrl = (b.slot_urls && Object.values(b.slot_urls)[0]) || "";
                if (b.results && b.results.length === 1 && b.results[0].slot_id !== RECORD_ID && firstUrl) {{
                    statusBanner.innerHTML += '<p style="margin-top: 8px;"><a class="btn btn-sm" href="' + esc(firstUrl) + '">Buka Halaman Edit Slot ' + esc(b.results[0].slot_id) + '</a></p>';
                }}
            }})
            .catch(function(err) {{
                showBanner("error", "ERROR: Gagal Menghubungi Server", [err.message || "Periksa koneksi internet lalu tekan Simpan ulang."]);
            }})
            .finally(function() {{
                state.saving = false;
                saveBtn.disabled = false;
                saveBtn.textContent = "Simpan ke DATA UNTUK VOL";
            }});
        }});

        wilayahSelect.addEventListener("change", function() {{ markDirty(); updateSlotPreview(); }});
        vendorSelect.addEventListener("change", function() {{ markDirty(); updateSlotPreview(); }});
        mingguSelect.addEventListener("change", function() {{ markDirty(); updateSlotPreview(); }});
        addRowTopBtn.addEventListener("click", addNewRow);
        addRowBtn.addEventListener("click", addNewRow);
        retryBtn.addEventListener("click", fetchRecord);

        scanToggleBtn.addEventListener("click", function() {{
            const collapsed = scanBody.classList.toggle("is-collapsed");
            scanToggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
            scanToggleBtn.textContent = collapsed ? "Tampilkan Scan" : "Sembunyikan Scan";
        }});

        zoomOutBtn.addEventListener("click", function() {{
            state.zoom = Math.max(0.75, Number((state.zoom - 0.25).toFixed(2)));
            applyScanTransform();
        }});
        zoomInBtn.addEventListener("click", function() {{
            state.zoom = Math.min(2.5, Number((state.zoom + 0.25).toFixed(2)));
            applyScanTransform();
        }});
        rotateBtn.addEventListener("click", function() {{
            state.rotate = (state.rotate + 90) % 360;
            applyScanTransform();
        }});
        prevPageBtn.addEventListener("click", function() {{ loadMediaPage(state.page - 1); }});
        nextPageBtn.addEventListener("click", function() {{ loadMediaPage(state.page + 1); }});

        function openLightbox() {{
            state.lastFocusedEl = document.activeElement;
            state.modalZoom = state.zoom;
            state.modalRotate = state.rotate;
            applyModalTransform();
            lightboxModal.classList.remove("hidden");
            closeLightboxBtn.focus();
        }}

        function closeLightbox() {{
            lightboxModal.classList.add("hidden");
            if (state.lastFocusedEl && typeof state.lastFocusedEl.focus === "function") {{
                state.lastFocusedEl.focus();
            }}
        }}

        openLightboxBtn.addEventListener("click", openLightbox);
        scanImg.addEventListener("click", openLightbox);
        closeLightboxBtn.addEventListener("click", closeLightbox);
        lightboxModal.addEventListener("click", function(e) {{
            if (e.target === lightboxModal) closeLightbox();
        }});
        document.addEventListener("keydown", function(e) {{
            if (e.key === "Escape" && !lightboxModal.classList.contains("hidden")) {{
                closeLightbox();
            }}
        }});
        modalZoomOutBtn.addEventListener("click", function() {{
            state.modalZoom = Math.max(0.75, Number((state.modalZoom - 0.25).toFixed(2)));
            applyModalTransform();
        }});
        modalZoomInBtn.addEventListener("click", function() {{
            state.modalZoom = Math.min(3.0, Number((state.modalZoom + 0.25).toFixed(2)));
            applyModalTransform();
        }});
        modalRotateBtn.addEventListener("click", function() {{
            state.modalRotate = (state.modalRotate + 90) % 360;
            applyModalTransform();
        }});

        fetchRecord();
    }})();
    </script>
</body>
</html>"""


def render_opname_list_page_html(token: str) -> str:
    js_token = _js_safe(token)
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daftar Slot &amp; Review Opname - AIS-VISTA</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
{_BASE_CSS}

main.list-main {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 16px 16px 48px 16px;
}}

.toolbar-panel {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
    align-items: end;
    margin-bottom: 16px;
}}

.toolbar-panel > *, .slot-cards > * {{
    min-width: 0;
}}

.roster-strip {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 18px;
}}

.section-title {{
    margin: 20px 0 10px 0;
    font-size: 1.05rem;
    font-weight: 700;
}}

.slot-cards {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
}}

.slot-card {{
    background-color: var(--bg-surface);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-panel);
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}}

.slot-card-head {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}}

.slot-meta {{
    font-size: 0.9rem;
    color: var(--text-secondary);
}}

.slot-actions {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}}

.desktop-table-wrap {{
    display: none;
}}

@media (min-width: 960px) {{
    main.list-main {{
        padding: 20px 24px 60px 24px;
    }}

    .toolbar-panel {{
        grid-template-columns: 200px 240px 1fr auto;
    }}

    .mobile-slots-only {{
        display: none;
    }}

    .desktop-table-wrap {{
        display: block;
        background-color: var(--bg-surface);
        border: 1px solid var(--border-divider);
        border-radius: var(--radius-panel);
        overflow-x: auto;
    }}

    table.slots-table {{
        width: 100%;
        border-collapse: collapse;
        text-align: left;
        font-size: 0.9375rem;
    }}

    table.slots-table th {{
        background-color: var(--bg-subtle);
        padding: 12px 14px;
        font-size: 0.8125rem;
        font-weight: 700;
        color: var(--text-secondary);
        border-bottom: 1px solid var(--border-divider);
    }}

    table.slots-table td {{
        padding: 12px 14px;
        border-bottom: 1px solid var(--border-divider);
        vertical-align: middle;
    }}

    table.slots-table tr:last-child td {{
        border-bottom: 0;
    }}
}}
    </style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-inner">
            <div class="topbar-left">
                <a class="btn btn-sm" href="/">&larr; Konsol Utama</a>
                <div class="topbar-title-group">
                    <h1>Daftar Slot &amp; Review Opname</h1>
                    <div class="topbar-sub">Buka ulang slot tersimpan atau periksa hasil scan sebelum masuk ke Excel</div>
                </div>
            </div>
        </div>
    </header>

    <main class="list-main">
        <section class="panel toolbar-panel" aria-label="Filter Data Opname">
            <div>
                <label class="field-label" for="cycleSelect">Siklus Tagihan</label>
                <select id="cycleSelect" class="select"></select>
            </div>
            <div>
                <label class="field-label" for="asetSelect">Aset Pekerjaan</label>
                <select id="asetSelect" class="select">
                    <option value="">Semua Aset</option>
                    <option value="PV">PV - Pavement</option>
                    <option value="DR">DR - Drainase</option>
                    <option value="FE">FE - Pagar ROW</option>
                    <option value="GR">GR - Guardrail</option>
                    <option value="SG">SG - Rambu &amp; Delineator</option>
                    <option value="LC">LC - Landscape</option>
                    <option value="RM">RM - Rumput &amp; Ketrik</option>
                    <option value="CA">CA - TRC &amp; Pembersihan</option>
                    <option value="WR">WR - Wire Rope</option>
                </select>
            </div>
            <div class="roster-strip" style="margin-bottom: 0;">
                <span class="tag mono" id="rosterProgressTag">Roster Terisi: 0 / 21 slot</span>
            </div>
            <div>
                <button type="button" class="btn" id="refreshBtn">Muat Ulang</button>
            </div>
        </section>

        <div id="listLoading" class="state-box" role="status" aria-live="polite">
            <h2>Memuat Daftar Opname</h2>
            <p>Mengambil daftar scan menunggu konfirmasi dan slot tersimpan...</p>
        </div>

        <div id="listError" class="state-box banner-error hidden" role="alert">
            <h2>ERROR: Gagal Memuat Daftar Slot</h2>
            <p id="listErrorMsg" style="color: var(--err-text);">Tidak dapat terhubung ke server.</p>
            <button type="button" class="btn" id="listRetryBtn">Coba Lagi</button>
        </div>

        <div id="listContent" class="hidden">
            <h2 class="section-title">Menunggu Review (Scan / Konfirmasi)</h2>
            <div id="pendingContainer" class="slot-cards"></div>

            <h2 class="section-title">Slot Tersimpan (DATA_UNTUK_VOL)</h2>
            <div id="slotsMobileContainer" class="slot-cards mobile-slots-only"></div>
            <div class="desktop-table-wrap" id="slotsTableWrap">
                <table class="slots-table">
                    <thead>
                        <tr>
                            <th>Slot ID</th>
                            <th>Aset</th>
                            <th>Wilayah</th>
                            <th>Vendor</th>
                            <th>Minggu</th>
                            <th>Baris</th>
                            <th>Diperbarui</th>
                            <th>Aksi</th>
                        </tr>
                    </thead>
                    <tbody id="slotsTableBody"></tbody>
                </table>
            </div>
            <div id="slotsEmptyBox" class="panel hidden" style="text-align: center; padding: 24px;">
                <p style="margin: 0; color: var(--text-secondary);">Belum ada slot opname tersimpan pada siklus dan filter ini. Kirim form Excel atau Scan Opname melalui WhatsApp untuk mencatat slot baru.</p>
            </div>
        </div>
    </main>

    <script>
    (function() {{
        const TOKEN = {js_token};
        const cycleSelect = document.getElementById("cycleSelect");
        const asetSelect = document.getElementById("asetSelect");
        const refreshBtn = document.getElementById("refreshBtn");
        const rosterProgressTag = document.getElementById("rosterProgressTag");
        const listLoading = document.getElementById("listLoading");
        const listError = document.getElementById("listError");
        const listErrorMsg = document.getElementById("listErrorMsg");
        const listRetryBtn = document.getElementById("listRetryBtn");
        const listContent = document.getElementById("listContent");
        const pendingContainer = document.getElementById("pendingContainer");
        const slotsMobileContainer = document.getElementById("slotsMobileContainer");
        const slotsTableWrap = document.getElementById("slotsTableWrap");
        const slotsTableBody = document.getElementById("slotsTableBody");
        const slotsEmptyBox = document.getElementById("slotsEmptyBox");

        function esc(str) {{
            return String(str == null ? "" : str)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }}

        function loadList(selectedCycle) {{
            listLoading.classList.remove("hidden");
            listError.classList.add("hidden");
            listContent.classList.add("hidden");

            const params = new URLSearchParams({{ token: TOKEN }});
            if (selectedCycle) params.set("cycle", selectedCycle);
            if (asetSelect.value) params.set("aset", asetSelect.value);

            fetch("/api/opname/slots?" + params.toString())
                .then(function(resp) {{
                    return resp.json().then(function(body) {{
                        if (!resp.ok) throw new Error(body.detail || ("Status " + resp.status));
                        return body;
                    }});
                }})
                .then(function(data) {{
                    const cycles = data.cycles || [];
                    if (cycles.length > 0) {{
                        cycleSelect.innerHTML = cycles.map(function(c) {{
                            return '<option value="' + esc(c) + '"' + (c === data.active_cycle ? " selected" : "") + '>' + esc(c) + '</option>';
                        }}).join("");
                    }}

                    const prog = data.roster_progress || {{ done: 0, total: 21 }};
                    rosterProgressTag.textContent = "Roster Terisi (" + (data.active_cycle || "-") + "): " + prog.done + " / " + prog.total + " slot";

                    const pending = data.pending || [];
                    if (pending.length === 0) {{
                        pendingContainer.innerHTML =
                            '<div class="panel"><p style="margin: 0; color: var(--text-secondary);">Tidak ada scan atau konfirmasi yang menunggu review. Kirim foto atau PDF form dengan caption Scan Opname di WhatsApp untuk memulai.</p></div>';
                    }} else {{
                        pendingContainer.innerHTML = pending.map(function(p) {{
                            return '<div class="slot-card">' +
                                '<div class="slot-card-head">' +
                                    '<strong class="mono">' + esc(p.pending_id) + '</strong>' +
                                    '<span class="tag tag-warn">MENUNGGU REVIEW</span>' +
                                '</div>' +
                                '<div class="slot-meta">' + esc(p.aset + " | " + (p.wilayah || "-") + " | " + (p.vendor || "-") + " | " + (p.minggu || "-") + " | " + p.row_count + " baris | " + p.created_at) + '</div>' +
                                '<div class="slot-actions">' +
                                    '<a class="btn btn-primary" href="' + esc(p.review_url) + '">Review &amp; Edit</a>' +
                                '</div>' +
                            '</div>';
                        }}).join("");
                    }}

                    const slots = data.slots || [];
                    if (slots.length === 0) {{
                        slotsMobileContainer.innerHTML = "";
                        slotsTableBody.innerHTML = "";
                        slotsTableWrap.classList.add("hidden");
                        slotsEmptyBox.classList.remove("hidden");
                    }} else {{
                        slotsEmptyBox.classList.add("hidden");
                        slotsTableWrap.classList.remove("hidden");

                        slotsMobileContainer.innerHTML = slots.map(function(s) {{
                            const xlsBtn = s.xlsx_web_url
                                ? '<a class="btn" href="' + esc(s.xlsx_web_url) + '" target="_blank" rel="noopener">Excel Arsip</a>'
                                : '';
                            return '<div class="slot-card">' +
                                '<div class="slot-card-head">' +
                                    '<strong class="mono">' + esc(s.slot_id) + '</strong>' +
                                    '<span class="tag tag-success">TERSIMPAN</span>' +
                                '</div>' +
                                '<div class="slot-meta">' + esc(s.aset + " | " + s.wilayah + " | " + s.vendor + " | " + s.minggu + " | " + s.row_count + " baris") + '</div>' +
                                '<div class="slot-meta">Diperbarui: ' + esc(s.updated_at || "-") + '</div>' +
                                '<div class="slot-actions">' +
                                    '<a class="btn" href="' + esc(s.review_url) + '">Edit Slot</a>' +
                                    xlsBtn +
                                '</div>' +
                            '</div>';
                        }}).join("");

                        slotsTableBody.innerHTML = slots.map(function(s) {{
                            const xlsLink = s.xlsx_web_url
                                ? '<a class="btn btn-sm" href="' + esc(s.xlsx_web_url) + '" target="_blank" rel="noopener">Excel</a>'
                                : '';
                            return '<tr>' +
                                '<td class="mono" style="font-weight: 600;">' + esc(s.slot_id) + '</td>' +
                                '<td>' + esc(s.aset) + '</td>' +
                                '<td>' + esc(s.wilayah) + '</td>' +
                                '<td>' + esc(s.vendor) + '</td>' +
                                '<td>' + esc(s.minggu) + '</td>' +
                                '<td class="mono">' + esc(s.row_count) + '</td>' +
                                '<td class="mono">' + esc(s.updated_at || "-") + '</td>' +
                                '<td><div style="display: flex; gap: 8px;"><a class="btn btn-sm" href="' + esc(s.review_url) + '">Edit</a>' + xlsLink + '</div></td>' +
                            '</tr>';
                        }}).join("");
                    }}

                    listLoading.classList.add("hidden");
                    listContent.classList.remove("hidden");
                }})
                .catch(function(err) {{
                    listLoading.classList.add("hidden");
                    listErrorMsg.textContent = err.message || "Gagal memuat daftar slot opname.";
                    listError.classList.remove("hidden");
                }});
        }}

        cycleSelect.addEventListener("change", function() {{ loadList(cycleSelect.value); }});
        asetSelect.addEventListener("change", function() {{ loadList(cycleSelect.value); }});
        refreshBtn.addEventListener("click", function() {{ loadList(cycleSelect.value); }});
        listRetryBtn.addEventListener("click", function() {{ loadList(cycleSelect.value); }});

        loadList("");
    }})();
    </script>
</body>
</html>"""


def _safe_action_link(url: str, label: str, empty_label: str, btn_class: str = "btn") -> str:
    clean_url = (url or "").strip()
    if not clean_url or clean_url == "#":
        return f'<button type="button" class="{btn_class}" disabled>{html.escape(empty_label)}</button>'
    is_external = clean_url.startswith(("http://", "https://"))
    extra = ' target="_blank" rel="noopener"' if is_external else ""
    return f'<a class="{btn_class}" href="{html.escape(clean_url)}"{extra}>{html.escape(label)}</a>'


def render_console_page_html(
    waha_url: str,
    logs_url: str,
    guide_url: str,
    opname_editor_url: str,
    sla_excel_url: str,
    opname_excel_url: str,
    opname_cycle_label: str,
    stats: dict[str, object],
) -> str:
    cycle_key = html.escape(str(stats.get("cycle_key") or "-"))
    pending_count = int(stats.get("pending_count") or 0)
    roster_done = int(stats.get("roster_done") or 0)
    roster_total = max(1, int(stats.get("roster_total") or 21))
    sla_today_count = int(stats.get("sla_today_count") or 0)
    roster_pct = min(100, max(0, round((roster_done / roster_total) * 100)))

    safe_editor_url = html.escape(opname_editor_url)
    safe_guide_url = html.escape(guide_url)
    safe_logs_url = html.escape(logs_url)
    safe_cycle_lbl = html.escape(opname_cycle_label or "siklus berjalan")

    pending_action = (
        f'<a class="btn btn-sm btn-primary" href="{safe_editor_url}">Review Sekarang</a>'
        if pending_count > 0
        else '<span class="topbar-sub">Semua form scan telah diproses.</span>'
    )
    pending_tag = (
        f'<span class="tag tag-warn mono">{pending_count} form menunggu</span>'
        if pending_count > 0
        else '<span class="tag tag-success mono">0 form menunggu</span>'
    )

    hero_excel_cta = _safe_action_link(
        opname_excel_url, "Buka Excel Opname", "Excel Opname Belum Diatur", "btn"
    )
    row_opname_excel = _safe_action_link(
        opname_excel_url, "Buka Workbook", "Belum Diatur", "btn btn-sm"
    )
    row_sla_excel = _safe_action_link(
        sla_excel_url, "Buka Spreadsheet", "Belum Diatur", "btn btn-sm"
    )
    row_waha_btn = _safe_action_link(
        waha_url, "Buka WAHA", "WAHA Belum Diatur", "btn btn-sm"
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Konsol Operasional - AIS-VISTA</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
{_BASE_CSS}

.console-nav {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
}}

main.console-main {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 20px 16px 48px 16px;
}}

.hero-grid {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
    margin-bottom: 24px;
}}

.hero-grid > * {{
    min-width: 0;
}}

.hero-copy {{
    padding: 24px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 18px;
}}

.hero-eyebrow {{
    font-size: 0.875rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 8px;
}}

.hero-title {{
    margin: 0 0 10px 0;
    font-size: 1.65rem;
    line-height: 1.25;
    font-weight: 700;
    color: var(--text-primary);
}}

.hero-desc {{
    margin: 0;
    font-size: 1rem;
    color: var(--text-secondary);
    max-width: 60ch;
}}

.hero-actions {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}}

.status-panel {{
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 14px;
}}

.status-panel h2 {{
    margin: 0;
    font-size: 1rem;
    font-weight: 700;
}}

.metric-item {{
    padding-top: 12px;
    border-top: 1px solid var(--border-divider);
    display: flex;
    flex-direction: column;
    gap: 8px;
}}

.metric-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}}

.metric-label {{
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-secondary);
}}

.metric-value {{
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
}}

.progress-track {{
    width: 100%;
    height: 10px;
    border-radius: 4px;
    background-color: var(--bg-subtle);
    border: 1px solid var(--border-control);
    overflow: hidden;
}}

.progress-fill {{
    height: 100%;
    background-color: var(--accent);
}}

.ops-grid {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
    align-items: start;
}}

.ops-grid > * {{
    min-width: 0;
}}

.section-heading {{
    margin: 0 0 10px 0;
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
}}

.work-list {{
    background-color: var(--bg-surface);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-panel);
}}

.work-row {{
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-bottom: 1px solid var(--border-divider);
}}

.work-row:last-child {{
    border-bottom: 0;
}}

.work-row-info h3 {{
    margin: 0 0 4px 0;
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
}}

.work-row-info p {{
    margin: 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
}}

.util-list {{
    background-color: var(--bg-surface);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-panel);
}}

.util-row {{
    padding: 14px 16px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border-bottom: 1px solid var(--border-divider);
}}

.util-row:last-child {{
    border-bottom: 0;
}}

.util-row-text {{
    flex: 1 1 200px;
    min-width: 0;
}}

.util-row .btn {{
    flex-shrink: 0;
}}

.util-row-text strong {{
    display: block;
    font-size: 0.95rem;
    color: var(--text-primary);
}}

.util-row-text span {{
    display: block;
    font-size: 0.85rem;
    color: var(--text-secondary);
}}

.console-footer {{
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid var(--border-divider);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 8px;
    font-size: 0.875rem;
    color: var(--text-secondary);
}}

@media (min-width: 960px) {{
    main.console-main {{
        padding: 28px 24px 60px 24px;
    }}

    .hero-grid {{
        grid-template-columns: minmax(0, 1.35fr) minmax(0, 0.9fr);
        gap: 24px;
    }}

    .hero-copy {{
        padding: 28px;
    }}

    .hero-title {{
        font-size: 2rem;
    }}

    .ops-grid {{
        grid-template-columns: minmax(0, 1.25fr) minmax(0, 0.75fr);
        gap: 24px;
    }}

    .work-row {{
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
    }}

    .util-row {{
        flex-wrap: nowrap;
    }}
}}
    </style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-inner">
            <div class="topbar-title-group">
                <h1>AIS-VISTA</h1>
                <div class="topbar-sub">Konsol Operasional Lapangan &amp; Tagihan</div>
            </div>
            <nav class="console-nav" aria-label="Navigasi Utama">
                <a class="btn btn-sm" href="{safe_editor_url}">Editor Opname</a>
                <a class="btn btn-sm" href="{safe_guide_url}">Panduan</a>
                <a class="btn btn-sm" href="{safe_logs_url}" target="_blank" rel="noopener">Log Sistem</a>
            </nav>
        </div>
    </header>

    <main class="console-main">
        <section class="hero-grid" aria-label="Ringkasan Utama">
            <div class="panel hero-copy">
                <div>
                    <div class="hero-eyebrow">Integrasi WhatsApp, OCR, dan OneDrive</div>
                    <h2 class="hero-title">Opname Volume dan Dokumentasi SLA dalam Satu Tempat.</h2>
                    <p class="hero-desc">Periksa hasil pembacaan formulir scan sebelum masuk ke DATA_UNTUK_VOL, perbarui slot vendor per minggu lewat HP atau PC, dan pantau sinkronisasi SLA harian.</p>
                </div>
                <div class="hero-actions">
                    <a class="btn btn-primary" href="{safe_editor_url}">Buka Editor Opname</a>
                    {hero_excel_cta}
                </div>
            </div>

            <aside class="panel status-panel" aria-labelledby="cycleStatusTitle">
                <div class="metric-row">
                    <h2 id="cycleStatusTitle">Ringkasan Siklus Aktif</h2>
                    <span class="tag mono">{cycle_key}</span>
                </div>

                <div class="metric-item">
                    <div class="metric-row">
                        <span class="metric-label">Menunggu Review Scan</span>
                        {pending_tag}
                    </div>
                    <div>{pending_action}</div>
                </div>

                <div class="metric-item">
                    <div class="metric-row">
                        <span class="metric-label">Progress Roster Opname</span>
                        <span class="metric-value mono">{roster_done} / {roster_total} slot</span>
                    </div>
                    <div class="progress-track" role="progressbar" aria-valuenow="{roster_done}" aria-valuemin="0" aria-valuemax="{roster_total}" aria-label="Progress slot opname">
                        <div class="progress-fill" style="width: {roster_pct}%;"></div>
                    </div>
                </div>

                <div class="metric-item">
                    <div class="metric-row">
                        <span class="metric-label">Update SLA Hari Ini</span>
                        <span class="metric-value mono">{sla_today_count} kode</span>
                    </div>
                </div>
            </aside>
        </section>

        <section class="ops-grid" aria-label="Akses Pekerjaan dan Sistem">
            <div>
                <h2 class="section-heading">Dokumen &amp; Pencatatan</h2>
                <div class="work-list">
                    <div class="work-row">
                        <div class="work-row-info">
                            <h3>Editor &amp; Review Opname (HP &amp; PC)</h3>
                            <p>Koreksi baris pekerjaan hasil OCR, ubah dimensi P x L x T, dan edit ulang slot tersimpan.</p>
                        </div>
                        <a class="btn btn-sm" href="{safe_editor_url}">Buka Editor</a>
                    </div>
                    <div class="work-row">
                        <div class="work-row-info">
                            <h3>Excel Opname (DATA_UNTUK_VOL)</h3>
                            <p>Database volume bulanan ({safe_cycle_lbl}) untuk seluruh tabel LOG dan rekap W1/W2.</p>
                        </div>
                        {row_opname_excel}
                    </div>
                    <div class="work-row">
                        <div class="work-row-info">
                            <h3>Excel Progress SLA</h3>
                            <p>Spreadsheet pusat pemantauan kode temuan SLA dan arsip foto lapangan.</p>
                        </div>
                        {row_sla_excel}
                    </div>
                </div>
            </div>

            <div>
                <h2 class="section-heading">Operasional Server &amp; Bantuan</h2>
                <div class="util-list">
                    <div class="util-row">
                        <div class="util-row-text">
                            <strong>WhatsApp Scanner (WAHA)</strong>
                            <span>Scan QR perangkat dan cek status koneksi sesi.</span>
                        </div>
                        {row_waha_btn}
                    </div>
                    <div class="util-row">
                        <div class="util-row-text">
                            <strong>Log Sistem Bot</strong>
                            <span>Pantau proses webhook, OCR, dan sinkronisasi OneDrive.</span>
                        </div>
                        <a class="btn btn-sm" href="{safe_logs_url}" target="_blank" rel="noopener">Lihat Log</a>
                    </div>
                    <div class="util-row">
                        <div class="util-row-text">
                            <strong>Panduan &amp; Troubleshooting</strong>
                            <span>Daftar perintah WhatsApp, reset WAHA, dan update server.</span>
                        </div>
                        <a class="btn btn-sm" href="{safe_guide_url}">Buka Panduan</a>
                    </div>
                </div>
            </div>
        </section>

        <footer class="console-footer">
            <span>AIS-VISTA Operasional Pemeliharaan &amp; Tagihan</span>
            <span class="mono">Oracle Ampere VPS (ARM64)</span>
        </footer>
    </main>
</body>
</html>"""


def render_guide_page_html(waha_dash_link: str, opname_editor_url: str) -> str:
    safe_waha = html.escape(waha_dash_link or "#")
    safe_editor = html.escape(opname_editor_url or "/opname")
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panduan Penggunaan - AIS-VISTA</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
{_BASE_CSS}

main.guide-main {{
    max-width: 960px;
    margin: 0 auto;
    padding: 20px 16px 60px 16px;
}}

.guide-section {{
    margin-bottom: 20px;
}}

.guide-section h2 {{
    margin: 0 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-divider);
    font-size: 1.15rem;
}}

.guide-section h3 {{
    margin: 16px 0 6px 0;
    font-size: 1rem;
}}

.guide-section p, .guide-section li {{
    color: var(--text-secondary);
    font-size: 0.95rem;
    line-height: 1.6;
}}

.guide-section ul, .guide-section ol {{
    margin: 8px 0 12px 20px;
    padding: 0;
}}

.guide-section code {{
    font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background-color: var(--bg-subtle);
    color: var(--text-primary);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.875rem;
}}

.guide-section pre {{
    background-color: var(--bg-subtle);
    border: 1px solid var(--border-divider);
    border-radius: var(--radius-control);
    padding: 12px 14px;
    overflow-x: auto;
    margin: 10px 0 14px 0;
}}

.guide-section pre code {{
    background: none;
    padding: 0;
}}
    </style>
</head>
<body>
    <header class="topbar">
        <div class="topbar-inner">
            <div class="topbar-left">
                <a class="btn btn-sm" href="/">&larr; Konsol Utama</a>
                <div class="topbar-title-group">
                    <h1>Panduan Penggunaan &amp; Troubleshooting</h1>
                    <div class="topbar-sub">Alur opname, tagihan bulanan, dan operasional WAHA</div>
                </div>
            </div>
            <a class="btn btn-sm btn-primary" href="{safe_editor}">Buka Editor Opname</a>
        </div>
    </header>

    <main class="guide-main">
        <section class="panel guide-section">
            <h2>1. Alur Opname &amp; Tagihan di WhatsApp</h2>
            <ul>
                <li><strong>Scan Form Opname:</strong> kirim foto atau PDF form bertanda tangan dengan caption <code>Scan Opname PV M1</code> (ganti kode aset/minggu). Bot membalas link review HP/PC, ringkasan OCR, dan file Excel siap edit.</li>
                <li><strong>Review &amp; Edit via Web:</strong> buka link review dari WhatsApp atau masuk ke <a href="{safe_editor}">Editor Opname</a> untuk mengoreksi baris pekerjaan lalu klik <code>Simpan ke DATA UNTUK VOL</code>.</li>
                <li><strong>Kirim File Excel Opname:</strong> sertakan kata <code>Opname</code> pada caption saat mengirim file <code>.xlsx</code> agar diproses bot (Excel tanpa kata <code>Opname</code> dilewati).</li>
                <li><strong>Perintah Opname &amp; Tagihan:</strong> <code>/simpan SCAN-...</code>, <code>/status opname [YYYY-MM]</code>, <code>/arsip &lt;SLOT_ID&gt;</code>, <code>/undo &lt;SLOT_ID&gt;</code>, <code>/tagihan base YYYY-MM</code>, dan <code>/tagihan [YYYY-MM]</code>.</li>
            </ul>
        </section>

        <section class="panel guide-section">
            <h2>2. Mengganti Nomor WhatsApp (WAHA)</h2>
            <ol>
                <li>Keluar dari sesi lama melalui WhatsApp di HP (Perangkat Tertaut &rarr; Keluar) atau lewat <a href="{safe_waha}" target="_blank" rel="noopener">WAHA Dashboard</a>.</li>
                <li>Masuk ke server VPS dan hentikan kontainer sementara:
                    <pre><code>cd ~/AIS-VISTA
docker compose -f docker-compose.arm.yml down
rm -rf waha_sessions/*
docker compose -f docker-compose.arm.yml up -d</code></pre>
                </li>
                <li>Tunggu 10 detik, lalu kirim <code>/qr</code> ke bot Telegram untuk memindai QR code dari HP baru.</li>
            </ol>
        </section>

        <section class="panel guide-section">
            <h2>3. Pembaruan Kode &amp; Log Server (Oracle ARM64)</h2>
            <h3>Memantau Log Kontainer</h3>
            <ul>
                <li>Log bot Python: <code>docker logs -f vista_bot</code></li>
                <li>Log engine WAHA: <code>docker logs -f waha</code></li>
                <li>Keluar dari tampilan log dengan menekan <code>Ctrl + C</code>.</li>
            </ul>

            <h3>Mengambil Pembaruan Terbaru dari Git</h3>
            <pre><code>cd ~/AIS-VISTA
git pull
docker compose -f docker-compose.arm.yml up -d --build vista_bot</code></pre>

            <h3>Error Database SQLite Terbuat Sebagai Folder</h3>
            <pre><code>docker compose -f docker-compose.arm.yml down
rm -rf processed_messages.db
touch processed_messages.db
docker compose -f docker-compose.arm.yml up -d</code></pre>
        </section>
    </main>
</body>
</html>"""

