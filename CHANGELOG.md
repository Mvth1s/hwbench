# CHANGELOG

<!-- version list -->

## v0.5.0 (2026-10-09)

### Bug Fixes

- **display**: Never raise on an unreadable date
  ([`dc3c28a`](https://github.com/Mvth1s/hwbench/commit/dc3c28aaa68f005f9f9bec7efae46f9afd4d24b7))

- **leaderboard**: Add a favicon to the site pages
  ([`b4cc954`](https://github.com/Mvth1s/hwbench/commit/b4cc954bc77cac46ba279a19eafa0b2df061688d))

- **leaderboard**: Refuse submissions with an invalid export date
  ([`aa4b946`](https://github.com/Mvth1s/hwbench/commit/aa4b9463ea2cbd8016c12c8bcfbfb5ed58c72cf5))

- **leaderboard**: Show the normalized GPU name and DD/MM/YYYY dates
  ([`6e9a7a8`](https://github.com/Mvth1s/hwbench/commit/6e9a7a8ef800adb410bd2fe291320697af010c0c))

### Continuous Integration

- Add a stdlib discord notification script
  ([`cdcb5b3`](https://github.com/Mvth1s/hwbench/commit/cdcb5b35184620b44fd2fec3830336bbf660eb7b))

- Add a weekly project report on discord
  ([`42f98ce`](https://github.com/Mvth1s/hwbench/commit/42f98ceaf7c43ab223adce9c1d2039f67a4faf0f))

- Add a weekly watch of bench tool and python versions
  ([`0a3e28d`](https://github.com/Mvth1s/hwbench/commit/0a3e28d7f7f36ea968c40354553f3ff52a931f4c))

- Announce releases and pypi publication on discord
  ([`f66b1f9`](https://github.com/Mvth1s/hwbench/commit/f66b1f9f417010d6550a3988b645456e66581cd1))

- Announce site deployments and new leaderboard machines
  ([`aabcb45`](https://github.com/Mvth1s/hwbench/commit/aabcb458edbe972651fdffe0127f813e53851826))

- Notify discord of ci, leaderboard and dependabot results
  ([`9fd735b`](https://github.com/Mvth1s/hwbench/commit/9fd735b53d98223c372327bb3a08d5ff68740ec8))

- Pin actions/checkout by commit sha in notification jobs
  ([`13514d4`](https://github.com/Mvth1s/hwbench/commit/13514d409d8f0f884507269f9a2f336b99590aae))

### Documentation

- Describe the discord notifications in the readme
  ([`cc4be77`](https://github.com/Mvth1s/hwbench/commit/cc4be776f941287085a7082398636c2bc92c684c))

- Record the discord notification rules in CLAUDE.md
  ([`6853f1f`](https://github.com/Mvth1s/hwbench/commit/6853f1f1f857c5c9d410ebc6259c0270906eabae))

- Verify provenance on the latest release instead of v0.3.0
  ([`aa60f13`](https://github.com/Mvth1s/hwbench/commit/aa60f13c7a39c1fb0d45ced5364e4742c0f1091f))

### Features

- **leaderboard**: Add a summary command with combined ranks
  ([`e70f642`](https://github.com/Mvth1s/hwbench/commit/e70f642d3eda89835d4f697a01523996348e9d17))

- **leaderboard**: Annotate refused submissions under github actions
  ([`4c43af1`](https://github.com/Mvth1s/hwbench/commit/4c43af1d27a2d4a59705464caa82861695d6e215))

### Refactoring

- Add gpu_name, the GPU name in its original case
  ([`fc23f66`](https://github.com/Mvth1s/hwbench/commit/fc23f662bd515582007afb123eeaa7b238b22858))

- **display**: Share the DD/MM/YYYY date formatter in fmt
  ([`e172d3a`](https://github.com/Mvth1s/hwbench/commit/e172d3ab5948f6dc0eb309bcdf2ff02fdfb822ce))


## v0.4.0 (2026-10-05)

### Bug Fixes

- **ci**: Keep the leaderboard validator out of the PR's reach
  ([`1633309`](https://github.com/Mvth1s/hwbench/commit/1633309e40849b40057a5f63cd90174a295643c8))

- **leaderboard**: Compare every stored score with the recomputed one
  ([`b011cfb`](https://github.com/Mvth1s/hwbench/commit/b011cfbd97a8e97f87d1ddcc8c663f18a2ad3ccd))

- **leaderboard**: Parse submitted JSON strictly
  ([`c885b93`](https://github.com/Mvth1s/hwbench/commit/c885b93526dbef46830b9a02014fbc6b834c9e6e))

- **leaderboard**: Refuse a symlinked results directory and path traversal
  ([`8da781f`](https://github.com/Mvth1s/hwbench/commit/8da781f51591496a93966fac826483f1721601de))

- **leaderboard**: Refuse symlinks and bound reads of submitted files
  ([`9b718af`](https://github.com/Mvth1s/hwbench/commit/9b718afac90fd02bb3a7881d7e8dc23a306d7f4a))

### Chores

- **results**: Add the B850 desktop as the first leaderboard entry
  ([`9039d56`](https://github.com/Mvth1s/hwbench/commit/9039d568f4a1eefdfc3caf65d2b6a8b1e9b3127b))

### Continuous Integration

- Deploy the leaderboard to GitHub Pages on push to main
  ([`5b200d8`](https://github.com/Mvth1s/hwbench/commit/5b200d852ee0f4c8636d8dff547933b3177c6c9a))

- Validate leaderboard submissions on pull requests
  ([`cd895af`](https://github.com/Mvth1s/hwbench/commit/cd895af7ee8447f09fc8ef3262658d7b1dc6c288))

### Documentation

- Add a license section and an explicit AGPL badge to the README
  ([`e61e0ae`](https://github.com/Mvth1s/hwbench/commit/e61e0ae5eaf7e22b1b014adacca6e1b357ec0b3c))

- Add CONTRIBUTING.md for leaderboard submissions
  ([`d067751`](https://github.com/Mvth1s/hwbench/commit/d06775168d902792d14129541d37ad9245ad988b))

- Document the leaderboard in the README and CLAUDE.md
  ([`fd3d215`](https://github.com/Mvth1s/hwbench/commit/fd3d215a8a2f6c1086d7ffa5dd86c0c726a509f5))

- Publish leaderboard results under CC0-1.0 (CONTRIBUTING)
  ([`ef9b8b6`](https://github.com/Mvth1s/hwbench/commit/ef9b8b65d4fc7612f9cfe3a337a5a308aa575c45))

- Record the AGPL-3.0-or-later license rules in CLAUDE.md
  ([`9101c99`](https://github.com/Mvth1s/hwbench/commit/9101c995506787218eaee8251a3fc2869ef3023c))

### Features

- **leaderboard**: Generate the static leaderboard site
  ([`29dd170`](https://github.com/Mvth1s/hwbench/commit/29dd17040f640fa12fa27001e670daa35bf84992))

- **leaderboard**: Validate exports submitted to the leaderboard
  ([`381c1ed`](https://github.com/Mvth1s/hwbench/commit/381c1ed1ae83b12dc4cf5db4493935c40584f961))

- **license**: Relicense under AGPL-3.0-or-later, versions up to 0.3.0 remain MIT
  ([`632e32d`](https://github.com/Mvth1s/hwbench/commit/632e32d529c52fd86b28480cee9e374ac109e113))


## v0.3.0 (2026-10-04)

### Build System

- Complete package metadata for PyPI
  ([`a40f0d8`](https://github.com/Mvth1s/hwbench/commit/a40f0d85ec59ac2a43ed0d3fa364165598c1d389))

### Continuous Integration

- Add a script reproducing the CI locally
  ([`abe28f3`](https://github.com/Mvth1s/hwbench/commit/abe28f3f4207493463c40e74fd589e414891fd2e))

- Add Dependabot updates for Python dependencies
  ([`a852677`](https://github.com/Mvth1s/hwbench/commit/a852677efffed4bbcce9783d6bb15f610c7f3f69))

- Report test coverage in the job summary
  ([`5573098`](https://github.com/Mvth1s/hwbench/commit/55730982bdf767f4170ebe7081e305ca9d85518c))

- **release**: Attest build provenance of release artifacts
  ([`3c9b3b0`](https://github.com/Mvth1s/hwbench/commit/3c9b3b0356729ff35d16ea73200231eca005d107))

- **release**: Publish to PyPI with trusted publishing
  ([`a9dec1a`](https://github.com/Mvth1s/hwbench/commit/a9dec1ab1ce2e4a223950124deae887d56e680d9))

### Documentation

- Add CI, release and license badges to the README
  ([`2515e42`](https://github.com/Mvth1s/hwbench/commit/2515e42e61d885e2bd2fb27b307f047cc6f81448))

- Add the MIT license text
  ([`2c641f0`](https://github.com/Mvth1s/hwbench/commit/2c641f0b253dab5cf78ccb9a0a5c405a7fb22efb))

- Commit subject case, commitlint before merge and zsh pitfalls in CLAUDE.md
  ([`611c54a`](https://github.com/Mvth1s/hwbench/commit/611c54a7f8f1f7885fa54bb99ed058b3d9c5f18b))

- Drop the stale phase status line from the README
  ([`52087ac`](https://github.com/Mvth1s/hwbench/commit/52087aca573bc4059809802fc4d90fb2f4feac46))

- Explain how to verify release provenance with gh attestation
  ([`15355cb`](https://github.com/Mvth1s/hwbench/commit/15355cb78764a593175e40c0f62a7f683d128ab4))

- Install from PyPI first, git URL as an alternative
  ([`b464024`](https://github.com/Mvth1s/hwbench/commit/b4640247063e1c2ad99bbfa06827604473db3458))

- Never gate a merge on a piped command (CLAUDE.md)
  ([`05b6610`](https://github.com/Mvth1s/hwbench/commit/05b66109bbe39afc8d0876cffbe47755839e23dc))

- Record phase A conventions in CLAUDE.md
  ([`0b8c9d2`](https://github.com/Mvth1s/hwbench/commit/0b8c9d29564beb5bffcc2750d95a28cd0395ec1b))

- Run scripts/ci-local.sh before every merge (CLAUDE.md)
  ([`80e9ab0`](https://github.com/Mvth1s/hwbench/commit/80e9ab07239165fc2e0311b873a11ff6322fb9a3))

### Features

- **cli**: Add hwbench --version
  ([`c7597b9`](https://github.com/Mvth1s/hwbench/commit/c7597b9e5c72f3b8b1b5781d85f72c9b955d7dfc))

- **cli**: Shell completion for fish and bash
  ([`cd64945`](https://github.com/Mvth1s/hwbench/commit/cd64945eac8301b0212d1e1aa923bb0f7fcb903b))

### Testing

- Check completion options without parsing the rendered help
  ([`4eb307d`](https://github.com/Mvth1s/hwbench/commit/4eb307d0da6da10edd9f0a3122cb476a5d0d571f))


## v0.2.0 (2026-10-04)

### Bug Fixes

- **compare**: Flag GPU driver differences only between same-GPU files
  ([`1a19258`](https://github.com/Mvth1s/hwbench/commit/1a19258304d2007c84d2addb9c9a537dadcb2a6c))

- **scoring**: Warn about the GPU driver only on the reference GPU
  ([`d6dba1c`](https://github.com/Mvth1s/hwbench/commit/d6dba1c06d3a114e62c99ac6ffb74f3fbf5b38b0))

### Continuous Integration

- **deps**: Bump actions/checkout from 4 to 7
  ([`80ccb8a`](https://github.com/Mvth1s/hwbench/commit/80ccb8afc5692093b20a4f9f4df0672a94362f07))

- **deps**: Bump actions/setup-node from 4 to 7
  ([`3beba7a`](https://github.com/Mvth1s/hwbench/commit/3beba7a5c29e57be27da7a8a7a1a239d3e149917))

- **deps**: Bump actions/setup-python from 5 to 7
  ([`166c11c`](https://github.com/Mvth1s/hwbench/commit/166c11ce8cf2201e751d55878c171b6975a28ea0))

### Documentation

- Describe the same-GPU, upstream-version GPU driver notice
  ([`102e055`](https://github.com/Mvth1s/hwbench/commit/102e055e1be514cd812e14a4cdfb666bb13141d6))

- Regenerate the reference only on bench or tool version changes
  ([`1c05142`](https://github.com/Mvth1s/hwbench/commit/1c05142ee8f9356b4b36dd71325f3fa3d27dfdf7))

### Features

- **compare**: Warn when the GPU driver differs between exports
  ([`c10aa1b`](https://github.com/Mvth1s/hwbench/commit/c10aa1b4cabd3e46d5feeb21a82eab6b305805c0))

- **scoring**: Warn when the GPU driver differs from the reference
  ([`2150c74`](https://github.com/Mvth1s/hwbench/commit/2150c748abf73326639002b8444ffecb6a548ebc))


## v0.1.0 (2026-10-03)

- Initial Release

## Before v0.1.0 (history prior to conventional commits)

The entries above are generated by python-semantic-release from conventional commits. The work
below predates that convention; it is summarised by phase from the git history.

### Phase 4: export and comparison

- `hwbench export -o FILE`: runs the benchmarks and writes a versioned JSON export (components
  without identifiers, results, scores, reference digest).
- `hwbench compare FILES...`: side-by-side comparison with percentage deltas; benches compared
  only with the same protocol version, tool version and presentation mode, scores only against
  the same reference with the same backends and weights.
- Rich markup from export files, firmware strings and tool errors is never interpreted.

### Phase 3: external backends and scoring

- sysbench (CPU single/multi), glmark2 (4K off-screen) and vkmark (4K headless) backends;
  `hwbench backends` with availability and install hints.
- Scoring against a reference machine (ASRock B850 desktop = 1000 points), native-only CPU
  categories, GPU geometric mean, weighted combined score, no silent averaging.
- `hwbench reference` with on-AC / performance-profile / stable-warm-up safeguards (`--force`).
- Desktop power detection, disambiguated sensors, RAM slot labels and EXPO/XMP speeds.

### Phase 2: benchmark engine

- Native CPU single-core and multi-core benchmarks (`multiprocessing`), adaptive warm-up with a
  cold "burst" run kept apart, median of at least 3 runs, machine state (governor, platform
  profile, EPP, power, temperature) and warnings.

### Phase 1: hardware inventory

- `hwbench info` for CPU, RAM, GPU, disks (SMART), board/BIOS, sensors and power, with
  identifiers filtered at collection time (`--show-serials` for local display only).
