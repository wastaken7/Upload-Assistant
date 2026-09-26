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

    assert stats_app.count('className="ua-theme-picker rounded-lg px-3 py-2 text-sm"') >= 2
    assert 'className="ua-theme-picker flex rounded-lg p-1"' in stats_app


def test_config_and_stats_rails_use_the_canonical_icons():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")
    config_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "config_app.js").read_text(encoding="utf-8")

    assert 'name="settings"' in stats_app
    assert 'name="palette"' in stats_app
    assert 'name="settings"' in config_app
    assert 'name="palette"' in config_app


def test_stats_offers_persistent_table_and_donut_views():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert 'const BREAKDOWN_VIEW_KEY = "ua_stats_breakdown_view"' in stats_app
    assert "function DonutChart" in stats_app
    assert 'aria-label="Breakdown visualization"' in stats_app
    assert 'view === "table" ? "Tables" : "Charts"' in stats_app
    assert 'label: "Other"' in stats_app


def test_upload_destination_views_use_local_tracker_favicons():
    stats_app = (server.CODE_DIR / "web_ui" / "static" / "js" / "stats_app.js").read_text(encoding="utf-8")

    assert "const TrackerFavicon" in stats_app
    assert "`/static/img/trackers/${slug}.png`" in stats_app
    assert "favicon: row.destination" in stats_app
    assert "<TrackerFavicon destination={r.destination}" in stats_app


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
        "api-operations",
        "cache-hit-rate",
        "cache-writes",
        "mode",
        "daily-activity",
        "uploads-by-destination",
        "categories",
        "artifact-activity",
        "cache-by-provider",
        "external-operations",
        "execution-source",
    )
    icon_dir = server.CODE_DIR / "web_ui" / "static" / "img" / "stats-icons"
    for icon in icons:
        assert f'icon="{icon}"' in stats_app
        assert (icon_dir / f"{icon}.svg").is_file()


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


def test_stats_api_validates_filters(monkeypatch):
    _authenticated(monkeypatch)
    response = server.app.test_client().get("/api/stats?range=invalid&mode=real")
    assert response.status_code == 400
    assert response.json["success"] is False


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
