"""
Report Tools
============
Generates three formats of the GTM audit report:

  generate_audit_report()     → .docx  (consultancy-grade Word document)
  generate_html_report()      → .html  (standalone, print-ready)
  generate_markdown_report()  → .md    (portable, paste into any AI chat)

All three formats read from the same shared_state, so run the full audit once
and generate whichever formats you need.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .. import shared_state

# ── Brand palette (shared across all formats) ─────────────────────────────────
BRAND_DARK   = "1F3864"
BRAND_MID    = "2E75B6"
BRAND_LIGHT  = "D6E4F0"
CRITICAL_BG  = "FFE0E0"
CRIT_BORDER  = "C00000"
WARNING_BG   = "FFF2CC"
WARN_BORDER  = "ED7D31"
SUGGEST_BG   = "E2EFDA"
SUGG_BORDER  = "70AD47"
TABLE_HEADER = "1F3864"
TABLE_ALT    = "EBF3FB"
TEXT_PRIMARY = "1A1A1A"
TEXT_MUTED   = "595959"
WHITE        = "FFFFFF"


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_findings(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """Parse the plain-text audit output into (critical, warnings, suggestions) lists."""
    critical: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []
    suggestions: list[tuple[str, str]] = []
    current: list | None = None

    for line in text.splitlines():
        s = line.strip()
        upper = s.upper()
        if "CRITICAL" in upper and not s.startswith("•"):
            current = critical
        elif "WARNING" in upper and not s.startswith("•"):
            current = warnings
        elif "SUGGESTION" in upper and not s.startswith("•"):
            current = suggestions
        elif s.startswith("•") and current is not None:
            body = s.lstrip("•").strip()
            m = re.search(r"'([^']+)'", body)
            area = m.group(1)[:30] if m else " ".join(body.split()[:4])[:30]
            current.append((area, body))

    return critical, warnings, suggestions


def _health_score(n_crit: int, n_warn: int, n_sugg: int) -> int:
    """Simple 0-100 health score."""
    penalty = n_crit * 15 + n_warn * 5 + n_sugg * 1
    return max(0, 100 - penalty)


def _health_label(score: int) -> str:
    if score >= 80: return "Good"
    if score >= 60: return "Fair"
    if score >= 40: return "Poor"
    return "Critical"


def _health_color(score: int) -> str:
    if score >= 80: return "70AD47"
    if score >= 60: return "ED7D31"
    if score >= 40: return "FF6B35"
    return "C00000"


def _load_state() -> tuple[dict, dict, dict] | str:
    """Returns (gtm_raw, analysis, author) or an error string."""
    gtm_raw  = shared_state.get_gtm_data()
    analysis = shared_state.get_analysis()
    author   = shared_state.get_author()
    if gtm_raw is None:
        return "No GTM file loaded. Ask the file_reader to load a GTM JSON export first."
    if analysis is None:
        return "No analysis found. Ask the gtm_analyzer to run the full audit first."
    return gtm_raw, analysis, author


def _container_meta(gtm_raw: dict) -> dict:
    cv        = gtm_raw.get("containerVersion", {})
    container = cv.get("container", {})
    return {
        "name"      : container.get("name", "Unknown Container"),
        "id"        : container.get("publicId", "GTM-UNKNOWN"),
        "account_id": container.get("accountId", "—"),
        "export_ts" : gtm_raw.get("exportTime", "—"),
        "contexts"  : ", ".join(container.get("usageContext", ["WEB"])),
        "tags"      : cv.get("tag",      []),
        "triggers"  : cv.get("trigger",  []),
        "variables" : cv.get("variable", []),
        "folders"   : cv.get("folder",   []),
        "cv"        : cv,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC TOOL: set_report_author
# ══════════════════════════════════════════════════════════════════════════════

def set_report_author(name: str, title: str, email: str) -> str:
    """
    Stores the report author details used on the cover page and footer of all reports.

    Args:
        name:  Full name of the report author.
        title: Professional title, e.g. 'Senior Analytics Consultant'.
        email: Contact email address.

    Returns:
        Confirmation string with the saved details.
    """
    try:
        shared_state.set_author(name, title, email)
        return (
            f"Author details saved:\n"
            f"  Name  : {name}\n"
            f"  Title : {title}\n"
            f"  Email : {email}\n\n"
            "Ready to generate reports in any format (docx / html / md)."
        )
    except Exception as exc:
        return f"Failed to save author details: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC TOOL: generate_audit_report  (.docx)
# ══════════════════════════════════════════════════════════════════════════════

def generate_audit_report(output_filename: str = "gtm_audit_report.docx") -> str:
    """
    Generates a professional consultancy-grade GTM audit report as a .docx file.

    Sections: cover page, executive summary dashboard, container structure,
    consent configuration, severity-coded findings, remediation plan,
    cleanup inventory, and verification checklist.

    Args:
        output_filename: Path for the output .docx file (default: gtm_audit_report.docx).

    Returns:
        Success message with file path and finding counts, or an error string.
    """
    result = _load_state()
    if isinstance(result, str):
        return result
    gtm_raw, analysis, author = result

    try:
        from docx import Document
        from docx.shared import Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        return (
            "python-docx is not installed.\n"
            "Run: pip install python-docx\n"
            "Or use generate_html_report() / generate_markdown_report() instead."
        )

    # ── Extract data ─────────────────────────────────────────────────────────
    meta    = _container_meta(gtm_raw)
    summary = analysis.get("summary", "")
    crit, warn, sugg = _parse_findings(summary)
    score   = _health_score(len(crit), len(warn), len(sugg))

    author_name  = author.get("name")  or "GTM Audit Specialist"
    author_title = author.get("title") or "Analytics Consultant"
    author_email = author.get("email") or ""
    audit_date   = datetime.now().strftime("%Y-%m-%d")
    month_year   = datetime.now().strftime("%B %Y")

    tags      = meta["tags"]
    triggers  = meta["triggers"]
    variables = meta["variables"]
    folders   = meta["folders"]

    paused   = [t for t in tags if t.get("paused", False)]
    used_ids: set[str] = set()
    for t in tags:
        used_ids.update(t.get("firingTriggerId", []))
        used_ids.update(t.get("blockingTriggerId", []))
    orphans = [
        tr for tr in triggers
        if tr.get("triggerId") not in used_ids and tr.get("type") != "ALWAYS"
    ]

    def _rgb(hex_str: str) -> RGBColor:
        h = hex_str.lstrip("#")
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _cell_shading(cell, hex_color: str):
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd  = OxmlElement("w:shd")
        shd.set(qn("w:val"),   "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"),  hex_color)
        tcPr.append(shd)

    def _cell_borders(cell):
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        borders = OxmlElement("w:tcBorders")
        for side in ("top", "left", "bottom", "right"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"),  "single")
            el.set(qn("w:sz"),   "4")
            el.set(qn("w:space"),"0")
            el.set(qn("w:color"), BORDER_LIGHT := "CCCCCC")
            borders.append(el)
        tcPr.append(borders)

    def _col_width(cell, twips: int):
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        w    = OxmlElement("w:tcW")
        w.set(qn("w:w"),    str(twips))
        w.set(qn("w:type"), "dxa")
        tcPr.append(w)

    def _font_color(font, hex_str: str):
        font.color.rgb = _rgb(hex_str)

    def _header_cell(cell, text: str, width: int):
        _col_width(cell, width)
        _cell_shading(cell, TABLE_HEADER)
        _cell_borders(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.font.name = "Calibri"; r.font.size = Pt(9); r.font.bold = True
        _font_color(r.font, WHITE)

    def _data_cell(cell, text: str, width: int, fill: str, bold: bool = False):
        _col_width(cell, width)
        _cell_shading(cell, fill)
        _cell_borders(cell)
        p = cell.paragraphs[0]
        r = p.add_run(str(text)[:200])
        r.font.name = "Calibri"; r.font.size = Pt(9); r.font.bold = bold
        _font_color(r.font, TEXT_PRIMARY)

    # ── Build document ───────────────────────────────────────────────────────
    doc = Document()
    for section in doc.sections:
        section.top_margin    = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    # Cover ──────────────────────────────────────────────────────────────────
    cover_tbl = doc.add_table(rows=1, cols=1)
    cover_tbl.style = "Table Grid"
    cell = cover_tbl.cell(0, 0)
    _cell_shading(cell, BRAND_DARK)
    for line in [
        (f"GTM AUDIT REPORT", 28, True),
        (meta["name"],         18, False),
        (f"{meta['id']}  ·  {month_year}", 12, False),
    ]:
        p = cell.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(line[0])
        r.font.name = "Calibri"; r.font.size = Pt(line[1]); r.font.bold = line[2]
        _font_color(r.font, WHITE)
    p = cell.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"Prepared by {author_name}  ·  {author_title}  ·  {author_email}")
    r.font.name = "Calibri"; r.font.size = Pt(10)
    _font_color(r.font, "A9C4E0")
    doc.add_paragraph()

    # Executive Summary Dashboard ────────────────────────────────────────────
    h = doc.add_heading("Executive Summary", level=1)
    h.runs[0].font.color.rgb = _rgb(BRAND_MID)

    dash_tbl = doc.add_table(rows=2, cols=5)
    dash_tbl.style = "Table Grid"
    headers  = ["Health Score", "Critical", "Warnings", "Suggestions", "Audit Date"]
    values   = [
        f"{score}/100 ({_health_label(score)})",
        str(len(crit)),
        str(len(warn)),
        str(len(sugg)),
        audit_date,
    ]
    fills    = [
        _health_color(score),
        CRIT_BORDER if crit else "70AD47",
        WARN_BORDER  if warn else "70AD47",
        SUGG_BORDER  if sugg else BRAND_MID,
        BRAND_MID,
    ]
    widths   = [1800, 1600, 1600, 1800, 1700]
    for i, h_txt in enumerate(headers):
        _header_cell(dash_tbl.cell(0, i), h_txt, widths[i])
    for i, v_txt in enumerate(values):
        _data_cell(dash_tbl.cell(1, i), v_txt, widths[i], fills[i], bold=True)

    doc.add_paragraph()

    # Container Structure ────────────────────────────────────────────────────
    doc.add_heading("Container Structure", level=2)
    struct_tbl = doc.add_table(rows=5, cols=2)
    struct_tbl.style = "Table Grid"
    rows_data = [
        ("Container Name",  meta["name"]),
        ("Container ID",    meta["id"]),
        ("Account ID",      meta["account_id"]),
        ("Usage Context",   meta["contexts"]),
        ("Exported",        meta["export_ts"]),
    ]
    for i, (k, v) in enumerate(rows_data):
        _data_cell(struct_tbl.cell(i, 0), k, 2500, TABLE_ALT if i % 2 == 0 else WHITE, bold=True)
        _data_cell(struct_tbl.cell(i, 1), v, 5000, TABLE_ALT if i % 2 == 0 else WHITE)

    doc.add_paragraph()

    count_tbl = doc.add_table(rows=2, cols=4)
    count_tbl.style = "Table Grid"
    for i, (h_txt, val) in enumerate(
        [("Tags", len(tags)), ("Triggers", len(triggers)),
         ("Variables", len(variables)), ("Folders", len(folders))]
    ):
        _header_cell(count_tbl.cell(0, i), h_txt, 1800)
        _data_cell(count_tbl.cell(1, i), str(val), 1800, TABLE_ALT, bold=True)
    doc.add_paragraph()

    # Findings ───────────────────────────────────────────────────────────────
    for level, items, bg, border, icon in [
        ("Critical Findings",   crit, CRITICAL_BG, CRIT_BORDER, "🔴"),
        ("Warnings",            warn, WARNING_BG,  WARN_BORDER,  "⚠️"),
        ("Recommendations",     sugg, SUGGEST_BG,  SUGG_BORDER,  "💡"),
    ]:
        doc.add_heading(f"{icon} {level} ({len(items)})", level=2)
        if not items:
            p = doc.add_paragraph("✅  No issues found in this category.")
            p.runs[0].font.color.rgb = _rgb("70AD47")
        else:
            tbl = doc.add_table(rows=1 + len(items), cols=2)
            tbl.style = "Table Grid"
            _header_cell(tbl.cell(0, 0), "Area",    2000)
            _header_cell(tbl.cell(0, 1), "Finding", 6000)
            for i, (area, body) in enumerate(items):
                _data_cell(tbl.cell(i + 1, 0), area, 2000, bg, bold=True)
                _data_cell(tbl.cell(i + 1, 1), body, 6000, bg)
        doc.add_paragraph()

    # Paused tags & orphan triggers ──────────────────────────────────────────
    if paused:
        doc.add_heading("⏸ Paused Tags", level=2)
        tbl = doc.add_table(rows=1 + len(paused), cols=2)
        tbl.style = "Table Grid"
        _header_cell(tbl.cell(0, 0), "Tag Name", 4000)
        _header_cell(tbl.cell(0, 1), "Type",     4000)
        for i, t in enumerate(paused):
            _data_cell(tbl.cell(i + 1, 0), t.get("name", "—"), 4000, WARNING_BG)
            _data_cell(tbl.cell(i + 1, 1), t.get("type", "—"), 4000, WARNING_BG)
        doc.add_paragraph()

    if orphans:
        doc.add_heading("👻 Orphan Triggers", level=2)
        tbl = doc.add_table(rows=1 + len(orphans), cols=2)
        tbl.style = "Table Grid"
        _header_cell(tbl.cell(0, 0), "Trigger Name", 4000)
        _header_cell(tbl.cell(0, 1), "Type",          4000)
        for i, tr in enumerate(orphans):
            _data_cell(tbl.cell(i + 1, 0), tr.get("name", "—"), 4000, WARNING_BG)
            _data_cell(tbl.cell(i + 1, 1), tr.get("type", "—"), 4000, WARNING_BG)
        doc.add_paragraph()

    # Footer note ─────────────────────────────────────────────────────────────
    p = doc.add_paragraph(
        f"Report generated {audit_date} by {author_name} · {author_title} · {author_email}"
    )
    p.runs[0].font.size = Pt(8)
    p.runs[0].font.color.rgb = _rgb(TEXT_MUTED)

    # Save ────────────────────────────────────────────────────────────────────
    out = Path(output_filename)
    doc.save(out)
    shared_state.add_report_path(str(out))

    return (
        f"docx report saved: {out.resolve()}\n\n"
        f"  Critical : {len(crit)}\n"
        f"  Warnings : {len(warn)}\n"
        f"  Suggestions: {len(sugg)}\n"
        f"  Health Score: {score}/100 ({_health_label(score)})\n\n"
        "Use generate_html_report() or generate_markdown_report() "
        "to export additional formats."
    )


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC TOOL: generate_html_report  (.html)
# ══════════════════════════════════════════════════════════════════════════════

def generate_html_report(output_filename: str = "") -> str:
    """
    Generates a standalone, print-ready HTML audit report.

    The HTML file is fully self-contained (no external dependencies) and opens
    directly in any browser. It includes collapsible finding sections,
    a health-score gauge, colour-coded severity cards, and print-friendly CSS.

    Args:
        output_filename: Path for the output .html file.
                         Defaults to 'GTM_Audit_<container-id>_<date>.html'.

    Returns:
        Success message with the file path, or an error string.
    """
    result = _load_state()
    if isinstance(result, str):
        return result
    gtm_raw, analysis, author = result

    meta    = _container_meta(gtm_raw)
    summary = analysis.get("summary", "")
    crit, warn, sugg = _parse_findings(summary)
    score   = _health_score(len(crit), len(warn), len(sugg))

    author_name  = author.get("name")  or "GTM Audit Specialist"
    author_title = author.get("title") or "Analytics Consultant"
    author_email = author.get("email") or ""
    audit_date   = datetime.now().strftime("%Y-%m-%d")
    month_year   = datetime.now().strftime("%B %Y")

    if not output_filename:
        output_filename = f"GTM_Audit_{meta['id']}_{audit_date}.html"

    tags      = meta["tags"]
    triggers  = meta["triggers"]
    variables = meta["variables"]
    folders   = meta["folders"]

    paused   = [t for t in tags if t.get("paused", False)]
    used_ids: set[str] = set()
    for t in tags:
        used_ids.update(t.get("firingTriggerId", []))
        used_ids.update(t.get("blockingTriggerId", []))
    orphans = [
        tr for tr in triggers
        if tr.get("triggerId") not in used_ids and tr.get("type") != "ALWAYS"
    ]

    hc     = f"#{_health_color(score)}"
    hl     = _health_label(score)

    def _finding_rows(items: list[tuple[str, str]], row_class: str) -> str:
        if not items:
            return '<tr><td colspan="2" class="no-issues">✅ No issues found in this category.</td></tr>'
        rows = []
        for area, body in items:
            rows.append(
                f'<tr class="{row_class}">'
                f'<td class="area-cell"><strong>{_esc(area)}</strong></td>'
                f'<td>{_esc(body)}</td>'
                f'</tr>'
            )
        return "\n".join(rows)

    def _esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )

    def _section(title: str, icon: str, count: int, items: list, row_class: str, section_id: str) -> str:
        badge_class = "badge-critical" if "Critical" in title else (
            "badge-warning" if "Warning" in title else "badge-suggestion"
        )
        return f"""
        <section class="findings-section" id="{section_id}">
          <div class="section-header" onclick="toggleSection('{section_id}')">
            <span class="section-icon">{icon}</span>
            <h2>{_esc(title)}</h2>
            <span class="badge {badge_class}">{count}</span>
            <span class="chevron" id="chev-{section_id}">▼</span>
          </div>
          <div class="section-body" id="body-{section_id}">
            <table class="findings-table">
              <thead>
                <tr><th style="width:25%">Area</th><th>Finding</th></tr>
              </thead>
              <tbody>
                {_finding_rows(items, row_class)}
              </tbody>
            </table>
          </div>
        </section>"""

    def _mini_table(rows_data: list[tuple[str, str]]) -> str:
        rows = "".join(
            f'<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>'
            for k, v in rows_data
        )
        return f'<table class="meta-table">{rows}</table>'

    def _tag_list(items: list[dict], key1: str = "name", key2: str = "type") -> str:
        if not items:
            return '<p class="no-issues">✅ None found.</p>'
        rows = "".join(
            f'<tr><td>{_esc(t.get(key1, "—"))}</td><td>{_esc(t.get(key2, "—"))}</td></tr>'
            for t in items
        )
        return f'<table class="findings-table"><thead><tr><th>Name</th><th>Type</th></tr></thead><tbody>{rows}</tbody></table>'

    stroke_dash = max(0, 100 - score)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GTM Audit — {_esc(meta['name'])} — {audit_date}</title>
  <style>
    :root {{
      --brand-dark:  #{BRAND_DARK};
      --brand-mid:   #{BRAND_MID};
      --brand-light: #{BRAND_LIGHT};
      --crit:        #C00000;
      --crit-bg:     #FFE0E0;
      --warn:        #ED7D31;
      --warn-bg:     #FFF2CC;
      --sugg:        #70AD47;
      --sugg-bg:     #E2EFDA;
      --text:        #1A1A1A;
      --muted:       #595959;
      --white:       #FFFFFF;
      --radius:      10px;
    }}

    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: #F0F4F8;
      color: var(--text);
      line-height: 1.6;
    }}

    /* ── Cover ─────────────────────────────────────────── */
    .cover {{
      background: linear-gradient(135deg, var(--brand-dark) 0%, var(--brand-mid) 100%);
      color: var(--white);
      padding: 60px 48px 48px;
      position: relative;
      overflow: hidden;
    }}
    .cover::before {{
      content: '';
      position: absolute;
      top: -80px; right: -80px;
      width: 320px; height: 320px;
      background: rgba(255,255,255,.06);
      border-radius: 50%;
    }}
    .cover-label {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: rgba(255,255,255,.6);
      margin-bottom: 12px;
    }}
    .cover h1 {{
      font-size: 38px;
      font-weight: 800;
      line-height: 1.15;
      margin-bottom: 8px;
    }}
    .cover-sub {{
      font-size: 16px;
      color: rgba(255,255,255,.75);
      margin-bottom: 4px;
    }}
    .cover-meta {{
      margin-top: 32px;
      font-size: 13px;
      color: rgba(255,255,255,.55);
      border-top: 1px solid rgba(255,255,255,.15);
      padding-top: 16px;
    }}

    /* ── Wrapper ───────────────────────────────────────── */
    .page {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px 80px; }}

    /* ── Dashboard ─────────────────────────────────────── */
    .dashboard {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin: 32px 0;
    }}
    .dash-card {{
      background: var(--white);
      border-radius: var(--radius);
      padding: 24px 20px;
      text-align: center;
      box-shadow: 0 2px 8px rgba(0,0,0,.08);
      border-top: 4px solid var(--brand-mid);
      transition: transform .15s;
    }}
    .dash-card:hover {{ transform: translateY(-2px); }}
    .dash-card.critical  {{ border-top-color: var(--crit); }}
    .dash-card.warning   {{ border-top-color: var(--warn); }}
    .dash-card.suggestion{{ border-top-color: var(--sugg); }}
    .dash-card .label {{
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .dash-card .value {{
      font-size: 36px;
      font-weight: 800;
      line-height: 1;
    }}
    .dash-card.critical  .value {{ color: var(--crit); }}
    .dash-card.warning   .value {{ color: var(--warn); }}
    .dash-card.suggestion .value {{ color: var(--sugg); }}
    .dash-card .sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}

    /* Health gauge */
    .gauge-wrap {{
      display: flex; flex-direction: column; align-items: center;
    }}
    .gauge-wrap svg {{ width: 90px; height: 90px; }}
    .gauge-text {{
      font-size: 28px;
      font-weight: 800;
      fill: {hc};
      dominant-baseline: middle;
      text-anchor: middle;
    }}
    .gauge-label {{
      font-size: 11px;
      fill: var(--muted);
      dominant-baseline: middle;
      text-anchor: middle;
    }}

    /* ── Section card ──────────────────────────────────── */
    .findings-section {{
      background: var(--white);
      border-radius: var(--radius);
      margin-bottom: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,.07);
      overflow: hidden;
    }}
    .section-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 18px 24px;
      cursor: pointer;
      user-select: none;
      background: var(--white);
      border-bottom: 1px solid #EEE;
      transition: background .1s;
    }}
    .section-header:hover {{ background: #F7F9FB; }}
    .section-icon {{ font-size: 20px; }}
    .section-header h2 {{
      flex: 1;
      font-size: 16px;
      font-weight: 700;
      color: var(--brand-dark);
    }}
    .badge {{
      padding: 3px 12px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 700;
    }}
    .badge-critical   {{ background: var(--crit-bg); color: var(--crit); }}
    .badge-warning    {{ background: var(--warn-bg);  color: var(--warn); }}
    .badge-suggestion {{ background: var(--sugg-bg);  color: var(--sugg); }}
    .chevron {{ color: var(--muted); font-size: 14px; transition: transform .2s; }}
    .chevron.open {{ transform: rotate(180deg); }}
    .section-body {{ padding: 0 24px 24px; }}

    /* ── Tables ─────────────────────────────────────────── */
    .findings-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      margin-top: 16px;
    }}
    .findings-table th {{
      background: var(--brand-dark);
      color: var(--white);
      padding: 10px 14px;
      text-align: left;
      font-size: 12px;
      letter-spacing: .5px;
    }}
    .findings-table td {{
      padding: 10px 14px;
      border-bottom: 1px solid #EEE;
      vertical-align: top;
    }}
    .findings-table tr:last-child td {{ border-bottom: none; }}
    .area-cell {{ font-size: 13px; white-space: nowrap; }}
    tr.row-critical  td {{ background: var(--crit-bg); }}
    tr.row-warning   td {{ background: var(--warn-bg); }}
    tr.row-suggestion td {{ background: var(--sugg-bg); }}
    tr.row-paused    td {{ background: var(--warn-bg); }}
    .meta-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      margin-top: 16px;
    }}
    .meta-table th {{
      width: 30%;
      background: #EBF3FB;
      padding: 9px 14px;
      text-align: left;
      font-weight: 600;
      border: 1px solid #D6E4F0;
    }}
    .meta-table td {{
      padding: 9px 14px;
      border: 1px solid #D6E4F0;
    }}
    .no-issues {{
      color: var(--sugg);
      font-weight: 600;
      padding: 16px 0;
    }}

    /* ── Stats strip ───────────────────────────────────── */
    .stats-strip {{
      display: flex;
      gap: 12px;
      margin: 16px 0;
      flex-wrap: wrap;
    }}
    .stat-pill {{
      background: #EBF3FB;
      border: 1px solid #D6E4F0;
      border-radius: 20px;
      padding: 6px 16px;
      font-size: 14px;
      font-weight: 600;
      color: var(--brand-dark);
    }}

    /* ── Section title ─────────────────────────────────── */
    .page-section {{ margin: 40px 0 16px; }}
    .page-section h2 {{
      font-size: 18px;
      font-weight: 700;
      color: var(--brand-dark);
      padding-bottom: 8px;
      border-bottom: 2px solid var(--brand-light);
    }}

    /* ── Footer ─────────────────────────────────────────── */
    footer {{
      text-align: center;
      font-size: 12px;
      color: var(--muted);
      margin-top: 60px;
      padding-top: 24px;
      border-top: 1px solid #DDD;
    }}

    /* ── Print ───────────────────────────────────────────── */
    @media print {{
      body {{ background: white; }}
      .cover {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
      .section-body {{ display: block !important; }}
      .chevron, .section-header {{ cursor: default; }}
      .dash-card {{ break-inside: avoid; }}
      .findings-section {{ break-inside: avoid; box-shadow: none; border: 1px solid #DDD; }}
    }}
  </style>
</head>
<body>

<!-- Cover -->
<div class="cover">
  <p class="cover-label">Google Tag Manager — Audit Report</p>
  <h1>{_esc(meta['name'])}</h1>
  <p class="cover-sub">{_esc(meta['id'])}</p>
  <p class="cover-sub">{month_year}</p>
  <div class="cover-meta">
    Prepared by <strong>{_esc(author_name)}</strong> · {_esc(author_title)} · {_esc(author_email)}
    &nbsp;|&nbsp; Audit Date: {audit_date}
  </div>
</div>

<div class="page">

  <!-- Dashboard -->
  <div class="page-section">
    <h2>Executive Summary</h2>
  </div>

  <div class="dashboard">

    <!-- Health gauge card -->
    <div class="dash-card">
      <div class="label">Health Score</div>
      <div class="gauge-wrap">
        <svg viewBox="0 0 36 36">
          <path d="M18 2 a 16 16 0 0 1 0 32 a 16 16 0 0 1 0 -32"
            fill="none" stroke="#EEE" stroke-width="3.5"/>
          <path d="M18 2 a 16 16 0 0 1 0 32 a 16 16 0 0 1 0 -32"
            fill="none"
            stroke="{hc}"
            stroke-width="3.5"
            stroke-dasharray="{score} 100"
            stroke-linecap="round"
            transform="rotate(-90 18 18)"/>
          <text x="18" y="18" class="gauge-text">{score}</text>
          <text x="18" y="25" class="gauge-label">{hl}</text>
        </svg>
      </div>
    </div>

    <div class="dash-card critical">
      <div class="label">Critical</div>
      <div class="value">{len(crit)}</div>
      <div class="sub">Must fix</div>
    </div>

    <div class="dash-card warning">
      <div class="label">Warnings</div>
      <div class="value">{len(warn)}</div>
      <div class="sub">Should fix</div>
    </div>

    <div class="dash-card suggestion">
      <div class="label">Suggestions</div>
      <div class="value">{len(sugg)}</div>
      <div class="sub">Nice to have</div>
    </div>

    <div class="dash-card">
      <div class="label">Audit Date</div>
      <div class="value" style="font-size:22px;color:var(--brand-dark)">{audit_date}</div>
      <div class="sub">{month_year}</div>
    </div>

  </div>

  <!-- Container Info -->
  <div class="page-section">
    <h2>Container Details</h2>
  </div>

  {_mini_table([
    ("Container Name", meta["name"]),
    ("Container ID",   meta["id"]),
    ("Account ID",     meta["account_id"]),
    ("Usage Context",  meta["contexts"]),
    ("Exported",       meta["export_ts"]),
  ])}

  <div class="stats-strip" style="margin-top:20px">
    <span class="stat-pill">🏷 {len(tags)} Tags</span>
    <span class="stat-pill">⚡ {len(triggers)} Triggers</span>
    <span class="stat-pill">📦 {len(variables)} Variables</span>
    <span class="stat-pill">📁 {len(folders)} Folders</span>
    <span class="stat-pill">⏸ {len(paused)} Paused</span>
    <span class="stat-pill">👻 {len(orphans)} Orphan Triggers</span>
  </div>

  <!-- Findings -->
  <div class="page-section">
    <h2>Audit Findings</h2>
  </div>

  {_section("Critical Findings", "🔴", len(crit), crit, "row-critical", "sec-crit")}
  {_section("Warnings", "⚠️", len(warn), warn, "row-warning", "sec-warn")}
  {_section("Suggestions", "💡", len(sugg), sugg, "row-suggestion", "sec-sugg")}

  <!-- Paused Tags -->
  <div class="page-section">
    <h2>⏸ Paused Tags ({len(paused)})</h2>
  </div>
  <div class="findings-section">
    <div class="section-body" style="padding:24px">
      {_tag_list(paused)}
    </div>
  </div>

  <!-- Orphan Triggers -->
  <div class="page-section">
    <h2>👻 Orphan Triggers ({len(orphans)})</h2>
  </div>
  <div class="findings-section">
    <div class="section-body" style="padding:24px">
      {_tag_list(orphans, key1="name", key2="type")}
    </div>
  </div>

  <footer>
    GTM Audit Report · {_esc(meta['name'])} ({_esc(meta['id'])}) ·
    {audit_date} · {_esc(author_name)} · {_esc(author_title)}
    {f'· {_esc(author_email)}' if author_email else ''}
  </footer>
</div>

<script>
  function toggleSection(id) {{
    const body  = document.getElementById('body-' + id);
    const chev  = document.getElementById('chev-' + id);
    const open  = body.style.display !== 'none' && body.style.display !== '';
    body.style.display = open ? 'none' : 'block';
    chev.classList.toggle('open', !open);
  }}
  // Open all sections by default
  document.querySelectorAll('.section-body').forEach(el => {{
    el.style.display = 'block';
  }});
  document.querySelectorAll('.chevron').forEach(el => {{
    el.classList.add('open');
  }});
</script>

</body>
</html>"""

    out = Path(output_filename)
    out.write_text(html, encoding="utf-8")
    shared_state.add_report_path(str(out))

    return (
        f"HTML report saved: {out.resolve()}\n\n"
        f"  Open in any browser — sections are collapsible, print-ready.\n"
        f"  Critical: {len(crit)}  |  Warnings: {len(warn)}  |  Suggestions: {len(sugg)}\n"
        f"  Health Score: {score}/100 ({hl})\n\n"
        "Tip: Use Ctrl+P in your browser to print or save as PDF."
    )


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC TOOL: generate_markdown_report  (.md)
# ══════════════════════════════════════════════════════════════════════════════

def generate_markdown_report(output_filename: str = "") -> str:
    """
    Generates a portable Markdown audit report (.md) designed for:
      • Pasting into future AI conversations for further analysis
      • Committing to a repository alongside the GTM JSON
      • Sharing via Slack, Notion, GitHub, or any Markdown renderer

    The report uses GitHub-Flavored Markdown (tables, task lists, badges).

    Args:
        output_filename: Path for the output .md file.
                         Defaults to 'GTM_Audit_<container-id>_<date>.md'.

    Returns:
        Success message with the file path, or an error string.
    """
    result = _load_state()
    if isinstance(result, str):
        return result
    gtm_raw, analysis, author = result

    meta    = _container_meta(gtm_raw)
    summary = analysis.get("summary", "")
    crit, warn, sugg = _parse_findings(summary)
    score   = _health_score(len(crit), len(warn), len(sugg))

    author_name  = author.get("name")  or "GTM Audit Specialist"
    author_title = author.get("title") or "Analytics Consultant"
    author_email = author.get("email") or ""
    audit_date   = datetime.now().strftime("%Y-%m-%d")
    month_year   = datetime.now().strftime("%B %Y")

    if not output_filename:
        output_filename = f"GTM_Audit_{meta['id']}_{audit_date}.md"

    tags      = meta["tags"]
    triggers  = meta["triggers"]
    variables = meta["variables"]
    folders   = meta["folders"]

    paused   = [t for t in tags if t.get("paused", False)]
    used_ids: set[str] = set()
    for t in tags:
        used_ids.update(t.get("firingTriggerId", []))
        used_ids.update(t.get("blockingTriggerId", []))
    orphans = [
        tr for tr in triggers
        if tr.get("triggerId") not in used_ids and tr.get("type") != "ALWAYS"
    ]

    hl = _health_label(score)

    def _finding_table(items: list[tuple[str, str]], icon: str) -> str:
        if not items:
            return "✅ No issues found.\n"
        rows = [
            "| Area | Finding |",
            "|------|---------|",
        ]
        for area, body in items:
            rows.append(f"| `{area}` | {body} |")
        return "\n".join(rows) + "\n"

    def _checklist(items: list[tuple[str, str]]) -> str:
        if not items:
            return "*(none)*\n"
        return "\n".join(f"- [ ] **{area}**: {body}" for area, body in items) + "\n"

    def _small_table(items: list[dict], k1: str = "name", k2: str = "type") -> str:
        if not items:
            return "*(none)*\n"
        rows = [
            "| Name | Type |",
            "|------|------|",
        ] + [f"| {t.get(k1, '—')} | {t.get(k2, '—')} |" for t in items]
        return "\n".join(rows) + "\n"

    md = f"""# GTM Audit Report — {meta['name']}

> **Container:** `{meta['id']}` &nbsp;|&nbsp; **Audit Date:** {audit_date} &nbsp;|&nbsp; **Auditor:** {author_name}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Health Score** | {score}/100 — {hl} |
| 🔴 Critical | {len(crit)} |
| ⚠️ Warnings | {len(warn)} |
| 💡 Suggestions | {len(sugg)} |
| Audit Date | {audit_date} |
| Prepared By | {author_name} · {author_title}{f' · {author_email}' if author_email else ''} |

---

## Container Details

| Field | Value |
|-------|-------|
| Container Name | {meta['name']} |
| Container ID | `{meta['id']}` |
| Account ID | `{meta['account_id']}` |
| Usage Context | {meta['contexts']} |
| Exported | {meta['export_ts']} |

### Inventory

| Component | Count |
|-----------|-------|
| 🏷 Tags | {len(tags)} |
| ⚡ Triggers | {len(triggers)} |
| 📦 Variables | {len(variables)} |
| 📁 Folders | {len(folders)} |
| ⏸ Paused Tags | {len(paused)} |
| 👻 Orphan Triggers | {len(orphans)} |

---

## 🔴 Critical Findings ({len(crit)})

{_finding_table(crit, "🔴")}

---

## ⚠️ Warnings ({len(warn)})

{_finding_table(warn, "⚠️")}

---

## 💡 Suggestions ({len(sugg)})

{_finding_table(sugg, "💡")}

---

## ⏸ Paused Tags

{_small_table(paused)}

---

## 👻 Orphan Triggers

{_small_table(orphans)}

---

## ✅ Remediation Checklist

> Copy this checklist into your project management tool to track fixes.

### Critical (fix immediately)
{_checklist(crit)}

### Warnings (fix in next sprint)
{_checklist(warn)}

### Suggestions (backlog)
{_checklist(sugg)}

---

## Raw Audit Output

<details>
<summary>Click to expand full audit text</summary>

```
{summary}
```

</details>

---

*Generated {audit_date} by {author_name} using GTM Analyst ADK Agent.*
*Container: {meta['name']} ({meta['id']}) — {month_year}*
"""

    out = Path(output_filename)
    out.write_text(md, encoding="utf-8")
    shared_state.add_report_path(str(out))

    return (
        f"Markdown report saved: {out.resolve()}\n\n"
        f"  Paste this .md file into any future Claude conversation\n"
        f"  to continue analysis with full context already loaded.\n\n"
        f"  Critical: {len(crit)}  |  Warnings: {len(warn)}  |  Suggestions: {len(sugg)}\n"
        f"  Health Score: {score}/100 ({hl})"
    )
