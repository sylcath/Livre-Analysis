"""
Compare the "taux de récupération" (capital / cumulated investment) across
three pension systems:
  1. 100% stock market (real total return with dividends)
  2. 100% notional account (real GDP growth)
  3. 2/3 notional + 1/3 stock market blend

Post-WW2, contributions growing at 2%/year real, 40-year horizon.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.optimize import brentq

DATA_DIR = Path("C:/Users/Windows/Dropbox/Livre/Analysis/Capitalisation")
REF_FILE = Path("C:/Users/Windows/Dropbox/Press/Capitalisation 1982/calculs retraite 1982.xlsx")
MADDISON_FILE = Path("C:/Users/Windows/Dropbox/Livre/Analysis/Maddison/mpd2023_web.xlsx")
OUT_DIR = Path(__file__).parent

# ── Parameters ───────────────────────────────────────────────────────────────
CONTRIBUTION_BASE = 100
GROWTH_RATE = 0.02
DURATION = 43
START_FROM = 1946
ANNUITY_YEARS = 20
DISCOUNT_RATE_FUNDED = 0.02   # for stock market / funded accounts
DISCOUNT_RATE_NOTIONAL = 0.01 # for notional (GDP-indexed) accounts

contributions = [CONTRIBUTION_BASE * (1 + GROWTH_RATE) ** t for t in range(DURATION)]
cumulated = sum(contributions)

# ── Load stock market real returns ───────────────────────────────────────────
raw = pd.read_excel(DATA_DIR / "french_stocks.xlsx", sheet_name="cours", header=None)
raw = raw.iloc[2:].copy()
raw.columns = ["year", "date", "price", "rate"]
raw["year"] = raw["year"].astype(float).astype(int)
raw["price"] = pd.to_numeric(raw["price"], errors="coerce")
yearly_price = raw.groupby("year")["price"].last().sort_index()

div_raw = pd.read_excel(DATA_DIR / "french_stocks.xlsx", sheet_name="dividende", header=None)
div_raw = div_raw.iloc[1:].copy()
div_raw.columns = ["year", "div_yield"]
div_raw["year"] = div_raw["year"].astype(float).astype(int)
div_raw["div_yield"] = pd.to_numeric(div_raw["div_yield"], errors="coerce")
div_yield = div_raw.set_index("year")["div_yield"]

# CPI
inf_raw = pd.read_excel(DATA_DIR / "inflation.xlsx", header=None)
years_inf = inf_raw.iloc[1, 1:].astype(float).astype(int).values
cpi_values = pd.to_numeric(inf_raw.iloc[2, 1:], errors="coerce").values
cpi = pd.Series(cpi_values, index=years_inf).sort_index()

inf2 = pd.read_excel(REF_FILE, sheet_name="Inflation apr\u00e8s 1990", header=None)
inf2 = inf2.iloc[4:].copy()
inf2.columns = ["period", "index", "monthly_inf"] + [f"c{i}" for i in range(len(inf2.columns) - 3)]
inf2["index"] = pd.to_numeric(inf2["index"], errors="coerce")
inf2_jan = inf2[inf2["period"].astype(str).str.endswith("-01")].copy()
inf2_jan["year"] = inf2_jan["period"].astype(str).str[:4].astype(int)
cpi_post = inf2_jan.set_index("year")["index"]
for y in range(2000, cpi_post.index.max() + 1):
    if y in cpi_post.index and (y - 1) in cpi_post.index:
        cpi[y] = cpi[y - 1] * cpi_post[y] / cpi_post[y - 1]

price_return = yearly_price / yearly_price.shift(1)
nominal_return = pd.Series(dtype=float)
for y in price_return.dropna().index:
    if y in div_yield.index and pd.notna(div_yield[y]):
        nominal_return[y] = price_return[y] * (1 + div_yield[y])

stock_real = pd.Series(dtype=float)
for y in nominal_return.index:
    if y in cpi.index and (y - 1) in cpi.index:
        stock_real[y] = nominal_return[y] / (cpi[y] / cpi[y - 1])

# ── Load GDP growth ──────────────────────────────────────────────────────────
maddison = pd.read_excel(MADDISON_FILE, sheet_name="Full data")
fra = maddison[maddison["countrycode"] == "FRA"][["year", "gdppc", "pop"]].copy()
fra = fra.dropna(subset=["gdppc", "pop"]).sort_values("year").set_index("year")
fra["gdp"] = fra["gdppc"] * fra["pop"]
gdp_growth = (fra["gdp"] / fra["gdp"].shift(1)).dropna()

# ── Find common starting years ───────────────────────────────────────────────
max_year = min(stock_real.index.max(), gdp_growth.index.max())
start_years = []
for y in range(START_FROM, int(max_year) - DURATION + 2):
    yrs = range(y, y + DURATION)
    if (all(yr in stock_real.index and pd.notna(stock_real[yr]) for yr in yrs) and
        all(yr in gdp_growth.index for yr in yrs)):
        start_years.append(y)

print(f"Common starting years: {start_years[0]}-{start_years[-1]} ({len(start_years)} cohorts)")

# ── Run simulations ──────────────────────────────────────────────────────────
res_stock = {}
res_gdp = {}
res_blend = {}

SHARE_NOTIONAL = 2 / 3
SHARE_STOCK = 1 / 3

for start in start_years:
    cap_stock = 0.0
    cap_gdp = 0.0
    cap_blend_n = 0.0  # notional part of blend
    cap_blend_s = 0.0  # stock part of blend

    for t in range(DURATION):
        year = start + t
        r_stock = stock_real[year]
        r_gdp = gdp_growth[year]

        cap_stock = cap_stock * r_stock + contributions[t]
        cap_gdp = cap_gdp * r_gdp + contributions[t]
        cap_blend_n = cap_blend_n * r_gdp + contributions[t] * SHARE_NOTIONAL
        cap_blend_s = cap_blend_s * r_stock + contributions[t] * SHARE_STOCK

    # Convert final capital to total annuity payments over ANNUITY_YEARS
    # Annual payment A = C * r / (1 - (1+r)^(-n))  (annuity formula)
    # Total payments = A * n
    n = ANNUITY_YEARS

    def payout_factor(r):
        if r == 0:
            return 1.0  # each year pays C/n, total = C
        return r / (1 - (1 + r) ** (-n)) * n

    pf_funded = payout_factor(DISCOUNT_RATE_FUNDED)
    pf_notional = payout_factor(DISCOUNT_RATE_NOTIONAL)

    res_stock[start] = cap_stock * pf_funded / cumulated
    res_gdp[start] = cap_gdp * pf_notional / cumulated
    # Blend: notional part uses notional discount, stock part uses funded discount
    res_blend[start] = (cap_blend_n * pf_notional + cap_blend_s * pf_funded) / cumulated

s_stock = pd.Series(res_stock).sort_index()
s_gdp = pd.Series(res_gdp).sort_index()
s_blend = pd.Series(res_blend).sort_index()

# ── Plot: English ────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(13, 7))

ax.plot(s_stock.index, s_stock.values, 'b-o', markersize=4, linewidth=1.8,
        label="100% Stock market")
ax.plot(s_blend.index, s_blend.values, 'g-s', markersize=4, linewidth=1.8,
        label=f"{SHARE_NOTIONAL:.0%} Notional + {SHARE_STOCK:.0%} Stock")
ax.plot(s_gdp.index, s_gdp.values, 'r-^', markersize=4, linewidth=1.8,
        label="100% Notional (GDP growth)")
ax.axhline(y=1, color='gray', linestyle='--', linewidth=0.8, label="Break-even")

ax.set_xlabel("Starting year", fontsize=12)
ax.set_ylabel("Total annuity payments / Cumulated contributions (real)", fontsize=12)
ax.set_title(f"Recovery rate: {DURATION}-year contributions, {ANNUITY_YEARS}-year annuity\n"
             f"(discount: {DISCOUNT_RATE_NOTIONAL:.0%} notional / {DISCOUNT_RATE_FUNDED:.0%} funded, "
             f"contributions +{GROWTH_RATE:.0%}/year real, "
             f"{start_years[0]}\u2013{start_years[-1]})",
             fontsize=13)
ax.legend(fontsize=11, loc="upper right")
ax.grid(True, alpha=0.3)
ax.set_xlim(s_stock.index[0] - 1, s_stock.index[-1] + 1)
plt.tight_layout()
plt.savefig(OUT_DIR / "recovery_rate_comparison.png", dpi=150)
plt.savefig(OUT_DIR / "recovery_rate_comparison.svg")
print("English plot saved")

# ── Plot: French ─────────────────────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(13, 7))

ax2.plot(s_stock.index, s_stock.values, 'b-o', markersize=4, linewidth=1.8,
         label="100 % March\u00e9 boursier")
ax2.plot(s_blend.index, s_blend.values, 'g-s', markersize=4, linewidth=1.8,
         label=f"{SHARE_NOTIONAL:.0%} Notionnel + {SHARE_STOCK:.0%} Boursier")
ax2.plot(s_gdp.index, s_gdp.values, 'r-^', markersize=4, linewidth=1.8,
         label="100 % Notionnel (croissance du PIB)")
ax2.axhline(y=1, color='gray', linestyle='--', linewidth=0.8,
            label="Seuil de rentabilit\u00e9")

ax2.set_xlabel("Ann\u00e9e de d\u00e9but", fontsize=12)
ax2.set_ylabel("Total des rentes vers\u00e9es / Cotisations cumul\u00e9es (r\u00e9el)", fontsize=12)
ax2.set_title(f"Taux de r\u00e9cup\u00e9ration : {DURATION} ans de cotisations, "
              f"rente sur {ANNUITY_YEARS} ans\n"
              f"(taux d\u2019actualisation : {DISCOUNT_RATE_NOTIONAL:.0%} notionnel / "
              f"{DISCOUNT_RATE_FUNDED:.0%} capitalis\u00e9, "
              f"cotisations +{GROWTH_RATE:.0%}/an, "
              f"{start_years[0]}\u2013{start_years[-1]})",
              fontsize=13)
ax2.legend(fontsize=11, loc="upper right")
ax2.grid(True, alpha=0.3)
ax2.set_xlim(s_stock.index[0] - 1, s_stock.index[-1] + 1)
plt.tight_layout()
plt.savefig(OUT_DIR / "taux_recuperation_comparaison.png", dpi=150)
plt.savefig(OUT_DIR / "taux_recuperation_comparaison.svg")
print("French plot saved")

# ── Plot: Book version (B&W, LaTeX, PDF) ─────────────────────────────────────
plt.rcParams.update({
    "text.usetex": True,
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman"],
    "font.size": 25,
})

fig3, ax3 = plt.subplots(figsize=(15, 8))

ax3.plot(s_stock.index, s_stock.values, 'k-o', markersize=6, linewidth=2.0)
ax3.plot(s_blend.index, s_blend.values, 'k-s', markersize=6, linewidth=2.0,
         markerfacecolor='gray')
ax3.plot(s_gdp.index, s_gdp.values, 'k-^', markersize=6, linewidth=1.4,
         markerfacecolor='white')
ax3.set_xlabel(r"Ann\'ee d'entr\'ee sur le march\'e du travail", fontsize=27)
ax3.grid(True, alpha=0.3)
ax3.set_xlim(s_stock.index[0] - 1, s_stock.index[-1] + 1)

# Inline labels at the right of the last data point (instead of legend)
label_offset = 0.8
for series, label in [(s_stock, r"100\,\% CAC40"),
                      (s_blend, r"67\,\% notionnel $+$" "\n" r"33\,\% CAC40"),
                      (s_gdp, r"100\,\% notionnel")]:
    ax3.text(series.index[-1] + label_offset, series.values[-1], label,
             fontsize=22, va='center', ha='left')

# Remove top/right spines, keep bottom/left in black
ax3.spines['top'].set_visible(False)
ax3.spines['right'].set_visible(False)
ax3.spines['left'].set_color('black')
ax3.spines['bottom'].set_color('black')
ax3.set_ylim(bottom=0)

# Remove the "0" label from y-axis
yticks = [t for t in ax3.get_yticks() if t >= 0]
ax3.set_yticks(yticks)
ax3.set_yticklabels(['' if t == 0 else f'{t:g}' for t in yticks])

plt.tight_layout()
plt.subplots_adjust(right=0.82)
plt.savefig(OUT_DIR / "taux_recuperation_bw.pdf")
plt.savefig(OUT_DIR / "taux_recuperation_bw.png", dpi=150)
print("Book version (B&W PDF) saved")

# Reset rcParams
plt.rcParams.update(plt.rcParamsDefault)

# ── Summary stats ────────────────────────────────────────────────────────────
print(f"\n{'System':<30} {'Min':>6} {'Q1':>6} {'Med':>6} {'Q3':>6} {'Max':>6} {'Mean':>6}")
print("-" * 72)
for name, s in [("100% Stock market", s_stock),
                (f"{SHARE_NOTIONAL:.0%} Not. + {SHARE_STOCK:.0%} Stock", s_blend),
                ("100% Notional (GDP)", s_gdp)]:
    v = s.values
    print(f"{name:<30} {v.min():>5.2f}x {np.percentile(v,25):>5.2f}x "
          f"{np.median(v):>5.2f}x {np.percentile(v,75):>5.2f}x "
          f"{v.max():>5.2f}x {v.mean():>5.2f}x")
