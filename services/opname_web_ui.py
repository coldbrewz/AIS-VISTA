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

.tag-added {
    background-color: var(--success-bg);
    color: var(--success-text);
    border-color: var(--success-border);
}

.tag-removed {
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
    <link rel="icon" type="image/svg+xml" href="/logo.svg">
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
    <link rel="icon" type="image/svg+xml" href="/logo.svg">
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

.filter-bar {{
    margin-bottom: 12px;
    padding: 12px 14px;
}}

.filter-controls {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
}}

.filter-controls > * {{
    min-width: 0;
}}

.filter-meta-row {{
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border-divider);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}}

.filter-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
}}

.filter-chip.is-active,
.filter-chip.is-active:hover:not(:disabled) {{
    background-color: var(--accent);
    color: #FFFFFF;
    border-color: var(--accent-hover);
}}

.filter-count {{
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-secondary);
}}

@media (min-width: 720px) {{
    .filter-controls {{
        grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);
    }}
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

.row-card.is-removed {{
    opacity: 0.72;
    border-style: dashed;
    border-color: var(--err-border);
    background-color: #FFFBFB;
}}

.diff-strip {{
    margin-bottom: 10px;
    padding: 7px 10px;
    border-radius: var(--radius-control);
    background-color: var(--warn-bg);
    border: 1px solid var(--warn-border);
    color: var(--warn-text);
    font-size: 0.85rem;
    font-weight: 600;
}}

.ocr-review-banner {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
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

                    <div id="ocrReviewBanner" class="banner banner-warn ocr-review-banner hidden" role="status">
                        <div id="ocrReviewBannerText"></div>
                        <button type="button" class="btn btn-sm" id="bannerFilterEditedBtn">Filter Revisi Tangan Saja</button>
                    </div>

                    <section id="rowFilterBar" class="panel filter-bar hidden" aria-label="Filter baris pekerjaan">
                        <div class="filter-controls">
                            <div>
                                <label class="field-label" for="rowSearchInput">Cari Lokasi / Kode / Item</label>
                                <input id="rowSearchInput" class="input" type="search" placeholder="Contoh: KM 45, Cikande, Permanen, L1..." />
                            </div>
                            <div>
                                <label class="field-label" for="rowItemFilter">Filter Item BOQ</label>
                                <select id="rowItemFilter" class="select">
                                    <option value="">Semua Item</option>
                                </select>
                            </div>
                            <div>
                                <label class="field-label" for="rowDateFilter">Filter Tanggal</label>
                                <select id="rowDateFilter" class="select">
                                    <option value="">Semua Tanggal</option>
                                </select>
                            </div>
                        </div>
                        <div class="filter-meta-row">
                            <div id="filterStatusText" class="filter-count">Menampilkan semua 0 baris</div>
                            <div class="filter-chips">
                                <button type="button" class="btn btn-sm filter-chip hidden" id="filterEditedChip" aria-pressed="false">Revisi OCR</button>
                                <button type="button" class="btn btn-sm filter-chip hidden" id="filterErrorChip" aria-pressed="false">Baris Error</button>
                                <button type="button" class="btn btn-sm hidden" id="clearFilterBtn">Reset Filter</button>
                            </div>
                        </div>
                    </section>

                    <div id="rowsContainer" class="rows-list"></div>

                    <div id="filterEmptyState" class="panel hidden" style="text-align: center; padding: 20px; margin-top: 12px;">
                        <p style="margin: 0 0 12px 0; color: var(--text-secondary);">Tidak ada baris yang cocok dengan filter saat ini.</p>
                        <button type="button" class="btn btn-sm" id="emptyResetFilterBtn">Tampilkan Semua Baris</button>
                    </div>

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
        const ocrReviewBanner = document.getElementById("ocrReviewBanner");
        const ocrReviewBannerText = document.getElementById("ocrReviewBannerText");
        const bannerFilterEditedBtn = document.getElementById("bannerFilterEditedBtn");
        const rowFilterBar = document.getElementById("rowFilterBar");
        const rowSearchInput = document.getElementById("rowSearchInput");
        const rowItemFilter = document.getElementById("rowItemFilter");
        const rowDateFilter = document.getElementById("rowDateFilter");
        const filterEditedChip = document.getElementById("filterEditedChip");
        const filterErrorChip = document.getElementById("filterErrorChip");
        const clearFilterBtn = document.getElementById("clearFilterBtn");
        const filterStatusText = document.getElementById("filterStatusText");
        const filterEmptyState = document.getElementById("filterEmptyState");
        const emptyResetFilterBtn = document.getElementById("emptyResetFilterBtn");
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
            filters: {{
                query: "",
                itemKey: "",
                tanggal: "",
                onlyEdited: false,
                onlyErrors: false,
            }},
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
                if (r.row_action === "REMOVED") return;
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

        function hasActiveFilters() {{
            const f = state.filters;
            return Boolean((f.query || "").trim() || f.itemKey || f.tanggal || f.onlyEdited || f.onlyErrors);
        }}

        function syncFilterChipButtons() {{
            const isEd = Boolean(state.filters.onlyEdited);
            filterEditedChip.classList.toggle("is-active", isEd);
            filterEditedChip.setAttribute("aria-pressed", isEd ? "true" : "false");
            filterErrorChip.classList.toggle("is-active", Boolean(state.filters.onlyErrors));
            filterErrorChip.setAttribute("aria-pressed", state.filters.onlyErrors ? "true" : "false");
            if (bannerFilterEditedBtn) {{
                bannerFilterEditedBtn.textContent = isEd ? "Tampilkan Semua Baris" : "Filter Revisi Tangan Saja";
            }}
        }}

        function resetFilters(skipApply) {{
            state.filters.query = "";
            state.filters.itemKey = "";
            state.filters.tanggal = "";
            state.filters.onlyEdited = false;
            state.filters.onlyErrors = false;
            rowSearchInput.value = "";
            rowItemFilter.value = "";
            rowDateFilter.value = "";
            syncFilterChipButtons();
            if (!skipApply) {{
                applyRowFilter();
            }}
        }}

        function populateFilterOptions() {{
            if (state.rows.length === 0) {{
                ocrReviewBanner.classList.add("hidden");
                rowFilterBar.classList.add("hidden");
                filterEmptyState.classList.add("hidden");
                return;
            }}
            rowFilterBar.classList.remove("hidden");

            const itemMap = new Map();
            const dateSet = new Set();
            let editedCount = 0;
            let addedCount = 0;
            let removedCount = 0;
            const hasErrors = Object.keys(state.rowErrors || {{}}).length > 0;

            state.rows.forEach(function(r) {{
                if (r.item_key && !itemMap.has(r.item_key)) {{
                    const boq = getBoqByKey(r.item_key);
                    const lbl = (boq ? boq.keyword : (r.keyword || r.item_key)) + " [" + r.item_key + "]";
                    itemMap.set(r.item_key, lbl);
                }}
                if (r.tanggal) {{
                    dateSet.add(r.tanggal);
                }}
                const isAdded = r.row_action === "ADDED";
                const isRemoved = r.row_action === "REMOVED";
                if (r.handwritten_edited || isAdded || isRemoved) {{
                    editedCount += 1;
                }}
                if (isAdded) addedCount += 1;
                if (isRemoved) removedCount += 1;
            }});

            const prevItem = state.filters.itemKey;
            let itemHtml = '<option value="">Semua Item</option>';
            itemMap.forEach(function(lbl, key) {{
                const sel = key === prevItem ? " selected" : "";
                itemHtml += '<option value="' + esc(key) + '"' + sel + '>' + esc(lbl) + '</option>';
            }});
            rowItemFilter.innerHTML = itemHtml;
            if (prevItem && !itemMap.has(prevItem)) {{
                state.filters.itemKey = "";
            }}

            const prevDate = state.filters.tanggal;
            let dateHtml = '<option value="">Semua Tanggal</option>';
            Array.from(dateSet).sort().forEach(function(dt) {{
                const sel = dt === prevDate ? " selected" : "";
                dateHtml += '<option value="' + esc(dt) + '"' + sel + '>' + esc(dt) + '</option>';
            }});
            rowDateFilter.innerHTML = dateHtml;
            if (prevDate && !dateSet.has(prevDate)) {{
                state.filters.tanggal = "";
            }}

            const hasEdited = editedCount > 0;
            filterEditedChip.textContent = "Revisi Tangan OCR (" + editedCount + ")";
            filterEditedChip.classList.toggle("hidden", !hasEdited);
            if (!hasEdited) state.filters.onlyEdited = false;
            if (hasEdited) {{
                const modifiedCount = Math.max(0, editedCount - addedCount - removedCount);
                const parts = [];
                if (modifiedCount > 0) parts.push(modifiedCount + " ubah angka");
                if (addedCount > 0) parts.push(addedCount + " tambah");
                if (removedCount > 0) parts.push(removedCount + " hapus");
                ocrReviewBannerText.textContent =
                    "Ditemukan " + editedCount + " baris revisi tangan OCR" +
                    (parts.length ? " (" + parts.join(", ") + ")" : "") + ".";
                ocrReviewBanner.classList.remove("hidden");
            }} else {{
                ocrReviewBanner.classList.add("hidden");
            }}
            filterErrorChip.classList.toggle("hidden", !hasErrors);
            if (!hasErrors) state.filters.onlyErrors = false;
            syncFilterChipButtons();
        }}

        function rowMatchesFilter(row, idx) {{
            const f = state.filters;
            if (f.itemKey && row.item_key !== f.itemKey) return false;
            if (f.tanggal && row.tanggal !== f.tanggal) return false;
            if (f.onlyEdited && !row.handwritten_edited && row.row_action !== "ADDED" && row.row_action !== "REMOVED") return false;
            if (f.onlyErrors && !state.rowErrors[idx]) return false;

            const q = String(f.query || "").trim().toLowerCase();
            if (!q) return true;
            const boq = getBoqByKey(row.item_key);
            const hay = [
                "#" + (idx + 1),
                row.tanggal,
                row.kode_temuan,
                row.lokasi,
                row.jalur,
                row.lajur,
                row.item_key,
                (boq && boq.keyword) || row.keyword,
                (boq && boq.uraian) || row.uraian,
                row.keterangan,
            ].map(function(v) {{ return String(v || "").toLowerCase(); }}).join(" ");

            const tokens = q.split(/\s+/).filter(Boolean);
            return tokens.every(function(tok) {{
                return hay.indexOf(tok) !== -1;
            }});
        }}

        function applyRowFilter() {{
            const total = state.rows.length;
            if (total === 0) {{
                filterEmptyState.classList.add("hidden");
                return;
            }}
            const cards = rowsContainer.querySelectorAll(".row-card");
            let visibleCount = 0;
            cards.forEach(function(card, i) {{
                const idx = parseInt(card.dataset.index || String(i), 10);
                const row = state.rows[idx];
                const match = row ? rowMatchesFilter(row, idx) : true;
                card.classList.toggle("hidden", !match);
                if (match) visibleCount += 1;
            }});

            const active = hasActiveFilters();
            clearFilterBtn.classList.toggle("hidden", !active);
            filterEmptyState.classList.toggle("hidden", visibleCount > 0);
            filterStatusText.textContent = active
                ? ("Menampilkan " + visibleCount + " dari " + total + " baris (semua " + total + " baris tetap tersimpan)")
                : ("Menampilkan semua " + total + " baris");
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
                populateFilterOptions();
                renderSummary();
                updateSlotPreview();
                return;
            }}

            const boqOpts = (state.data && state.data.boq_options) || [];
            rowsContainer.innerHTML = "";

            state.rows.forEach(function(row, idx) {{
                const card = document.createElement("div");
                const rowErr = state.rowErrors[idx];
                const isRemoved = row.row_action === "REMOVED";
                const isAdded = row.row_action === "ADDED";
                card.className = "row-card" + (rowErr ? " has-error" : "") + (isRemoved ? " is-removed" : "");
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

                let statusBadges = "";
                if (isRemoved) {{
                    statusBadges += '<span class="tag tag-removed">DIHAPUS / BATAL</span>';
                }} else if (isAdded) {{
                    statusBadges += '<span class="tag tag-added">+ TAMBAHAN</span>';
                }} else if (row.handwritten_edited) {{
                    statusBadges += '<span class="tag tag-warn">Revisi Tangan OCR</span>';
                }}

                const diffParts = [];
                if (!isRemoved && !isAdded) {{
                    if (row.vendor_keyword && row.vendor_item_key && row.vendor_item_key !== row.item_key) {{
                        diffParts.push("Item " + row.vendor_keyword + " -> " + (row.keyword || row.item_key));
                    }}
                    [["P", "p", "vendor_p"], ["L", "l", "vendor_l"], ["T", "t", "vendor_t"], ["Jml", "jml", "vendor_jml"]].forEach(function(pair) {{
                        const lbl = pair[0], k = pair[1], vk = pair[2];
                        if (row[vk] != null && row[vk] !== "" && row[k] != null && row[k] !== "") {{
                            const vOld = Number(String(row[vk]).replace(",", "."));
                            const vNew = Number(String(row[k]).replace(",", "."));
                            if (!isNaN(vOld) && !isNaN(vNew) && Math.abs(vOld - vNew) > 0.001) {{
                                diffParts.push(lbl + " " + vOld + " -> " + vNew);
                            }}
                        }}
                    }});
                    if (row.vol_vendor != null && row.vol_vendor !== "" && row.volume != null && row.volume !== "") {{
                        const vvOld = Number(String(row.vol_vendor).replace(",", "."));
                        const vvNew = Number(String(row.volume).replace(",", "."));
                        if (!isNaN(vvOld) && !isNaN(vvNew) && Math.abs(vvOld - vvNew) > 0.001) {{
                            diffParts.push("Vol " + vvOld + " -> " + vvNew + (row.satuan ? " " + row.satuan : ""));
                        }}
                    }}
                }}
                const diffHtml = diffParts.length > 0
                    ? '<div class="diff-strip">Vendor -> Opname: ' + esc(diffParts.join(" | ")) + '</div>'
                    : "";

                const restoreBtnHtml = isRemoved
                    ? '<button type="button" class="btn btn-sm restore-row-btn" aria-label="Pulihkan baris ' + (idx + 1) + '">Pulihkan Baris</button>'
                    : "";

                card.innerHTML =
                    '<div class="row-card-top">' +
                        '<div class="row-card-title">' +
                            '<span class="mono">Baris #' + (idx + 1) + '</span>' +
                            statusBadges +
                        '</div>' +
                        '<div class="row-card-actions">' +
                            restoreBtnHtml +
                            '<button type="button" class="btn btn-sm dup-row-btn" aria-label="Duplikat baris ' + (idx + 1) + '">Duplikat</button>' +
                            '<button type="button" class="btn btn-sm btn-danger del-row-btn" aria-label="Hapus baris ' + (idx + 1) + '">Hapus</button>' +
                        '</div>' +
                    '</div>' +
                    errHtml +
                    diffHtml +
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

                const restoreBtn = card.querySelector(".restore-row-btn");
                if (restoreBtn) {{
                    restoreBtn.addEventListener("click", function() {{
                        row.row_action = "";
                        const dimV = calcDimVolume(row);
                        if (row.vol_vendor != null && Number(row.vol_vendor) > 0) {{
                            row.volume = Number(row.vol_vendor);
                        }} else if (dimV !== null && dimV > 0) {{
                            row.volume = dimV;
                        }}
                        state.rowErrors = {{}};
                        markDirty();
                        renderRows();
                    }});
                }}

                card.querySelector(".dup-row-btn").addEventListener("click", function() {{
                    const copy = Object.assign({{}}, row, {{ handwritten_edited: false, row_action: "" }});
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

            populateFilterOptions();
            applyRowFilter();
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
            resetFilters(true);
            markDirty();
            renderRows();
            const cards = rowsContainer.querySelectorAll(".row-card");
            if (cards.length > 0) {{
                cards[cards.length - 1].scrollIntoView({{ block: "nearest", behavior: "smooth" }});
            }}
        }}

        function populatePage(data) {{
            state.data = data;
            state.rows = (data.entries || []).map(function(e) {{
                const [jal, laj] = splitJalurLajur(e.jalur_lajur);
                return Object.assign({{}}, e, {{ jalur: jal, lajur: laj, _autoCalc: false }});
            }});
            state.dirty = false;
            state.rowErrors = {{}};
            resetFilters(true);

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

            const activeRows = state.rows.filter(function(r) {{ return r.row_action !== "REMOVED"; }});
            if (activeRows.length === 0) {{
                showBanner("error", "ERROR: Belum Ada Baris Aktif", ["Minimal 1 baris aktif wajib ada (pulihkan atau tambah baris)."]);
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
                        row_action: r.row_action || "",
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
                    resetFilters(true);
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

        rowSearchInput.addEventListener("input", function() {{
            state.filters.query = rowSearchInput.value || "";
            applyRowFilter();
        }});
        rowItemFilter.addEventListener("change", function() {{
            state.filters.itemKey = rowItemFilter.value || "";
            applyRowFilter();
        }});
        rowDateFilter.addEventListener("change", function() {{
            state.filters.tanggal = rowDateFilter.value || "";
            applyRowFilter();
        }});
        filterEditedChip.addEventListener("click", function() {{
            state.filters.onlyEdited = !state.filters.onlyEdited;
            syncFilterChipButtons();
            applyRowFilter();
        }});
        bannerFilterEditedBtn.addEventListener("click", function() {{
            state.filters.onlyEdited = !state.filters.onlyEdited;
            syncFilterChipButtons();
            applyRowFilter();
        }});
        filterErrorChip.addEventListener("click", function() {{
            state.filters.onlyErrors = !state.filters.onlyErrors;
            syncFilterChipButtons();
            applyRowFilter();
        }});
        clearFilterBtn.addEventListener("click", function() {{ resetFilters(false); }});
        emptyResetFilterBtn.addEventListener("click", function() {{ resetFilters(false); }});

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
    <link rel="icon" type="image/svg+xml" href="/logo.svg">
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

.tabs-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border-divider);
    padding-bottom: 12px;
}}

.tab-btn {{
    min-height: 44px;
    padding: 8px 16px;
    border-radius: var(--radius-control);
    border: 1px solid var(--border-control);
    background-color: var(--bg-surface);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.9375rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 120ms ease, border-color 120ms ease;
}}

.tab-btn:hover {{
    background-color: var(--bg-subtle);
}}

.tab-btn.is-active {{
    background-color: var(--accent);
    border-color: var(--accent);
    color: #FFFFFF;
}}

.roster-form-grid {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
    margin-bottom: 14px;
}}

.roster-form-grid > * {{
    min-width: 0;
}}

.roster-filter-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
}}

.chk-label {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 44px;
    padding: 0 4px;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-primary);
    cursor: pointer;
}}

.chk-label input[type="checkbox"] {{
    width: 20px;
    height: 20px;
    accent-color: var(--accent);
}}

.tagihan-form-grid {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
    margin-bottom: 14px;
}}

.tagihan-form-grid > * {{
    min-width: 0;
}}

.tagihan-summary-strip {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
}}

@media (min-width: 960px) {{
    main.list-main {{
        padding: 20px 24px 60px 24px;
    }}

    .toolbar-panel {{
        grid-template-columns: 200px 240px 1fr auto;
    }}

    .roster-form-grid {{
        grid-template-columns: 160px 1fr 220px 120px;
        align-items: end;
    }}

    .tagihan-form-grid {{
        grid-template-columns: 180px 1fr;
        align-items: end;
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
        <div class="tabs-bar" role="tablist" aria-label="Menu Opname">
            <button type="button" role="tab" id="tabSlotsBtn" class="tab-btn is-active" aria-selected="true" aria-controls="panelSlots">Slot &amp; Review</button>
            <button type="button" role="tab" id="tabRosterBtn" class="tab-btn" aria-selected="false" aria-controls="panelRoster">Vendor &amp; Roster</button>
            <button type="button" role="tab" id="tabTagihanBtn" class="tab-btn" aria-selected="false" aria-controls="panelTagihan">Tagihan (MC)</button>
        </div>

        <div id="panelSlots" role="tabpanel" aria-labelledby="tabSlotsBtn">
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
        </div>

        <div id="panelRoster" class="hidden" role="tabpanel" aria-labelledby="tabRosterBtn">
            <div id="rosterFeedback" class="banner hidden" role="status" aria-live="polite"></div>

            <section class="panel" style="margin-bottom: 16px;" aria-labelledby="addVendorTitle">
                <h2 id="addVendorTitle" style="margin: 0 0 12px 0; font-size: 1.05rem;">Tambah / Perbarui Vendor &amp; Slot Roster</h2>
                <form id="rosterAddForm">
                    <div class="roster-form-grid">
                        <div>
                            <label class="field-label" for="rvCode">Kode Vendor</label>
                            <input id="rvCode" class="input input-mono" type="text" maxlength="20" placeholder="Contoh: KARYA" required />
                        </div>
                        <div>
                            <label class="field-label" for="rvAliases">Alias / Nama PT (opsional, pisah koma)</label>
                            <input id="rvAliases" class="input" type="text" placeholder="Contoh: PT KARYA MANDIRI, KARYA" />
                        </div>
                        <div>
                            <label class="field-label" for="rvAset">Aset Pekerjaan</label>
                            <select id="rvAset" class="select">
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
                        <div>
                            <label class="field-label" for="rvWil">Wilayah</label>
                            <select id="rvWil" class="select">
                                <option value="W1">W1</option>
                                <option value="W2">W2</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary" id="rvSubmitBtn">Simpan ke Roster</button>
                </form>
            </section>

            <section class="panel" style="margin-bottom: 16px;" aria-labelledby="migrationTitle">
                <h2 id="migrationTitle" style="margin: 0 0 8px 0; font-size: 1.05rem;">Migrasi VPS &amp; Backup OneDrive</h2>
                <p style="margin: 0 0 12px 0; font-size: 0.9rem; color: var(--text-secondary);">
                    Setiap perubahan tersimpan di SQLite dan otomatis disinkronkan ke <span class="mono" id="onedrivePathLabel">Arsip Opname/_config/opname_roster.json</span>.
                    Sync terakhir: <strong class="mono" id="onedriveSyncTime">-</strong>
                </p>
                <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                    <a class="btn" id="exportRosterBtn" href="#">Ekspor JSON</a>
                    <button type="button" class="btn" id="importRosterTriggerBtn">Impor JSON</button>
                    <input type="file" id="importRosterFile" accept=".json,application/json" class="sr-only" />
                    <button type="button" class="btn" id="pullOnedriveBtn">Tarik dari OneDrive</button>
                </div>
            </section>

            <section class="panel" aria-labelledby="rosterListTitle">
                <div class="roster-filter-row">
                    <h2 id="rosterListTitle" style="margin: 0; font-size: 1.05rem;">Daftar Slot Roster (<span id="rosterActiveCount" class="mono">0</span> aktif)</h2>
                    <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 10px;">
                        <select id="rosterAsetFilter" class="select" style="width: auto; min-width: 180px;" aria-label="Filter aset roster">
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
                        <label class="chk-label">
                            <input type="checkbox" id="showInactiveChk" />
                            <span>Tampilkan Nonaktif</span>
                        </label>
                    </div>
                </div>

                <div id="rosterLoading" class="state-box" style="margin: 12px 0;" role="status">
                    <p style="margin: 0;">Memuat daftar vendor &amp; roster...</p>
                </div>
                <div id="rosterMobileContainer" class="slot-cards mobile-slots-only"></div>
                <div class="desktop-table-wrap" id="rosterTableWrap">
                    <table class="slots-table">
                        <thead>
                            <tr>
                                <th>Aset</th>
                                <th>Wilayah</th>
                                <th>Vendor</th>
                                <th>Alias OCR</th>
                                <th>Status</th>
                                <th>Aksi</th>
                            </tr>
                        </thead>
                        <tbody id="rosterTableBody"></tbody>
                    </table>
                </div>
                <div id="rosterEmptyBox" class="hidden" style="padding: 16px 0; text-align: center; color: var(--text-secondary);">
                    Tidak ada slot roster pada filter ini. Gunakan form di atas untuk menambah vendor baru.
                </div>
            </section>
        </div>

        <div id="panelTagihan" class="hidden" role="tabpanel" aria-labelledby="tabTagihanBtn">
            <div id="tagihanFeedback" class="banner hidden" role="status" aria-live="polite"></div>

            <section class="panel" style="margin-bottom: 16px;" aria-labelledby="tagihanGenTitle">
                <h2 id="tagihanGenTitle" style="margin: 0 0 12px 0; font-size: 1.05rem;">Generate Tagihan Bulanan (MC)</h2>
                <div class="tagihan-form-grid">
                    <div>
                        <label class="field-label" for="tgCycleInput">Siklus Tagihan (YYYY-MM)</label>
                        <input id="tgCycleInput" class="input input-mono" type="month" />
                    </div>
                    <div>
                        <label class="field-label" for="tgTemplateFile">Template MC Khusus (Opsional - kosongkan untuk auto-rollover)</label>
                        <input id="tgTemplateFile" class="input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
                    </div>
                </div>
                <div id="tgStatusSummary" class="tagihan-summary-strip"></div>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
                    <button type="button" class="btn btn-primary" id="tgGenerateBtn">Generate Tagihan MC</button>
                    <a class="btn hidden" id="tgExistingDownloadBtn" href="#">Unduh MC Siklus Ini</a>
                    <a class="btn hidden" id="tgExistingOnedriveLink" href="#" target="_blank" rel="noopener">Buka MC di OneDrive</a>
                </div>
                <div id="tgResultBox" class="banner banner-success hidden" style="margin-top: 14px; margin-bottom: 0;" role="status"></div>
            </section>

            <section class="panel" style="margin-bottom: 16px;" aria-labelledby="tagihanBaseTitle">
                <h2 id="tagihanBaseTitle" style="margin: 0 0 8px 0; font-size: 1.05rem;">Simpan Baseline MC Bulan Lalu</h2>
                <p style="margin: 0 0 12px 0; font-size: 0.9rem; color: var(--text-secondary);">
                    Unggah file MC bulan sebelumnya sekali (setara <span class="mono">/tagihan base YYYY-MM</span>) agar <span class="mono">S.D. BULAN LALU</span> terakumulasi otomatis di bulan berikutnya.
                </p>
                <form id="tagihanBaseForm">
                    <div class="tagihan-form-grid">
                        <div>
                            <label class="field-label" for="tgBaseCycleInput">Siklus Baseline (YYYY-MM)</label>
                            <input id="tgBaseCycleInput" class="input input-mono" type="month" required />
                        </div>
                        <div>
                            <label class="field-label" for="tgBaseFile">File Excel MC (.xlsx)</label>
                            <input id="tgBaseFile" class="input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required />
                        </div>
                    </div>
                    <button type="submit" class="btn" id="tgBaseSubmitBtn">Simpan Baseline MC</button>
                </form>
            </section>

            <section class="panel" aria-labelledby="tagihanHistTitle">
                <div class="roster-filter-row">
                    <h2 id="tagihanHistTitle" style="margin: 0; font-size: 1.05rem;">Riwayat Tagihan (MC)</h2>
                    <button type="button" class="btn btn-sm" id="tgRefreshBtn">Muat Ulang</button>
                </div>
                <div id="tagihanLoading" class="state-box" style="margin: 12px 0;" role="status">
                    <p style="margin: 0;">Memuat status &amp; riwayat Tagihan MC...</p>
                </div>
                <div id="tagihanMobileContainer" class="slot-cards mobile-slots-only"></div>
                <div class="desktop-table-wrap" id="tagihanTableWrap">
                    <table class="slots-table">
                        <thead>
                            <tr>
                                <th>Siklus</th>
                                <th>File MC</th>
                                <th>Sheet Aktif</th>
                                <th>Dibuat</th>
                                <th>Aksi</th>
                            </tr>
                        </thead>
                        <tbody id="tagihanTableBody"></tbody>
                    </table>
                </div>
                <div id="tagihanEmptyBox" class="hidden" style="padding: 16px 0; text-align: center; color: var(--text-secondary);">
                    Belum ada baseline atau hasil Tagihan MC tersimpan.
                </div>
            </section>
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

        const tabSlotsBtn = document.getElementById("tabSlotsBtn");
        const tabRosterBtn = document.getElementById("tabRosterBtn");
        const tabTagihanBtn = document.getElementById("tabTagihanBtn");
        const panelSlots = document.getElementById("panelSlots");
        const panelRoster = document.getElementById("panelRoster");
        const panelTagihan = document.getElementById("panelTagihan");
        const tagihanFeedback = document.getElementById("tagihanFeedback");
        const tgCycleInput = document.getElementById("tgCycleInput");
        const tgTemplateFile = document.getElementById("tgTemplateFile");
        const tgStatusSummary = document.getElementById("tgStatusSummary");
        const tgGenerateBtn = document.getElementById("tgGenerateBtn");
        const tgExistingDownloadBtn = document.getElementById("tgExistingDownloadBtn");
        const tgExistingOnedriveLink = document.getElementById("tgExistingOnedriveLink");
        const tgResultBox = document.getElementById("tgResultBox");
        const tagihanBaseForm = document.getElementById("tagihanBaseForm");
        const tgBaseCycleInput = document.getElementById("tgBaseCycleInput");
        const tgBaseFile = document.getElementById("tgBaseFile");
        const tgBaseSubmitBtn = document.getElementById("tgBaseSubmitBtn");
        const tgRefreshBtn = document.getElementById("tgRefreshBtn");
        const tagihanLoading = document.getElementById("tagihanLoading");
        const tagihanMobileContainer = document.getElementById("tagihanMobileContainer");
        const tagihanTableWrap = document.getElementById("tagihanTableWrap");
        const tagihanTableBody = document.getElementById("tagihanTableBody");
        const tagihanEmptyBox = document.getElementById("tagihanEmptyBox");
        const rosterFeedback = document.getElementById("rosterFeedback");
        const rosterAddForm = document.getElementById("rosterAddForm");
        const rvCode = document.getElementById("rvCode");
        const rvAliases = document.getElementById("rvAliases");
        const rvAset = document.getElementById("rvAset");
        const rvWil = document.getElementById("rvWil");
        const rvSubmitBtn = document.getElementById("rvSubmitBtn");
        const exportRosterBtn = document.getElementById("exportRosterBtn");
        const importRosterTriggerBtn = document.getElementById("importRosterTriggerBtn");
        const importRosterFile = document.getElementById("importRosterFile");
        const pullOnedriveBtn = document.getElementById("pullOnedriveBtn");
        const onedrivePathLabel = document.getElementById("onedrivePathLabel");
        const onedriveSyncTime = document.getElementById("onedriveSyncTime");
        const rosterActiveCount = document.getElementById("rosterActiveCount");
        const rosterAsetFilter = document.getElementById("rosterAsetFilter");
        const showInactiveChk = document.getElementById("showInactiveChk");
        const rosterLoading = document.getElementById("rosterLoading");
        const rosterMobileContainer = document.getElementById("rosterMobileContainer");
        const rosterTableWrap = document.getElementById("rosterTableWrap");
        const rosterTableBody = document.getElementById("rosterTableBody");
        const rosterEmptyBox = document.getElementById("rosterEmptyBox");

        let rosterPayload = null;
        exportRosterBtn.href = "/api/opname/roster/export?token=" + encodeURIComponent(TOKEN);

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

        function showRosterBanner(type, text) {{
            rosterFeedback.className = "banner " + (type === "success" ? "banner-success" : (type === "warn" ? "banner-warn" : "banner-error"));
            rosterFeedback.setAttribute("role", type === "error" ? "alert" : "status");
            rosterFeedback.innerHTML = '<div class="banner-title">' + esc(text) + '</div>';
            rosterFeedback.classList.remove("hidden");
        }}

        function renderRosterList() {{
            if (!rosterPayload) return;
            const aliasesByVendor = new Map();
            (rosterPayload.vendors || []).forEach(function(v) {{
                aliasesByVendor.set(v.code, (v.aliases || []).join(", "));
            }});

            const allSlots = rosterPayload.roster || [];
            const activeCnt = allSlots.filter(function(r) {{ return r.active; }}).length;
            rosterActiveCount.textContent = String(activeCnt);
            onedriveSyncTime.textContent = rosterPayload.onedrive_last_sync || "Belum ada sync";
            if (rosterPayload.onedrive_path) {{
                onedrivePathLabel.textContent = rosterPayload.onedrive_path;
            }}

            const fAset = rosterAsetFilter.value;
            const showInactive = showInactiveChk.checked;
            const rows = allSlots.filter(function(r) {{
                if (fAset && r.aset !== fAset) return false;
                if (!showInactive && !r.active) return false;
                return true;
            }});

            if (rows.length === 0) {{
                rosterMobileContainer.innerHTML = "";
                rosterTableBody.innerHTML = "";
                rosterTableWrap.classList.add("hidden");
                rosterEmptyBox.classList.remove("hidden");
                return;
            }}

            rosterEmptyBox.classList.add("hidden");
            rosterTableWrap.classList.remove("hidden");

            rosterMobileContainer.innerHTML = rows.map(function(r) {{
                const statusTag = r.active
                    ? '<span class="tag tag-success">AKTIF</span>'
                    : '<span class="tag tag-error">NONAKTIF</span>';
                const toggleLabel = r.active ? "Nonaktifkan" : "Aktifkan";
                const btnCls = r.active ? "btn btn-sm btn-danger roster-toggle-btn" : "btn btn-sm roster-toggle-btn";
                return '<div class="slot-card">' +
                    '<div class="slot-card-head">' +
                        '<strong class="mono">' + esc(r.aset + " | " + r.wilayah + " | " + r.vendor) + '</strong>' +
                        statusTag +
                    '</div>' +
                    '<div class="slot-meta">Alias: ' + esc(aliasesByVendor.get(r.vendor) || r.vendor) + '</div>' +
                    '<div class="slot-actions">' +
                        '<button type="button" class="' + btnCls + '" data-aset="' + esc(r.aset) + '" data-vendor="' + esc(r.vendor) + '" data-wil="' + esc(r.wilayah) + '" data-next="' + (r.active ? "0" : "1") + '">' + toggleLabel + '</button>' +
                    '</div>' +
                '</div>';
            }}).join("");

            rosterTableBody.innerHTML = rows.map(function(r) {{
                const statusTag = r.active
                    ? '<span class="tag tag-success">AKTIF</span>'
                    : '<span class="tag tag-error">NONAKTIF</span>';
                const toggleLabel = r.active ? "Nonaktifkan" : "Aktifkan";
                const btnCls = r.active ? "btn btn-sm btn-danger roster-toggle-btn" : "btn btn-sm roster-toggle-btn";
                return '<tr>' +
                    '<td class="mono" style="font-weight: 600;">' + esc(r.aset) + '</td>' +
                    '<td class="mono">' + esc(r.wilayah) + '</td>' +
                    '<td class="mono" style="font-weight: 600;">' + esc(r.vendor) + '</td>' +
                    '<td>' + esc(aliasesByVendor.get(r.vendor) || r.vendor) + '</td>' +
                    '<td>' + statusTag + '</td>' +
                    '<td><button type="button" class="' + btnCls + '" data-aset="' + esc(r.aset) + '" data-vendor="' + esc(r.vendor) + '" data-wil="' + esc(r.wilayah) + '" data-next="' + (r.active ? "0" : "1") + '">' + toggleLabel + '</button></td>' +
                '</tr>';
            }}).join("");

            document.querySelectorAll(".roster-toggle-btn").forEach(function(btn) {{
                btn.addEventListener("click", function() {{
                    const nextActive = btn.dataset.next === "1";
                    btn.disabled = true;
                    fetch("/api/opname/roster/slot/toggle?token=" + encodeURIComponent(TOKEN), {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{
                            aset: btn.dataset.aset,
                            vendor: btn.dataset.vendor,
                            wilayah: btn.dataset.wil,
                            active: nextActive,
                        }}),
                    }})
                    .then(function(resp) {{ return resp.json().then(function(b) {{ return {{ ok: resp.ok, body: b }}; }}); }})
                    .then(function(res) {{
                        if (!res.ok) throw new Error((res.body && res.body.detail) || "Gagal mengubah status slot.");
                        rosterPayload = res.body.roster;
                        renderRosterList();
                        showRosterBanner(res.body.onedrive_synced ? "success" : "warn", (nextActive ? "OK: Slot diaktifkan. " : "OK: Slot dinonaktifkan. ") + (res.body.sync_note || ""));
                    }})
                    .catch(function(err) {{
                        btn.disabled = false;
                        showRosterBanner("error", "ERROR: " + err.message);
                    }});
                }});
            }});
        }}

        function loadRoster() {{
            rosterLoading.classList.remove("hidden");
            rosterTableWrap.classList.add("hidden");
            rosterEmptyBox.classList.add("hidden");
            fetch("/api/opname/roster?token=" + encodeURIComponent(TOKEN))
                .then(function(resp) {{
                    return resp.json().then(function(b) {{
                        if (!resp.ok) throw new Error((b && b.detail) || ("Status " + resp.status));
                        return b;
                    }});
                }})
                .then(function(data) {{
                    rosterPayload = data;
                    rosterLoading.classList.add("hidden");
                    renderRosterList();
                }})
                .catch(function(err) {{
                    rosterLoading.classList.add("hidden");
                    showRosterBanner("error", "ERROR: Gagal memuat daftar roster: " + err.message);
                }});
        }}

        function showTagihanBanner(type, text) {{
            tagihanFeedback.className = "banner " + (type === "success" ? "banner-success" : (type === "warn" ? "banner-warn" : "banner-error"));
            tagihanFeedback.setAttribute("role", type === "error" ? "alert" : "status");
            tagihanFeedback.innerHTML = '<div class="banner-title">' + esc(text) + '</div>';
            tagihanFeedback.classList.remove("hidden");
        }}

        function formatRp(val) {{
            return "Rp " + Number(val || 0).toLocaleString("id-ID", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
        }}

        function readFileAsBase64(file) {{
            return new Promise(function(resolve, reject) {{
                const reader = new FileReader();
                reader.onload = function() {{
                    resolve({{ filename: file.name, file_b64: String(reader.result || "") }});
                }};
                reader.onerror = function() {{
                    reject(new Error("Gagal membaca file " + file.name));
                }};
                reader.readAsDataURL(file);
            }});
        }}

        function renderTagihanStatus(data) {{
            if (!data) return;
            if (!tgCycleInput.value || tgCycleInput.value !== data.cycle_key) {{
                tgCycleInput.value = data.cycle_key;
            }}
            if (!tgBaseCycleInput.value && data.prev_cycle_key) {{
                tgBaseCycleInput.value = data.prev_cycle_key;
            }}

            const tags = [];
            if (data.silo_ready) {{
                tags.push('<span class="tag tag-success">Data Siap: ' + esc(data.silo_filename) + ' (' + esc(data.active_slot_count || 0) + ' slot)</span>');
            }} else {{
                tags.push('<span class="tag tag-warn">Data Belum Ada: ' + esc(data.silo_filename) + '</span>');
            }}
            if (data.prev_baseline) {{
                tags.push('<span class="tag tag-success">Rollover S.D. Bulan Lalu: ' + esc(data.prev_baseline.cycle_key) + '</span>');
            }} else if (data.has_cached_template || data.has_env_template_link) {{
                tags.push('<span class="tag tag-warn">Template MC Tersedia (tanpa rollover ' + esc(data.prev_cycle_key) + ')</span>');
            }} else {{
                tags.push('<span class="tag tag-error">Belum Ada Baseline / Template MC</span>');
            }}
            tgStatusSummary.innerHTML = tags.join("");

            if (data.current_output && data.current_output.download_url) {{
                tgExistingDownloadBtn.href = data.current_output.download_url;
                tgExistingDownloadBtn.classList.remove("hidden");
            }} else {{
                tgExistingDownloadBtn.classList.add("hidden");
            }}
            if (data.current_output && data.current_output.web_url) {{
                tgExistingOnedriveLink.href = data.current_output.web_url;
                tgExistingOnedriveLink.classList.remove("hidden");
            }} else {{
                tgExistingOnedriveLink.classList.add("hidden");
            }}

            const hist = data.history || [];
            if (hist.length === 0) {{
                tagihanMobileContainer.innerHTML = "";
                tagihanTableBody.innerHTML = "";
                tagihanTableWrap.classList.add("hidden");
                tagihanEmptyBox.classList.remove("hidden");
                return;
            }}

            tagihanEmptyBox.classList.add("hidden");
            tagihanTableWrap.classList.remove("hidden");
            tagihanMobileContainer.innerHTML = hist.map(function(h) {{
                const odBtn = h.web_url
                    ? '<a class="btn btn-sm" href="' + esc(h.web_url) + '" target="_blank" rel="noopener">OneDrive</a>'
                    : '';
                return '<div class="slot-card">' +
                    '<div class="slot-card-head">' +
                        '<strong class="mono">' + esc(h.cycle_key) + '</strong>' +
                        '<span class="tag">' + esc(h.sheet_count > 0 ? (h.sheet_count + " sheet") : "Baseline") + '</span>' +
                    '</div>' +
                    '<div class="slot-meta">' + esc(h.filename) + '</div>' +
                    '<div class="slot-meta">Dibuat: ' + esc(h.created_at || "-") + '</div>' +
                    '<div class="slot-actions">' +
                        '<a class="btn btn-sm" href="' + esc(h.download_url) + '">Unduh Excel</a>' +
                        odBtn +
                    '</div>' +
                '</div>';
            }}).join("");

            tagihanTableBody.innerHTML = hist.map(function(h) {{
                const odBtn = h.web_url
                    ? '<a class="btn btn-sm" href="' + esc(h.web_url) + '" target="_blank" rel="noopener">OneDrive</a>'
                    : '';
                return '<tr>' +
                    '<td class="mono" style="font-weight: 600;">' + esc(h.cycle_key) + '</td>' +
                    '<td>' + esc(h.filename) + '</td>' +
                    '<td class="mono">' + esc(h.sheet_count > 0 ? String(h.sheet_count) : "Baseline") + '</td>' +
                    '<td class="mono">' + esc(h.created_at || "-") + '</td>' +
                    '<td><div style="display: flex; gap: 8px;"><a class="btn btn-sm" href="' + esc(h.download_url) + '">Unduh</a>' + odBtn + '</div></td>' +
                '</tr>';
            }}).join("");
        }}

        function loadTagihanStatus(rawCycle) {{
            tagihanLoading.classList.remove("hidden");
            tagihanTableWrap.classList.add("hidden");
            tagihanEmptyBox.classList.add("hidden");
            const params = new URLSearchParams({{ token: TOKEN }});
            if (rawCycle) params.set("cycle", rawCycle);
            fetch("/api/opname/tagihan/status?" + params.toString())
                .then(function(resp) {{
                    return resp.json().then(function(b) {{
                        if (!resp.ok) throw new Error((b && b.detail) || ("Status " + resp.status));
                        return b;
                    }});
                }})
                .then(function(data) {{
                    tagihanLoading.classList.add("hidden");
                    renderTagihanStatus(data);
                }})
                .catch(function(err) {{
                    tagihanLoading.classList.add("hidden");
                    showTagihanBanner("error", "ERROR: Gagal memuat status Tagihan: " + err.message);
                }});
        }}

        function activateTab(tabName) {{
            const isRoster = tabName === "roster";
            const isTagihan = tabName === "tagihan";
            const isSlots = !isRoster && !isTagihan;

            tabSlotsBtn.classList.toggle("is-active", isSlots);
            tabSlotsBtn.setAttribute("aria-selected", isSlots ? "true" : "false");
            tabRosterBtn.classList.toggle("is-active", isRoster);
            tabRosterBtn.setAttribute("aria-selected", isRoster ? "true" : "false");
            tabTagihanBtn.classList.toggle("is-active", isTagihan);
            tabTagihanBtn.setAttribute("aria-selected", isTagihan ? "true" : "false");

            panelSlots.classList.toggle("hidden", !isSlots);
            panelRoster.classList.toggle("hidden", !isRoster);
            panelTagihan.classList.toggle("hidden", !isTagihan);

            if (isRoster) {{
                loadRoster();
            }} else if (isTagihan) {{
                loadTagihanStatus(tgCycleInput.value || cycleSelect.value || "");
            }} else {{
                loadList(cycleSelect.value);
            }}
        }}

        tabSlotsBtn.addEventListener("click", function() {{ activateTab("slots"); }});
        tabRosterBtn.addEventListener("click", function() {{ activateTab("roster"); }});
        tabTagihanBtn.addEventListener("click", function() {{ activateTab("tagihan"); }});
        rosterAsetFilter.addEventListener("change", renderRosterList);
        showInactiveChk.addEventListener("change", renderRosterList);

        tgCycleInput.addEventListener("change", function() {{ loadTagihanStatus(tgCycleInput.value); }});
        tgRefreshBtn.addEventListener("click", function() {{ loadTagihanStatus(tgCycleInput.value); }});

        tgGenerateBtn.addEventListener("click", function() {{
            tagihanFeedback.classList.add("hidden");
            tgResultBox.classList.add("hidden");
            tgGenerateBtn.disabled = true;
            tgGenerateBtn.textContent = "Memproses Tagihan MC...";

            const fileObj = tgTemplateFile.files && tgTemplateFile.files[0];
            const readPromise = fileObj ? readFileAsBase64(fileObj) : Promise.resolve({{ filename: "", file_b64: "" }});
            readPromise
                .then(function(fData) {{
                    return fetch("/api/opname/tagihan/generate?token=" + encodeURIComponent(TOKEN), {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{
                            cycle: tgCycleInput.value || "",
                            filename: fData.filename,
                            file_b64: fData.file_b64,
                        }}),
                    }});
                }})
                .then(function(resp) {{ return resp.json().then(function(b) {{ return {{ ok: resp.ok, body: b }}; }}); }})
                .then(function(res) {{
                    if (!res.ok) throw new Error((res.body && res.body.detail) || "Gagal generate Tagihan MC.");
                    const d = res.body;
                    tgTemplateFile.value = "";
                    if (d.status) renderTagihanStatus(d.status);

                    const sheetItems = (d.ordered_sheets || []).filter(function(s) {{
                        return Number((d.grand_totals || {{}})[s] || 0) > 0;
                    }}).map(function(s) {{
                        return '<li>' + esc(s + ": " + formatRp(d.grand_totals[s])) + '</li>';
                    }}).join("");
                    const warnItems = (d.warnings || []).slice(0, 5).map(function(w) {{
                        return '<li style="color: var(--warn-text);">' + esc("Catatan: " + w) + '</li>';
                    }}).join("");
                    const rollLine = d.rollover_applied
                        ? '<p style="margin: 0 0 6px 0;">Rollover S.D. BULAN LALU: <strong class="mono">' + esc(d.prev_cycle_key) + '</strong></p>'
                        : '';
                    const dlBtn = d.download_url
                        ? '<a class="btn btn-primary btn-sm" href="' + esc(d.download_url) + '">Unduh ' + esc(d.output_filename) + '</a>'
                        : '';
                    const odBtn = d.web_url
                        ? '<a class="btn btn-sm" href="' + esc(d.web_url) + '" target="_blank" rel="noopener">Buka di OneDrive</a>'
                        : '';
                    tgResultBox.innerHTML =
                        '<div class="banner-title">' + esc("OK: Tagihan MC Selesai (" + d.month_label + " " + d.cycle_key.slice(0, 4) + ")") + '</div>' +
                        rollLine +
                        '<p style="margin: 0 0 8px 0;">Total Pilar 1 (sheet aktif): <strong class="mono">' + esc(formatRp(d.total_grand)) + '</strong></p>' +
                        ((sheetItems || warnItems) ? '<ul>' + sheetItems + warnItems + '</ul>' : '') +
                        '<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;">' + dlBtn + odBtn + '</div>';
                    tgResultBox.classList.remove("hidden");
                }})
                .catch(function(err) {{
                    showTagihanBanner("error", err.message || "Gagal generate Tagihan MC.");
                }})
                .finally(function() {{
                    tgGenerateBtn.disabled = false;
                    tgGenerateBtn.textContent = "Generate Tagihan MC";
                }});
        }});

        tagihanBaseForm.addEventListener("submit", function(e) {{
            e.preventDefault();
            const fObj = tgBaseFile.files && tgBaseFile.files[0];
            if (!fObj) {{
                showTagihanBanner("error", "Pilih file Excel MC (.xlsx) terlebih dahulu.");
                return;
            }}
            tagihanFeedback.classList.add("hidden");
            tgBaseSubmitBtn.disabled = true;
            tgBaseSubmitBtn.textContent = "Mengunggah Baseline...";
            readFileAsBase64(fObj)
                .then(function(fData) {{
                    return fetch("/api/opname/tagihan/baseline?token=" + encodeURIComponent(TOKEN), {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{
                            cycle: tgBaseCycleInput.value || "",
                            filename: fData.filename,
                            file_b64: fData.file_b64,
                        }}),
                    }});
                }})
                .then(function(resp) {{ return resp.json().then(function(b) {{ return {{ ok: resp.ok, body: b }}; }}); }})
                .then(function(res) {{
                    if (!res.ok) throw new Error((res.body && res.body.detail) || "Gagal menyimpan baseline Tagihan.");
                    const b = res.body.baseline || {{}};
                    tgBaseFile.value = "";
                    if (res.body.status) renderTagihanStatus(res.body.status);
                    showTagihanBanner("success", "OK: Baseline " + (b.cycle_key || "") + " tersimpan. Siap generate " + (b.next_cycle_key || "") + ".");
                }})
                .catch(function(err) {{
                    showTagihanBanner("error", "ERROR: " + err.message);
                }})
                .finally(function() {{
                    tgBaseSubmitBtn.disabled = false;
                    tgBaseSubmitBtn.textContent = "Simpan Baseline MC";
                }});
        }});

        rosterAddForm.addEventListener("submit", function(e) {{
            e.preventDefault();
            rvSubmitBtn.disabled = true;
            rvSubmitBtn.textContent = "Menyimpan...";
            fetch("/api/opname/roster/slot?token=" + encodeURIComponent(TOKEN), {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{
                    vendor: rvCode.value,
                    aliases: rvAliases.value,
                    aset: rvAset.value,
                    wilayah: rvWil.value,
                    active: true,
                }}),
            }})
            .then(function(resp) {{ return resp.json().then(function(b) {{ return {{ ok: resp.ok, body: b }}; }}); }})
            .then(function(res) {{
                if (!res.ok) throw new Error((res.body && res.body.detail) || "Gagal menyimpan vendor ke roster.");
                rvCode.value = "";
                rvAliases.value = "";
                rosterPayload = res.body.roster;
                renderRosterList();
                showRosterBanner(res.body.onedrive_synced ? "success" : "warn", "OK: Vendor & slot disimpan. " + (res.body.sync_note || ""));
            }})
            .catch(function(err) {{
                showRosterBanner("error", "ERROR: " + err.message);
            }})
            .finally(function() {{
                rvSubmitBtn.disabled = false;
                rvSubmitBtn.textContent = "Simpan ke Roster";
            }});
        }});

        importRosterTriggerBtn.addEventListener("click", function() {{ importRosterFile.click(); }});
        importRosterFile.addEventListener("change", function() {{
            const f = importRosterFile.files && importRosterFile.files[0];
            if (!f) return;
            f.text().then(function(txt) {{
                const parsed = JSON.parse(txt);
                return fetch("/api/opname/roster/import?token=" + encodeURIComponent(TOKEN), {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify(parsed),
                }});
            }})
            .then(function(resp) {{ return resp.json().then(function(b) {{ return {{ ok: resp.ok, body: b }}; }}); }})
            .then(function(res) {{
                if (!res.ok) throw new Error((res.body && res.body.detail) || "File JSON tidak valid.");
                rosterPayload = res.body.roster;
                renderRosterList();
                showRosterBanner(res.body.onedrive_synced ? "success" : "warn", "OK: Konfigurasi roster berhasil diimpor. " + (res.body.sync_note || ""));
            }})
            .catch(function(err) {{
                showRosterBanner("error", "ERROR Impor JSON: " + err.message);
            }})
            .finally(function() {{
                importRosterFile.value = "";
            }});
        }});

        pullOnedriveBtn.addEventListener("click", function() {{
            pullOnedriveBtn.disabled = true;
            fetch("/api/opname/roster/sync-onedrive?token=" + encodeURIComponent(TOKEN), {{ method: "POST" }})
                .then(function(resp) {{ return resp.json().then(function(b) {{ return {{ ok: resp.ok, body: b }}; }}); }})
                .then(function(res) {{
                    if (!res.ok) throw new Error((res.body && res.body.detail) || "Gagal menarik dari OneDrive.");
                    rosterPayload = res.body.roster;
                    renderRosterList();
                    showRosterBanner("success", "OK: " + (res.body.sync_note || "Dipulihkan dari OneDrive."));
                }})
                .catch(function(err) {{
                    showRosterBanner("error", "ERROR: " + err.message);
                }})
                .finally(function() {{
                    pullOnedriveBtn.disabled = false;
                }});
        }});

        if (window.location.hash === "#roster") {{
            activateTab("roster");
        }} else if (window.location.hash === "#tagihan") {{
            activateTab("tagihan");
        }} else {{
            loadList("");
        }}
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


def _console_href(url: str, fallback_href: str = "#workspace") -> tuple[str, bool]:
    clean = (url or "").strip()
    if not clean or clean == "#":
        return fallback_href, False
    is_ext = clean.startswith(("http://", "https://"))
    return clean, is_ext


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

    opname_xls_href, opname_xls_ext = _console_href(opname_excel_url)
    sla_xls_href, sla_xls_ext = _console_href(sla_excel_url)
    waha_href, waha_ext = _console_href(waha_url)

    opname_xls_target = ' target="_blank" rel="noopener"' if opname_xls_ext else ""
    sla_xls_target = ' target="_blank" rel="noopener"' if sla_xls_ext else ""
    waha_target = ' target="_blank" rel="noopener"' if waha_ext else ""

    waha_pill = (
        f'<a class="cta-pill cta-dark" href="{html.escape(waha_href)}"{waha_target}>WAHA Scanner</a>'
        if waha_ext
        else '<a class="cta-pill cta-dark" href="#workspace">Server Tools</a>'
    )

    dir_opname_btn = _safe_action_link(
        opname_excel_url, "Open Excel", "Not Configured", "dir-btn"
    )
    dir_sla_btn = _safe_action_link(
        sla_excel_url, "Open SLA Sheet", "Not Configured", "dir-btn"
    )
    dir_waha_btn = _safe_action_link(
        waha_url, "Open WAHA", "Not Configured", "dir-btn"
    )

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/logo.svg">
    <title>AIS-VISTA</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
:root {{
    --outer-bg: #050607;
    --stage-bg: #0A0C0E;
    --surface-1: #0E1114;
    --surface-pill: #15191D;
    --border-subtle: #23282D;
    --border-control: #6C7680;
    --text-primary: #F4F6F8;
    --text-dim: #A8B0B8;
}}

* {{
    box-sizing: border-box;
}}

html {{
    font-size: 16px;
    max-width: 100%;
    overflow-x: clip;
    scroll-behavior: smooth;
}}

body {{
    margin: 0;
    min-height: 100vh;
    background-color: var(--outer-bg);
    color: var(--text-primary);
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}}

.mono {{
    font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
}}

:focus-visible {{
    outline: 2px solid #FFFFFF;
    outline-offset: 2px;
}}

.shell {{
    max-width: 1400px;
    margin: 0 auto;
    padding: 12px 14px 48px 14px;
}}

.console-top {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 6px 4px 14px 4px;
}}

.brand-mark {{
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-height: 44px;
    color: var(--text-primary);
    text-decoration: none;
    font-weight: 600;
    font-size: 1rem;
    letter-spacing: -0.02em;
    order: 1;
}}

.nav-pill {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 4px;
    width: 100%;
    padding: 4px;
    border-radius: 14px;
    background-color: #111417;
    border: 1px solid var(--border-subtle);
    order: 3;
}}

.nav-pill a {{
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    padding: 0 12px;
    border-radius: 10px;
    color: var(--text-dim);
    text-decoration: none;
    font-size: 0.875rem;
    font-weight: 500;
    transition: background-color 120ms ease, color 120ms ease;
}}

.nav-pill a:hover {{
    color: #FFFFFF;
    background-color: #1A1F24;
}}

.nav-pill a.nav-active {{
    color: #FFFFFF;
    background-color: #1E242B;
    border: 1px solid var(--border-control);
    font-weight: 600;
}}

.top-right-link {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 44px;
    padding: 0 12px;
    border-radius: 999px;
    color: var(--text-primary);
    text-decoration: none;
    font-size: 0.875rem;
    font-weight: 500;
    order: 2;
}}

.top-right-link:hover {{
    text-decoration: underline;
}}

.hero-stage {{
    position: relative;
    overflow: hidden;
    border-radius: 20px;
    border: 1px solid var(--border-subtle);
    background:
        radial-gradient(circle at 86% 14%, rgba(176, 194, 184, 0.20) 0%, rgba(10, 12, 14, 0) 48%),
        radial-gradient(circle at 14% 88%, rgba(164, 178, 174, 0.14) 0%, rgba(10, 12, 14, 0) 42%),
        var(--stage-bg);
    padding: 44px 20px 32px 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 28px;
}}

.hero-center {{
    position: relative;
    z-index: 2;
    text-align: center;
    max-width: 680px;
}}

.hero-title {{
    margin: 0 0 10px 0;
    font-size: clamp(2.5rem, 6vw, 4.4rem);
    font-weight: 600;
    line-height: 1.06;
    letter-spacing: -0.04em;
}}

.brand-solid {{
    color: #FFFFFF;
}}

.brand-dim {{
    color: #B8C0C8;
}}

.hero-sub {{
    margin: 0 0 26px 0;
    font-size: 1rem;
    color: var(--text-dim);
    font-weight: 400;
}}

.cta-row {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 12px;
}}

.cta-pill {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 46px;
    padding: 0 22px;
    border-radius: 999px;
    font-size: 0.9375rem;
    font-weight: 600;
    text-decoration: none;
    transition: background-color 120ms ease, border-color 120ms ease;
}}

.cta-dark {{
    background-color: var(--surface-pill);
    color: var(--text-primary);
    border: 1px solid var(--border-control);
}}

.cta-dark:hover {{
    background-color: #20262C;
    border-color: #9AA4AE;
}}

.cta-white {{
    background-color: #FFFFFF;
    color: #090B0D;
    border: 1px solid #FFFFFF;
}}

.cta-white:hover {{
    background-color: #E2E6EA;
    border-color: #E2E6EA;
}}

.hero-stems {{
    display: none;
}}

.telemetry-nodes {{
    position: relative;
    z-index: 2;
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}}

.node-card {{
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 54px;
    padding: 10px 12px;
    border-radius: 12px;
    background-color: rgba(14, 17, 20, 0.85);
    border: 1px solid var(--border-subtle);
    color: var(--text-primary);
    text-decoration: none;
    transition: border-color 120ms ease;
}}

.node-card:hover {{
    border-color: var(--border-control);
}}

.node-icon {{
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 1px solid var(--border-control);
    background-color: #14181C;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: var(--text-primary);
    font-size: 0.75rem;
    font-weight: 600;
}}

.node-text {{
    min-width: 0;
}}

.node-label {{
    display: block;
    font-size: 0.8125rem;
    color: var(--text-dim);
    line-height: 1.25;
}}

.node-val {{
    display: block;
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
}}

.node-line {{
    display: none;
}}

.stage-footer-corners {{
    display: none;
}}

.quick-strip {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 8px 26px;
    padding: 18px 12px 6px 12px;
}}

.quick-link {{
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    padding: 0 8px;
    color: var(--text-dim);
    text-decoration: none;
    font-size: 0.9375rem;
    font-weight: 500;
    letter-spacing: -0.01em;
    transition: color 120ms ease;
}}

.quick-link:hover {{
    color: #FFFFFF;
}}

.directory {{
    margin-top: 32px;
    padding-top: 24px;
    border-top: 1px solid var(--border-subtle);
}}

.directory-head {{
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 16px;
}}

.directory-head h2 {{
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-primary);
}}

.directory-head span {{
    font-size: 0.875rem;
    color: var(--text-dim);
}}

.dir-grid {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
}}

.dir-item {{
    background-color: var(--surface-1);
    border: 1px solid var(--border-subtle);
    border-radius: 14px;
    padding: 16px 18px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}}

.dir-info {{
    min-width: 0;
    flex: 1 1 220px;
}}

.dir-info h3 {{
    margin: 0 0 4px 0;
    font-size: 0.98rem;
    font-weight: 600;
    color: var(--text-primary);
}}

.dir-info p {{
    margin: 0;
    font-size: 0.875rem;
    color: var(--text-dim);
}}

.dir-btn {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    padding: 0 16px;
    border-radius: 999px;
    background-color: var(--surface-pill);
    border: 1px solid var(--border-control);
    color: var(--text-primary);
    text-decoration: none;
    font-family: inherit;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
    transition: background-color 120ms ease, border-color 120ms ease;
}}

.dir-btn:hover:not(:disabled) {{
    background-color: #20262C;
    border-color: #FFFFFF;
}}

.dir-btn:disabled {{
    opacity: 0.45;
    cursor: not-allowed;
}}

.console-foot {{
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid var(--border-subtle);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 8px;
    font-size: 0.85rem;
    color: var(--text-dim);
}}

@media (min-width: 960px) {{
    .shell {{
        padding: 16px 24px 60px 24px;
    }}

    .brand-mark {{
        order: 1;
    }}

    .nav-pill {{
        order: 2;
        width: auto;
        border-radius: 999px;
    }}

    .nav-pill a {{
        padding: 0 14px;
        border-radius: 999px;
    }}

    .top-right-link {{
        order: 3;
    }}

    .hero-stage {{
        min-height: min(74vh, 640px);
        padding: 64px 48px 110px 48px;
    }}

    .hero-stems {{
        display: block;
        position: absolute;
        left: 50%;
        bottom: 0;
        transform: translateX(-50%);
        width: 140px;
        height: 155px;
        pointer-events: none;
        z-index: 1;
    }}

    .stem {{
        position: absolute;
        bottom: 0;
        width: 1px;
        background: linear-gradient(to top, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.55) 75%, rgba(255, 255, 255, 0) 100%);
    }}

    .stem-1 {{ left: 26px; height: 90px; opacity: 0.45; }}
    .stem-2 {{ left: 52px; height: 145px; opacity: 0.7; }}
    .stem-3 {{ left: 78px; height: 110px; opacity: 0.85; }}
    .stem-4 {{ left: 104px; height: 130px; opacity: 0.5; }}

    .telemetry-nodes {{
        position: static;
        display: block;
        width: auto;
    }}

    .node-card {{
        position: absolute;
        background: transparent;
        border: 0;
        padding: 6px;
        min-height: 44px;
    }}

    .node-tl {{ top: 20%; left: 5%; }}
    .node-tr {{ top: 20%; right: 5%; flex-direction: row-reverse; text-align: right; }}
    .node-bl {{ bottom: 24%; left: 5%; }}
    .node-br {{ bottom: 24%; right: 5%; flex-direction: row-reverse; text-align: right; }}

    .node-line {{
        display: block;
        width: 72px;
        height: 1px;
        background-color: rgba(255, 255, 255, 0.14);
        margin: 0 8px;
    }}

    .stage-footer-corners {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: absolute;
        left: 28px;
        right: 28px;
        bottom: 24px;
        z-index: 2;
    }}

    .scroll-anchor {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        min-height: 44px;
        padding: 0 14px 0 8px;
        border-radius: 999px;
        color: var(--text-dim);
        text-decoration: none;
        font-size: 0.875rem;
        border: 1px solid var(--border-subtle);
        background-color: rgba(14, 17, 20, 0.72);
    }}

    .scroll-anchor:hover {{
        color: #FFFFFF;
        border-color: var(--border-control);
    }}

    .scroll-circle {{
        width: 26px;
        height: 26px;
        border-radius: 50%;
        background-color: #FFFFFF;
        color: #090B0D;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.85rem;
    }}

    .cycle-bar-wrap {{
        text-align: right;
    }}

    .cycle-bar-label {{
        display: block;
        font-size: 0.85rem;
        color: var(--text-primary);
        margin-bottom: 6px;
    }}

    .cycle-track {{
        width: 110px;
        height: 3px;
        border-radius: 2px;
        background-color: #2A3036;
        overflow: hidden;
    }}

    .cycle-fill {{
        height: 100%;
        background-color: #FFFFFF;
    }}

    .dir-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
    }}
}}
    </style>
</head>
<body>
    <div class="shell">
        <header class="console-top">
            <a class="brand-mark" href="/">
                <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" fill="none" stroke="#F4F6F8" stroke-width="2.5"/>
                    <circle cx="14.5" cy="12" r="4" fill="#050607"/>
                </svg>
                <span>AIS-VISTA</span>
            </a>

            <nav class="nav-pill" aria-label="Navigasi Utama">
                <a class="nav-active" href="{safe_editor_url}">Editor</a>
                <a href="{html.escape(opname_xls_href)}"{opname_xls_target}>Excel Vol</a>
                <a href="{html.escape(sla_xls_href)}"{sla_xls_target}>Excel SLA</a>
                <a href="{html.escape(waha_href)}"{waha_target}>WAHA</a>
                <a href="{safe_logs_url}" target="_blank" rel="noopener">Logs</a>
                <a href="{safe_guide_url}">Guide</a>
            </nav>

            <a class="top-right-link" href="{safe_editor_url}">Open Editor &rarr;</a>
        </header>

        <main>
            <section class="hero-stage" aria-label="Console Overview">
                <div class="hero-center">
                    <h1 class="hero-title"><span class="brand-solid">AIS</span> <span class="brand-dim">VISTA</span></h1>
                    <p class="hero-sub">Opname &amp; SLA Console</p>
                    <div class="cta-row">
                        {waha_pill}
                        <a class="cta-pill cta-white" href="{safe_editor_url}">Open Editor</a>
                    </div>
                </div>

                <div class="telemetry-nodes">
                    <a class="node-card node-tl" href="{safe_editor_url}">
                        <span class="node-icon mono">SC</span>
                        <span class="node-text">
                            <span class="node-label">Pending Scan</span>
                            <span class="node-val mono">{pending_count} form</span>
                        </span>
                        <span class="node-line" aria-hidden="true"></span>
                    </a>

                    <a class="node-card node-tr" href="{safe_editor_url}">
                        <span class="node-icon mono">SL</span>
                        <span class="node-text">
                            <span class="node-label">Roster</span>
                            <span class="node-val mono">{roster_done} / {roster_total}</span>
                        </span>
                        <span class="node-line" aria-hidden="true"></span>
                    </a>

                    <a class="node-card node-bl" href="{html.escape(sla_xls_href)}"{sla_xls_target}>
                        <span class="node-icon mono">DT</span>
                        <span class="node-text">
                            <span class="node-label">SLA Today</span>
                            <span class="node-val mono">{sla_today_count} kode</span>
                        </span>
                        <span class="node-line" aria-hidden="true"></span>
                    </a>

                    <a class="node-card node-br" href="{html.escape(opname_xls_href)}"{opname_xls_target}>
                        <span class="node-icon mono">CY</span>
                        <span class="node-text">
                            <span class="node-label">Cycle</span>
                            <span class="node-val mono">{cycle_key}</span>
                        </span>
                        <span class="node-line" aria-hidden="true"></span>
                    </a>
                </div>

                <div class="hero-stems" aria-hidden="true">
                    <span class="stem stem-1"></span>
                    <span class="stem stem-2"></span>
                    <span class="stem stem-3"></span>
                    <span class="stem stem-4"></span>
                </div>

                <div class="stage-footer-corners">
                    <a class="scroll-anchor" href="#workspace">
                        <span class="scroll-circle" aria-hidden="true">&darr;</span>
                        <span>All Tools</span>
                    </a>
                    <div class="cycle-bar-wrap">
                        <span class="cycle-bar-label mono">{cycle_key} ({roster_done}/{roster_total})</span>
                        <div class="cycle-track" aria-hidden="true">
                            <div class="cycle-fill" style="width: {roster_pct}%;"></div>
                        </div>
                    </div>
                </div>
            </section>

            <nav class="quick-strip" aria-label="Akses Cepat">
                <a class="quick-link" href="{safe_editor_url}">Editor Opname</a>
                <a class="quick-link" href="{html.escape(opname_xls_href)}"{opname_xls_target}>Excel Opname</a>
                <a class="quick-link" href="{html.escape(sla_xls_href)}"{sla_xls_target}>Excel SLA</a>
                <a class="quick-link" href="{html.escape(waha_href)}"{waha_target}>WAHA</a>
                <a class="quick-link" href="{safe_logs_url}" target="_blank" rel="noopener">Logs</a>
                <a class="quick-link" href="{safe_guide_url}">Guide</a>
            </nav>

            <section id="workspace" class="directory" aria-label="Direktori Sistem">
                <div class="directory-head">
                    <h2>Workspace Links</h2>
                    <span class="mono">{safe_cycle_lbl}</span>
                </div>

                <div class="dir-grid">
                    <div class="dir-item">
                        <div class="dir-info">
                            <h3>Editor Opname</h3>
                            <p>Review OCR scans, edit dimensions, and manage weekly vendor slots.</p>
                        </div>
                        <a class="dir-btn" href="{safe_editor_url}">Open Editor</a>
                    </div>

                    <div class="dir-item">
                        <div class="dir-info">
                            <h3>Excel Opname (DATA_UNTUK_VOL)</h3>
                            <p>Monthly OneDrive workbook ({safe_cycle_lbl}) for LOG tables and W1/W2 summary.</p>
                        </div>
                        {dir_opname_btn}
                    </div>

                    <div class="dir-item">
                        <div class="dir-info">
                            <h3>Excel Progress SLA</h3>
                            <p>Master SLA tracking workbook synced with field photo updates.</p>
                        </div>
                        {dir_sla_btn}
                    </div>

                    <div class="dir-item">
                        <div class="dir-info">
                            <h3>WAHA Dashboard</h3>
                            <p>WhatsApp session engine and linked device QR scanner.</p>
                        </div>
                        {dir_waha_btn}
                    </div>

                    <div class="dir-item">
                        <div class="dir-info">
                            <h3>System Logs</h3>
                            <p>Live stdout tail for webhook, OCR, and OneDrive requests.</p>
                        </div>
                        <a class="dir-btn" href="{safe_logs_url}" target="_blank" rel="noopener">View Logs</a>
                    </div>

                    <div class="dir-item">
                        <div class="dir-info">
                            <h3>Guide &amp; Troubleshooting</h3>
                            <p>WhatsApp commands, WAHA session reset, and VPS update notes.</p>
                        </div>
                        <a class="dir-btn" href="{safe_guide_url}">Open Guide</a>
                    </div>
                </div>
            </section>
        </main>

        <footer class="console-foot">
            <span>AIS-VISTA</span>
            <span class="mono">Oracle Ampere ARM64</span>
        </footer>
    </div>
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
    <link rel="icon" type="image/svg+xml" href="/logo.svg">
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

