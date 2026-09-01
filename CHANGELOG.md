# Changelog

## [0.2.2] - 2026-09-01

### Fixes

- Recovered pooled kube clients after stale connections (idle timeout, network switch) instead of failing forever until restart.
- Bounded Kubernetes API requests with a 60s total timeout so a dead network can no longer wedge the polling loop.

### Verification

- Ruff and full test suite pass: `193 passed`.

## [0.2.1] - 2026-08-28

### Fixes

- Added `kuno --version` and `kuno -v` CLI flags.
- Fixed release type-checking failures in table sorting.
- Refreshed release validation and packaging metadata.

### Verification

- Ruff, ty, and full test suite pass: `193 passed`.

## [0.2.0] - 2026-08-28

### Highlights

- Added persistent namespace memory per Kubernetes context.
- Added a floating shortcut guide opened with `?`, including global, view-specific, command-palette, Logs, YAML, and detail-screen shortcuts.
- Added separate log copy modes: `Y` copies rendered output and `Ctrl+C` copies raw output.
- Added deployment workload logs from a selected pod with `Ctrl+L`.
- Added structured formatting for workload logs with pod prefixes.

### Kubernetes

- Added detailed pod status reporting, including `OOMKilled` and `CrashLoopBackOff`.
- Added cleanup commands for failed, succeeded, and evicted pods.
- Improved Kubernetes client reuse and shutdown handling.
- Fixed context-switch races affecting clear operations and refreshes.
- Fixed namespace restoration when switching contexts.
- Added fallback when a remembered namespace no longer exists.

### Logs

- Logs now begin streaming when the Logs screen opens.
- Deployment workload logs load concurrently across pods.
- Added structured/raw log display modes, parsing limits, and memoized parsing.
- Preserved pod identity when formatting workload logs.
- Simplified the Logs footer to show the most relevant actions.

### Performance and UX

- Deferred expensive third-party imports to improve startup time.
- Optimized table row indexing and refresh behavior.
- Preserved table state during sorting and reordering.
- Reduced unnecessary detail-panel rendering.
- Improved confirmation-dialog keyboard navigation.
- Added regression coverage across client lifecycle, context switching, logs, Kubernetes resources, table synchronization, and UI behavior.

### Commits Included

- `05d53fd` Reuse shared KubeClient per context and cache namespaces
- `0ec37f8` Start log streaming on mount so follow mode is active by default
- `ffd63ad` Remember the last namespace used per context
- `60ea689` Make confirmation dialog arrow keys move focus between buttons
- `964f2fc` Show detailed pod statuses
- `a306ac6` Add cleanup for failed, succeeded, and evicted pods
- `d9510c1` Memoize log parsing and enforce LogView max lines
- `7a9b8bd` Preserve TableSync on sort and reorder rows without clearing columns
- `c91339a` Defer heavy third-party imports to cut startup time
- `61b7e9e` Index rows by key, skip unchanged detail re-render, and copy highlighted line
- `4352156` Stabilize shared client and context switching
- `8afbffd` Split rendered and raw log copying
- `d7674ac` Size shortcut guide as a floating panel
- `848c9ad` Show active screen shortcuts
- `6e3e957` Trim Logs footer shortcuts
- `a8d1f8f` Format prefixed workload logs
- `aeefa8e` Parallelize deployment log loading
- `0fc7966` Open deployment logs from pods

### Verification

- Full test suite: `190 passed`.
