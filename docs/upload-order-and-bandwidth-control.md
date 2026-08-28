# Upload Order and qBittorrent Bandwidth Control

Upload Assistant can coordinate two upload phases:

- **Usenet phase**: post the payload to Usenet, generate the NZB, and submit it to selected Usenet indexers.
- **Torrent tracker phase**: upload the torrent to the selected torrent trackers.

`upload_order` controls how those phases are sequenced. qBittorrent bandwidth settings can pause at a phase boundary or before individual torrent tracker uploads, depending on the selected workflow.

## Configuration

Add these settings to `DEFAULT` in the user-state `config.py` that Upload Assistant reads after initialization. Do not edit the bundled `data/example_config.py` in the checkout.

- Windows: `%LOCALAPPDATA%\Upload-Assistant\data\config.py`
- Linux/macOS: `$XDG_DATA_HOME/Upload-Assistant/data/config.py` (normally `~/.local/share/Upload-Assistant/data/config.py`)
- Custom state directory: `<UA_DATA_DIR>/data/config.py`

```python
"upload_order": "concurrent",
"qbit_bandwidth_control": False,
"qbit_bandwidth_control_after_usenet": False,
"qbit_bandwidth_threshold": 500,
"qbit_bandwidth_time": 30,
```

- `upload_order`: `"concurrent"`, `"usenet"`, or `"tracker"`.
- `qbit_bandwidth_control`: master switch for every bandwidth check. When `False`, no workflow checks qBittorrent speed.
- `qbit_bandwidth_control_after_usenet`: when `True`, retain per-tracker checks after the Usenet phase in the `"usenet"` workflow. The default is `False`.
- `qbit_bandwidth_threshold`: maximum average qBittorrent upload speed in KB/s.
- `qbit_bandwidth_time`: averaging period in seconds. The upload continues when the measured average is at or below the threshold.

`qbit_bandwidth_control` must be `True`, and both the threshold and time must be greater than zero, for a bandwidth check to run.

Bandwidth is sampled immediately and then every five seconds. The rolling window contains `max(1, qbit_bandwidth_time // 5)` samples, so values from 1 through 9 use one immediate sample and non-multiples of five do not measure the exact requested duration.

Bandwidth checks require the `DEFAULT.default_torrent_client` to be a directly accessible qBittorrent client. Configure `qbit_url`, `qbit_port`, and either `qbit_api_key` or `qbit_user` and `qbit_pass` under that client in `TORRENT_CLIENTS`:

```python
"qbittorrent": {
    "torrent_client": "qbit",
    "qbit_url": "http://127.0.0.1",
    "qbit_port": "8080",
    "qbit_api_key": "your-api-key",
},
```

The QUI reverse proxy is not used for bandwidth measurements. Direct qBittorrent connection settings are still required when `qui_proxy_url` is configured.

## Workflows

| `upload_order` | Phase sequence                                                                                  | Per-tracker bandwidth control                  |
| -------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `concurrent`   | Usenet and torrent tracker phases start together. There is no phase-boundary bandwidth check.   | Checks before each tracker when enabled.       |
| `usenet`       | When enabled, check bandwidth; complete the Usenet phase; then upload to all torrent trackers.  | Follows `qbit_bandwidth_control_after_usenet`. |
| `tracker`      | Complete the torrent tracker phase; when enabled, check bandwidth; then start the Usenet phase. | Checks before each tracker when enabled.       |

### Concurrent

Use `"concurrent"` for the shortest overall runtime when Usenet and torrent traffic may run at the same time.

If `qbit_bandwidth_control` is enabled, the torrent tracker phase checks bandwidth before each tracker and processes those tracker uploads sequentially. The Usenet phase starts independently and does not wait for those checks.

### Usenet first

Use `"usenet"` when the Usenet post must have the connection first:

1. If bandwidth control is enabled and a Usenet upload is requested, wait until qBittorrent bandwidth satisfies the configured threshold and time.
2. Post to Usenet and submit the resulting NZB to the selected Usenet indexers.
3. Upload to all torrent trackers. By default there are no additional checks; enable `qbit_bandwidth_control_after_usenet` to check before each tracker.

The subordinate setting only applies when the master `qbit_bandwidth_control` setting is enabled. If no Usenet upload is requested, the special post-Usenet behavior is not applied; torrent trackers retain their normal configured behavior.

### Torrent trackers first

Use `"tracker"` when tracker uploads should finish before Usenet begins:

1. Upload to the torrent trackers. If `qbit_bandwidth_control` is enabled, check before each tracker and repeat its duplicate check after a successful bandwidth wait.
2. When bandwidth control is enabled and both phases are present, check qBittorrent bandwidth after the torrent tracker phase.
3. Post to Usenet and submit the NZB to the selected Usenet indexers.

Because the master switch enables both kinds of checks, this workflow can check before each torrent tracker and again before Usenet.

### Single-phase uploads

When only torrent trackers are selected, there is no phase-boundary check. The trackers follow the normal `qbit_bandwidth_control` setting regardless of `upload_order`.

When only Usenet is selected, `"usenet"` checks bandwidth before posting only when control is enabled. `"concurrent"` and `"tracker"` start the Usenet phase without a boundary check because there is no torrent tracker phase to coordinate.

## Command-line overrides

The equivalent CLI options are:

| Short option | Long option                      | Purpose                                                               |
| ------------ | -------------------------------- | --------------------------------------------------------------------- |
| `-uo`        | `--upload-order`                 | Select `concurrent`, `usenet`, or `tracker`.                          |
| `-qbcon`     | `--qbit-bw-control`              | Enable every bandwidth check in the selected workflow.                |
|              | `--qbit-bw-control-after-usenet` | Retain per-tracker checks after the Usenet phase.                     |
| `-qbcrl`     | `--qbit-bw-threshold`            | Set the threshold in KB/s.                                            |
| `-qbctime`   | `--qbit-bw-time`                 | Set the requested averaging period, evaluated in five-second samples. |

For example, wait for qBittorrent to average no more than 500 KB/s for 30 seconds, upload to Usenet, and then upload to the torrent trackers without further checks:

```bash
ua "/path/to/content" -tk BLUTOPIA,CURUPIRA -u -uo usenet -qbcon -qbcrl 500 -qbctime 30
```

Add `--qbit-bw-control-after-usenet` to the command when the torrent trackers should continue checking bandwidth after Usenet:

```bash
ua "/path/to/content" -tk BLUTOPIA,CURUPIRA -u -uo usenet -qbcon --qbit-bw-control-after-usenet -qbcrl 500 -qbctime 30
```

To run the phases concurrently while checking bandwidth before each torrent tracker:

```bash
ua "/path/to/content" -tk BLUTOPIA,CURUPIRA -u -uo concurrent -qbcon -qbcrl 500 -qbctime 30
```

CLI values apply to the current upload. `--upload-order` and positive threshold/time values override their configured defaults; the two bandwidth-control flags enable their respective settings for that run.
