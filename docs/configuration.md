# Melete — Configuration Reference

Every section and every key of `config.toml`, with its default and its accepted
values. This page states behaviour; the reasoning behind it lives in the epic #1
specification (§5 *Instrument Model*, §7 *Exercise Families*, §9
*Coverage-Aware Selection*, §10 *Configuration*, §13 *Error Handling*), which
[docs/design.md](design.md) links to.

For the commands that read this file, see [cli.md](cli.md).

[`examples/config.toml`](../examples/config.toml) is a **complete working
configuration** — every axis of every family its `shape` names is declared. Copy
it to the directory you intend to run from and edit it; it is a starting point,
not a file melete reads out of the repository.

## Table of Contents

- [Where the file lives](#where-the-file-lives)
- [Top level](#top-level)
- [`[instrument]`](#instrument)
- [`[output]`](#output)
- [`[session]`](#session)
- [`[pool.<family>]`](#poolfamily)
- [`[pool.rhythm]`](#poolrhythm)
- [Axis values](#axis-values)
- [The rules that catch everyone](#the-rules-that-catch-everyone)
- [What is renderer-specific](#what-is-renderer-specific)

## Where the file lives

`config.toml`, in the working directory melete is run from — the same directory
`sessions/` is written under. No command takes a path to it, and there is no
default configuration to fall back on: a missing or unreadable file is a hard
error naming the path.

Invalid TOML is an error carrying the parser's own message. Every other
rejection names the exact key it came from, and lists the accepted values
wherever there is a set to list. **Nothing ever falls back to a default because
a key was misspelled**: a key no section defines is indistinguishable from a
misspelling of one that is read, so unknown keys are rejected section by
section.

## Top level

Exactly four sections are accepted: `instrument`, `output`, `session` and
`pool`. Anything else is an error listing those four.

All four are optional as *tables* — omitting one takes every default below —
but a configuration whose `[pool]` declares nothing cannot draw anything, and
fails at generation rather than at load.

## `[instrument]`

| Key | Type | Default | Accepted |
|---|---|---|---|
| `profile` | string or inline table | `"bass6"` | a built-in name, or an explicit tuning table |
| `position_span` | integer | `4` | 1 or greater |

### `profile` as a built-in name

| Name | Tuning (absolute pitches, low to high) | Strings | Frets |
|---|---|---|---|
| `bass4` | 28, 33, 38, 43 (E1 A1 D2 G2) | 4 | 20 |
| `bass5` | 23, 28, 33, 38, 43 (B0 E1 A1 D2 G2) | 5 | 24 |
| `bass6` | 23, 28, 33, 38, 43, 48 (B0 E1 A1 D2 G2 C3) | 6 | 24 |

Pitches are absolute integers with C4 = 60. A misspelled name is an error
listing the built-ins; it never falls back to a default, because the fret count
and string count it would silently substitute are exactly what decide whether a
drawn exercise is valid.

### `profile` as an explicit tuning

```toml
[instrument]
profile = { name = "drop_d", tuning = [26, 33, 38, 43], fret_count = 20 }
```

All three keys are **required**, and no others are accepted:

| Key | Type | Meaning |
|---|---|---|
| `name` | string | Names the instrument on the cover page and in the session log |
| `tuning` | list of integers | Absolute pitches, low to high; index 0 is the lowest string |
| `fret_count` | integer | 1 or greater. Never inferred: it decides which specifications are valid, therefore the pool, therefore the draw |

`tuning` must be non-empty and **strictly ascending**. A tuning that is not is a
load error naming the offending index — it is never re-sorted, because sorting
would shift every string index and engrave convincing tablature for the wrong
instrument.

### `position_span`

How many frets the fretting hand covers without shifting, stated as a **span**:
the distance from its lowest fretted note to its highest. It is what makes the
`positional` traversal mean a position rather than a label.

The default of 4 is four fingers over four frets with one fret of ordinary
reach — five frets of neck, four frets of span. It sits beside `profile` rather
than inside an explicit tuning so that a player whose hand disagrees with the
default does not have to write out a whole tuning to say so, and it applies to
built-in and explicit profiles alike.

## `[output]`

| Key | Type | Default | Accepted |
|---|---|---|---|
| `staves` | string | `"both"` | `"both"`, `"tab"`, `"notation"` |
| `key_signatures` | boolean | `true` | `true`, `false` |

Both keys are validated and accepted, but they are **inert for the `.gp`
output** — see [What is renderer-specific](#what-is-renderer-specific). A Guitar
Pro file settles what each one used to choose:

- `staves` selected standard notation, tablature, or both. A `.gp` carries
  notation and tablature together and inseparably, so there is nothing to
  select. `--staves` overrides the key for one run and is equally inert.
- `key_signatures` chose between two correct notations — a key signature with
  diatonic spelling, or no signature with an explicit accidental on every
  altered tone. The alphaTab emitter always writes the key signature, so the key
  no longer switches between them.

`[output]` is deliberately excluded from the configuration hash the session seed
is derived from, so changing either key never changes which exercises are drawn.

## `[session]`

| Key | Type | Default | Accepted |
|---|---|---|---|
| `count` | integer | `5`, or the sum of `shape` | 1 or greater |
| `horizon` | integer | `14` | 1 or greater |
| `max_notes` | integer | `96` | 1 or greater |
| `max_fret_span` | integer | `12` | 1 or greater |
| `shape` | table of family → integer | unset | family names, each with a count of 1 or greater |

`count` is how many exercises one session holds. `--count` overrides it for one
run, unless `shape` is declared.

`horizon` is how many past sessions the selector weights against. A value is
avoided in proportion to how recently it was last drawn, over this many days.

`max_notes` bounds how long one exercise may be, and `max_fret_span` bounds how
far it may make the fretting hand travel — again as a span, lowest fretted note
to highest, with open strings excluded. Both are hard gates: a sampled
specification that violates either is discarded and redrawn, never trimmed into
something renderable. `max_fret_span` is deliberately looser than
`position_span`, because shifting is legitimate practice; twelve frets is one
octave of neck, past which an exercise contains a repetition of itself.

### `shape`

```toml
shape = { chromatic = 1, scales = 2, arpeggios = 1, intervals = 1 }
```

The declared mix of families: one slot per exercise, filled in the order
written. Keys must be family names (`chromatic`, `scales`, `arpeggios`,
`intervals`); each count must be 1 or greater; an empty table is an error.

Leaving `shape` unset weights the families instead, drawing the family itself as
an axis.

`count` and `shape` must agree. If both are given and `count` differs from the
sum of the shape's values, that is a load error naming both numbers — one of
them is wrong and guessing which would silently generate the wrong session. If
only `shape` is given, `count` becomes its sum.

## `[pool.<family>]`

One section per family, plus [`[pool.rhythm]`](#poolrhythm). The accepted
sections are exactly `chromatic`, `scales`, `arpeggios`, `intervals` and
`rhythm`; anything else is an error.

Each section holds the candidate values the selector samples that family's axes
from, plus an optional `tempo`. Each key is the **plural** TOML spelling; the
axis it feeds is the singular name that appears in `session.json` and in
`melete families` output.

**The exercise geometry is now computed, not sampled.** Every family draws one
coherent up-and-down journey: anchored at the root on the lowest string, it
traverses outer string to opposite outer string and returns as the exact
retrograde, with the octave count *emergent* from reaching the top string rather
than a target. The `directions`, `string_sets` and `octaves` axes the old
sampled model carried are therefore **gone from every family** — direction is
always up-and-down, string coverage is the whole instrument, and octaves are
computed — and `arpeggios` also drops `traversals`, laying every quality out
from one canonical seed shape. A `config.toml` that still lists any of those keys
is rejected as an unknown key by the section that no longer reads it, the same
way any misspelling is. `scales` keeps `traversals` as its fingering-style axis.

### `tempo`

| Key | Type | Default | Accepted |
|---|---|---|---|
| `tempo` | two-element list of integers | the family's own range | `[low, high]`, both 1 or greater, `low` not exceeding `high` |

Beats per minute, slowest to fastest. Tempo is **not a sampled axis** — it is a
per-family setting, printed on the cover page for every exercise of that family.

| Family | Default tempo |
|---|---|
| `chromatic` | `[60, 120]` |
| `scales` | `[80, 140]` |
| `arpeggios` | `[80, 140]` |
| `intervals` | `[70, 130]` |

These are one player's ranges on one instrument, and they are a starting point
rather than a prescription. `[pool.rhythm]` carries no `tempo`, because rhythm
is a modifier rather than a family.

### `[pool.chromatic]`

| Key | Axis | Accepted values |
|---|---|---|
| `permutations` | `permutation` | lists of the four fingers `1`–`4`; the universe is all 24 orderings. `"all"` accepted |
| `start_strings` | `start_string` | integers `0` to one less than the string count |
| `start_frets` | `start_fret` | integers `0` to `fret_count`, inclusive; 0 is the open string |
| `string_traversals` | `string_traversal` | `adjacent`, `skip_1`, `single_string` |
| `shifts` | `shift` | `none`, `fret_per_cycle`, `position_per_cycle` |
| `spans` | `span` | integers `1` to the string count |

### `[pool.scales]`

| Key | Axis | Accepted values |
|---|---|---|
| `roots` | `root` | integers `0`–`11`, pitch classes with `0` = C |
| `scale_types` | `scale_type` | see [scale types](#scale-types) |
| `traversals` | `traversal` | the two fingering styles `scales` realizes: `positional`, `three_note_per_string` |
| `patterns` | `pattern` | see [patterns](#patterns) |

### `[pool.arpeggios]`

| Key | Axis | Accepted values |
|---|---|---|
| `roots` | `root` | integers `0`–`11` |
| `qualities` | `quality` | see [chord qualities](#chord-qualities) |
| `inversions` | `inversion` | `root`, `first`, `second`, `third` |
| `patterns` | `pattern` | see [patterns](#patterns) |

### `[pool.intervals]`

| Key | Axis | Accepted values |
|---|---|---|
| `intervals` | `interval` | integers `2`–`10`, a 2nd through a 10th |
| `contexts` | `context` | `chromatic`, `diatonic` |
| `roots` | `root` | integers `0`–`11` |
| `scale_types` | `scale_type` | see [scale types](#scale-types) |
| `string_skips` | `string_skip` | `0`, `1`, `2` — adjacent, skipping one, skipping two |
| `patterns` | `pattern` | see [patterns](#patterns) |

`scale_type` is the one **conditional** axis: it is drawn only when the drawn
`context` is `diatonic`. A pool whose `contexts` is `["chromatic"]` alone may
therefore omit `scale_types`; any pool that can draw `diatonic` must declare it.

## `[pool.rhythm]`

The rhythm modifier applies over all four families rather than being a fifth
family, so it has one pool and carries no `tempo`. Every exercise carries these
two axes.

| Key | Axis | Accepted values |
|---|---|---|
| `accent_patterns` | `accent_pattern` | `none`, `every_3`, `every_5`, `displaced` |
| `note_value_patterns` | `note_value_pattern` | `straight`, `long_short`, `short_long` |

The subdivision and time signature are **not** configured here. The layout
fitter derives both from each exercise's note count so the voice tiles into
whole measures, so `subdivisions` and `time_signatures` are no longer sampled
axes — a `[pool.rhythm]` that lists either key is rejected as unknown.

## Axis values

### How a value list is read

Every axis key takes a **list** of candidate values, in the order written, or
the string `"all"`.

- `"all"` expands the axis to every value it accepts. It is honest on
  `roots`, `permutations` and `contexts`; on axes a family realizes only part
  of — `traversals` and `patterns` are shared across families — it fills the
  pool with combinations that family rejects, which costs retries and buys
  nothing.
- An **empty list** is an error: an axis with no candidate values cannot be
  sampled.
- A value outside the axis's universe is an error naming the index in the list
  and listing the accepted values.

Duplicates are kept as written; a value listed twice is simply a value with two
entries in the candidate list.

### Scale types

`ionian`, `dorian`, `phrygian`, `lydian`, `mixolydian`, `aeolian`, `locrian`,
`melodic_minor`, `dorian_b2`, `lydian_augmented`, `lydian_dominant`,
`mixolydian_b6`, `locrian_natural2`, `altered`, `harmonic_minor`,
`locrian_natural6`, `ionian_sharp5`, `dorian_sharp4`, `phrygian_dominant`,
`lydian_sharp2`, `ultralocrian`, `major_pentatonic`, `minor_pentatonic`,
`blues`, `whole_tone`, `diminished_whole_half`, `diminished_half_whole`.

### Chord qualities

`maj`, `min`, `dim`, `aug`, `maj7`, `min7`, `dom7`, `m7b5`, `dim7`,
`min_maj7`, `maj6`, `min6`.

### Patterns

`straight`, `thirds`, `fourths`, `groups_of_3`, `groups_of_4`, `numeric_1235`,
`numeric_1353`, `broken`, `sweep_ordered`, `ascending_pairs`,
`descending_pairs`, `alternating`.

Not every family realizes every pattern: `broken` and `sweep_ordered` are
arpeggio patterns, and the paired patterns belong to `intervals`.

### The registry is the authority

`melete vocabulary` prints every enumerated axis, every accepted identifier and
its display name, from the same registry this validation reads.
`melete families` prints which axes each family requires. Neither can drift
from what melete actually generates; the lists above are a convenience.

## The rules that catch everyone

### An undeclared axis is a loud error, never a default

**An axis a family reads but its `[pool.*]` section does not declare stops the
draw with an error naming both the axis and the section.** Nothing is defaulted,
nothing is inferred from the axes that *were* declared, and the failure lands
before anything is engraved.

This is the same stance as the refusal to default a misspelled key, applied to
an absent one, and the argument is the same: a candidate pool the configuration
did not write produces a sheet the author did not ask for and cannot account
for.

The alternative looks attractive because most axes seem to have an obvious
fallback. `roots` is the axis that shows they do not. Defaulting to all twelve
pitch classes is a drill in random keys nobody asked for; defaulting to C alone
invents the musical judgment that C is the key to practise; and any middle
ground picks a set of keys the author never wrote. **There is no defensible
default for which keys to drill**, so melete declines to choose one, and it
declines uniformly rather than defaulting the easy axes and erroring on the hard
one.

The error arrives at the first draw from that pool — that is, from
`melete generate` — rather than at load, because a pool is only incomplete
relative to the family that samples it.

### A pool section that declares nothing opts the family out

A `[pool.<family>]` section that configures no axis at all (or is absent
entirely) is a family this configuration does not practise, so it is not a
candidate when `[session] shape` is unset. Declaring the section is how a family
is opted **in** to an unshaped draw.

Naming a family in `shape` is the other way in, and it takes the other route: a
family named in `shape` whose pool is empty or half-written is the undeclared
axis error above, not a family quietly dropped.

If no `[pool.<family>]` section configures any axis and no shape is declared,
there is nothing to draw from, and that is an error too.

### An over-constrained pool fails loudly

Axes are sampled independently, so a draw routinely combines values that
contradict each other — chromatic's `single_string` string traversal covers
exactly one string and so requires `span == 1`, yet `string_traversal` and
`span` are drawn without consulting one another, so a `single_string` value
routinely arrives alongside a `span` of 3. A journey that runs off the neck
under the drawn root and fingering style is rejected the same way. Invalid
specifications are discarded and redrawn, up to 500 attempts per exercise. A
high rejection rate is expected and is not a symptom of anything.

Exhausting the retries is a loud error naming the over-constrained axis. It is
never a silent fallback to something that does draw.

## What is renderer-specific

The `[output]` section is the only renderer-specific configuration, and under
alphaTab both of its keys are **inert**. Melete renders to a Guitar Pro `.gp`,
which carries standard notation and tablature together and always shows the key
signature, so `staves` has nothing to select and `key_signatures` has nothing to
switch. Both are still validated, so an existing `config.toml` keeps loading;
they simply no longer change the output.

Every other key on this page describes the instrument, the session or the
candidate pool, and is renderer-agnostic.
