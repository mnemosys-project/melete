# melete

Practice exercise generator. Parameterized bass exercises engraved as
standard notation and tablature, one printable sheet per day.

## Table of Contents

- [Status](#status)
- [Overview](#overview)
- [Getting Started](#getting-started)
- [Documentation](#documentation)
- [License](#license)

## Status

v1 is built and in use: melete generates, renders and replays practice
sheets end to end, and the output has been validated on paper.

Melete currently engraves through LilyPond, and **that renderer is being
replaced.** Nearly all of the code outlives the change — see
[the renderer boundary](docs/design.md#the-renderer-boundary) for which
modules do not.

## Overview

See [docs/design.md](docs/design.md) for what melete is and links to the
authoritative specification.

## Getting Started

LilyPond is a prerequisite, as a binary on `PATH` rather than a Python
package — `apt-get install lilypond` on Debian or Ubuntu, `brew install
lilypond` on macOS.

```bash
uv tool install .
mkdir -p build && cd build && cp ../examples/config.toml .
melete generate
```

Melete resolves both `config.toml` and the `sessions/` output directory
relative to the current working directory, so run it from the directory
you want the sheets to land in.

## Documentation

- [docs/design.md](docs/design.md) — design orientation: the module
  layout, the load-bearing boundaries, the renderer boundary.
- [docs/cli.md](docs/cli.md) — every subcommand and flag.
- [docs/configuration.md](docs/configuration.md) — every key of
  `config.toml`.
- [docs/repository-standards.md](docs/repository-standards.md) — the
  toolchain, the checks, and where melete departs from the default.
- [docs/reports/](docs/reports/) — research findings, including the
  survey of renderers that could succeed LilyPond.

## License

MIT — see [LICENSE](LICENSE).
