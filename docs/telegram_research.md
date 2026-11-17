# Research: t.me/aichatiran — posts relevant to this project

Searched 2026-11-15 via the public web preview (`t.me/s/aichatiran?q=...`) with queries `OCR`, `agent`, `Claude Code`, `parser`.
The preview hides calendar dates (only time of day). Vendor numbers below are the posters' claims, not verified.

## OCR / document extraction
| Post | What | Use for this project |
|---|---|---|
| [74](https://t.me/aichatiran/74) | Bina OCR — Persian OCR benchmark, Bina 0.1 beat Gemini 3.5 Flash | Not needed (catalog is Chinese + English), but shows VLM-style OCR beats classic OCR on hard scripts |
| [77](https://t.me/aichatiran/77) | Agentic Document Processing (ADP): models that understand layout, not plain OCR | Design idea: OCR boxes + layout (column) analysis + rule parser, optional vision-LLM engine |
| [264](https://t.me/aichatiran/264) | OXR — 1.3B open-source document parser → Markdown/JSON | Candidate alternative engine if RapidOCR accuracy is poor |
| [86](https://t.me/aichatiran/86) | Hands-On-AI-Engineering repo (OCR, RAG, agents projects) | Reference patterns |

## Agents / orchestration / Claude Code
| Post | What | Applied as |
|---|---|---|
| [160](https://t.me/aichatiran/160) | Team agents vs sub-agents (sub-agent works alone on one task for the main agent) | Orchestrator + specialist sessions, each owning disjoint files |
| [133](https://t.me/aichatiran/133) | oh-my-subagents — self-organising agent coordination | Supervisor session that answers worker questions |
| [266](https://t.me/aichatiran/266) | Claude Code course: CLAUDE.md, permissions, plan mode, skills, sub-agents, context mgmt | Project `CLAUDE.md` holds the contract; `.claude/agents/*` + project skill |
| [301](https://t.me/aichatiran/301) | 19 rules for AI coding tools — "define the work, not just the prompt" | Each agent brief has explicit scope, files, done-criteria |
| [80](https://t.me/aichatiran/80) | SOUL.md — file defining an agent's identity | Agent definition files with role + boundaries |
| [231](https://t.me/aichatiran/231) | Superpowers — TDD, planning, review for coding agents | Each worker writes pytest tests for its module |
| [63](https://t.me/aichatiran/63) | Ten engineering skills (debug, test, optimise) | Workers use `engineering:testing-strategy`, `engineering:debug`, `code-review` |

## Token saving
| Post | What | Applied as |
|---|---|---|
| [115](https://t.me/aichatiran/115) | Compaction plugin: drop/shorten old tool calls | Keep sessions short and scoped; no re-reading big files |
| [308](https://t.me/aichatiran/308) | Plugins for the 5-hour limit / avoiding full file re-reads | Contract lives in one small file; workers read only what they need |
| [65](https://t.me/aichatiran/65) | Book → skill with chapter summaries (fewer tokens) | Catalog format knowledge packed into one project skill |
| [232](https://t.me/aichatiran/232), [217](https://t.me/aichatiran/217) | Cheaper models for routine work | Model per task: Opus for OCR/parse logic, Sonnet for exporters/GUI/QA |

## UI design
| Post | What | Applied as |
|---|---|---|
| [75](https://t.me/aichatiran/75), [78](https://t.me/aichatiran/78) | apple-design skill; Emil Kowalski design-taste repo (installed locally as `apple-design`, `emil-design-eng`) | GUI worker loads these for layout/feedback principles |
| [15](https://t.me/aichatiran/15) | DESIGN.md — fixed design rules file | GUI rules section in `CLAUDE.md` |
