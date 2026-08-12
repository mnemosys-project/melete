// melete-render: alphaTex (stdin) -> Guitar Pro `.gp` (stdout). No musical logic.
// Parse -> export -> write bytes. Non-zero exit + stderr (verbatim) on failure.
//
// CommonJS (require), NOT ESM. The dev/CI container bakes alphaTab via a global
// `npm install -g` exposed on NODE_PATH (see vergil.toml `[container]` and
// melete#85). NODE_PATH is honoured only by CommonJS `require()` -- an ESM
// `import` would fail MODULE_NOT_FOUND. alphaTab 1.8.4 is a dual package, so
// `require()` yields the same full API the ESM build does.
//
// This tool is acknowledged, extraction-bound technical debt: dumb by design,
// driven only over stdin/stdout, destined for its own TypeScript repo once
// Vergil supports TypeScript. See README.md and melete#82.
const alphaTab = require('@coderline/alphatab');

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

// alphaTex parse errors do not carry their detail on the thrown error's message;
// they accumulate on the importer's diagnostic bags. Surface them verbatim so a
// failure is never silent.
function dumpDiagnostics(importer) {
  const dump = (label, bag) => {
    for (const d of bag?.items ?? []) {
      process.stderr.write(
        `${label} ${d.code}: ${d.message} (line ${d.start?.line}, col ${d.start?.col})\n`,
      );
    }
  };
  dump('lexer', importer.lexerDiagnostics);
  dump('parser', importer.parserDiagnostics);
  dump('semantic', importer.semanticDiagnostics);
}

async function main() {
  const alphaTex = await readStdin();
  const settings = new alphaTab.Settings();
  const importer = new alphaTab.importer.AlphaTexImporter();
  importer.initFromString(alphaTex, settings);

  let score;
  try {
    score = importer.readScore();
  } catch (err) {
    dumpDiagnostics(importer);
    process.stderr.write(`${String(err?.stack ?? err)}\n`);
    process.exit(1);
  }

  const data = new alphaTab.exporter.Gp7Exporter().export(score, settings);
  process.stdout.write(Buffer.from(data.buffer, data.byteOffset, data.byteLength));
}

main().catch((err) => {
  process.stderr.write(`melete-render: ${String(err?.stack ?? err)}\n`);
  process.exit(1);
});
