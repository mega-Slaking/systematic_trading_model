---
name: readme-update
description: Update README.md for a new version/release of the systematic trading model — bump the Current Version line and append a changelog entry under "# Additions:", following this repo's SemVer and entry conventions. Use whenever a change is being recorded for release, the version is being bumped, or the user asks to "update the README", "add a changelog entry", or "bump the version".
---

# README update procedure

The README is the single place this repo records versions and a changelog. There
is **no** separate `VERSION` or `CHANGELOG` file. A release touches README.md in
exactly two spots, plus a matching commit message.

## Step 1 — Determine the new version (SemVer)

Strict SemVer `x.y.z`:
- **x (major)** — breaking change
- **y (minor)** — backward-compatible feature
- **z (patch)** — bugfix / cleanup, no new feature

Bumping a tier resets the lower tiers to 0 (e.g. `1.9.5 → 1.10.0` for a feature;
`1.9.5 → 1.9.6` for a bugfix; `1.9.5 → 2.0.0` for a breaking change). Read the
current version from the `## Current Version:` line — do not assume it.

## Step 2 — Bump the version line

Near the top of `README.md`:

```
## Current Version: V <new x.y.z>
```

Note the space after `V` (`V 1.10.0`, not `V1.10.0`) — match the existing format.

## Step 3 — Append the changelog entry

Under the `# Additions:` section, append a new block **after the most recent
version block** (entries are in ascending version order, newest last):

```
  ## V <x.y.z>

- **<Theme / area>**:
  - <what changed and why, present-tense, specific>
  - <reference concrete modules/files where useful, in `backticks`>

- **<Another theme>**:
  - ...
```

Style rules (match the surrounding entries):
- Group changes under **bold theme headers**, each with a bullet list beneath.
- Be specific and reference real files/modules (e.g. `src/strategy/presets.py`).
- Append `(no behaviour change)` to a theme header when the change is purely a
  refactor/cleanup, so readers can tell behaviour-affecting changes apart.
- Describe behaviour preservation explicitly when relevant (e.g. "byte-identical
  to the old path, verified by <test>").
- Do not rewrite or reflow older entries.

## Step 4 — Commit message

Commit messages in this repo follow:

```
V<x.y.z> <short imperative summary>
```

(no space after `V` in the commit subject — e.g. `V1.10.0 Unified selectable
StrategyConfig registry for backtest and live`). One commit per version where
practical. Only commit when the user has asked; if on `main` (the default
branch), create a branch first — feature work normally lands on `dev`.

## Checklist
- [ ] `## Current Version:` line bumped (with the `V ` space)
- [ ] New `## V x.y.z` block appended under `# Additions:` in order
- [ ] Version tier chosen correctly per SemVer (lower tiers reset to 0)
- [ ] Changelog groups under bold themes; `(no behaviour change)` noted where apt
- [ ] Commit subject uses `V<x.y.z> <summary>` (no space after `V`)
