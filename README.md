# kuno

A terminal UI for Kubernetes, focused on the parts of cluster work that happen most often: finding a resource, tailing its logs, reading a manifest or describe output, checking events. Everything is keyboard-driven and fast.

## Requirements

- [uv](https://github.com/astral-sh/uv)
- A valid kubeconfig

## Install

```sh
uv tool install kuno
```

If you don't have uv:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install kuno
```

Then run:

```sh
kuno
```

To update:

```sh
uv tool upgrade kuno
```

## Install from source

```sh
git clone https://github.com/1cadumagalhaes/kuno
cd kuno
uv sync
uv run python -m kuno
```

## Usage

```
kuno [-c CONTEXT] [-n NAMESPACE] [-d]
```

| flag | description |
|---|---|
| `-c`, `--context` | Kubernetes context to use (overrides config default) |
| `-n`, `--ns`, `--namespace` | Namespace to use (overrides config default) |
| `-d`, `--debug` | Write debug output to `/tmp/kuno_debug.log` |

### Navigation

`j` / `k` or arrow keys move through the resource list. `g` / `G` jump to top and bottom.

Press `:` to open the command palette. Most features are commands:

| command | description |
|---|---|
| `:pods` | list pods |
| `:deployments` | list deployments |
| `:statefulsets` | list stateful sets |
| `:services` | list services |
| `:pvc` | list persistent volume claims |
| `:secrets` | list secrets |
| `:contexts` | switch context |
| `:namespaces` | switch namespace |
| `:logs` | open logs for selected resource |
| `:yaml` | view raw manifest |
| `:describe` | describe output with inline events |
| `:events` | namespace-wide events |
| `:delete` | delete selected resource |
| `:restart` | rollout restart selected resource |
| `:config` | open config screen |
| `:theme NAME` | switch theme |
| `:keys` | show all keybindings |

`ctrl+p` opens the command palette with the same actions plus context and namespace switching.

Inside the logs screen, `/` toggles a search bar. `n` / `N` cycle matches. `w` toggles line wrapping. `t` toggles timestamps. `f` toggles follow mode.

In the manifest and describe screens, `/` also toggles search. `[` and `]` jump between YAML keys at any nesting level.

## Configuration

kuno reads from `~/.config/kuno/config.toml` on startup and writes back when you save from `:config`.

```toml
[ui]
theme = "nord"
yaml_theme = "monokai"

[logs]
wrap = false
timestamps = false
mode = "raw"        # raw or structured
tail_lines = 500

[defaults]
# context = "my-context"
# namespace = "default"
```

`theme` accepts any [Textual built-in theme](https://textual.textualize.io/guide/design/#themes). `yaml_theme` accepts any Pygments style name.

## Development

```sh
uv sync
make test
make check   # format + lint + typecheck + tests
make run     # run against current kubeconfig
```

To target a specific context or namespace during development:

```sh
make run CTX=my-context NS=my-namespace
```
