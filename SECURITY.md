# Security Policy

open-jersey-db is a **data project**: plain YAML files compiled to JSON by two
small Python scripts (`scripts/validate.py`, `scripts/build.py`) that depend only
on **PyYAML** and, in CI, **jsonschema**. It ships **no runtime service, no
server, and no deployed application**. The attack surface is therefore limited
to the build/validation tooling, the Python dependencies, and the repository
contents themselves.

## Reporting a vulnerability

Please report security issues **privately** — do **not** open a public issue.

Email **info@dmnkrdr.com** with:

- a description of the issue and the affected files,
- steps to reproduce (for tooling issues),
- any suggested fix, if you have one.

We aim to acknowledge reports within a few days and to address confirmed issues
promptly. Please give us a reasonable window to respond before any public
disclosure.

### In scope

- Vulnerabilities in the build/validation scripts under `scripts/` — e.g. unsafe
  deserialization, path traversal, or arbitrary code execution.
- Supply-chain concerns in the (minimal) Python dependencies.
- Accidental inclusion of **secrets, credentials, or sensitive/personal data**
  in the repository or its git history.

### Out of scope — please use the normal channels instead

- **Data accuracy, attribution, trademark, or rights/takedown** requests: see
  *“Reporting a rights or data concern”* in the [README](README.md#reporting-a-rights-or-data-concern),
  or open a regular issue. These are not security vulnerabilities.

## Supported versions

Only the latest `main` branch — and the most recent tagged release — receive
fixes. There are no long-term support branches.
