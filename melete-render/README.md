# melete-render

A dumb-as-possible renderer: it reads **alphaTex** on stdin and writes a
**Guitar Pro `.gp`** file on stdout, using
[alphaTab](https://www.alphatab.net/)'s `Gp7Exporter`. It holds **no musical
logic** — parse, export, write bytes. All musical decisions live in melete's
Python core; this tool only crosses the language boundary to alphaTab.

## Contract

- **stdin:** alphaTex text (UTF-8).
- **stdout:** the `.gp` file bytes (a GP7/GP8 ZIP container).
- **failure:** a non-zero exit with the alphaTab diagnostics and error written
  verbatim to stderr — never a silent failure.

This stdin/stdout contract is frozen: melete's Python blast door
(`src/melete/alphatab/render.py`) and any future standalone package depend on
exactly it.

## Usage

```bash
node render.js < exercise.atex > exercise.gp
```

## Why CommonJS

`render.js` is CommonJS (`require`), not ESM (`import`), on purpose. The dev/CI
container bakes alphaTab via a global `npm install -g` exposed on `NODE_PATH`
(see the repo's `vergil.toml` `[container]` and melete#85). `NODE_PATH` is
honoured only by CommonJS `require()` — an ESM `import` ignores it and fails
`MODULE_NOT_FOUND`. alphaTab is a dual package, so `require()` yields the same
full API the ESM build exposes. The alphaTab dependency is **not** installed
here; it is baked into the container image and resolved from the global root.

## Technical debt — extraction-bound

This tool is **acknowledged, tracked technical debt**. It is deliberately
minimal and driven only over stdin/stdout so it can be lifted, unchanged, into
its own TypeScript-engineered repository once Vergil supports TypeScript. The
extraction disposition (defer / follow-on epic / drop) is owned by the
follow-on brainstorm bookend, melete#82.
