---
name: release
description: Cut a release — version bump, changelog, tag, GitHub release
---

Release skill. Bumps version, finalizes changelog, tags, and creates
a GitHub release.

## Steps

### 1. Determine version

Review commits since the last tag:
```bash
git log --oneline "$(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~20)"..HEAD
```

Suggest a version following semver:
- **patch** (0.X.Y → 0.X.Y+1): bug fixes only
- **minor** (0.X.Y → 0.X+1.0): new features, non-breaking changes
- **major** (0.X.Y → 1.0.0): breaking changes

Present the suggestion and ask the user to confirm or override.

### 2. Finalize changelog

Read `CHANGELOG.md`. Replace the `## Unreleased` header with:
```
## X.Y.Z — YYYY-MM-DD
```

Review the entries — clean up wording if needed, ensure sections
follow [Keep a Changelog](https://keepachangelog.com/) format
(`Added`, `Changed`, `Fixed`, `Removed`).

### 3. Bump version

Update all version locations (see `docs/releasing.md`):

| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `openwrt/Makefile` | `PKG_VERSION:=X.Y.Z` |

### 4. Commit and tag

```bash
git add CHANGELOG.md pyproject.toml openwrt/Makefile
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

### 5. Create GitHub release

Extract the release notes from `CHANGELOG.md` (everything under the
new version header until the next `## ` header) and create the release:

```bash
gh release create vX.Y.Z \
  --title "vX.Y.Z — Short description" \
  --notes "release notes from changelog"
```

The title's short description should summarize the main theme of the
release (e.g. "station IP enrichment", "timeline fix").

### 6. Report

Tell the human:
- Version: old → new
- Tag pushed
- GitHub release URL
- Any follow-up needed (opkg rebuild, dashboard re-push, etc.)
