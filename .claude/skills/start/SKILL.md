---
name: start
description: Session start protocol — pending work, git status, memory review
---

Session start skill. Produce a quick status report and set the tone.

## Steps

### 1. Read memory

Read `MEMORY.md` and any relevant memory files. Note what was happening
last session and whether any project memories are stale.

### 2. Check git status

```bash
git status
git log --oneline -10
```

Note any uncommitted changes, unpushed commits, or active worktrees.

### 3. Quick health check

```bash
.venv/bin/pytest -v --tb=short 2>&1 | tail -5
.venv/bin/pyright src/ tests/ 2>&1 | tail -3
```

Report test count and whether pyright is clean. If either fails, flag
it — don't investigate yet, just report.

### 4. Produce the report

Format:

```
🌿 **Git State**: clean / uncommitted changes / unpushed commits
🧪 **Tests**: N passed / N failed
🔍 **Types**: clean / N errors
📍 **Last session**: brief summary from memory

## What's on the table
- items from memory, recent commits, or known pending work
```

Keep it short. The goal is orientation, not archaeology.
