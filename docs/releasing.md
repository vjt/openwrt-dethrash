# Releasing

Use `/release` to cut a release interactively, or follow the manual
steps below.

## Version Locations

Update all before committing:

| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `openwrt/Makefile` | `PKG_VERSION:=X.Y.Z` |
| `CHANGELOG.md` | `## X.Y.Z — YYYY-MM-DD` (replace `## Unreleased`) |

## Changelog Workflow

Changes accumulate under `## Unreleased` at the top of `CHANGELOG.md`
(added by `/close` at session end). At release time, the `## Unreleased`
header is replaced with `## X.Y.Z — YYYY-MM-DD`.

Follow [Keep a Changelog](https://keepachangelog.com/) with sections:
`Added`, `Changed`, `Fixed`, `Removed`.

## Manual Steps

```bash
# 1. Replace ## Unreleased with ## X.Y.Z — YYYY-MM-DD in CHANGELOG.md
# 2. Bump version in pyproject.toml and openwrt/Makefile
# 3. Commit and tag
git add CHANGELOG.md pyproject.toml openwrt/Makefile
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push && git push --tags

# 4. Create GitHub release from changelog
gh release create vX.Y.Z \
  --title "vX.Y.Z — Short description" \
  --notes "release notes from CHANGELOG.md"
```
