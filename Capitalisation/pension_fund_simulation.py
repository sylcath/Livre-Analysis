"""
Pension fund simulation: invest in the French stock market with contributions
growing at 2% per year in real terms (starting at 100 EUR).
For each starting year from 1900 to the latest year with 40 years of data,
compute total capital after 40 years and plot capital / cumulated investment.

Note: The Le Bris & Hautcoeur stock index is NOMINAL. We deflate using CPI
to obtain real returns. CPI data is chained from two sources:
  - inflation.xlsx (1840-1999, base 1999=1)
  - "Inflation après 1990" from the reference spreadsheet (1990-2024, INSEE
    monthly CPI base 2015=100), converted to annual January values.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from collections import defaultdict
from scipy.optimize import brentq

DATA_DIR = Path("C:/Users/Windows/Dropbox/Livre/Analysis/Capitalisation")
REF_FILE = Path("C:/Users/Windows/Dropbox/Press/Capitalisation 1982/calculs retraite 1982.xlsx")
OUT_DIR = Path(__file__).parent

# ── Load stock price data (monthly, NOMINAL) ─────────────────────────────────
raw = pd.read_excel(DATA_DIR / "french_stocks.xlsx", sheet_name="cours", header=None)
raw = raw.iloc[2:].copy()
raw.columns = ["year", "date", "price", "rate"]
raw["year"] = raw["year"].astype(float).astype(int)
raw["price"] = pd.to_numeric(raw["price"], errors="coerce")

# Take end-of-year price (last observation per year)
yearly_price = raw.groupby("year")["price"].last().sort_index()

# ── Load dividend yield data (annual) ────────────────────────────────────────
div_raw = pd.read_excel(DATA_DIR / "french_stocks.xlsx", sheet_name="dividende", header=None)
div_raw = div_raw.iloc[1:].copy()
div_raw.columns = ["year", "div_yield"]
div_raw["year"] = div_raw["year"].astype(float).astype(int)
div_raw["div_yield"] = pd.to_numeric(div_raw["div_yield"], errors="coerce")
div_yield = div_raw.set_index("year")["div_yield"]

# ── Build CPI series (1840-2024) ─────────────────────────────────────────────
# Source 1: inflation.xlsx (1840-1999, base 1999=1)
inf_raw = pd.read_excel(DATA_DIR / "inflation.xlsx", header=None)
years_inf = inf_raw.iloc[1, 1:].astype(float).astype(int).values
cpi_values = pd.to_numeric(inf_raw.iloc[2, 1:], errors="coerce").values
cpi_old = pd.Series(cpi_values, index=years_inf).sort_index()

# Source 2: reference spreadsheet post-1990 monthly CPI (INSEE, base 2015=100)
inf2 = pd.read_excel(REF_FILE, sheet_name="Inflation apr\u00e8s 1990", header=None)
inf2 = inf2.iloc[4:].copy()
inf2.columns = ["period", "index", "monthly_inf"] + [f"c{i}" for i in range(len(inf2.columns) - 3)]
inf2["index"] = pd.to_numeric(inf2["index"], errors="coerce")
# Extract January values for annual CPI
inf2_jan = inf2[inf2["period"].astype(str).str.endswith("-01")].copy()
inf2_jan["year"] = inf2_jan["period"].astype(str).str[:4].astype(int)
cpi_post = inf2_jan.set_index("year")["index"]

# Chain: use cpi_old up to 1999, then extend with cpi_post growth rates
# Overlap year: 1999. cpi_old[1999] = 1.0, cpi_post for 2000-2024
# Convert cpi_post to same base: ratio at overlap point
# cpi_post is Jan values (base 2015=100). Use Jan 1999 as link.
# cpi_post[1990]=66.56 (Jan 1990). cpi_old[1989]=0.8277 (annual).
# Better: use the annual inflation rates from cpi_post to extend cpi_old.
cpi = cpi_old.copy()
for y in range(2000, cpi_post.index.max() + 1):
    if y in cpi_post.index and (y - 1) in cpi_post.index:
        annual_inflation = cpi_post[y] / cpi_post[y - 1]
        cpi[y] = cpi[y - 1] * annual_inflation

print(f"CPI range: {cpi.index.min()}-{cpi.index.max()}")
print(f"CPI 1999={cpi[1999]:.4f}, CPI 2024={cpi.get(2024, 'N/A')}")

# ── Compute annual nominal total return ──────────────────────────────────────
# Total return factor for year t: P_t/P_{t-1} * (1 + div_yield_t)
price_return = yearly_price / yearly_price.shift(1)

all_years = sorted(set(price_return.dropna().index) &
                   set(div_yield.dropna().index))
min_year = min(all_years)
max_year = max(all_years)
print(f"Stock data available: {min_year}-{max_year}")

# Nominal total return factor
nominal_return = pd.Series(index=range(min_year, max_year + 1), dtype=float)
for y in range(min_year, max_year + 1):
    if y in price_return.index and y in div_yield.index:
        pr = price_return.loc[y]
        dy = div_yield.loc[y]
        if pd.notna(pr) and pd.notna(dy):
            nominal_return.loc[y] = pr * (1 + dy)

# Real total return factor: nominal / inflation
real_return = pd.Series(index=range(min_year, max_year + 1), dtype=float)
for y in range(min_year, max_year + 1):
    if pd.notna(nominal_return.get(y, np.nan)) and y in cpi.index and (y - 1) in cpi.index:
        inflation_factor = cpi[y] / cpi[y - 1]
        real_return.loc[y] = nominal_return[y] / inflation_factor

print(f"Real return years available: "
      f"{real_return.dropna().index.min()}-{real_return.dropna().index.max()}")

# ── Simulation parameters ────────────────────────────────────────────────────
CONTRIBUTION_BASE = 100  # EUR first year (real euros)
GROWTH_RATE = 0.02       # 2% real growth per year
DURATION = 43            # years of contributions

# Pre-compute contribution schedule (real euros)
contributions = [CONTRIBUTION_BASE * (1 + GROWTH_RATE) ** t for t in range(DURATION)]
cumulated_contributions = sum(contributions)

# Find valid starting years (need DURATION consecutive years of REAL return data)
START_FROM = 1946  # post-WW2
start_years = []
for y in range(START_FROM, max_year - DURATION + 2):
    yrs = range(y, y + DURATION)
    if all(pd.notna(real_return.get(yr, np.nan)) for yr in yrs):
        start_years.append(y)

if start_years:
    print(f"Valid starting years: {start_years[0]}-{start_years[-1]} "
          f"({len(start_years)} simulations)")
else:
    print("WARNING: No valid starting years with full real return coverage!")
    # Fall back to years where we have at least nominal data
    for y in range(1900, max_year - DURATION + 2):
        yrs = range(y, y + DURATION)
        if all(pd.notna(nominal_return.get(yr, np.nan)) for yr in yrs):
            start_years.append(y)
    print(f"Using nominal returns: {start_years[0]}-{start_years[-1]} "
          f"({len(start_years)} simulations)")

print(f"Contribution growth: {GROWTH_RATE:.0%}/year real, "
      f"total invested over {DURATION} years: {cumulated_contributions:.0f} EUR")

# ── Run simulations ──────────────────────────────────────────────────────────
results = {}
capitals = {}

for start in start_years:
    capital = 0.0

    for t in range(DURATION):
        year = start + t
        # Use real return if available, else nominal
        r = real_return.get(year, np.nan)
        if pd.isna(r):
            r = nominal_return.get(year, np.nan)

        # Grow existing capital by real return, then add new contribution
        capital = capital * r + contributions[t]

    results[start] = capital / cumulated_contributions
    capitals[start] = capital

# ── Helper: build brick histogram ────────────────────────────────────────────
def brick_histogram(ax, data_series, bin_width, xlabel, title, median_label,
                    mean_label, fmt_val, xlim_left=None):
    vals = data_series.values
    bins = np.arange(
        np.floor(vals.min() / bin_width) * bin_width,
        np.ceil(vals.max() / bin_width) * bin_width + bin_width + 0.001,
        bin_width)

    bi_indices = np.digitize(vals, bins) - 1
    bi_contents = defaultdict(list)
    for year, bi in zip(data_series.index, bi_indices):
        bi_contents[bi].append(year)

    max_stack = max(len(v) for v in bi_contents.values())
    brick_h = 0.9

    for bi, years in bi_contents.items():
        x_left = bins[bi]
        for row, year in enumerate(sorted(years)):
            rect = plt.Rectangle((x_left, row), bin_width, brick_h,
                                  facecolor='steelblue', edgecolor='white',
                                  linewidth=1.5)
            ax.add_patch(rect)
            ax.text(x_left + bin_width / 2, row + brick_h / 2, str(year),
                    ha='center', va='center', fontsize=7, color='white',
                    fontweight='bold')

    med = np.median(vals)
    mn = np.mean(vals)
    ax.axvline(x=med, color='red', linestyle='--', linewidth=1.5,
               label=f"{median_label}{fmt_val(med)}")
    ax.axvline(x=mn, color='orange', linestyle='--', linewidth=1.5,
               label=f"{mean_label}{fmt_val(mn)}")

    left = xlim_left if xlim_left is not None else bins[0]
    ax.set_xlim(left, bins[-1])
    ax.set_ylim(0, max_stack + 0.5)
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.legend(fontsize=11)
    ax.grid(True, axis='y', alpha=0.3)

    return vals, max_stack

# ── Subtitle helper ──────────────────────────────────────────────────────────
sub_en = (f"(French stock market, contributions growing at {GROWTH_RATE:.0%}/year real, "
          f"starting years {start_years[0]}\u2013{start_years[-1]}, "
          f"{len(start_years)} cohorts)")
sub_fr = (f"(March\u00e9 boursier fran\u00e7ais, cotisations croissant de {GROWTH_RATE:.0%}/an en r\u00e9el, "
          f"ann\u00e9es de d\u00e9but {start_years[0]}\u2013{start_years[-1]}, "
          f"{len(start_years)} cohortes)")

# ── Plot 1: Time series (EN) ────────────────────────────────────────────────
series = pd.Series(results).sort_index()

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(series.index, series.values, 'b-o', markersize=3, linewidth=1.5,
        label="Capital / Cumulated investment")
ax.axhline(y=1, color='gray', linestyle='--', linewidth=0.8, label="Break-even")
ax.set_xlabel("Starting year", fontsize=12)
ax.set_ylabel("Total capital / Cumulated investment (real)", fontsize=12)
ax.set_title(f"French stock market: {DURATION}-year pension fund simulation\n"
             f"(contributions growing at {GROWTH_RATE:.0%}/year in real terms, "
             f"real total return with dividends reinvested)", fontsize=13)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)
ax.set_xlim(series.index[0] - 1, series.index[-1] + 1)
plt.tight_layout()
plt.savefig(OUT_DIR / "pension_fund_simulation.png", dpi=150)
plt.savefig(OUT_DIR / "pension_fund_simulation.svg")
print(f"\nPlot saved")

# ── Plot 2: Multiple histogram (EN) ─────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(12, 8))
values, max_stack = brick_histogram(
    ax2, series, bin_width=1,
    xlabel="Capital / Cumulated investment (real)",
    title=f"Distribution of {DURATION}-year pension fund multiples\n{sub_en}",
    median_label="Median: ", mean_label="Mean: ",
    fmt_val=lambda v: f"{v:.1f}x")
ax2.set_ylabel("Number of cohorts", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "pension_fund_histogram.png", dpi=150)
plt.savefig(OUT_DIR / "pension_fund_histogram.svg")
print(f"Histogram saved")

print(f"\nMultiple statistics ({len(values)} cohorts):")
print(f"  Min:    {values.min():.2f}x")
print(f"  Q1:     {np.percentile(values, 25):.2f}x")
print(f"  Median: {np.median(values):.2f}x")
print(f"  Q3:     {np.percentile(values, 75):.2f}x")
print(f"  Max:    {values.max():.2f}x")
print(f"  Mean:   {np.mean(values):.2f}x")

# ── IRR computation ──────────────────────────────────────────────────────────
irr_results = {}
for start in start_years:
    capital = capitals[start]

    def npv(rate):
        pv = 0.0
        for t in range(DURATION):
            pv -= contributions[t] / (1 + rate) ** t
        pv += capital / (1 + rate) ** DURATION
        return pv

    try:
        irr = brentq(npv, -0.5, 5.0)
    except ValueError:
        irr = np.nan
    irr_results[start] = irr

irr_series = pd.Series(irr_results).sort_index()
irr_pct = irr_series * 100  # convert to percent

# ── Plot 3: IRR histogram (EN) ──────────────────────────────────────────────
fig3, ax3 = plt.subplots(figsize=(12, 8))
irr_vals, max_stack_irr = brick_histogram(
    ax3, irr_pct, bin_width=0.5,
    xlabel="Real internal rate of return (%)",
    title=f"Distribution of {DURATION}-year pension fund real IRR\n{sub_en}",
    median_label="Median: ", mean_label="Mean: ",
    fmt_val=lambda v: f"{v:.1f}%")
ax3.set_ylabel("Number of cohorts", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "pension_fund_irr_histogram.png", dpi=150)
plt.savefig(OUT_DIR / "pension_fund_irr_histogram.svg")
print(f"IRR histogram saved")

print(f"\nIRR statistics ({len(irr_vals)} cohorts):")
print(f"  Min:    {irr_vals.min():.2f}%")
print(f"  Q1:     {np.percentile(irr_vals, 25):.2f}%")
print(f"  Median: {np.median(irr_vals):.2f}%")
print(f"  Q3:     {np.percentile(irr_vals, 75):.2f}%")
print(f"  Max:    {irr_vals.max():.2f}%")
print(f"  Mean:   {np.mean(irr_vals):.2f}%")

# ── French versions ──────────────────────────────────────────────────────────

# French: time series
fig4, ax4 = plt.subplots(figsize=(12, 6))
ax4.plot(series.index, series.values, 'b-o', markersize=3, linewidth=1.5,
         label="Capital / Investissement cumul\u00e9")
ax4.axhline(y=1, color='gray', linestyle='--', linewidth=0.8,
            label="Seuil de rentabilit\u00e9")
ax4.set_xlabel("Ann\u00e9e de d\u00e9but", fontsize=12)
ax4.set_ylabel("Capital total / Investissement cumul\u00e9 (r\u00e9el)", fontsize=12)
ax4.set_title(f"March\u00e9 boursier fran\u00e7ais : simulation de fonds de pension sur {DURATION} ans\n"
              f"(cotisations croissant de {GROWTH_RATE:.0%}/an en r\u00e9el, "
              f"rendement total r\u00e9el avec dividendes r\u00e9investis)", fontsize=13)
ax4.legend(fontsize=11)
ax4.grid(True, alpha=0.3)
ax4.set_xlim(series.index[0] - 1, series.index[-1] + 1)
plt.tight_layout()
plt.savefig(OUT_DIR / "pension_fund_simulation_fr.png", dpi=150)
plt.savefig(OUT_DIR / "pension_fund_simulation_fr.svg")
print(f"\nFrench time series saved")

# French: multiple histogram
fig5, ax5 = plt.subplots(figsize=(12, 8))
brick_histogram(
    ax5, series, bin_width=1,
    xlabel="Capital / Investissement cumul\u00e9 (r\u00e9el)",
    title=f"Distribution des multiples d\u2019un fonds de pension sur {DURATION} ans\n{sub_fr}",
    median_label="M\u00e9diane : ", mean_label="Moyenne : ",
    fmt_val=lambda v: f"{v:.1f}x")
ax5.set_ylabel("Nombre de cohortes", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "pension_fund_histogram_fr.png", dpi=150)
plt.savefig(OUT_DIR / "pension_fund_histogram_fr.svg")
print(f"French multiple histogram saved")

# French: IRR histogram
fig6, ax6 = plt.subplots(figsize=(12, 8))
brick_histogram(
    ax6, irr_pct, bin_width=0.5,
    xlabel="Taux de rendement interne r\u00e9el (%)",
    title=f"Distribution du TRI r\u00e9el d\u2019un fonds de pension sur {DURATION} ans\n{sub_fr}",
    median_label="M\u00e9diane : ", mean_label="Moyenne : ",
    fmt_val=lambda v: f"{v:.1f} %")
ax6.set_ylabel("Nombre de cohortes", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "pension_fund_irr_histogram_fr.png", dpi=150)
plt.savefig(OUT_DIR / "pension_fund_irr_histogram_fr.svg")
print(f"French IRR histogram saved")
