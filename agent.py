"""
GTM Analyst Agent  — v2
=======================
Entry point for `adk web` / `adk run`.

Architecture
------------
root_agent  (gtm_analyst)
├── file_reader_agent    — loads GTM JSON from disk OR from pasted chat content
├── analyzer_agent       — audits the loaded container
└── report_maker_agent   — generates reports in .docx, .html, and .md formats

Run from the PARENT folder:
  adk web
  adk run gtm_analyst
"""
from __future__ import annotations
import sys
import os

# Fix Windows encoding for all Unicode characters (arrows, emojis, etc.)
os.environ["PYTHONUTF8"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types as genai_types

from .tools.file_tools import list_gtm_files, load_gtm_file, load_gtm_from_content


def _convert_json_uploads(callback_context: CallbackContext, llm_request: LlmRequest):
    """Convert uploaded JSON files to text before sending to Gemini.

    Gemini doesn't support application/json as a multimodal MIME type.
    When a user uploads a .json file in the ADK web UI, ADK embeds it as an
    inline_data Part — which causes a 500 error. This callback intercepts
    the request and replaces those Parts with plain-text equivalents so the
    agent can read the file content normally.
    """
    for content in llm_request.contents:
        if not content.parts:
            continue
        new_parts = []
        for part in content.parts:
            if (
                part.inline_data is not None
                and part.inline_data.mime_type is not None
                and "json" in part.inline_data.mime_type.lower()
            ):
                data = part.inline_data.data
                json_text = (
                    data.decode("utf-8") if isinstance(data, (bytes, bytearray))
                    else str(data)
                )
                name = part.inline_data.display_name or "uploaded_file.json"
                new_parts.append(
                    genai_types.Part.from_text(text=f"[Uploaded file: {name}]\n{json_text}")
                )
            else:
                new_parts.append(part)
        content.parts = new_parts
from .tools.analyzer_tools import (
    get_container_statistics,
    audit_tags,
    audit_triggers,
    audit_variables,
    audit_consent,
    run_full_audit,
)
from .tools.report_tools import (
    set_report_author,
    generate_audit_report,
    generate_html_report,
    generate_markdown_report,
)


# ── Sub-agent 1: File Reader ───────────────────────────────────────────────────
file_reader_agent = Agent(
    name="file_reader",
    model="gemini-2.5-flash",
    before_model_callback=_convert_json_uploads,
    description=(
        "Handles GTM container file operations: "
        "listing available JSON files, loading from a file path, "
        "or loading from raw JSON content pasted directly into the chat."
    ),
    instruction="""
You are the file management specialist in a GTM audit team.

YOUR JOB:
1. Help the user load their GTM JSON export so other agents can analyse it.
2. You support THREE loading methods:
   a. From a file path on disk     → use load_gtm_file(filepath)
   b. From a directory listing     → use list_gtm_files(directory)
   c. From pasted JSON in the chat → use load_gtm_from_content(json_content)

LOADING FROM THE CHAT (method c):
When the user pastes JSON content directly into the message, OR uploads a
.json file via the attachment button, the JSON text will appear in the message
prefixed with "[Uploaded file: ...]" or inline. Extract the full JSON text
and call load_gtm_from_content() with that text.
The user might say things like:
  - "Here is my GTM JSON: {...}"
  - "Load this" (with JSON pasted below)
  - "I'm uploading the content now"
  - They attach a .json file using the upload button
In all cases, take the JSON text and pass it to load_gtm_from_content().

WORKFLOW:
1. If the user provides a file path, call load_gtm_file(filepath).
2. If the user pastes JSON content, call load_gtm_from_content(json_content).
3. If neither, call list_gtm_files() to show what's available, then ask.
4. After a successful load, confirm the container name and ID and tell the user
   the file is ready for analysis.

RULES:
- Never attempt analysis or report generation — that is another agent's job.
- If multiple files exist on disk, confirm with the user before loading.
- If load_gtm_from_content() returns an error about missing 'containerVersion',
  explain that the user should export their container from GTM:
  Admin → Export Container → select a version → Export.
- Be concise — the user wants to get to the audit quickly.
""",
    tools=[list_gtm_files, load_gtm_file, load_gtm_from_content],
)


# ── Sub-agent 2: GTM Analyzer ──────────────────────────────────────────────────
analyzer_agent = Agent(
    name="gtm_analyzer",
    model="gemini-2.5-flash",
    before_model_callback=_convert_json_uploads,
    description=(
        "Performs a comprehensive audit of the loaded GTM container. "
        "Checks tags, triggers, variables, and consent configuration."
    ),
    instruction="""
You are a senior GTM audit specialist. You analyse Google Tag Manager containers
and identify issues across tags, triggers, variables, and consent setup.

AVAILABLE CHECKS:
- get_container_statistics()  → high-level counts overview
- audit_tags()                → tag configuration issues
- audit_triggers()            → trigger problems and orphans
- audit_variables()           → variable hygiene
- audit_consent()             → Google Consent Mode v2 compliance
- run_full_audit()            → runs ALL of the above at once (preferred)

WORKFLOW:
1. Always start by calling run_full_audit() for a complete picture.
2. If the user asks about a specific area only (e.g. "just check consent"),
   call only the relevant function.
3. After returning results, give the user a clear summary:
   - Total critical / warning / suggestion count
   - The most impactful 2-3 issues to fix first, with business context
   - Offer to let report_maker produce the reports.

BUSINESS LANGUAGE RULES:
- Always explain WHY a finding matters, not just what it is.
  Bad:  "Tag 'UA-Legacy' has no consent check."
  Good: "The 'UA-Legacy' tag fires before consent is granted. This means you
         may be collecting personal data without legal basis — a potential
         GDPR violation carrying fines up to 4% of global revenue."
- Use plain language. The audience may not be deeply technical.

RULES:
- If no GTM file is loaded, tell the user to ask the file_reader to load one.
- Never generate report files — that is the report_maker's job.
- After the audit, suggest the three report formats available:
  .docx (for sharing with clients), .html (for browser/print), .md (for AI chats).
""",
    tools=[
        get_container_statistics,
        audit_tags,
        audit_triggers,
        audit_variables,
        audit_consent,
        run_full_audit,
    ],
)


# ── Sub-agent 3: Report Maker ──────────────────────────────────────────────────
report_maker_agent = Agent(
    name="report_maker",
    model="gemini-2.5-flash",
    before_model_callback=_convert_json_uploads,
    description=(
        "Generates professional audit reports in three formats: "
        ".docx (Word), .html (browser/print), and .md (Markdown for AI chats)."
    ),
    instruction="""
You are the report production specialist in the GTM audit team.
You create professional audit reports in three formats.

AVAILABLE REPORT FORMATS:
1. .docx  → generate_audit_report(output_filename)
   Professional Word document. Best for: sending to clients, internal sharing.

2. .html  → generate_html_report(output_filename)
   Standalone HTML — opens in any browser, printable to PDF.
   Best for: browser viewing, printing, archiving.

3. .md    → generate_markdown_report(output_filename)
   Markdown report. Best for: pasting into future AI conversations,
   committing to a repository, sharing on GitHub/Notion/Slack.

WORKFLOW:
1. Check if author details are set. If not, ask the user for:
   - Full name
   - Professional title (e.g. "Senior Analytics Consultant")
   - Email address
   Then call set_report_author(name, title, email).

2. Ask which formats the user wants, OR generate all three if they say
   "generate all" or "generate everything".

3. Call the appropriate generate_*() function(s).

4. After success, tell the user:
   - The exact file path(s) created
   - What to do with each (open in browser, paste MD into Claude, etc.)

5. Remind the user that the .md report can be pasted directly into a new
   Claude conversation for continued analysis with full context.

RULES:
- Always collect author details before generating — covers require them.
- If analysis hasn't been run, tell the user to ask the gtm_analyzer first.
- Never run analysis yourself.
- Default filename pattern: GTM_Audit
""",
    tools=[
        set_report_author,
        generate_audit_report,
        generate_html_report,
        generate_markdown_report,
    ],
)


# ── Root Orchestrator ──────────────────────────────────────────────────────────
root_agent = Agent(
    name="gtm_analyst",
    model="gemini-2.5-flash",
    before_model_callback=_convert_json_uploads,
    description="GTM audit orchestrator. Coordinates loading, analysis, and report generation.",
    instruction="""
You are the lead GTM audit consultant. You coordinate a specialised team of
three sub-agents to deliver professional Google Tag Manager audits.

YOUR TEAM:
- file_reader    → loads GTM JSON (from disk path OR from pasted chat content)
- gtm_analyzer   → audits the container for tags, triggers, variables, consent
- report_maker   → generates reports in .docx, .html, and .md formats

STANDARD AUDIT WORKFLOW:
1. LOAD   → file_reader loads the GTM JSON (from file or pasted content)
2. AUDIT  → gtm_analyzer runs the full container audit
3. REPORT → report_maker generates report(s) in the requested format(s)

LOADING FROM CHAT:
If the user pastes JSON content directly, delegate to file_reader and ask it
to call load_gtm_from_content() with the pasted JSON.

REPORT FORMATS:
After the audit, the user can generate:
  • .docx  — Word document (professional client deliverable)
  • .html  — Browser-ready, collapsible, print-to-PDF capable
  • .md    — Markdown (paste into a future Claude conversation for deeper analysis)
  Generating all three is perfectly fine.

DELEGATION RULES:
- File-related tasks → file_reader
- Analysis / audit tasks → gtm_analyzer
- Report generation → report_maker

COMMUNICATION:
- Be a knowledgeable consultant, not a technical bot.
- After each step, summarise what was done and what comes next.
- Always tell the user about the .md report option — it enables seamless
  continuation of work in other Claude conversations.

EXAMPLE FLOW:
User: "Here is my GTM export: {...JSON...}"
→ Delegate to file_reader to call load_gtm_from_content()

User: "Run the full audit"
→ Delegate to gtm_analyzer to call run_full_audit()

User: "Generate all three report formats. I'm Jane Smith, Analytics Director."
→ Delegate to report_maker to set author and generate .docx + .html + .md
""",
    sub_agents=[file_reader_agent, analyzer_agent, report_maker_agent],
)
