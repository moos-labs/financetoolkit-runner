#!/usr/bin/env python3
"""Fundamental ratios for Cairo Poultry (EGX: POUL) from a verified-statements CSV.

Input : data/poul_statements.csv  (generic format: item, unit, <period columns>, basis_notes)
Output: results/ratios.json, results/report.md

Method: try FinanceToolkit's manual-statements API first and record what it
returns; the headline ratios are computed directly from the verified figures
with pandas/plain Python so every number is traceable to a CSV line item.
Whichever path produced the headline numbers is stated in the outputs.
"""
import json
import os
import sys

import pandas as pd

CSV_PATH = os.environ.get("STATEMENTS_CSV", "data/poul_statements.csv")
RESULTS_DIR = "results"
PRICE_EGP = 10.00  # reference price used by the 10-Nov-2026 research (close 9 Nov 2026: 9.99)
SHARES_POST = 1_789_351_397

os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------- load inputs
raw = pd.read_csv(CSV_PATH, dtype=str).fillna("")
PERIODS = [c for c in raw.columns if c not in ("item", "unit", "basis_notes")]

def num(period, item):
    row = raw.loc[raw["item"] == item]
    if row.empty:
        return None
    v = str(row.iloc[0].get(period, "")).strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None

def pct(n, d, nd=2):
    if n is None or d in (None, 0):
        return None
    return round(n / d * 100, nd)

def x_(n, d, nd=3):
    if n is None or d in (None, 0):
        return None
    return round(n / d, nd)

def add(store, period, name, value, basis):
    if value is not None:
        store.setdefault(period, {})[name] = {"value": value, "basis": basis}

R = {}  # computed ratios

# ---------------------------------------------------------------- FY2025
p = "FY2025"
rev, gp, ebitda = num(p, "revenue"), num(p, "gross_profit"), num(p, "ebitda_adjusted")
npat, npat_sp = num(p, "net_profit_total"), num(p, "net_profit_special_purpose")
eq, eq_sp, assets = num(p, "total_equity"), num(p, "total_equity_special_purpose"), num(p, "total_assets")
cash, debt = num(p, "cash_and_investments"), num(p, "total_debt")
ocf, capex, fcf = num(p, "operating_cash_flow"), num(p, "capex"), num(p, "free_cash_flow")
nii, gains = num(p, "net_interest_income"), num(p, "gains_on_sale_of_assets")
opinc_v = num(p, "operating_income_vendor")
div_total, pool = num("CURRENT_NOV2026", "dividend_total"), num(p, "distributable_pool_special_purpose")
dps = num("CURRENT_NOV2026", "dividend_per_share")

add(R, p, "gross_margin_pct", pct(gp, rev), "gross profit (release definition) / revenue")
add(R, p, "ebitda_margin_pct", pct(ebitda, rev), "adjusted EBITDA / revenue")
add(R, p, "operating_margin_vendor_pct", pct(opinc_v, rev), "vendor operating income / revenue")
add(R, p, "net_margin_total_pct", pct(npat, rev), "total NPAT / revenue")
add(R, p, "net_margin_special_purpose_pct", pct(npat_sp, rev), "special-purpose NPAT / consolidated revenue")
add(R, p, "roe_pct", pct(npat, eq), "total NPAT / total equity at 31-Dec-2025 (period-end, no average available)")
add(R, p, "roe_special_purpose_pct", pct(npat_sp, eq_sp), "special-purpose NPAT / special-purpose equity at end-2025")
add(R, p, "roa_pct", pct(npat, assets), "total NPAT / total assets at 31-Dec-2025 (period-end)")
add(R, p, "asset_turnover_x", x_(rev, assets), "revenue / total assets (period-end)")
add(R, p, "equity_multiplier_x", x_(assets, eq), "total assets / total equity (period-end)")
add(R, p, "debt_to_equity_x", x_(debt, eq), "total debt / total equity at 31-Dec-2025")
net_cash_25 = (cash - debt) if (cash is not None and debt is not None) else None
add(R, p, "net_cash_EGPm", net_cash_25, "cash & investments - total debt at 31-Dec-2025")
add(R, p, "ocf_margin_pct", pct(ocf, rev), "operating cash flow / revenue")
add(R, p, "capex_to_revenue_pct", pct(capex, rev), "capex / revenue")
add(R, p, "fcf_margin_pct", pct(fcf, rev), "free cash flow / revenue")
add(R, p, "fcf_conversion_pct", pct(fcf, npat), "free cash flow / total NPAT")
add(R, p, "net_interest_income_pct_of_npat", pct(nii, npat), "net interest income / total NPAT")
add(R, p, "asset_sale_gains_pct_of_npat", pct(gains, npat), "gains on sale of assets / total NPAT")
eps_c = (npat * 1e6 / SHARES_POST) if npat else None
eps_s = (npat_sp * 1e6 / SHARES_POST) if npat_sp else None
bvps_c = (eq * 1e6 / SHARES_POST) if eq else None
bvps_s = (eq_sp * 1e6 / SHARES_POST) if eq_sp else None
add(R, p, "eps_post_merger_shares_consol_EGP", round(eps_c, 4) if eps_c else None, "total NPAT / 1,789,351,397 post-merger shares")
add(R, p, "eps_post_merger_shares_special_EGP", round(eps_s, 4) if eps_s else None, "special-purpose NPAT / post-merger shares")
add(R, p, "bvps_post_merger_consol_EGP", round(bvps_c, 4) if bvps_c else None, "consolidated equity end-2025 / post-merger shares")
add(R, p, "bvps_post_merger_special_EGP", round(bvps_s, 4) if bvps_s else None, "special-purpose equity end-2025 / post-merger shares")
add(R, p, "net_cash_per_share_end2025_EGP", round(net_cash_25 * 1e6 / SHARES_POST, 4) if net_cash_25 else None, "net cash end-2025 / post-merger shares")

# DuPont check (FY2025)
if all(v is not None for v in (pct(npat, rev), x_(rev, assets), x_(assets, eq))):
    dupont = pct(npat, rev) / 100 * x_(rev, assets) * x_(assets, eq) * 100
    add(R, p, "dupont_roe_check_pct", round(dupont, 2), "net margin x asset turnover x equity multiplier (should equal roe_pct)")

# Payout (dividend declared Nov 2026 against FY2025 profit)
add(R, "PAYOUT_FY2025", "payout_vs_consolidated_npat_pct", pct(div_total, npat), "EGP 3,399.77m dividend / FY2025 consolidated NPAT 2,890")
add(R, "PAYOUT_FY2025", "payout_vs_special_purpose_npat_pct", pct(div_total, npat_sp), "dividend / FY2025 special-purpose NPAT 2,932")
add(R, "PAYOUT_FY2025", "dividend_pct_of_distributable_pool", pct(div_total, pool), "dividend / special-purpose distributable pool 5,022")
add(R, "PAYOUT_FY2025", "dividend_yield_at_reference_price_pct", pct(dps, PRICE_EGP), "1.90 / 10.00 reference price (one-off, non-recurring)")

# Valuation snapshot at the research reference price (not a live price)
mcap = PRICE_EGP * SHARES_POST / 1e6  # EGP m
net_cash_jun = None
add(R, "VALUATION_AT_10.00", "market_cap_EGPm", round(mcap, 1), "10.00 x 1,789,351,397 shares")
if eps_c: add(R, "VALUATION_AT_10.00", "pe_consolidated_npat_x", x_(PRICE_EGP, eps_c, 2), "price / EPS on post-merger shares (consolidated NPAT)")
if eps_s: add(R, "VALUATION_AT_10.00", "pe_special_purpose_npat_x", x_(PRICE_EGP, eps_s, 2), "price / EPS on post-merger shares (special-purpose NPAT)")
if bvps_s: add(R, "VALUATION_AT_10.00", "pb_special_purpose_x", x_(PRICE_EGP, bvps_s, 2), "price / special-purpose BVPS end-2025")
if bvps_c: add(R, "VALUATION_AT_10.00", "pb_consolidated_x", x_(PRICE_EGP, bvps_c, 2), "price / consolidated BVPS end-2025")

# ---------------------------------------------------------------- FY2024
p = "FY2024"
rev4 = num(p, "revenue")
add(R, p, "operating_margin_vendor_pct", pct(num(p, "operating_income_vendor"), rev4), "vendor operating income / revenue")
add(R, p, "net_margin_eps_basis_pct", pct(num(p, "net_income_eps_basis"), rev4), "EPS-basis net income (after appropriations) / revenue")
add(R, p, "fcf_margin_pct", pct(num(p, "free_cash_flow"), rev4), "free cash flow / revenue")

# ---------------------------------------------------------------- H1 2026
p = "H1_2026"
revh = num(p, "revenue")
add(R, p, "gross_margin_pct", pct(num(p, "gross_profit"), revh), "release gross profit / revenue (6 months)")
add(R, p, "ebitda_margin_pct", pct(num(p, "ebitda_adjusted"), revh), "adjusted EBITDA / revenue (6 months)")
add(R, p, "operating_margin_pct", pct(num(p, "operating_profit"), revh), "release operating profit / revenue (6 months)")
add(R, p, "net_margin_pct", pct(num(p, "net_profit_total"), revh), "total NPAT / revenue (6 months)")
add(R, p, "debt_to_equity_x", x_(num(p, "total_debt"), num(p, "total_equity")), "total debt / total equity at 30-Jun-2026")
nc_h = num(p, "cash_and_investments") - num(p, "total_debt")
add(R, p, "net_cash_EGPm", nc_h, "cash & investments - total debt at 30-Jun-2026 (research rounds this to 3,922 from unrounded inputs)")
add(R, p, "net_cash_per_share_EGP", round(nc_h * 1e6 / SHARES_POST, 4), "net cash 30-Jun-2026 / post-merger shares")
add(R, p, "net_interest_income_pct_of_npat", pct(num(p, "net_interest_income"), num(p, "net_profit_total")), "net interest income / total NPAT (6 months)")
net_cash_jun = nc_h

ev = mcap - net_cash_jun if net_cash_jun else None
if ev: add(R, "VALUATION_AT_10.00", "ev_ebitda_fy2025_x", x_(ev, ebitda, 2), "(market cap - net cash Jun-2026) / FY2025 adjusted EBITDA")

# ---------------------------------------------------------------- coverage gaps
COVERAGE = [
    ("current_ratio / quick_ratio / cash_ratio", "Current assets and current liabilities are not split out in any verified source figure."),
    ("interest_coverage_ratio", "Only NET interest income (+676 FY25) is disclosed in the sources; gross interest expense is not verified."),
    ("inventory_turnover / receivables_turnover / payables_turnover / cash_conversion_cycle", "Inventory, receivables and payables balances do not appear in the verified sources."),
    ("return_on_invested_capital (ROIC)", "NOPAT cannot be derived: the effective tax charge is not verified (pre-tax profit is given only approximately, ~EGP 3,667m)."),
    ("effective_tax_rate", "Pre-tax profit is stated only approximately in the sources."),
    ("altman_z_score / piotroski_f_score", "Require full balance-sheet detail (working capital, current items) and, for Piotroski, two full years of balance sheets; not available in verified form."),
    ("roe / roa FY2024", "FY2024 total equity and total assets are not verified (special-purpose FY2024 equity was not disclosed in the source)."),
    ("roa H1_2026", "Total assets at 30-Jun-2026 are not stated in the sources (only total liabilities and equity)."),
    ("dividend_payout_ratio FY2024", "No FY2024 dividend per share appears in the extracted verified sources."),
    ("dupont FY2024 / H1_2026", "Needs total assets and equity for the same period-end; missing for FY2024 and (assets) for Jun-2026."),
]

# ---------------------------------------------------------------- FinanceToolkit attempt
def df_to_jsonable(df):
    out = {}
    try:
        for col in df.columns:
            out[str(col)] = {}
            for idx, val in df[col].items():
                try:
                    out[str(col)][str(idx)] = round(float(val), 4)
                except (TypeError, ValueError):
                    out[str(col)][str(idx)] = str(val)
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}
    return out

ft_result = {"status": "not_attempted"}
try:
    import inspect
    from financetoolkit import Toolkit

    dates = ["2025-12-31"]
    income = pd.DataFrame(
        {
            "2025-12-31": [15825, 11216, 4609, 2668, 3098, 2890]
        },
        index=["Revenue", "Cost Of Revenue", "Gross Profit", "Operating Income", "EBITDA", "Net Income"],
    )
    balance = pd.DataFrame(
        {"2025-12-31": [4535, 10704.8, 7340.8, 236]},
        index=["Cash And Cash Equivalents", "Total Assets", "Total Stockholders Equity", "Total Debt"],
    )
    sig = inspect.signature(Toolkit.__init__).parameters
    kwargs = {}
    for key, frame in (("income", income), ("balance", balance),
                       ("income_statement", income), ("balance_sheet", balance),
                       ("financial_statements", None)):
        if key in sig and frame is not None:
            kwargs[key] = frame
    tk = None
    for tickers in (["POUL"], "POUL"):
        try:
            tk = Toolkit(tickers, **kwargs)
            break
        except TypeError:
            continue
    if tk is None:
        tk = Toolkit(["POUL"], api_key="", **kwargs)
    collected = {}
    for getter in ("get_profitability_ratios", "get_liquidity_ratios",
                   "get_solvency_ratios", "get_efficiency_ratios", "get_valuation_ratios"):
        try:
            fn = getattr(tk.ratios, getter)
            res = fn()
            if res is not None and hasattr(res, "columns") and not res.empty:
                collected[getter] = df_to_jsonable(res)
        except Exception as e:  # noqa: BLE001
            collected[getter] = {"_error": f"{type(e).__name__}: {e}"}
    try:
        dup = tk.models.get_dupont_analysis()
        if dup is not None and hasattr(dup, "columns") and not dup.empty:
            collected["get_dupont_analysis"] = df_to_jsonable(dup)
    except Exception as e:  # noqa: BLE001
        collected["get_dupont_analysis"] = {"_error": f"{type(e).__name__}: {e}"}
    usable = {k: v for k, v in collected.items() if "_error" not in v}
    ft_result = {
        "status": "ok" if usable else "returned_no_usable_ratios",
        "toolkit_kwargs_used": sorted(kwargs.keys()),
        "collected": collected,
    }
except Exception as e:  # noqa: BLE001
    ft_result = {"status": "failed", "error": f"{type(e).__name__}: {e}"}

PATH = ("pandas_direct (headline ratios computed in this script from the verified CSV); "
        f"FinanceToolkit manual-statements attempt status: {ft_result['status']}")

# ---------------------------------------------------------------- outputs
out = {
    "company": "Cairo Poultry Company (EGX: POUL)",
    "input_csv": CSV_PATH,
    "computation_path": PATH,
    "financetoolkit_attempt": ft_result,
    "ratios": R,
    "coverage_gaps": [{"ratio": r, "blocker": b} for r, b in COVERAGE],
}
with open(os.path.join(RESULTS_DIR, "ratios.json"), "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

def fmt(v):
    return f"{v:,.2f}" if isinstance(v, (int, float)) else str(v)

lines = []
lines.append("# Cairo Poultry (EGX: POUL) — Fundamental Ratios")
lines.append("")
lines.append("Source data: `data/poul_statements.csv` — figures extracted **only** from the verified "
             "10-Nov-2026 buy-decision research (company earnings releases, EGX disclosures, "
             "post-merger special-purpose statements). No figure was invented; gaps in the CSV are "
             "gaps in the verified record.")
lines.append("")
lines.append("## Computation path")
lines.append("")
lines.append(f"- Headline ratios: **computed directly with pandas/plain Python from the verified CSV** (traceable line-by-line).")
lines.append(f"- FinanceToolkit manual-statements API attempt: **{ft_result['status']}**"
             + (f" ({ft_result.get('error','')})" if ft_result['status'] == 'failed' else "")
             + ". Its raw outcome is preserved in `ratios.json` under `financetoolkit_attempt`.")
lines.append("")
lines.append("## Computed ratios")
for period in ("FY2025", "FY2024", "H1_2026", "PAYOUT_FY2025", "VALUATION_AT_10.00"):
    if period not in R:
        continue
    title = {"FY2025": "FY2025 (year to 31 Dec 2025)", "FY2024": "FY2024 (partial — see coverage)",
             "H1_2026": "H1 2026 (six months to 30 Jun 2026)",
             "PAYOUT_FY2025": "FY2025 dividend (coupon #42, paid 18 Nov 2026)",
             "VALUATION_AT_10.00": "Valuation snapshot at EGP 10.00 reference price (research price, not live)"}[period]
    lines.append("")
    lines.append(f"### {title}")
    lines.append("")
    lines.append("| Ratio | Value | Basis |")
    lines.append("|---|---|---|")
    for name, entry in R[period].items():
        lines.append(f"| {name} | {fmt(entry['value'])} | {entry['basis']} |")
lines.append("")
lines.append("## Coverage — standard ratios that could NOT be computed")
lines.append("")
lines.append("| Ratio | Missing line item / blocker |")
lines.append("|---|---|")
for r, b in COVERAGE:
    lines.append(f"| {r} | {b} |")
lines.append("")
lines.append("## Caveats")
lines.append("")
lines.append("- Balance-sheet ratios use **period-end** balances (no averaged balances exist in the verified sources), so ROE/ROA are point-in-time variants.")
lines.append("- Gross profit and EBITDA follow the **company earnings-release definitions**; a vendor definition (COGS incl. depreciation) gives lower gross profit (FY25: 3,338 vs 4,609).")
lines.append("- FY2024 is thin: total NPAT is reported only as a conflicting range (2,387–2,420), and FY2024 equity/assets are unverified, so FY2024 return ratios are blocked rather than estimated.")
lines.append("- The 19.0% dividend yield is a **one-off** return of accumulated retained earnings (payout >100% of FY2025 profit) and is not repeatable at this size.")
with open(os.path.join(RESULTS_DIR, "report.md"), "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"FinanceToolkit attempt: {ft_result['status']}")
print(f"Ratios computed for periods: {sorted(R.keys())}")
print(f"Total ratio entries: {sum(len(v) for v in R.values())}")
print("Wrote results/ratios.json and results/report.md")
