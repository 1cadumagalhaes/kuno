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

> kuno requires Python 3.14+. If your system Python is older, uv automatically downloads a compatible interpreter.

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

Press `:` to open the command bar, or `ctrl+p` for the Textual system command palette.

### Key Bindings (main explorer)

| Key | Action |
|---|---|
| `j` / `k` or arrows | Navigate list |
| `g` / `G` | Jump top / bottom |
| `Enter` | Drill into selected resource |
| `d` | **Describe** selected resource |
| `i` | Toggle **Info** side panel |
| `y` | View **YAML** manifest |
| `r` | **Refresh** current view |
| `L` or `l` | Open **Logs** for selected resource |
| `C` | Jump to **Contexts** view |
| `N` | Jump to **Namespaces** view |
| `ctrl+d` | **Delete** selected resource (with confirmation) |
| `ctrl+r` | **Restart** selected deployment/statefulset (with confirmation) |
| `ctrl+e` | View **Events** |
| `ctrl+o` | **Sort** cycle |
| `Backspace` | Go back |
| `?` | Show all keybindings |
| `:` | Open command bar |
| `ctrl+p` | Textual system command palette |

### `:` Commands

| command | description |
|---|---|
| `:pods` / `:containers` | switch to pods / containers |
| `:deploy` / `:deployments` | switch to deployments view |
| `:sts` / `:statefulsets` | switch to statefulsets view |
| `:svc` / `:services` | switch to services view |
| `:pvc` | switch to PVC view |
| `:secrets` | switch to secrets view |
| `:contexts` | switch to contexts view |
| `:namespaces` / `:ns [name]` / `:namespace [name]` | switch or set namespace |
| `:ctx <name>` | switch context |
| `:logs` | open logs for selected resource |
| `:yaml` | view raw manifest |
| `:describe` | describe output with inline events |
| `:events` | view events |
| `:del` / `:delete` | delete selected resource (with confirmation) |
| `:restart` | rollout restart selected resource (with confirmation) |
| `:info` / `:hide-info` | toggle the info side panel |
| `:config` | open config screen |
| `:theme [name]` | cycle or set theme |
| `:help` | show this command list |

### Logs Screen

| Key | Action |
|---|---|
| `y` / `ctrl+c` | Copy text selection (if any) |
| `d` | Open log detail panel |
| `f` | Toggle follow mode |
| `j` / `k` | Previous / next line |
| `g` / `G` | Jump to top / bottom |
| `/` | Focus filter input |
| `s` | Focus since (time) input |
| `t` | Toggle timestamps |
| `w` | Toggle line wrapping |
| `m` | Cycle display mode (raw / structured) |
| `r` | Reload logs |
| `ctrl+u` | Clear filter |
| `n` / `N` | Cycle search matches |
| `[` / `]` | Previous / next pod (workload views) |
| `ctrl+h` / `ctrl+l` | Previous / next container |

### Manifest / Describe Screens

`/` toggles search. `[` and `]` jump between YAML keys at any nesting level.

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
