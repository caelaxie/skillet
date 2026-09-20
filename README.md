# supragent

[![skills.sh](https://skills.sh/b/caelaxie/supragent)](https://skills.sh/caelaxie/supragent)

`supragent` is a compact repository of agent skills for standardizing and accelerating common agent workflows.

Skills follow the [Agent Skills](https://agentskills.io) format (`skills/<name>/SKILL.md`) and are managed with the open skills CLI:

```bash
npx skills --help
```

Browse this package on [skills.sh/caelaxie/supragent](https://skills.sh/caelaxie/supragent).

## Install

List skills without installing:

```bash
npx skills add caelaxie/supragent --list
```

Install all skills globally (recommended for personal use):

```bash
npx skills add caelaxie/supragent --global --all
```

Install one skill globally:

```bash
npx skills add caelaxie/supragent --global --skill commit
```

Install into the current project only (omit `--global`):

```bash
npx skills add caelaxie/supragent --skill commit
```

Install from a local clone:

```bash
npx skills add ./path/to/supragent --list
npx skills add ./path/to/supragent --skill rust-guidelines
```

## Manage

```bash
# List installed skills (project scope)
npx skills list

# List globally installed skills
npx skills list --global

# Update installed skills from their sources
npx skills update
npx skills update --global

# Remove a skill
npx skills remove commit
npx skills remove commit --global

# Search the public skills index
npx skills find rust guidelines
```

Use a skill once without installing it:

```bash
npx skills use caelaxie/supragent@commit
```

## Skill Catalog

| Skill | Description |
|---|---|
| `asd-ste100` | Applies ASD-STE100 Simplified Technical English principles to documentation, commit messages, PR descriptions, and code comments. |
| `1password-cli` | Secure secret access via 1Password CLI (`op`) for reading, injecting, and templating secrets. |
| `bitwarden-cli` | Bitwarden CLI (`bw`) workflows for vault auth, session management, and secret retrieval. |
| `codeberg-cli` | Codeberg/Forgejo CLI (`cb`) workflows for auth, repos, issues, PRs, releases, and Actions. |
| `commit` | Fallback commit workflow using conventional messages when a project has no commit-specific guidance. |
| `d2lang` | Supports D2 diagram creation, refactoring, validation, and export workflows. |
| `explain-diff-html` | Geoffrey Litt's skill for generating rich, interactive HTML explanations of code changes, diffs, branches, and PRs. |
| `hermes-plugin-development` | Guides Hermes plugin authoring and validation across manifests, registration, tools, hooks, and enablement. |
| `modified-karpathy-guidelines` | Provides coding guidance to reduce overcomplication and improve code quality. |
| `model-detector` | Finds exact model IDs for Oh My Pi (OMP), Codex, OpenCode, APIs, and extensible coding-agent runners from first-party runtime evidence, config, logs, and request or response fields. |
| `pr` | Fallback GitHub pull-request workflow when a project has no PR-specific guidance; self-assigns unassigned PRs by default. |
| `review-team` | Coordinates parallel review roles for evidence-based, severity-ranked findings and fixes. |
| `roam-research-pro` | Writes Roam Research pages and `{{mermaid}}` diagrams in a dialect Roam will actually render. |
| `rust-guidelines` | Rust coding, review, test, Cargo, and API guidance with focused local references and official-doc fallback for uncovered details. |
| `sql-antipatterns` | Audits PostgreSQL designs for anti-patterns and recommends constraint-first alternatives. |
| `stash-override-rules` | Helps author, merge, and validate Stash VPN override rules and routing behavior. |

## Repository layout

```text
skills/
  <skill-name>/
    SKILL.md              # required: name + description frontmatter + instructions
    agents/openai.yaml    # optional: Codex/OpenAI display metadata
    references/           # optional: progressive-disclosure docs
skills.sh.json            # skills.sh page groupings
```

Each skill requires YAML frontmatter with `name` (must match the folder name) and `description`.

## Validate packaging

Confirm the CLI can discover every skill in this repo:

```bash
./scripts/validate-skills.sh
```

Or manually:

```bash
npx skills add . --list
```
