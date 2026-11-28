# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

## Users

People using multiple AI accounts and installed clients on Windows, macOS and Linux.

## Product Purpose

One desktop application to create, find and open client-specific profiles for Claude, Codex and Antigravity / Gemini. Success means opening the intended profile quickly without losing existing sessions.

## Operating Context

Python backend, SQLite metadata and external browser, terminal and desktop clients. The approved replacement UI uses PySide6 / Qt Widgets. Profiles remain specific to a client; the app does not combine credentials or embed provider UIs.

## Capabilities and Constraints

Unified searchable profile list, product/client filters, multi-launch, contextual details, client discovery and recoverable errors. Reuse existing profile IDs and directories. Settings, MCP servers and history can be imported from, or transferred back to, the original client additively and with backups, after a per-category size and free-space check, a confirmation and a progress bar with Cancel. Native qualification is required on all three systems. Product copy is English. Provider account isolation must be verified in real clients.

## Brand Commitments

Keep the name AI Profile Hub. Use system typography, compact task-focused layout, light/dark system appearance with an override, visible focus and familiar platform shortcuts.

## Evidence on Hand

Existing backend tests and synthetic Windows captures in docs/screenshots.

## Product Principles

- Find and open profiles from one shared list.
- Make clear that imports are copies and that profiles and original clients diverge afterwards.
- Report launch requests honestly; never infer authenticated identity.
- Keep slow client operations outside the UI thread.
