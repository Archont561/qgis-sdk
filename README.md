# Offline sandbox (orphan branch)

Built 2026-11-19T22:03:37Z from commit `d44858c` for platform `linux-64`.
`pixi.lock` sha256 `ceac67db6d2d26d1f3bf81e7b0a7f83520b5533ea425f9bea29e41ab74592e6b`.

The verified self-bootstrap binary is stored at `.pixi-sandbox/tools/linux-64/pixi-sandbox`. The branch root intentionally contains documentation only.

| env | platform | packed | unpacked | files |
| --- | --- | ---: | ---: | ---: |
| `build` | linux-64 | 81.7 MiB | 297.3 MiB | 117 |
| `bun` | linux-64 | 40.3 MiB | 119.8 MiB | 21 |
| `default` | linux-64 | 738.1 MiB | 3137.1 MiB | 470 |


## Restore on the disconnected machine

```bash
./.pixi-sandbox/tools/linux-64/pixi-sandbox doctor --branch-location . --verify
./.pixi-sandbox/tools/linux-64/pixi-sandbox restore --branch-location . --output-path <project> --force
# then, from <project> with no network, use pixi as the sole entrypoint:
pixi install --frozen --offline
pixi run --frozen -- cargo build --offline
```

Every manifest blob is verified before it is written into the working tree.
