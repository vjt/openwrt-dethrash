# Releasing

## Version Locations

Update all three before committing:

| File | Field |
|------|-------|
| `pyproject.toml` | `version = "X.Y.Z"` |
| `openwrt/Makefile` | `PKG_VERSION:=X.Y.Z` |
| `CHANGELOG.md` | `## X.Y.Z — YYYY-MM-DD` |

## Steps

```bash
# 1. Update CHANGELOG.md with release notes
# 2. Bump version in pyproject.toml and openwrt/Makefile
# 3. Commit and tag
git add CHANGELOG.md pyproject.toml openwrt/Makefile
git commit -m "chore: bump version to X.Y.Z"
git tag vX.Y.Z
git push && git push --tags

# 4. Create GitHub release from changelog
gh release create vX.Y.Z \
  --title "vX.Y.Z — Short description" \
  --notes "$(cat release-notes)"
```

## Changelog Format

Follow [Keep a Changelog](https://keepachangelog.com/) with sections:
`Added`, `Changed`, `Fixed`, `Removed`.
