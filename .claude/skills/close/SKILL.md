---
name: close
description: End-of-session protocol — push, update memory, check docs
---

Session closing skill. Invoke with `/close` at end of session.

## Steps

### 1. Push unpushed commits

```bash
git log --oneline origin/master..HEAD
```

If commits exist, push:
```bash
git push
```

### 2. Update memory

Review what happened this session and update memory files:

- **Update** existing memories if facts changed (e.g. version bumped,
  config changed, new decisions made)
- **Create** new memories for non-obvious learnings, user feedback,
  or project state that future sessions need
- **Delete** stale memories that are no longer true
- Update `MEMORY.md` index if files were added/removed

Focus on what's useful for next time. Don't save things derivable
from code or git history.

### 3. Check docs freshness

Scan `docs/` and `CLAUDE.md` for references to things that changed
this session (renamed functions, changed field names, new config
options, updated architecture). Fix any stale references.

Only touch docs that are actually wrong. Don't rewrite for cosmetic
reasons.

### 4. Deploy dashboard

If dashboard code changed this session and wasn't already pushed:
```bash
.venv/bin/wifi-dethrash --push-dashboard
```

If station-resolver changed, remind the user to rebuild and deploy
(see memory for deploy procedure).

### 5. Report

Tell the human:
- Commits pushed (count + range)
- Memory updates (what changed)
- Docs updated (if any)
- Deploy status (dashboard pushed / station-resolver needs rebuild / nothing to deploy)
- Any pending work for next session
