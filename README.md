# GTM Analyst v2 — ADK Audit Agent

AI-powered Google Tag Manager audit system built with Google ADK.
Load a GTM JSON export **from disk or by pasting directly in the chat** and get reports in three formats.

---

## What's New in v2

| Feature | v1 | v2 |
|---------|----|----|
| Load JSON from disk | ✅ | ✅ |
| **Paste JSON into chat** | ❌ | ✅ `load_gtm_from_content()` |
| .docx report | ✅ | ✅ improved |
| **.html report** | ❌ | ✅ collapsible, print-ready |
| **.md report** | ❌ | ✅ paste into AI conversations |
| Health score gauge | ❌ | ✅ 0–100 with label |
| Shared state clears on new file load | ❌ | ✅ |
| Report path tracking | ❌ | ✅ |

---

## Folder Structure

```
gtm_audit_project/             ← run ALL adk commands from here
│
├── requirements.txt
│
└── gtm_analyst/
    ├── __init__.py
    ├── agent.py               ← root_agent + 3 sub-agents (v2)
    ├── shared_state.py        ← persistent state store (v2)
    ├── .env                   ← your API key
    ├── .env.example
    │
    └── tools/
        ├── __init__.py
        ├── file_tools.py      ← list_gtm_files · load_gtm_file · load_gtm_from_content
        ├── analyzer_tools.py  ← audit_tags · audit_triggers · run_full_audit …
        └── report_tools.py    ← set_report_author · generate_audit_report
                                    · generate_html_report · generate_markdown_report
```

---

## Agent Architecture

```
root_agent (gtm_analyst)
│  Orchestrates the full audit workflow
│
├── file_reader
│     Tools: list_gtm_files · load_gtm_file · load_gtm_from_content
│     Job: load the GTM JSON (from file OR from pasted chat content)
│
├── gtm_analyzer
│     Tools: get_container_statistics · audit_tags · audit_triggers
│            audit_variables · audit_consent · run_full_audit
│     Job: validate the container against the GTM audit checklist
│
└── report_maker
      Tools: set_report_author · generate_audit_report
             generate_html_report · generate_markdown_report
      Job: produce reports in .docx, .html, and .md formats
```

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API key
```bash
cp gtm_analyst/.env.example gtm_analyst/.env
# Edit .env and set GOOGLE_API_KEY
```

---

## Running

Always run from **`gtm_audit_project/`** (the parent folder):

```bash
adk web        # Browser UI at http://localhost:8000 (recommended)
adk run gtm_analyst
```

---

## Loading a GTM File

### Option A — From disk (as before)
```
You: Load the file at ./samples/GTM-ABC123.json
```

### Option B — Paste JSON directly into the chat (NEW in v2)
```
You: Here is my GTM JSON export:
     { "containerVersion": { ... } }  ← paste the full content
```
The agent will call `load_gtm_from_content()` automatically.

---

## Report Formats

After the audit you can generate **all three formats at once**:

| Format | Best for |
|--------|----------|
| `.docx` | Sending to clients, Word review |
| `.html` | Opening in browser, printing to PDF, archiving |
| `.md`  | Pasting into a future Claude/AI conversation with full context |

```
You: Generate all three reports. I'm Jane Smith, Analytics Director, jane@agency.com
```

The `.md` report is especially useful for the ATE project — paste it into
a supervisor agent or a new conversation to continue analysis with the full
audit context already present.

---

## Typical Conversation

```
You:   Here is my GTM export: { "containerVersion": ... }

Agent: Loaded: My Container (GTM-ABC123) — 87 tags, 64 triggers, 42 variables ✅

You:   Run the full audit

Agent: 🔴 Critical (3): UA legacy tags, duplicate GA4 config, missing consent
       ⚠️  Warnings (8): orphan triggers, broad click triggers ...
       💡 Suggestions (12): naming conventions, unused variables ...
       Health Score: 62/100 (Fair)

You:   Generate all three reports. I'm Jane Smith, Analytics Director, jane@co.com

Agent: ✅ GTM_Audit_GTM-ABC123_2026-03-11.docx
       ✅ GTM_Audit_GTM-ABC123_2026-03-11.html  (open in browser or print to PDF)
       ✅ GTM_Audit_GTM-ABC123_2026-03-11.md    (paste into any AI chat)
```

---

## Saving to Another Repository

All generated files land in your current working directory (wherever you ran `adk web`).
To push them to a separate repo:

```bash
# From gtm_audit_project/
cp GTM_Audit_*.* /path/to/your/reports-repo/
cd /path/to/your/reports-repo
git add .
git commit -m "Add GTM audit — GTM-ABC123 — 2026-03-11"
git push
```

Or set `output_filename` to a path inside the target repo:
```
You: Generate the HTML report at ../gtm-reports/GTM_Audit_March2026.html
```
