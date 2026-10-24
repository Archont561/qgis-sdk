# Offline sandbox (orphan branch)

Built 2026-10-24T22:42:18Z from commit `7e1bbb9` for platform `linux-64`.
`pixi.lock` sha256 `7402a1c70f7fa13a72dc6c4adeb180108500e161a5522ccee5969f7ffac32664`.

The verified self-bootstrap binary is stored at `.pixi-sandbox/tools/linux-64/pixi-sandbox`. The branch root intentionally contains documentation only.

| env | platform | packed | unpacked | files |
| --- | --- | ---: | ---: | ---: |
| `build` | linux-64 | 74.5 MiB | 279.0 MiB | 111 |
| `bun` | linux-64 | 40.3 MiB | 119.8 MiB | 21 |
| `default` | linux-64 | 731.8 MiB | 3122.1 MiB | 466 |


## Restore on the disconnected machine

```bash
./.pixi-sandbox/tools/linux-64/pixi-sandbox doctor --branch-location . --verify
./.pixi-sandbox/tools/linux-64/pixi-sandbox restore --branch-location . --output-path <project> --force
# then, from <project> with no network, use pixi as the sole entrypoint:
pixi install --frozen --offline
pixi run --frozen -- cargo build --offline
```

Every manifest blob is verified before it is written into the working tree.
