from src import stats
from web_ui import server


def _authenticated(monkeypatch):
    monkeypatch.setattr(server, "_is_authenticated", lambda: True)
    monkeypatch.setattr(server, "_verify_csrf_header", lambda: True)
    monkeypatch.setattr(server, "_verify_same_origin", lambda: True)
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: None)


def test_stats_page_renders_for_authenticated_session(monkeypatch):
    _authenticated(monkeypatch)
    response = server.app.test_client().get("/stats")
    assert response.status_code == 200
    assert b"stats_app.js" in response.data


def test_existing_workspaces_link_to_stats():
    upload_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    config_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "config_app.js").read_text(encoding="utf-8")

    assert "/stats" in upload_app
    assert "/stats" in config_app


def test_stats_desktop_rail_has_shared_controls_without_desktop_switcher():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert 'className="mx-4 mt-4 md:hidden"' in stats_app
    assert 'className="ua-workspace-switcher rounded-lg"' in stats_app
    assert "<span>Changelog</span>" in stats_app
    assert "<span>Help</span>" in stats_app
    assert "<span>Appearance</span>" in stats_app
    assert "<span>Log out</span>" in stats_app


def test_stats_filters_use_theme_aware_selects():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    theme = (server.CODE_DIR / "web_ui" / "static" / "css" / "theme.css").read_text(encoding="utf-8")

    assert 'className="ua-stats-control w-full min-w-0 rounded-xl px-4 text-sm"' in stats_app
    assert 'className="ua-theme-picker rounded-lg px-3 py-2 text-sm"' in stats_app
    focus_styles = theme.split(".ua-stats-custom-summary:focus-visible {", 1)[1].split("}", 1)[0]
    assert "outline: 2px solid var(--ua-copper-bright)" in focus_styles
    assert "outline-offset: 2px" in focus_styles


def test_stats_period_selector_is_segmented_and_remembered():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert 'const STATS_PERIOD_KEY = "ua_stats_period"' in stats_app
    assert '["1y", "1y"]' in stats_app
    assert 'aria-label="Statistics period"' in stats_app
    assert "aria-pressed={period === value}" in stats_app
    assert "window.UAStorage.set(STATS_PERIOD_KEY, period)" in stats_app


def test_stats_settings_are_persistent_and_control_the_requested_views():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    theme_css = (server.CODE_DIR / "web_ui" / "static" / "css" / "theme.css").read_text(encoding="utf-8")
    settings_icon = server.CODE_DIR / "web_ui" / "static" / "img" / "stats-icons" / "settings.svg"

    assert 'const STATS_SETTINGS_KEY = "ua_stats_settings_v1"' in stats_app
    assert 'name="settings"' in stats_app
    assert settings_icon.is_file()
    assert "Stats display" in stats_app
    assert "Close stats display" in stats_app
    assert "Display" in stats_app
    assert "Real activity" in stats_app
    assert "Debug simulations" in stats_app
    assert '<option value="browser">{localTimeLabel}</option>' in stats_app
    assert "Historical statistics are stored in UTC calendar-day buckets." in stats_app
    assert 'query.set("today", isoTodayLocal())' in stats_app
    assert '<option value="DD-MM-YYYY">DD-MM-YYYY</option>' in stats_app
    assert 'label="Daily activity color gradient"' in stats_app
    assert 'label="Tracker and indexer favicons"' in stats_app
    assert "visible.throughput" in stats_app
    assert "visible.dataUploaded" in stats_app
    assert "visible.uploadsByDestination" in stats_app
    assert "const areaPath" in stats_app
    assert "<linearGradient" in stats_app
    assert "fill={`url(#daily-activity-gradient-${entry.key})`}" in stats_app
    assert 'filter="url(#daily-activity-gradient)"' not in stats_app
    assert "showFavicons={settings.showFavicons}" in stats_app
    assert "JSON.stringify(settings)" in stats_app
    assert "sm:grid-cols-2 md:grid-cols-3" in stats_app
    assert stats_app.count("grid min-w-0 gap-1 text-sm") == 3
    assert ".ua-stats-settings-modal\n  :where(" in theme_css
    assert "var(--ua-config-border) 88%" in theme_css


def test_modal_scroll_lock_preserves_the_page_width():
    shared_utils = (server.CODE_DIR / "web_ui" / "static" / "js" / "shared_utils.js").read_text(encoding="utf-8")

    assert "window.innerWidth - document.documentElement.clientWidth" in shared_utils
    assert "bodyPaddingRight + scrollbarWidth" in shared_utils
    assert "document.body.style.paddingRight = previousPaddingRight" in shared_utils


def test_application_rails_use_the_supplied_icons():
    upload_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    config_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "config_app.js").read_text(encoding="utf-8")

    icon_names = ("upload", "config", "stats", "changelog", "help", "logout")
    for icon_name in icon_names:
        assert f'name="{icon_name}"' in upload_app
        assert f'name="{icon_name}"' in config_app
        assert (server.CODE_DIR / "web_ui" / "static" / "img" / "webui-icons" / f"{icon_name}.svg").is_file()

    assert "<AssetIcon name={id} />" in stats_app
    assert all(f'name="{icon_name}"' in stats_app for icon_name in ("changelog", "help", "logout"))
    assert 'name="palette"' in stats_app
    assert 'name="palette"' in config_app


def test_stats_combines_charts_with_expandable_tables():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "function DonutChart" in stats_app
    assert "const ChartWithTable" in stats_app
    assert stats_app.count("<ChartWithTable") == 10
    assert 'title="Successful media time"' in stats_app
    assert 'centerLabel="uploaded"' in stats_app
    assert "valueFormatter={formatMediaHours}" in stats_app
    assert 'className="ua-stats-table-details mt-5"' in stats_app
    assert 'aria-label="Show or hide data table"' in stats_app
    assert 'className="ml-auto flex h-9 w-9 cursor-pointer' in stats_app
    assert "<span>Table</span>" not in stats_app
    assert "BREAKDOWN_VIEW_KEY" not in stats_app
    assert 'aria-label="Breakdown visualization"' not in stats_app
    assert 'label: "Other"' in stats_app


def test_upload_destination_views_use_local_tracker_favicons():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "const TrackerFavicon" in stats_app
    assert "`/static/img/trackers/${slug}.png`" in stats_app
    assert "label: row.display_name || row.destination" in stats_app
    assert "favicon: row.destination" in stats_app
    assert "<TrackerFavicon destination={r.destination}" in stats_app
    assert "<span>{r.display_name || r.destination}</span>" in stats_app


def test_stats_tables_sort_comparable_columns():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "aria-sort={active ? sort.direction : undefined}" in stats_app
    assert "sortedRows.map" in stats_app
    assert "sortValue: (r) => r.average_duration_ms" in stats_app
    assert "sortValue: (r) => r.bytes_written" in stats_app
    assert 'label: "Skip reasons"' in stats_app


def test_external_operation_bytes_distinguish_unknown_from_zero():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert 'label: "Bytes sent"' in stats_app
    assert 'r.bytes > 0 ? formatBytes(r.bytes) : "—"' in stats_app
    assert "Bytes sent are available for NNTP and successful image uploads." in stats_app


def test_stats_operations_use_friendly_labels_with_a_readable_fallback():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert 'torrent_client_add: "Add to torrent client"' in stats_app
    assert 'torrent_client_search: "Search torrent client"' in stats_app
    assert 'credential_sync: "Sync credentials"' in stats_app
    assert 'nntp_post: "Post to Usenet"' in stats_app
    assert 'image_upload: "Upload images"' in stats_app
    assert "const formatOperation" in stats_app
    assert '.replaceAll("_", " ")' in stats_app
    assert stats_app.count("render: (row) => formatOperation(row.operation)") == 2


def test_stats_tables_fit_their_panels_and_theme_required_scrollbars():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    theme_css = (server.CODE_DIR / "web_ui" / "static" / "css" / "theme.css").read_text(encoding="utf-8")

    assert 'className="ua-stats-table-scroll overflow-x-auto"' in stats_app
    assert 'className="ua-stats-table w-full text-left text-sm"' in stats_app
    assert ".ua-stats-table-scroll::-webkit-scrollbar" in theme_css
    assert ".ua-stats-table tbody tr:nth-child(even)" in theme_css
    assert 'className="border-b last:border-0"' not in stats_app


def test_stats_summary_cards_have_distinct_icons():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "const MetricIcon" in stats_app
    assert 'className="ua-stats-summary-card relative rounded-xl p-4 shadow-sm"' in stats_app
    assert 'className="ua-stats-panel rounded-xl p-4 shadow-sm sm:p-5"' in stats_app
    assert 'className="ua-stats-panel rounded-xl p-8 text-center shadow-sm"' in stats_app
    icons = (
        "items-completed",
        "successful-uploads",
        "torrents-created",
        "nzbs-created",
        "screenshots-created",
        "api-operations",
        "cache-hit-rate",
        "cache-writes",
        "daily-activity",
        "upload-flow",
        "uploads-by-destination",
        "categories",
        "artifact-activity",
        "cache-by-provider",
        "external-operations",
        "execution-source",
        "data-uploaded",
        "duplicates-prevented",
        "hashing-io-avoided",
        "activity-heatmap",
        "media-profile",
        "unique-data-uploaded",
        "streaming-services",
        "personal-releases",
        "pioneering-rate",
    )
    icon_dir = server.CODE_DIR / "web_ui" / "static" / "img" / "stats-icons"
    for icon in icons:
        assert f'icon="{icon}"' in stats_app
        assert (icon_dir / f"{icon}.svg").is_file()


def test_stats_ui_exposes_volume_profiles_comparisons_and_actions():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    theme_css = (server.CODE_DIR / "web_ui" / "static" / "css" / "theme.css").read_text(encoding="utf-8")

    assert 'label="Data uploaded"' in stats_app
    assert 'label="Unique data uploaded"' in stats_app
    assert "overview.unique_uploaded_bytes" in stats_app
    assert 'label="Mode"' not in stats_app
    assert "Debug never affects real totals" not in stats_app
    assert 'label="Hashing I/O avoided"' in stats_app
    assert "function MediaProfile" in stats_app
    assert "function ActivityHeatmap" in stats_app
    assert "vs previous period" in stats_app
    assert "function StatsActionsMenu" in stats_app
    assert 'aria-haspopup="menu"' in stats_app
    assert 'aria-label="Statistics actions"' in stats_app
    assert '<span aria-hidden="true">⋯</span>' in stats_app
    assert "exportsDisabled={!statsEnabled || !hasData}" in stats_app
    assert "CSV timeline" in stats_app
    assert "JSON details" in stats_app
    assert "onReset={() => setResetOpen(true)}" in stats_app
    assert 'className="ua-stats-actions-danger' in stats_app
    assert ".ua-stats-actions-menu" in theme_css
    assert "ReliabilityBadge" in stats_app
    assert 'title="Streaming services"' in stats_app
    assert 'title="Personal releases"' in stats_app
    assert "function StreamingServices" in stats_app
    assert "function ReleaseProfiles" in stats_app
    assert "release groups and tags are never stored" in stats_app


def test_stats_generated_artifacts_combines_screenshot_types():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert 'label="Screenshots created"' in stats_app
    assert "overview.screenshots_created" in stats_app
    assert 'row.type === "screenshot" && row.operation === "created"' in stats_app
    assert "screenshotArtifactMap.standard" in stats_app
    assert "screenshotArtifactMap.menu" in stats_app
    assert "screenshotArtifactMap.spectrogram" in stats_app
    assert "(screenshotArtifactMap.dovi_plot || 0) +" in stats_app
    assert "(screenshotArtifactMap.hdr10plus_plot || 0)" in stats_app
    assert "HDR plots" in stats_app


def test_activity_heatmap_fits_panel_without_horizontal_scroll():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    theme_css = (server.CODE_DIR / "web_ui" / "static" / "css" / "theme.css").read_text(encoding="utf-8")

    heatmap = stats_app.split("function ActivityHeatmap", 1)[1].split("const ReliabilityBadge", 1)[0]
    assert 'className="ua-stats-heatmap w-full pb-1"' in heatmap
    assert "overflow-x-auto" not in heatmap
    assert "min-w-[760px]" not in heatmap
    assert 'gridTemplateColumns: "repeat(52, minmax(0, 1fr))"' in heatmap
    assert "visibleMonthMarkers.map" in heatmap
    assert "monthMarkers.slice(1)" in heatmap
    assert "today.getUTCDate() - 363" in heatmap
    assert "offset < 364" in heatmap
    assert all(label in heatmap for label in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Less", "More"))
    assert "currentStreak = cell.count > 0 ? currentStreak + 1 : 0" in heatmap
    assert "longestStreak = Math.max(longestStreak, currentStreak)" in heatmap
    assert "Longest streak:" in heatmap
    assert 'longestStreak === 1 ? "day" : "days"' in heatmap
    assert "var(--ua-stats-heatmap-empty)" in heatmap
    assert "--ua-stats-heatmap-empty:" in theme_css


def test_daily_activity_uses_curved_paths_without_changing_data_points():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    trend = stats_app.split("function TrendChart", 1)[1].split("function ActivityHeatmap", 1)[0]
    assert "const curvePath" in trend
    assert " C ${controlX},${previous.y} ${controlX},${current.y}" in trend
    assert "d={curvePath(entry)}" in trend
    assert "<polyline" not in trend


def test_daily_activity_labels_date_and_count_axes():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    trend = stats_app.split("function TrendChart", 1)[1].split("function ActivityHeatmap", 1)[0]
    assert "const yTicks" in trend
    assert "const xTickIndices" in trend
    assert "const plot = { top: 12, right: 56, bottom: 44, left: 56 }" in trend
    assert "const xTickCount = Math.min(7, rows.length)" in trend
    assert "formatCompactNumber(value)" in trend
    assert "formatAxisDate(rows[index].date)" in trend
    assert "rows.length > 365" in trend
    assert 'aria-label="Count axis"' not in trend
    assert 'aria-label="Date axis"' not in trend


def test_stats_disabled_state_blurs_results_and_links_to_configuration():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "Statistics collection is disabled" in stats_app
    assert "blur-[3px]" in stats_app
    assert "href={`${APP_BASE}/config`}" in stats_app


def test_stats_requests_cancel_stale_filters_and_report_reset_failures():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "new AbortController()" in stats_app
    assert "controller.abort()" in stats_app
    assert 'err?.name === "AbortError"' in stats_app
    assert "response.json().catch(() => ({}))" in stats_app
    assert 'setError("Unable to reset statistics")' in stats_app


def test_stats_ui_exposes_advanced_ranges_tracker_filter_and_sankey():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert '["today", "Today"]' in stats_app
    assert '["this_month", "This month"]' in stats_app
    assert '["last_month", "Last month"]' in stats_app
    assert 'query.set("from", customRange.from)' in stats_app
    assert 'query.set("tracker", activeTracker)' in stats_app
    assert 'aria-label="Clear tracker filter"' in stats_app
    assert "function SankeyDiagram" in stats_app
    assert 'aria-label="Upload route Sankey diagram"' in stats_app
    assert "function MediaMatrix" in stats_app
    assert "Resolution \u00d7 video/HDR profile" in stats_app
    assert 'label="Pioneering rate"' in stats_app
    assert 'label="Average item size"' not in stats_app


def test_stats_summary_cards_have_distinct_visual_containers():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    theme = (server.CODE_DIR / "web_ui" / "static" / "css" / "theme.css").read_text(encoding="utf-8")

    card_styles = theme.split(".ua-stats-summary-card {", 1)[1].split("}", 1)[0]
    assert 'className="ua-stats-summary-card relative rounded-xl p-4 shadow-sm"' in stats_app
    assert "border: 1px solid" in card_styles
    assert "ua-stats-range-chip-icon" not in stats_app


def test_donut_legend_rows_do_not_use_colored_backgrounds():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    donut = stats_app.split("function DonutChart", 1)[1].split("const Section", 1)[0]

    assert "ua-stats-series-active" not in donut
    assert 'activeLabel && activeLabel === segment.id ? "font-semibold"' in donut


def test_daily_activity_can_switch_between_counts_and_volume():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    trend = stats_app.split("function TrendChart", 1)[1].split("function ActivityHeatmap", 1)[0]

    assert 'key: "processed_bytes"' in trend
    assert 'key: "uploaded_bytes"' in trend
    assert '["count", "volume", "both"]' in trend
    assert 'view === "both"' in trend


def test_stats_api_validates_filters(monkeypatch):
    _authenticated(monkeypatch)
    response = server.app.test_client().get("/api/stats?range=invalid&mode=real")
    assert response.status_code == 400
    assert response.json["success"] is False


def test_stats_api_accepts_one_year_range(monkeypatch):
    _authenticated(monkeypatch)
    response = server.app.test_client().get("/api/stats?range=1y&mode=real")

    assert response.status_code == 200
    assert response.json["range"] == "1y"


def test_stats_api_accepts_browser_time_and_rejects_unknown_timezones(monkeypatch):
    _authenticated(monkeypatch)
    response = server.app.test_client().get("/api/stats?range=today&mode=real&timezone=browser&today=2026-09-27")

    assert response.status_code == 200
    assert response.json["time_context"]["basis"] == "browser"
    assert response.json["period"] == {
        "from": "2026-09-27",
        "to": "2026-09-27",
        "timezone": "Browser local time",
    }

    invalid = server.app.test_client().get("/api/stats?range=today&mode=real&timezone=server")
    assert invalid.status_code == 400
    assert "timezone must be one of" in invalid.json["error"]


def test_stats_api_accepts_custom_utc_range_and_tracker(monkeypatch, tmp_path):
    _authenticated(monkeypatch)
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"DEFAULT": {"stats_enabled": True}})
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.record_event(
        "upload",
        service="FICTIONAL",
        operation="torrent_tracker",
        outcome="success",
        destination="FICTIONAL",
        state_dir=tmp_path,
    )
    today = stats.get_empty_stats("today")["period"]["to"]

    response = server.app.test_client().get(f"/api/stats?range=custom&from={today}&to={today}&mode=real&tracker=FICTIONAL")

    assert response.status_code == 200
    assert response.json["filters"]["active_tracker"] == "FICTIONAL"
    assert response.json["period"]["timezone"] == "UTC"
    assert response.json["overview"]["items_completed"] == 1


def test_stats_reset_requires_exact_confirmation(monkeypatch):
    _authenticated(monkeypatch)
    response = server.app.test_client().delete("/api/stats", json={"confirmation": "reset"})
    assert response.status_code == 400


def test_stats_api_rejects_bearer_tokens(monkeypatch):
    _authenticated(monkeypatch)
    monkeypatch.setattr(server, "_get_bearer_from_header", lambda: "token")
    response = server.app.test_client().get("/api/stats")
    assert response.status_code == 401


def test_stats_api_reads_and_resets_aggregates(monkeypatch, tmp_path):
    _authenticated(monkeypatch)
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"DEFAULT": {"stats_enabled": True}})
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.set_stats_context(debug=False, category="MOVIE")
    stats.record_event("item", operation="completed", outcome="success", state_dir=tmp_path)

    client = server.app.test_client()
    response = client.get("/api/stats?range=all&mode=real")
    assert response.status_code == 200
    assert response.json["enabled"] is True
    assert response.json["overview"]["items_completed"] == 1

    response = client.delete("/api/stats", json={"confirmation": "RESET"})
    assert response.status_code == 200
    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 0


def test_stats_api_uses_canonical_destination_display_names(monkeypatch, tmp_path):
    _authenticated(monkeypatch)
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"DEFAULT": {"stats_enabled": True}})
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.record_event(
        "upload",
        service="BJSHARE",
        operation="torrent_tracker",
        outcome="success",
        state_dir=tmp_path,
    )

    response = server.app.test_client().get("/api/stats?range=all&mode=real")

    assert response.status_code == 200
    destination = response.json["uploads"]["by_destination"][0]
    assert destination["destination"] == "BJSHARE"
    assert destination["display_name"] == "BJ-Share"


def test_stats_api_hides_preserved_aggregates_while_collection_is_disabled(monkeypatch, tmp_path):
    _authenticated(monkeypatch)
    monkeypatch.setattr(server, "STATE_DIR", tmp_path)
    stats.configure_stats({"DEFAULT": {"stats_enabled": True}})
    stats.record_event("item", operation="completed", outcome="success", state_dir=tmp_path)

    monkeypatch.setattr(server, "_load_config_from_file", lambda _path: {"DEFAULT": {"stats_enabled": False}})
    response = server.app.test_client().get("/api/stats?range=all&mode=real")

    assert response.status_code == 200
    assert response.json["enabled"] is False
    assert response.json["overview"]["items_completed"] == 0
    assert stats.get_stats("all", "real", tmp_path)["overview"]["items_completed"] == 1
