# XNU Kernel for Google Pixel 10 (Tensor G5)

Built on GitHub's macOS arm64 runners by `.github/workflows/xnu.yml`, using
[blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) (MIT) at a pinned commit.

- `MACOS_VERSION=13.5` -> xnu-8796 (same generation as iOS 16.7.16 `20H392`).
- `patches/*.patch` are copied into the build script's patch dir and applied to the XNU tree with `git apply`.
- Output: `kernel.pixel10` as a workflow artifact.

Fetch the latest build: `gh run download -n xnu-kernel -D xnu/out`
