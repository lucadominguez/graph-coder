# Installation

## Python package (`aps` CLI)

```sh
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
# .venv/bin/python -m pip install -e ".[dev]"     # POSIX
```

Python 3.11 or later is required. Runtime dependencies are limited to `jsonschema` and `PyYAML`.

## Portable skills installers

The installers copy the seven Graph Coder skills (`aps-plan`, `idea-grill`, `plan-forge`, `plan-rehearsal`, `routing-plan`, `delegation-graph`, `execution-manager`) into the project. They are idempotent and safe to re-run.

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

## Security notes

- No installer reads or writes secrets, and the `aps` CLI never persists provider credentials.
- `LLM_STATS_API_KEY` is read from the environment only when `aps route refresh` makes a network request, and is never written to the cache.
- Terminal helpers use `wt.exe` and intentionally do not require Komorebi. `aps terminal open` is a dry run unless `--execute` is passed.
