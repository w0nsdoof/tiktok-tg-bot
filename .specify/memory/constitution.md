<!--
  Sync Impact Report
  ──────────────────
  Version change: N/A → 1.0.0 (initial ratification)
  Modified principles: N/A (initial version)
  Added sections:
    - Core Principles (3 principles: Code Quality, UX Consistency,
      No Backwards Compatibility)
    - Development Standards
    - Quality Gates
    - Governance
  Removed sections: N/A
  Templates requiring updates:
    - .specify/templates/plan-template.md ── ✅ no update needed
      (Constitution Check section is dynamic)
    - .specify/templates/spec-template.md ── ✅ no update needed
      (requirements structure compatible)
    - .specify/templates/tasks-template.md ── ✅ no update needed
      (task phases compatible)
  Follow-up TODOs: none
-->

# TikTok TG Bot Constitution

## Core Principles

### I. Code Quality

All code MUST meet a high quality bar before merge. This means:

- Every function and module MUST have a single, clear responsibility.
- Code MUST pass linting and formatting checks with zero warnings.
- Dead code, unused imports, and TODO-without-issue comments MUST
  NOT be committed to the main branch.
- All public interfaces MUST be typed (type hints, schemas, or
  equivalent for the chosen language).
- Duplicated logic MUST be extracted; copy-paste reuse is forbidden.
- Test coverage MUST exist for all business logic; untested code
  MUST NOT ship.

**Rationale**: A Telegram bot interacting with TikTok APIs will
accumulate integration complexity quickly. Strict code quality
prevents debt from compounding and keeps the codebase navigable
for future contributors.

### II. User Experience Consistency

Every user-facing interaction MUST feel like it belongs to the
same product. This means:

- Bot responses MUST use a uniform tone, formatting, and structure
  (e.g., consistent use of Markdown, emoji, and message length).
- Error messages shown to users MUST be human-friendly and
  actionable — never expose raw stack traces or API errors.
- Latency-sensitive operations MUST provide immediate feedback
  (e.g., "Processing your request...") before performing work.
- All commands and interactions MUST be documented in a single
  help/menu system accessible to the user.
- UI/UX patterns (button layouts, inline keyboards, message flows)
  MUST be reused across features — not reinvented per command.

**Rationale**: Telegram bots live or die by user trust. Inconsistent
responses, cryptic errors, or unpredictable behavior erode trust
fast and increase support burden.

### III. No Backwards Compatibility

The project MUST NOT carry backwards-compatibility shims, migration
layers, or deprecated code paths. This means:

- When a feature, API, or data format changes, the old version MUST
  be removed in the same change — no deprecation period.
- Database migrations MUST be destructive when schemas change; data
  migration scripts are acceptable but the old schema MUST NOT
  coexist with the new one.
- Configuration keys, environment variables, and command names MUST
  be renamed/removed outright — no aliases or fallbacks.
- Unused feature flags, compatibility wrappers, and version-checking
  code MUST be deleted immediately.

**Rationale**: This is a greenfield project with a small user base.
Backwards compatibility adds complexity for no benefit at this stage.
Moving fast and keeping the codebase clean is more valuable than
preserving old behavior nobody depends on.

## Development Standards

- Commit messages MUST follow Conventional Commits format.
- Secrets (API keys, bot tokens) MUST NEVER appear in source
  control; use environment variables exclusively.
- Dependencies MUST be pinned to exact versions.
- All external API calls (TikTok, Telegram) MUST have timeout and
  retry logic with exponential backoff.

## Quality Gates

- Every pull request MUST pass CI (lint + test) before merge.
- Every pull request MUST be reviewed against this constitution's
  principles before approval.
- No pull request MUST introduce new linting warnings or reduce
  test coverage.

## Governance

This constitution is the highest-authority document for the
TikTok TG Bot project. All development decisions, code reviews,
and architectural choices MUST comply with the principles above.

**Amendment procedure**:

1. Propose a change via pull request modifying this file.
2. Document the rationale for the change in the PR description.
3. If a principle is removed or redefined, bump the MAJOR version.
   If a principle is added or materially expanded, bump MINOR.
   Clarifications and wording fixes bump PATCH.
4. Update `LAST_AMENDED_DATE` to the merge date.
5. After amendment, run a consistency check against all templates
   in `.specify/templates/` and update references as needed.

**Compliance review**: Every PR review MUST include a constitution
compliance check. Reviewers MUST verify that changes do not
violate any principle listed above.

**Version**: 1.0.0 | **Ratified**: 2026-02-24 | **Last Amended**: 2026-02-24
