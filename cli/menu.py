"""Legacy Python entrypoint for the FlowHub management menu.

The production interactive menu is the installed Docker-backed shell wrapper:
`flowhub` from scripts/flowhub. Keeping this module as a delegation notice
prevents a second menu contract from drifting out of sync.
"""

from __future__ import annotations


def show_menu() -> None:
    """Point operators to the canonical installed menu."""
    print(
        "The canonical interactive menu is the installed FlowHub wrapper.\n"
        "Run: flowhub"
    )
