import argparse
import csv
import json
from collections import defaultdict, deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import config


ROOT = Path(__file__).resolve().parent
TRADES_FILE = ROOT / "paper_trades.csv"
STATE_FILE = ROOT / "paper_state.json"

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#080d18">
  <title>Options Paper Trading Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, "Segoe UI", sans-serif;
      background: #080d18;
      color: #e7edf7;
      font-synthesis: none;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 320px; }
    .shell { max-width: 1500px; margin: auto; padding: 26px 30px 36px; }
    .topbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
    h1 { margin: 0; font-size: 1.45rem; letter-spacing: -.03em; }
    .subtitle, .muted, .label { color: #8d9bb2; }
    .subtitle { margin-top: 5px; font-size: .88rem; }
    .live-state { display: flex; align-items: center; gap: 9px; color: #a7b3c7; font-size: .8rem; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #43d69b; box-shadow: 0 0 12px #43d69b88; }
    .mode { display: inline-flex; align-items: center; gap: 7px; color: #ffc96c; background: #332713; border: 1px solid #62481d; border-radius: 999px; padding: 6px 10px; font-size: .72rem; font-weight: 750; letter-spacing: .07em; }
    .summary { display: grid; grid-template-columns: minmax(250px, 1.7fr) repeat(3, minmax(145px, 1fr)); gap: 12px; margin: 23px 0 12px; }
    .panel, .metric, .strategy-card { background: #111a2a; border: 1px solid #202c40; border-radius: 13px; }
    .metric { padding: 17px 19px; min-height: 102px; }
    .metric.primary { background: linear-gradient(125deg, #16243a, #111a2a 76%); border-color: #293a55; }
    .label { font-size: .75rem; letter-spacing: .025em; }
    .value { margin-top: 7px; font-size: 1.35rem; font-weight: 700; font-variant-numeric: tabular-nums; }
    .primary .value { font-size: 1.8rem; }
    .metric-note { margin-top: 5px; font-size: .74rem; color: #8492a8; }
    .positive { color: #57d69a !important; }
    .negative { color: #ff777d !important; }
    .warning { color: #ffc96c !important; }
    .alerts { display: flex; flex-wrap: wrap; gap: 8px; min-height: 17px; margin: 12px 0 18px; }
    .alert { padding: 6px 10px; border-radius: 7px; font-size: .76rem; font-weight: 650; }
    .alert.warn { color: #ffc96c; background: #302614; border: 1px solid #60471f; }
    .alert.danger { color: #ff8c91; background: #351c26; border: 1px solid #63303a; }
    .alert.good { color: #62dda2; background: #142a25; border: 1px solid #275340; }
    .section-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin: 25px 0 12px; }
    h2 { margin: 0; font-size: 1rem; letter-spacing: -.01em; }
    .section-note { font-size: .76rem; color: #8290a6; }
    .strategy-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    .strategy-card { padding: 17px; border-top: 2px solid #34445e; }
    .strategy-card.profit { border-top-color: #43d69b; }
    .strategy-card.loss { border-top-color: #ff777d; }
    .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
    .strategy-name { font-size: .95rem; font-weight: 700; }
    .symbol { margin-top: 4px; color: #8c9ab0; font-size: .77rem; }
    .status { flex: 0 0 auto; border-radius: 999px; padding: 5px 8px; color: #a9b5c8; background: #202b3d; font-size: .68rem; font-weight: 750; letter-spacing: .045em; }
    .status.open { color: #80c4ff; background: #172a3d; }
    .status.stale { color: #ffc96c; background: #302614; }
    .status.target { color: #62dda2; background: #142a25; }
    .status.stop { color: #ff8c91; background: #351c26; }
    .card-pnl { display: flex; align-items: baseline; gap: 8px; margin: 17px 0 14px; }
    .card-pnl strong { font-size: 1.45rem; font-variant-numeric: tabular-nums; }
    .card-pnl span { color: #8d9bb2; font-size: .78rem; }
    .details { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px 10px; }
    .detail .label { font-size: .68rem; }
    .detail-value { margin-top: 4px; font-size: .82rem; font-weight: 600; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
    .card-foot { margin-top: 15px; padding-top: 12px; border-top: 1px solid #253147; color: #8492a8; font-size: .73rem; }
    .charts { display: grid; grid-template-columns: 1.5fr 1fr; gap: 12px; }
    .panel { padding: 16px 18px; min-width: 0; }
    .chart-title { margin: 0 0 12px; font-size: .83rem; font-weight: 650; }
    .chart { display: block; width: 100%; height: 155px; overflow: visible; }
    .chart-empty { display: grid; height: 155px; place-items: center; color: #8290a6; font-size: .8rem; text-align: center; }
    .axis { stroke: #29364b; stroke-width: 1; }
    .chart-line { fill: none; stroke: #5da8ff; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
    .chart-area { fill: url(#pnlFill); }
    .chart-dot { fill: #5da8ff; stroke: #111a2a; stroke-width: 2; }
    .chart-text { fill: #8290a6; font-size: 10px; }
    .bar-row { display: grid; grid-template-columns: minmax(70px, 1fr) 2fr 72px; align-items: center; gap: 10px; margin: 12px 0; font-size: .75rem; }
    .bar-track { height: 9px; overflow: hidden; border-radius: 99px; background: #202b3d; }
    .bar { height: 100%; border-radius: inherit; background: #43d69b; }
    .bar.loss { background: #ff777d; }
    .bar-value { text-align: right; font-variant-numeric: tabular-nums; }
    .table-panel { padding: 0; overflow: hidden; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; min-width: 1120px; border-collapse: collapse; white-space: nowrap; font-size: .77rem; }
    th, td { padding: 12px 13px; text-align: left; border-bottom: 1px solid #202c40; }
    th { color: #8d9bb2; background: #131e30; font-size: .68rem; font-weight: 650; letter-spacing: .045em; text-transform: uppercase; }
    tbody tr:last-child td { border-bottom: 0; }
    td { color: #d7dfec; font-variant-numeric: tabular-nums; }
    .empty { padding: 26px; text-align: center; color: #8290a6; }
    .footer { margin-top: 16px; color: #728198; font-size: .72rem; line-height: 1.5; }
    .error { margin-top: 14px; padding: 10px 12px; border: 1px solid #63303a; border-radius: 8px; color: #ff9a9f; background: #351c26; font-size: .8rem; }
    @media (max-width: 850px) {
      .shell { padding: 20px 16px 30px; }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .metric.primary { grid-column: span 2; }
      .charts { grid-template-columns: 1fr; }
    }
    @media (max-width: 500px) {
      .topbar { align-items: flex-start; flex-direction: column; }
      .summary { gap: 8px; }
      .metric { padding: 14px; }
      .value { font-size: 1.12rem; }
      .primary .value { font-size: 1.55rem; }
      .details { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .section-heading { align-items: flex-start; flex-direction: column; gap: 5px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>Options trading</h1>
        <div class="subtitle">Intraday paper portfolio · BUY to open · SELL only to exit bought positions</div>
      </div>
      <div class="live-state"><span class="dot"></span><span id="updated">Loading…</span><span class="mode">PAPER</span></div>
    </header>
    <div id="error" class="error" hidden></div>

    <section class="summary" aria-label="Today's summary">
      <div class="metric primary">
        <div class="label">Today's realized P&amp;L</div>
        <div class="value" id="pnl">—</div>
        <div class="metric-note" id="pnl-note">Open-position mark-to-market unavailable</div>
      </div>
      <div class="metric">
        <div class="label">Closed positions</div>
        <div class="value" id="closed">—</div>
        <div class="metric-note" id="win-loss">—</div>
      </div>
      <div class="metric">
        <div class="label">Trades today</div>
        <div class="value" id="trade-count">—</div>
        <div class="metric-note" id="open-count">— open</div>
      </div>
      <div class="metric">
        <div class="label">Daily loss limit</div>
        <div class="value" id="loss-limit">—</div>
        <div class="metric-note" id="orders-note">—</div>
      </div>
    </section>
    <div id="alerts" class="alerts" aria-live="polite"></div>

    <div class="section-heading">
      <h2>Strategy breakdown</h2>
      <div class="section-note">Capacity: 1 long PUT + 1 long CALL · Live option quotes and target levels are unavailable.</div>
    </div>
    <section id="strategies" class="strategy-grid" aria-live="polite"></section>

    <div class="section-heading">
      <h2>Intraday performance</h2>
      <div class="section-note">Realized P&amp;L from today's closed trades</div>
    </div>
    <div class="charts">
      <section class="panel">
        <h3 class="chart-title">P&amp;L curve</h3>
        <div id="curve"></div>
      </section>
      <section class="panel">
        <h3 class="chart-title">P&amp;L by strategy</h3>
        <div id="bars"></div>
      </section>
    </div>

    <div class="section-heading">
      <h2>Buying information</h2>
      <div class="section-note">Today's open and closed long-option positions</div>
    </div>
    <section class="panel table-panel">
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Symbol / strike</th><th>Type</th><th>Strategy</th><th>Buy price</th><th>Current / exit</th>
            <th>P&amp;L</th><th>Qty</th><th>Entry time</th><th>Exit time</th><th>Stop loss</th><th>Target</th><th>Status</th>
          </tr></thead>
          <tbody id="positions"></tbody>
        </table>
      </div>
      <div id="empty" class="empty" hidden>No position records for today.</div>
    </section>
    <footer class="footer">
      BUY opens a long option; SELL closes that bought position and never opens a short option. Positions are intraday only.
      Refreshes every 15 seconds. Data is read from local paper_trades.csv and paper_state.json; this dashboard does not place orders.
      No live option quote provider or profit target is configured, so those values are shown as unavailable rather than estimated.
    </footer>
  </main>
  <script>
    const rupees = value => value == null ? "—" : "₹" + Number(value).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const set = (id, value) => { document.getElementById(id).textContent = value; };
    const field = (label, value) => {
      const box = document.createElement("div"); box.className = "detail";
      const title = document.createElement("div"); title.className = "label"; title.textContent = label;
      const text = document.createElement("div"); text.className = "detail-value"; text.textContent = value == null || value === "" ? "—" : value;
      box.append(title, text); return box;
    };
    function renderCurve(points) {
      const root = document.getElementById("curve"); root.replaceChildren();
      if (!points.length) {
        const empty = document.createElement("div"); empty.className = "chart-empty"; empty.textContent = "No closed trades yet — realized P&L curve will appear here.";
        root.append(empty); return;
      }
      const values = [0, ...points.map(point => point.pnl)];
      const width = 620, height = 155, left = 44, right = 12, top = 10, bottom = 25;
      const min = Math.min(0, ...values), max = Math.max(0, ...values);
      const spread = max - min || 1;
      const x = index => left + index * (width - left - right) / Math.max(values.length - 1, 1);
      const y = value => top + (max - value) * (height - top - bottom) / spread;
      const coords = values.map((value, index) => [x(index), y(value)]);
      const line = coords.map((point, index) => (index ? "L" : "M") + point[0] + " " + point[1]).join(" ");
      const area = line + " L " + coords[coords.length - 1][0] + " " + (height - bottom) + " L " + coords[0][0] + " " + (height - bottom) + " Z";
      const zero = y(0);
      const ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.setAttribute("class", "chart"); svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Cumulative realized intraday P&L");
      const defs = document.createElementNS(ns, "defs");
      const gradient = document.createElementNS(ns, "linearGradient");
      gradient.setAttribute("id", "pnlFill"); gradient.setAttribute("x1", "0"); gradient.setAttribute("x2", "0");
      gradient.setAttribute("y1", "0"); gradient.setAttribute("y2", "1");
      [["0", ".24"], ["1", "0"]].forEach(stopData => {
        const stop = document.createElementNS(ns, "stop");
        stop.setAttribute("offset", stopData[0]); stop.setAttribute("stop-color", "#5da8ff");
        stop.setAttribute("stop-opacity", stopData[1]); gradient.append(stop);
      });
      defs.append(gradient); svg.append(defs);
      const axis = document.createElementNS(ns, "line");
      axis.setAttribute("class", "axis"); axis.setAttribute("x1", left); axis.setAttribute("y1", zero);
      axis.setAttribute("x2", width - right); axis.setAttribute("y2", zero); svg.append(axis);
      const areaPath = document.createElementNS(ns, "path");
      areaPath.setAttribute("class", "chart-area"); areaPath.setAttribute("d", area); svg.append(areaPath);
      const linePath = document.createElementNS(ns, "path");
      linePath.setAttribute("class", "chart-line"); linePath.setAttribute("d", line); svg.append(linePath);
      const addText = (text, xPos, yPos, anchor) => {
        const node = document.createElementNS(ns, "text"); node.setAttribute("class", "chart-text");
        node.setAttribute("x", xPos); node.setAttribute("y", yPos);
        if (anchor) node.setAttribute("text-anchor", anchor);
        node.textContent = text; svg.append(node);
      };
      addText(rupees(max), 2, top + 8);
      addText(rupees(min), 2, height - bottom);
      addText(points[0].time, left, height - 5);
      addText(points[points.length - 1].time, width - right, height - 5, "end");
      root.append(svg);
    }
    function renderBars(strategies) {
      const root = document.getElementById("bars"); root.replaceChildren();
      if (!strategies.length) {
        const empty = document.createElement("div"); empty.className = "chart-empty"; empty.textContent = "No strategy P&L data recorded today.";
        root.append(empty); return;
      }
      const max = Math.max(1, ...strategies.map(item => Math.abs(item.pnl)));
      strategies.forEach(item => {
        const row = document.createElement("div"); row.className = "bar-row";
        const name = document.createElement("div"); name.textContent = item.name;
        const track = document.createElement("div"); track.className = "bar-track";
        const bar = document.createElement("div"); bar.className = "bar" + (item.pnl < 0 ? " loss" : "");
        bar.style.width = Math.max(item.pnl === 0 ? 2 : 5, Math.abs(item.pnl) / max * 100) + "%";
        const value = document.createElement("div"); value.className = "bar-value " + (item.pnl > 0 ? "positive" : item.pnl < 0 ? "negative" : "");
        value.textContent = rupees(item.pnl); track.append(bar); row.append(name, track, value); root.append(row);
      });
    }
    function renderPositionCard(position) {
      const card = document.createElement("article");
      const pnl = position.pnl;
      card.className = "strategy-card" + (pnl > 0 ? " profit" : pnl < 0 ? " loss" : "");
      const head = document.createElement("div"); head.className = "card-head";
      const identity = document.createElement("div");
      const title = document.createElement("div"); title.className = "strategy-name"; title.textContent = position.strategy + " · " + (position.type === "CE" ? "CALL BUY" : "PUT BUY");
      const symbol = document.createElement("div"); symbol.className = "symbol"; symbol.textContent = position.symbol || "Option symbol unavailable";
      identity.append(title, symbol);
      const status = document.createElement("span"); status.className = "status";
      status.textContent = position.status;
      if (position.status === "OPEN") status.classList.add("open");
      else if (position.status === "STALE") status.classList.add("stale");
      else if (position.status === "TARGET HIT") status.classList.add("target");
      else if (position.status === "SL HIT") status.classList.add("stop");
      head.append(identity, status);
      const pnlLine = document.createElement("div"); pnlLine.className = "card-pnl";
      const pnlValue = document.createElement("strong"); pnlValue.textContent = rupees(pnl);
      if (pnl != null) pnlValue.className = pnl > 0 ? "positive" : pnl < 0 ? "negative" : "";
      const pct = document.createElement("span"); pct.textContent = position.pnl_pct == null ? "P&L % unavailable" : position.pnl_pct.toFixed(2) + "% return";
      pnlLine.append(pnlValue, pct);
      const details = document.createElement("div"); details.className = "details";
      [
        ["Entry price", rupees(position.entry_price)], ["Current price", rupees(position.current_price)],
        ["Quantity", position.qty], ["Strike", position.strike], ["Expiry", position.expiry],
        ["Option type", position.type], ["Entry time", position.entry_time], ["Exit time", position.exit_time],
        ["Stop loss", rupees(position.stop_loss_price)], ["Target", rupees(position.target_price)]
      ].forEach(item => details.append(field(item[0], item[1])));
      const foot = document.createElement("div"); foot.className = "card-foot";
      foot.textContent = position.status === "STALE" ? "Previous-day position remains in paper state · run the paper runner for a safety exit" :
        position.status === "OPEN" ? "Mark-to-market unavailable · " + (position.stop_loss_limit == null ? "No stop level configured" : "Configured max loss ₹" + Number(position.stop_loss_limit).toLocaleString("en-IN")) :
        "Exit reason: " + (position.reason || "not recorded");
      card.append(head, pnlLine, details, foot); return card;
    }
    function addCell(row, value, className) {
      const td = row.insertCell(); td.textContent = value == null || value === "" ? "—" : value;
      if (className) td.className = className; return td;
    }
    function render(data) {
      set("updated", "Updated " + data.updated_at);
      const pnl = document.getElementById("pnl"); pnl.textContent = rupees(data.realized_pnl);
      pnl.className = "value " + (data.realized_pnl > 0 ? "positive" : data.realized_pnl < 0 ? "negative" : "");
      set("pnl-note", data.open_positions ? "Realized only · open-position mark-to-market unavailable" : "Realized P&L · no open positions");
      set("closed", data.closed_positions);
      set("win-loss", data.wins + " wins · " + data.losses + " losses");
      set("trade-count", data.trade_count);
      set("open-count", data.stale_positions
        ? data.open_positions + " unresolved · " + data.stale_positions + " stale"
        : data.open_positions + " open position" + (data.open_positions === 1 ? "" : "s"));
      set("loss-limit", rupees(data.daily_loss_limit));
      set("orders-note", data.order_count + " orders · " + data.orders_remaining + " remaining");

      const alerts = document.getElementById("alerts"); alerts.replaceChildren();
      const addAlert = (text, kind) => { const badge = document.createElement("span"); badge.className = "alert " + kind; badge.textContent = text; alerts.append(badge); };
      if (data.daily_loss_hit) addAlert("DAILY LOSS LIMIT HIT", "danger");
      data.positions.filter(position => position.status === "STALE").forEach(() => addAlert("PREVIOUS-DAY POSITION · SAFETY EXIT REQUIRED", "danger"));
      data.positions.filter(position => position.status === "SL HIT").forEach(() => addAlert("STOP LOSS HIT", "danger"));
      data.positions.filter(position => position.status === "TARGET HIT").forEach(() => addAlert("TARGET HIT", "good"));
      data.positions.filter(position => position.status === "OPEN" && position.pnl != null && position.pnl < -data.big_drawdown_threshold)
        .forEach(() => addAlert("BIG DRAWDOWN", "danger"));
      if (!alerts.childElementCount) addAlert(data.open_positions ? "PAPER POSITIONS · LIVE QUOTES UNAVAILABLE" : "NO OPEN POSITIONS", "warn");

      const cards = document.getElementById("strategies"); cards.replaceChildren();
      if (!data.positions.length) {
        const empty = document.createElement("div"); empty.className = "panel muted"; empty.textContent = "No position records for today.";
        cards.append(empty);
      } else data.positions.forEach(position => cards.append(renderPositionCard(position)));
      renderCurve(data.pnl_curve); renderBars(data.strategy_pnl);

      const body = document.getElementById("positions"); body.replaceChildren();
      data.positions.forEach(position => {
        const row = body.insertRow();
        addCell(row, [position.symbol, position.strike == null ? "" : position.strike].filter(Boolean).join(" / "));
        addCell(row, position.type);
        addCell(row, position.strategy);
        addCell(row, rupees(position.entry_price));
        addCell(row, rupees(position.current_price == null ? position.exit_price : position.current_price));
        addCell(row, rupees(position.pnl), position.pnl > 0 ? "positive" : position.pnl < 0 ? "negative" : "");
        addCell(row, position.qty);
        addCell(row, position.entry_time);
        addCell(row, position.exit_time);
        addCell(row, rupees(position.stop_loss_price));
        addCell(row, rupees(position.target_price));
        addCell(row, position.status);
      });
      document.getElementById("empty").hidden = data.positions.length !== 0;
    }
    async function refresh() {
      try {
        const response = await fetch("/api/data", {cache: "no-store"});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not read dashboard data");
        document.getElementById("error").hidden = true; render(data);
      } catch (error) {
        const element = document.getElementById("error");
        element.textContent = "Dashboard data error: " + error.message; element.hidden = false;
      }
    }
    refresh();
    setInterval(refresh, 15000);
  </script>
</body>
</html>
"""


def _number(value):
    if value in (None, ""):
        return None
    return float(value)


def _position_status(reason):
    normalized = (reason or "").strip().lower()
    if "target" in normalized:
        return "TARGET HIT"
    if "stop loss" in normalized or normalized == "sl":
        return "SL HIT"
    return "CLOSED"


def _position_record(symbol, strategy="Unattributed"):
    return {
        "symbol": symbol,
        "strategy": strategy or "Unattributed",
        "type": symbol.rsplit("-", 1)[-1] if symbol else None,
        "strike": None,
        "expiry": None,
        "qty": None,
        "entry_price": None,
        "current_price": None,
        "exit_price": None,
        "pnl": None,
        "pnl_pct": None,
        "entry_time": None,
        "exit_time": None,
        "reason": "",
        "status": "OPEN",
        "stop_loss_price": None,
        "stop_loss_limit": config.MAX_LOSS_PER_TRADE,
        "target_price": None,
    }


def load_dashboard_data(today=None):
    today = today or datetime.now().date()
    today_text = today.isoformat()

    trades = []
    positions = []
    pending_buys = defaultdict(deque)
    if TRADES_FILE.exists():
        with TRADES_FILE.open(newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                timestamp = datetime.fromisoformat(row["time"])
                if timestamp.date() != today:
                    continue
                pnl_text = (row.get("pnl_net") or "").strip()
                trade = {
                    "time": timestamp.strftime("%H:%M:%S"),
                    "action": row.get("action", "").upper(),
                    "symbol": row.get("symbol", ""),
                    "qty": int(row["qty"]) if row.get("qty") else None,
                    "price": _number(row.get("price")),
                    "pnl_net": _number(pnl_text),
                    "reason": row.get("reason", ""),
                }
                trades.append(trade)
                if trade["action"] == "BUY":
                    position = _position_record(trade["symbol"], row.get("strategy"))
                    position.update(
                        qty=trade["qty"],
                        entry_price=trade["price"],
                        entry_time=trade["time"],
                    )
                    pending_buys[trade["symbol"]].append(position)
                    positions.append(position)
                elif trade["action"] == "SELL":
                    if pending_buys[trade["symbol"]]:
                        position = pending_buys[trade["symbol"]].popleft()
                    else:
                        position = _position_record(trade["symbol"], row.get("strategy"))
                        positions.append(position)
                    position.update(
                        status=_position_status(trade["reason"]),
                        exit_price=trade["price"],
                        exit_time=trade["time"],
                        reason=trade["reason"],
                        pnl=trade["pnl_net"],
                        strategy=row.get("strategy") or position["strategy"],
                    )
                    if position["pnl"] is not None and position["entry_price"] and position["qty"]:
                        position["pnl_pct"] = round(
                            position["pnl"] / (position["entry_price"] * position["qty"]) * 100, 2
                        )

    state = {"position": None}
    if STATE_FILE.exists():
        with STATE_FILE.open(encoding="utf-8") as file:
            state = json.load(file)

    open_positions = state.get("positions")
    if open_positions is None:
        legacy_position = state.get("position")
        open_positions = [legacy_position] if legacy_position else []
    if not isinstance(open_positions, list):
        raise ValueError("Open positions must be stored as a list.")
    stale_state = bool(open_positions and state.get("day") not in (None, today_text))

    matched_positions = set()
    for open_position in open_positions:
        if not isinstance(open_position, dict):
            raise ValueError("Each open position must be an object.")
        if open_position.get("type") not in ("CE", "PE"):
            raise ValueError("Open position has an unsupported option type.")
        match_index = next(
            (index for index, position in enumerate(positions)
             if index not in matched_positions and position["status"] == "OPEN"
             and position["symbol"] == open_position.get("symbol")
             and position["qty"] == open_position.get("qty")
             and position["entry_price"] == open_position.get("entry_price")),
            None,
        )
        if match_index is None:
            match = _position_record(open_position.get("symbol"), open_position.get("strategy"))
            positions.append(match)
        else:
            matched_positions.add(match_index)
            match = positions[match_index]
        entry_time = open_position.get("entry_time") or match.get("entry_time")
        if entry_time and "T" in entry_time:
            entry_time = datetime.fromisoformat(entry_time).strftime("%H:%M:%S")
        match.update(
            type=open_position.get("type"),
            strike=open_position.get("strike"),
            expiry=open_position.get("expiry"),
            qty=open_position.get("qty"),
            entry_price=open_position.get("entry_price"),
            entry_time=entry_time,
            strategy=open_position.get("strategy") or match.get("strategy", "Unattributed"),
            status="STALE" if stale_state else "OPEN",
        )
        if match["entry_price"] is not None and match["qty"]:
            match["stop_loss_price"] = round(
                max(match["entry_price"] - config.MAX_LOSS_PER_TRADE / match["qty"], 0), 2
            )

    for position in positions:
        if position["type"] not in ("CE", "PE") and position["symbol"]:
            suffix = position["symbol"].rsplit("-", 1)[-1]
            position["type"] = suffix if suffix in ("CE", "PE") else None
        if position["entry_price"] is not None and position["qty"] and position["stop_loss_price"] is None:
            position["stop_loss_price"] = round(
                max(position["entry_price"] - config.MAX_LOSS_PER_TRADE / position["qty"], 0), 2
            )

    closed = [
        position for position in positions
        if position["status"] not in ("OPEN", "STALE")
    ]
    realized_pnl = sum(position["pnl"] or 0 for position in closed)
    wins = sum(1 for position in closed if (position["pnl"] or 0) > 0)
    losses = sum(1 for position in closed if (position["pnl"] or 0) < 0)
    open_positions = sum(position["status"] in ("OPEN", "STALE") for position in positions)
    stale_positions = sum(position["status"] == "STALE" for position in positions)
    strategy_totals = defaultdict(float)
    strategy_trade_counts = defaultdict(int)
    pnl_curve = []
    running_pnl = 0.0
    for position in positions:
        if position["status"] not in ("OPEN", "STALE"):
            strategy = position["strategy"] or "Unattributed"
            strategy_totals[strategy] += position["pnl"] or 0
            strategy_trade_counts[strategy] += 1
    closed_by_exit = sorted(
        (position for position in positions if position["status"] not in ("OPEN", "STALE")),
        key=lambda position: position["exit_time"] or "",
    )
    for position in closed_by_exit:
        running_pnl += position["pnl"] or 0
        pnl_curve.append({"time": position["exit_time"] or "—", "pnl": round(running_pnl, 2)})
    strategy_pnl = [
        {"name": name, "pnl": round(value, 2), "closed_positions": strategy_trade_counts[name]}
        for name, value in strategy_totals.items()
    ]

    order_count = len(trades)
    return {
        "trading_day": today_text,
        "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "underlying": config.UNDERLYING,
        "paper_mode": config.PAPER_MODE,
        "realized_pnl": round(realized_pnl, 2),
        "live_pnl_available": False,
        "closed_positions": len(closed),
        "wins": wins,
        "losses": losses,
        "trade_count": sum(trade["action"] == "BUY" for trade in trades),
        "open_positions": open_positions,
        "stale_positions": stale_positions,
        "order_count": order_count,
        "max_orders": config.MAX_ORDERS_PER_DAY,
        "orders_remaining": max(config.MAX_ORDERS_PER_DAY - order_count, 0),
        "daily_loss_limit": config.MAX_LOSS_PER_DAY,
        "daily_loss_hit": realized_pnl <= -config.MAX_LOSS_PER_DAY,
        "big_drawdown_threshold": config.MAX_LOSS_PER_TRADE,
        "positions": positions,
        "strategy_pnl": strategy_pnl,
        "pnl_curve": pnl_curve,
        "trades": trades,
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode("utf-8")
            content_type = "text/html; charset=utf-8"
            status = 200
        elif path == "/api/data":
            try:
                body = json.dumps(load_dashboard_data(), ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
                status = 200
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.log_error("Dashboard data could not be loaded: %s", error)
                body = json.dumps({"error": str(error)}).encode("utf-8")
                content_type = "application/json; charset=utf-8"
                status = 500
        else:
            body = b"Not found"
            content_type = "text/plain; charset=utf-8"
            status = 404

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args))


def main():
    parser = argparse.ArgumentParser(description="Serve the local paper-trading dashboard.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Paper dashboard: http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
