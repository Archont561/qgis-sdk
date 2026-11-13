# Offline sandbox (orphan branch)

Built 2026-11-13T00:16:23Z from commit `b1afbeb` for platform `linux-64`.
`pixi.lock` sha256 `04a19f9d9c31ead10d9198d2d2d0699567670eee3081814275ebc635d98faea9`.

The verified self-bootstrap binary is stored at `.pixi-sandbox/tools/linux-64/pixi-sandbox`. The branch root intentionally contains documentation only.

| env | platform | packed | unpacked | files |
| --- | --- | ---: | ---: | ---: |
| `build` | linux-64 | 81.3 MiB | 296.0 MiB | 112 |
| `bun` | linux-64 | 40.3 MiB | 119.8 MiB | 21 |
| `default` | linux-64 | 737.9 MiB | 3136.3 MiB | 466 |


## Restore on the disconnected machine

```bash
./.pixi-sandbox/tools/linux-64/pixi-sandbox doctor --branch-location . --verify
./.pixi-sandbox/tools/linux-64/pixi-sandbox restore --branch-location . --output-path <project> --force
# then, from <project> with no network, use pixi as the sole entrypoint:
pixi install --frozen --offline
pixi run --frozen -- cargo build --offline
```

Every manifest blob is verified before it is written into the working tree.
