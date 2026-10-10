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

They are kept unmodified so that the vendored contract is tested against what the kernel
really writes. The hand-written `valley-fold.fold` one directory up predates kernel 0.2.
The cartridges are licensed CERN-OHL-W-2.0 by their authors (see each `project.json` in
the commons), not under this repository's Apache-2.0. Re-render them when the kernel's
output changes, and re-vendor the schema when Pliego changes it.
