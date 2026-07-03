"""FlowHub - FLOWHUB-specific extensions package.

Builds on the frozen A2 Platform Core (app/a2/) without modifying it.
All FlowHub-only functionality lives in this package.

One-way dependency rule: app/a2/ must never import from app/flowhub/.

Implementation of individual modules begins in later B phases.
"""
