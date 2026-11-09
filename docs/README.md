# Documentation

The `docs/` directory is the entry point to the repository's documentation: it
states how documentation is written and validated here, and where each kind of
knowledge lives. The pages themselves are canonical in one place each - the
published site for readers, the backlog for records - and `docs/` routes to
them instead of restating them.

## Purpose

Documentation is the user-facing knowledge layer of this repository: the
maintained, discoverable source of truth for understanding, using,
configuring and operating the software. It serves human readers and AI agents
alike, and it must be accurate, actionable, easy to navigate and consistent
with the implementation.

## Principles

1. **Documentation is part of the product.** It is not an afterthought or an
   optional summary of the implementation.
2. **Prefer one canonical explanation.** The same knowledge is not restated in
   two places; a second copy is a link.
3. **Document observable behaviour.** Describe what the software does, not what
   it was meant to do.
4. **Write for users first.** Practical explanations, examples and instructions
   before implementation detail.
5. **Keep documentation discoverable.** Organise by purpose, and give every
   directory an index.
6. **Treat outdated documentation as a defect.** Wrong instructions and stale
   references are fixed like wrong code.

## Layout

| Directory | What it holds | Canonical source today |
| :-- | :-- | :-- |
| [`guides/`](guides/README.md) | Task-oriented instructions and workflows | `apps/docs/content/docs/start`, `apps/docs/content/docs/guides` - published at [archont561.github.io/qgis-sdk](https://archont561.github.io/qgis-sdk/) |
| [`concepts/`](concepts/README.md) | Domain concepts and explanations | `apps/docs/content/docs/start/concepts.md` and the opening sections of the reference guides |
| [`reference/`](reference/README.md) | APIs, configuration, commands, schemas | generated pages on the site (`/python/`, `/typescript/`, `/reference/`) plus `qgis-sdk --help` |
| [`architecture/`](architecture/README.md) | System architecture and architectural decisions | `backlog/decisions/` (73 records, one table on the site) |
| [`development/`](development/README.md) | Contribution, testing and development workflows | `AGENTS.md`, `apps/docs/guides/doc-14`, the site's `/contributing/workspace/` section |

The published site is the reader-facing surface. It is generated on every push
to `main` from three reference guides in `apps/docs/guides/` and the
hand-written pages under `apps/docs/content/docs/`; every page is also served
as markdown (`.md`), and the whole corpus is in `llms.txt` / `llms-full.txt`
for agents.

## Preventing documentation drift

Documentation evolves with the software. A change that affects user-visible
behaviour, configuration, APIs, workflows or operational requirements carries
an assessment of its documentation impact - during implementation and in
review:

- Identify the affected documentation.
- Update the canonical document instead of adding a near-duplicate.
- Add documentation when a user-facing capability appears.
- Remove obsolete instructions, examples and references.
- Verify that commands, configuration examples and code snippets still run.
- Check that internal links and navigation resolve.

An implementation is not fully documented merely because it is complete. When
no documentation change is needed, that decision is stated in the review.

## Validation

Documentation is checked automatically; the checks run in CI on every pull
request that touches documentation and are required before merging.

| Layer | Tool | Scope | Config | Runs in |
| :-- | :-- | :-- | :-- | :-- |
| Repository conventions | [alint](https://alint.org) | the whole repository | `.alint.yml` | `Linux checks` |
| Markdown structure | markdownlint-cli2 | `docs/`, `README.md`, `AGENTS.md` | `.markdownlint-cli2.jsonc` | `Documentation` |
| Writing style | [Vale](https://vale.sh) | `docs/`, `README.md` | `.vale.ini`, `docs/vale/styles` | `Documentation` |
| Links and references | [lychee](https://github.com/lycheeverse/lychee) | `docs/`, `README.md`, `AGENTS.md` | `.lychee.toml` | `Documentation` |

Vale keeps to the prose written for people. `AGENTS.md` is instructions to
agents - terse imperatives, paths and commands - and it is held to the Markdown
structure and link rules only.

```sh
pixi run -e bun lint-docs     # Markdown structure, as CI runs it
pixi run -e bun bun run readme  # regenerate README.md from its template
vale docs README.md           # style, when Vale is installed
lychee --config .lychee.toml --offline docs README.md
```

Vale and lychee are single binaries that the `Documentation` job installs from
pinned actions; the pinned Pixi environments carry neither, so outside CI they
are a local install rather than part of `restore.sh`.

Automated checks are necessary but not sufficient: a reviewer still judges
whether the documentation matches the implemented behaviour. The behavioural
guards stay where they are - the link check over the exported site
(`docs-link-check`), the Python tests that compare guide snippets with the
sources they quote, and the site build's refusal to export a page without its
markdown twin.

## Definition of done

A change that affects documentation satisfies all of:

- the relevant documents are identified;
- existing canonical documents are updated where necessary;
- new user-facing behaviour is documented;
- examples and instructions match the current implementation;
- obsolete information is removed;
- the validation above passes.

## Ownership

Everyone who changes the product assesses its documentation impact, and every
reviewer checks that assessment. Documentation is maintained continuously as
part of normal development, not deferred to occasional cleanup exercises: the
goal is for this directory and the site behind it to remain a trustworthy
representation of the software at all times.
