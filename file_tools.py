"""
File Tools
==========
Tools used by the file_reader sub-agent.

Tools:
  list_gtm_files        — discover JSON files on disk
  load_gtm_file         — load from a local file path
  load_gtm_from_content — load from raw JSON text (paste / upload from chat)
"""
from __future__ import annotations
import json
from pathlib import Path

from .. import shared_state


# ── Helper ────────────────────────────────────────────────────────────────────

def _summarise_container(raw: dict, source_label: str) -> str:
    """Return a human-readable summary card for a loaded GTM container."""
    cv        = raw.get("containerVersion", {})
    container = cv.get("container", {})
    name      = container.get("name", "Unknown")
    public_id = container.get("publicId", "Unknown")
    account   = container.get("accountId", "Unknown")
    contexts  = ", ".join(container.get("usageContext", ["Unknown"]))
    export_ts = raw.get("exportTime", "Unknown")

    tags      = cv.get("tag",      [])
    triggers  = cv.get("trigger",  [])
    variables = cv.get("variable", [])
    folders   = cv.get("folder",   [])

    return (
        f"GTM file loaded: {source_label}\n\n"
        f"Container : {name}\n"
        f"ID        : {public_id}\n"
        f"Account   : {account}\n"
        f"Context   : {contexts}\n"
        f"Exported  : {export_ts}\n\n"
        f"Tags      : {len(tags)}\n"
        f"Triggers  : {len(triggers)}\n"
        f"Variables : {len(variables)}\n"
        f"Folders   : {len(folders)}\n\n"
        "The file is now loaded and ready for analysis.\n"
        "Ask the gtm_analyzer to run the full audit."
    )


# ── Public tools ──────────────────────────────────────────────────────────────

def list_gtm_files(directory: str = ".") -> str:
    """
    Lists all JSON files in the given directory that could be GTM exports.

    Args:
        directory: Folder path to search. Defaults to the current working directory.

    Returns:
        A plain-text list of found JSON files with their sizes,
        or a message if none are found.
    """
    path = Path(directory)
    if not path.exists():
        return f"Directory '{directory}' does not exist."

    files = sorted(path.glob("*.json"))
    if not files:
        return (
            f"No JSON files found in '{directory}'.\n\n"
            "Tip: You can also paste the raw JSON content directly into the chat\n"
            "and ask the file_reader to load it from content."
        )

    lines = [f"Found {len(files)} JSON file(s) in '{directory}':"]
    for i, f in enumerate(files, 1):
        kb = f.stat().st_size / 1024
        lines.append(f"  {i}. {f.name}  ({kb:.1f} KB)")
    lines.append(
        "\nTip: You can also paste the raw JSON content directly into the chat\n"
        "and ask the file_reader to load it from content."
    )
    return "\n".join(lines)


def load_gtm_file(filepath: str) -> str:
    """
    Reads and validates a GTM container JSON export file from disk,
    then stores it in shared state so other agents can access it.

    Args:
        filepath: Full or relative path to the GTM JSON file.

    Returns:
        A summary card of the container on success, or an error message.
    """
    path = Path(filepath)
    if not path.exists():
        return (
            f"File not found: '{filepath}'.\n"
            "Use list_gtm_files() to see available files, or paste the JSON "
            "content directly and use load_gtm_from_content()."
        )

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON in '{filepath}': {exc}"
    except OSError as exc:
        return f"Could not read '{filepath}': {exc}"

    if not raw.get("containerVersion"):
        return (
            f"'{filepath}' does not look like a GTM export "
            "(missing 'containerVersion' key). "
            "Please export the container from GTM > Admin > Export Container."
        )

    shared_state.set_gtm_data(path.name, raw)
    return _summarise_container(raw, path.name)


def load_gtm_from_content(json_content: str) -> str:
    """
    Loads a GTM container directly from raw JSON text.

    Use this when the user pastes the JSON content into the chat window
    instead of providing a file path.  The content is validated and stored
    in shared state exactly like load_gtm_file().

    Args:
        json_content: The raw JSON string of a GTM container export.
                      Must contain a 'containerVersion' key at the top level.

    Returns:
        A summary card of the container on success, or a descriptive error.

    Example:
        User pastes the entire contents of their GTM JSON export.
        Then says: "Load this GTM JSON" — the agent calls this tool
        with the pasted text as json_content.
    """
    if not json_content or not json_content.strip():
        return (
            "No content provided.  Please paste the full JSON content of your "
            "GTM container export and try again."
        )

    # Strip common wrapping (markdown code fences, BOM, etc.)
    content = json_content.strip()
    if content.startswith("```"):
        # Remove ```json ... ``` or ``` ... ```
        lines = content.splitlines()
        content = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )
    # Remove UTF-8 BOM if present
    content = content.lstrip("\ufeff").strip()

    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        return (
            f"Invalid JSON content: {exc}\n\n"
            "Make sure you pasted the complete, unmodified GTM export JSON.\n"
            "In GTM: Admin → Export Container → select version → Export."
        )

    if not raw.get("containerVersion"):
        return (
            "The pasted content does not look like a GTM export "
            "(missing 'containerVersion' key).\n"
            "In GTM: Admin → Export Container → select a version → Export.\n"
            "Paste the entire contents of the downloaded .json file."
        )

    # Use container ID as the label since there's no filename
    cv        = raw.get("containerVersion", {})
    container = cv.get("container", {})
    public_id = container.get("publicId", "pasted-content")
    label     = f"{public_id}_from_chat.json"

    shared_state.set_gtm_data(label, raw)
    return _summarise_container(raw, label)
