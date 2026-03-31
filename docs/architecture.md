# Architecture

## What bubseek does

bubseek is an attempt to explore a different approach to enterprise data needs: instead of scheduling BI tickets, tell the agent what you want and get insights back.

- Packages Bub with pre-configured dependencies
- Provides OceanBase/seekdb storage support via bub-tapestore-sqlalchemy
- Ships builtin channels: Feishu, DingTalk, WeChat, Discord, Telegram, Marimo
- Ships builtin skills: github-repo-cards, web-search, schedule
- Provides built-in observability: agent's own footprint becomes queryable data

## What bubseek does not do

- It does not fork Bub
- It does not define custom formats
- It does not replace Bub's CLI

## Responsibility split

| Component | Responsibility |
| --- | --- |
| Bub | Runtime, CLI, extension model, tape design |
| bubseek | Packaging, defaults, plugin wiring, skills |
| Python packaging | Dependencies, installation |
| seekdb | Storage for tapes, sessions, tasks |

## Data flow

All data (tapes, sessions, tasks) flows through bub-tapestore-sqlalchemy into a single seekdb database. This enables:

1. **External observability** — Agent serves team requests, produces insights
2. **Internal observability** — Agent's own footprint (tapes) becomes data for analysis

The same agent that serves the team can also analyze its own history to understand: what questions are most frequent? What tasks fail often? What does the team care about?
