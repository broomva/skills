"""Local dashboard server for technician access via WiFi AP.

Serves a JSON API and minimal static page. Designed for phone access
when connected to the RPi's WiFi hotspot.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from .agent import MicrogridAgent

log = logging.getLogger(__name__)

# Minimal dashboard page served as static HTML.
# Data is populated client-side via fetch() to /api/status every 5 seconds.
# The DOM is built using safe textContent assignments — no raw HTML injection.
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Microgrid Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, system-ui, sans-serif; background: #0d1117; color: #c9d1d9; padding: 16px; }
  h1 { font-size: 1.4em; margin-bottom: 12px; color: #58a6ff; }
  h2 { font-size: 1.1em; margin: 16px 0 8px; color: #8b949e; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
  .metric { display: flex; justify-content: space-between; padding: 4px 0; }
  .metric .label { color: #8b949e; }
  .metric .value { font-weight: 600; font-variant-numeric: tabular-nums; }
  .ok { color: #3fb950; }
  .warn { color: #d29922; }
  .error { color: #f85149; }
  .bar { height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; margin-top: 4px; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s; }
  #status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
</style>
</head>
<body>
<h1><span id="status-dot"></span> Microgrid Agent</h1>
<div id="app">Loading...</div>
<script>
function el(tag, cls) { var e = document.createElement(tag); if (cls) e.className = cls; return e; }
function metric(label, value, cls) {
  var row = el('div', 'metric');
  var l = el('span', 'label'); l.textContent = label; row.appendChild(l);
  var v = el('span', 'value' + (cls ? ' ' + cls : '')); v.textContent = value; row.appendChild(v);
  return row;
}
async function load() {
  try {
    var r = await fetch('/api/status');
    var d = await r.json();
    var soc = d.battery_soc_pct || 0;
    var socCls = soc > 50 ? 'ok' : soc > 20 ? 'warn' : 'error';
    var dot = document.getElementById('status-dot');
    dot.style.background = d.agent_status === 'running' ? '#3fb950' : '#f85149';

    var app = document.getElementById('app');
    while (app.firstChild) app.removeChild(app.firstChild);

    var c1 = el('div', 'card');
    c1.appendChild(Object.assign(el('h2'), {textContent: 'Power'}));
    c1.appendChild(metric('Solar', (d.solar_kw||0).toFixed(2) + ' kW', 'ok'));
    c1.appendChild(metric('Battery', (d.battery_kw||0).toFixed(2) + ' kW'));
    c1.appendChild(metric('Diesel', (d.diesel_kw||0).toFixed(2) + ' kW', d.diesel_kw > 0 ? 'warn' : ''));
    c1.appendChild(metric('Load', (d.demand_kw||0).toFixed(2) + ' kW'));
    c1.appendChild(metric('Unserved', (d.unserved_kw||0).toFixed(2) + ' kW', d.unserved_kw > 0 ? 'error' : 'ok'));
    app.appendChild(c1);

    var c2 = el('div', 'card');
    c2.appendChild(Object.assign(el('h2'), {textContent: 'Battery SOC'}));
    c2.appendChild(metric('State of Charge', soc.toFixed(1) + '%', socCls));
    var bar = el('div', 'bar'); var fill = el('div', 'bar-fill');
    fill.style.width = soc + '%';
    fill.style.background = soc > 50 ? '#3fb950' : soc > 20 ? '#d29922' : '#f85149';
    bar.appendChild(fill); c2.appendChild(bar);
    app.appendChild(c2);

    var c3 = el('div', 'card');
    c3.appendChild(Object.assign(el('h2'), {textContent: 'System'}));
    c3.appendChild(metric('Status', d.agent_status, d.agent_status === 'running' ? 'ok' : 'error'));
    c3.appendChild(metric('Dispatch', d.dispatch_method || '--'));
    c3.appendChild(metric('MQTT', d.mqtt_connected ? 'Online' : 'Offline', d.mqtt_connected ? 'ok' : 'warn'));
    c3.appendChild(metric('Queue', (d.sync_queue_depth || 0) + ' msgs'));
    c3.appendChild(metric('Uptime', d.uptime || '--'));
    app.appendChild(c3);
  } catch(e) {
    var app = document.getElementById('app');
    while (app.firstChild) app.removeChild(app.firstChild);
    var err = el('div', 'card error'); err.textContent = 'Connection lost'; app.appendChild(err);
  }
}
load();
setInterval(load, 5000);
</script>
</body>
</html>"""


class DashboardServer:
    """Lightweight HTTP server for local technician access."""

    def __init__(self, agent: MicrogridAgent, host: str = "0.0.0.0", port: int = 8080):
        self.agent = agent
        self.host = host
        self.port = port
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self):
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/forecast", self._handle_forecast)
        self._app.router.add_get("/api/dispatch", self._handle_dispatch)
        self._app.router.add_get("/api/history", self._handle_history)

    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        log.info("Dashboard running at http://%s:%d", self.host, self.port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=DASHBOARD_HTML, content_type="text/html")

    async def _handle_status(self, request: web.Request) -> web.Response:
        state = self.agent.get_state_snapshot()
        return web.json_response(state)

    async def _handle_forecast(self, request: web.Request) -> web.Response:
        forecast = self.agent.last_forecast
        if forecast is None:
            return web.json_response({"error": "No forecast available"}, status=404)
        return web.json_response(forecast.to_dict())

    async def _handle_dispatch(self, request: web.Request) -> web.Response:
        decision = self.agent.last_dispatch
        if decision is None:
            return web.json_response({"error": "No dispatch decision"}, status=404)
        return web.json_response(decision.to_dict())

    async def _handle_history(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", "100"))
        history = self.agent.get_history(limit)
        return web.json_response(history)
