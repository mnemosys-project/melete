# melete

Practice exercise generator. Parameterized bass exercises engraved as
standard notation and tablature, one Guitar Pro file per day.

## Table of Contents

- [Status](#status)
- [Overview](#overview)
- [Getting Started](#getting-started)
- [Documentation](#documentation)
- [License](#license)

## Status

v1 is built and in use: melete generates, renders and replays practice
sheets end to end, and the output has been validated.

Melete engraves to Guitar Pro `.gp` files through alphaTab: it emits
alphaTex and renders with the vendored `melete-render` Node tool. Nearly
all of the code is renderer-agnostic — see
[the renderer boundary](docs/design.md#the-renderer-boundary) for the two
modules that are not.

## Overview

See [docs/design.md](docs/design.md) for what melete is and links to the
authoritative specification.

## Getting Started

The renderer's toolchain is Node with alphaTab, not a Python package. The
dev and CI container bakes it in — `@coderline/alphatab` installed globally
at image-build time, on top of the Node already in the base image — so
nothing is required there. A host install instead needs Node on `PATH` and
the `melete-render/` dependencies present (`npm install` in that
directory). Melete itself declares no runtime Python dependency.

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
  survey of renderers that led to alphaTab succeeding LilyPond.

## License

MIT — see [LICENSE](LICENSE).
