# Real kernel-0.2 sheet documents

These are emitted by the Pliego kernel at
[madfam-org/pliego](https://github.com/madfam-org/pliego) `4b3fbfe` (main, kernel 0.2.0), from
the cartridges of [madfam-org/sheet-hyperobjects](https://github.com/madfam-org/sheet-hyperobjects)
`5516c3b` (main):

```bash
PYTHONPATH=<pliego>/packages/kernel/src PLIEGO_MATERIALS=<pliego>/materials \
  python -m pliego.cartridge <cartridge> --out <dir>
```

| File | Cartridge | Mode / preset |
|---|---|---|
| `valley-fold.default.fold` | `valley-fold` | `default` |
| `reveal-block.default.preview.fold` | `reveal-block` | `default:preview` (uses `pliego:pieces` and the step `remove`) |

A second set was emitted by the kernel at `pliego@6b6243a` (main, still kernel 0.2.0,
with the packaging blocks of pliego#8 and the print layout of pliego#9), from
sheet-hyperobjects `2c12300` (main) and from the open commons PR branches that first use
those blocks: `w2b/packaging` at `a8a015d` (madfam-org/sheet-hyperobjects#7) and
`w2b/papercraft` at `127c3ff` (#9). Same command, kernel and materials from `6b6243a`.

| File | Cartridge (source) | Mode / preset | Exercises |
|---|---|---|---|
| `folding-carton.carton.fold` | `folding-carton` (`w2b/packaging`) | `carton` | `pliego:dielines`, `pliego:artwork` |
| `embossed-stationery.card.fold` | `embossed-stationery` (`w2b/packaging`) | `card` | `pliego:finishes` (emboss) |
| `papercraft-unfold.fold.crystal.fold` | `papercraft-unfold` (`w2b/papercraft`) | `fold:crystal` | `pliego:annotations`, `pliego:pages` |
| `origamic-architecture.default.fold` | `origamic-architecture` (main) | `default` | `pliego:meta.min_feature_mm` |

If a PR branch changes its cartridge before it merges, these files stay what that commit's
cartridge produced: they test the contract, not the cartridge.

They are kept unmodified so that the vendored contract is tested against what the kernel
really writes. The hand-written `valley-fold.fold` one directory up predates kernel 0.2.
The cartridges are licensed CERN-OHL-W-2.0 by their authors (see each `project.json` in
the commons), not under this repository's Apache-2.0. Re-render them when the kernel's
output changes, and re-vendor the schema when Pliego changes it.
