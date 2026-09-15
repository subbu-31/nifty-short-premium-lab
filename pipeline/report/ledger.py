"""
Renders the confirmed/null/retracted ledger as a markdown table.

Deliberately small: the ledger lives as a single hand-maintained list here
rather than a separate machine-readable registry file kept in sync with the
README by hand -- for a project this size, one source of truth beats
pretending there's automation keeping two files aligned (see the repo
structure discussion in the project history: a registry.yaml was
considered and dropped for exactly this reason).
"""
from dataclasses import dataclass
from typing import List


@dataclass
class LedgerEntry:
    idea: str
    status: str  # "confirmed" | "null" | "retracted" | "open_lead"
    evidence: str


def render_markdown_table(entries: List[LedgerEntry]) -> str:
    lines = ["| Idea | Status | Evidence |", "|---|---|---|"]
    for e in entries:
        label = e.status.replace("_", " ").title()
        lines.append(f"| {e.idea} | {label} | {e.evidence} |")
    return "\n".join(lines)
