# Offline sandbox (orphan branch)

Built 2026-10-31T02:46:14Z from commit `f466d86` for platform `linux-64`.
`pixi.lock` sha256 `d60fe18e98ffa851b014f36f2310b2e7b102f49c56d4fc514ac7f67ef7435209`.

The verified self-bootstrap binary is stored at `.pixi-sandbox/tools/linux-64/pixi-sandbox`. The branch root intentionally contains documentation only.

| env | platform | packed | unpacked | files |
| --- | --- | ---: | ---: | ---: |
| `build` | linux-64 | 80.6 MiB | 293.7 MiB | 109 |
| `bun` | linux-64 | 40.3 MiB | 119.8 MiB | 21 |
| `default` | linux-64 | 737.2 MiB | 3134.0 MiB | 463 |


## Restore on the disconnected machine

```bash
./.pixi-sandbox/tools/linux-64/pixi-sandbox doctor --branch-location . --verify
./.pixi-sandbox/tools/linux-64/pixi-sandbox restore --branch-location . --output-path <project> --force
# then, from <project> with no network, use pixi as the sole entrypoint:
pixi install --frozen --offline
pixi run --frozen -- cargo build --offline
```

Every manifest blob is verified before it is written into the working tree.
