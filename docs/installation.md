# Installation

## Python package (`graph-coder` CLI)

```sh
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
# .venv/bin/python -m pip install -e ".[dev]"     # POSIX
```

Python 3.11 or later is required. Runtime dependencies are limited to `jsonschema` and `PyYAML`.

## Portable skills installers

The installers copy the eight Graph Coder skills (`graph-coder`, `concept-grill`, `technical-research`, `plan-forge`, `plan-rehearsal`, `delegation-graph`, `routing-plan`, `execution-manager`) into the project. They are idempotent and safe to re-run.

Default project-local install to `.agents/skills`:

```sh
./scripts/install.sh
```

Windows PowerShell 5.1 compatible install:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
```

Dry run safely (prints planned mkdir/copy operations without writing):

```sh
./scripts/install.sh --dry-run
powershell -File scripts/install.ps1 -DryRun
```

Optional Jcode view copies the same skills to `.jcode/skills`:

```sh
./scripts/install.sh --jcode-view
powershell -File scripts/install.ps1 -JcodeView
```

Both installers also accept an explicit project root and destination:

```sh
./scripts/install.sh --project-root <path> --dest <relative-or-absolute-dir>
powershell -File scripts/install.ps1 -ProjectRoot <path> -Dest <dir>
```

## Retired skills

Installing copies the eight active skills and deletes nothing, so a destination
that predates a rename keeps the old skill alongside its replacement. Both names
then describe the same phase and a run can select the retired one, which is how
a working directory can stay out of date without any error. `aps-plan` was
replaced by `graph-coder`, and `idea-grill` by `concept-grill`.

Every install warns when it finds one. Remove them with:

```sh
./scripts/install.sh --remove-retired
powershell -File scripts/install.ps1 -RemoveRetired
```

Combine with `--dry-run` / `-DryRun` to see what would be deleted first. Nothing
is removed unless the flag is passed.

## Security notes

- No installer reads or writes secrets, and the `graph-coder` CLI never persists provider credentials.
- `LLM_STATS_API_KEY` is read from the environment only when `graph-coder route refresh` makes a network request, and is never written to the cache.
- Terminal helpers use `wt.exe` and intentionally do not require Komorebi. `graph-coder terminal open` is a dry run unless `--execute` is passed.
