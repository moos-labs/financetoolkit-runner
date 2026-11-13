#!/usr/bin/env python3
"""Generic EGX fundamentals from StockAnalysis.com (issue #30).

For any EGX ticker WITHOUT a hand-verified statements CSV, fetch the
income statement, balance sheet and cash-flow tables from
stockanalysis.com/quote/egx/<CODE>/..., compute the standard ratio set
ourselves, and write results/ratios.json in the same {"value", "basis"}
leaf convention the deep POUL script produces (the Borsagator ensemble
scans both shapes identically).

Two hard lessons from the POUL research are baked in:
- NEVER copy the vendor's per-share figures: StockAnalysis still
  divides POUL by the PRE-merger 479M shares, printing a P/E of 2.2
  where the true figure is ~6.2. Shares come from
  data/shares_overrides.json when present (post-merger counts), else
  the vendor's shares-outstanding row, and the source is recorded.
- Vendor statement LINES (revenue, net income, equity, assets) are
  used as-is and labelled vendor-basis; definitions differ from
  earnings-release figures (e.g. gross profit) and the basis notes
  say so. The calibration ledger judges this family over time.

Outputs: results/ratios.json, results/statements.csv (the generic
fleet format), results/report.md. Any page that fails leaves its
items absent — ratios are only computed from lines actually found.
"""
import csv
import io
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"}
RESULTS = "results"
BASE = "https://stockanalysis.com/quote/egx/{code}/{page}"

# label-prefix -> generic item name. First match wins; growth rows are
# detected by their % values and skipped before mapping.
ITEM_MAP = [
    ("Revenue", "revenue"),
    ("Gross Profit", "gross_profit"),
    ("Operating Income", "operating_income"),
    ("Net Income", "net_income"),
    ("Cash & Short-Term Investments", "cash_and_investments"),
    ("Cash & Equivalents", "cash_and_investments"),
    ("Total Current Assets", "total_current_assets"),
    ("Total Assets", "total_assets"),
    ("Total Current Liabilities", "total_current_liabilities"),
    ("Total Liabilities", "total_liabilities"),
    ("Shareholders' Equity", "total_equity"),
    ("Total Common Equity", "total_equity_common"),
    ("Total Debt", "total_debt"),
    ("Net Cash (Debt)", "net_cash"),
    ("Total Common Shares Outstanding", "shares_outstanding_m"),
    ("Net Cash from Operating", "operating_cash_flow"),
    ("Operating Cash Flow", "operating_cash_flow"),
    ("Capital Expenditures", "capex"),
    ("Free Cash Flow", "free_cash_flow"),
]


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def num(cell):
    if cell is None:
        return None
    s = str(cell).strip().replace(",", "")
    if s in ("", "-", "—", "nan", "None"):
        return None
    pct = s.endswith("%")
    s = s.rstrip("%")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_tables(html):
    """Yield {item: {period: value}} merged across all data tables."""
    import pandas as pd
    merged = {}
    try:
        tables = pd.read_html(io.StringIO(html))
    except Exception:
        return merged
    for t in tables:
        if t.shape[1] < 3 or t.shape[0] < 4:
            continue
        # Flatten the 2-row header: fiscal labels live in row 0 of the
        # header block; with read_html they surface as column tuples.
        cols = []
        for c in t.columns:
            parts = [str(p) for p in (c if isinstance(c, tuple) else (c,))]
            fy = next((p for p in parts if re.fullmatch(r"FY \d{4}|TTM|Current", p)), None)
            cols.append(fy)
        if not any(cols):
            continue
        periods = []
        for fy in cols:
            if fy is None:
                periods.append(None)
            elif fy == "TTM":
                periods.append("TTM")
            elif fy == "Current":
                periods.append("CURRENT")
            else:
                periods.append("FY" + fy.split()[1])
        for _, row in t.iterrows():
            label = str(row.iloc[0]).strip()
            if not label or label.lower() == "nan":
                continue
            vals = [num(row.iloc[i]) for i in range(1, len(periods) + 1)
                    if i < len(row)]
            if vals and sum(1 for v in vals if v is not None) and \
                    any(str(row.iloc[i]).strip().endswith("%")
                        for i in range(1, len(periods) + 1) if i < len(row)):
                continue  # a growth/% row, not a statement line
            item = None
            for prefix, name in ITEM_MAP:
                if label.startswith(prefix):
                    item = name
                    break
            if not item or item in merged:
                continue
            entry = {}
            for p, v in zip(periods[1:], vals):
                if p and v is not None:
                    entry[p] = v
            if entry:
                merged[item] = entry
    return merged


def yahoo_last_close(ticker):
    now = int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={now - 200 * 86400}&period2={now}&interval=1d")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c]
        return closes[-1] if closes else None
    except Exception:
        return None


def pct(n, d):
    return round(n / d * 100, 2) if n is not None and d else None


def x_(n, d):
    return round(n / d, 3) if n is not None and d else None


def main():
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    code = ticker.split(".")[0]
    if not code:
        print("usage: ft_generic.py <TICKER>", file=sys.stderr)
        return 2
    os.makedirs(RESULTS, exist_ok=True)
    items = {}
    for page in ("financials/", "financials/balance-sheet/",
                 "financials/cash-flow-statement/"):
        try:
            items.update({k: v for k, v in
                          parse_tables(fetch(BASE.format(code=code, page=page))).items()
                          if k not in items})
        except Exception as e:
            print(f"WARN page {page}: {e}", file=sys.stderr)
    if "net_income" not in items and "revenue" not in items:
        print(f"ft_generic: no statement lines found for {code}",
              file=sys.stderr)
        return 1

    overrides = {}
    try:
        with open("data/shares_overrides.json") as f:
            overrides = json.load(f)
    except Exception:
        pass
    ov = overrides.get(code) or {}
    periods = []
    for it in items.values():
        for p in it:
            if p.startswith("FY") and p not in periods:
                periods.append(p)
    periods.sort(reverse=True)
    if "TTM" in {p for it in items.values() for p in it}:
        periods = ["TTM"] + periods

    def g(item, period):
        return items.get(item, {}).get(period)

    R = {}
    for p in periods:
        rev, gp = g("revenue", p), g("gross_profit", p)
        op, ni = g("operating_income", p), g("net_income", p)
        eq = g("total_equity", p) or g("total_equity_common", p)
        assets, debt = g("total_assets", p), g("total_debt", p)
        tca, tcl = g("total_current_assets", p), g("total_current_liabilities", p)
        ocf, fcf = g("operating_cash_flow", p), g("free_cash_flow", p)
        block = {}
        def add(name, value, basis):
            if value is not None:
                block[name] = {"value": value, "basis": basis}
        add("revenue_EGPm", rev, "vendor income statement")
        add("net_income_EGPm", ni, "vendor income statement")
        add("gross_margin_pct", pct(gp, rev), "vendor gross profit / revenue")
        add("operating_margin_pct", pct(op, rev), "vendor operating income / revenue")
        add("net_margin_pct", pct(ni, rev), "vendor net income / revenue")
        add("roe_pct", pct(ni, eq), "vendor net income / period-end shareholders' equity")
        add("roa_pct", pct(ni, assets), "vendor net income / period-end total assets")
        add("debt_to_equity_x", x_(debt, eq), "vendor total debt / equity")
        add("current_ratio_x", x_(tca, tcl), "current assets / current liabilities")
        add("ocf_margin_pct", pct(ocf, rev), "operating cash flow / revenue")
        add("fcf_margin_pct", pct(fcf, rev), "free cash flow / revenue")
        if block:
            R[p] = block

    # ---- valuation (latest FY with net income) ----
    fy = next((p for p in periods if p.startswith("FY")
               and g("net_income", p) is not None), None)
    shares, shares_src = None, None
    if ov.get("shares"):
        shares, shares_src = float(ov["shares"]), "override: " + ov.get("note", "")
    elif fy and g("shares_outstanding_m", fy):
        shares = g("shares_outstanding_m", fy) * 1e6
        shares_src = "vendor shares outstanding (may lag corporate actions)"
    price = yahoo_last_close(f"{code}.CA")
    meta = {"ticker": f"{code}.CA", "source": "StockAnalysis.com EGX pages",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "shares": shares, "shares_source": shares_src,
            "price": price, "vendor_net_income_basis": True}
    if fy and shares and price:
        ni = g("net_income", fy)
        eq = g("total_equity", fy) or g("total_equity_common", fy)
        eps = ni * 1e6 / shares if ni is not None else None
        sec = {}
        if eps:
            sec["eps_EGP"] = {"value": round(eps, 4),
                              "basis": f"vendor net income {fy} / shares ({shares_src})"}
            sec["pe_ratio_x"] = {"value": round(price / eps, 2),
                                 "basis": "live price / EPS (vendor net income)"}
        if eq:
            bvps = eq * 1e6 / shares
            sec["pb_ratio_x"] = {"value": round(price / bvps, 2),
                                 "basis": "live price / book value per share"}
        sec["market_cap_EGPm"] = {"value": round(price * shares / 1e6, 1),
                                  "basis": "live price x shares"}
        if sec:
            R[f"VALUATION_AT_{price:.2f}"] = sec
    R["_meta"] = meta

    with open(os.path.join(RESULTS, "ratios.json"), "w") as f:
        json.dump(R, f, indent=1, ensure_ascii=False)
    cols = [p for p in periods if p.startswith("FY")]
    with open(os.path.join(RESULTS, "statements.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "unit"] + cols + ["basis_notes"])
        for item in sorted(items):
            unit = "shares m" if item == "shares_outstanding_m" else "EGP m"
            w.writerow([item, unit] + [items[item].get(c, "") for c in cols]
                       + ["StockAnalysis.com vendor basis"])
    with open(os.path.join(RESULTS, "report.md"), "w") as f:
        f.write(f"# Fundamentals (generic) — {code}.CA\n\n"
                f"Source: StockAnalysis.com EGX pages, fetched "
                f"{meta['fetched_at']}. Vendor statement basis; per-share "
                f"figures computed here, never copied.\n\n"
                f"Shares: {shares} ({shares_src}). Live price: {price}.\n\n"
                f"Periods: {', '.join(periods)}. Latest FY block: "
                f"{json.dumps(R.get(fy, {}), ensure_ascii=False)[:600]}\n")
    print(f"ft_generic: {code}.CA periods={periods} fy={fy} "
          f"shares={shares} price={price}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
