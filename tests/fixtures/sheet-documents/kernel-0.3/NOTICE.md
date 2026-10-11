# Real kernel-0.3 sheet documents

These are emitted by the Pliego kernel at
[madfam-org/pliego](https://github.com/madfam-org/pliego) `2f85906` (main, kernel 0.3.0), from
the cartridges of [madfam-org/sheet-hyperobjects](https://github.com/madfam-org/sheet-hyperobjects)
`ddc3ed3` (main, 139 cartridges):

```bash
PYTHONPATH=<pliego>/packages/kernel/src PLIEGO_MATERIALS=<pliego>/materials \
  python -m pliego.cartridge <cartridge> --out <dir>
```

| File | Cartridge | Mode / preset | Exercises |
|---|---|---|---|
| `valley-fold.default.fold` | `valley-fold` | `default` | a kinematic fold program |
| `reveal-block.default.preview.fold` | `reveal-block` | `default:preview` | `pliego:pieces` and the step `remove` |
| `folding-carton.carton.fold` | `folding-carton` | `carton` | `pliego:dielines`, `pliego:artwork` |
| `embossed-stationery.card.fold` | `embossed-stationery` | `card` | `pliego:finishes` (emboss) |
| `papercraft-unfold.fold.crystal.fold` | `papercraft-unfold` | `fold:crystal` | `pliego:annotations`, `pliego:pages` |
| `origamic-architecture.default.fold` | `origamic-architecture` | `default` | `pliego:meta.min_feature_mm` |

They replace `../kernel-0.2/` as the current output. Kernel 0.3 stamps the spec §5.15
digest (RFC 8785), which `pliego_spec.canonical` reproduces; kernel 0.2 stamped the GOC-1
form, so `../kernel-0.2/` is kept unmodified as the record of that contract change (its
test says which three files now fail rule 10, and why).

They are kept unmodified so that the vendored contract is tested against what the kernel
really writes; they test the contract, not the cartridge. The cartridges are licensed
CERN-OHL-W-2.0 by their authors (see each `project.json` in the commons), not under this
repository's Apache-2.0. Re-render them when the kernel's output changes, and re-vendor the
schema when Pliego changes it.
