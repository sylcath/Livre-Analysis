"""
Notional account pension simulation: contributions are compounded at the
real GDP growth rate (Maddison Project Database 2023).

This simulates a pay-as-you-go system where the notional return equals
GDP growth (the "Aaron-Samuelson" return of a PAYG system).

Contributions grow at 2% per year in real terms (starting at 100 EUR).
Post-WW2 analysis: starting years 1946 to latest with 40 years of data.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from collections import defaultdict
from scipy.optimize import brentq

MADDISON_FILE = Path("C:/Users/Windows/Dropbox/Livre/Analysis/Maddison/mpd2023_web.xlsx")
OUT_DIR = Path(__file__).parent

# ── Load Maddison GDP data for France ────────────────────────────────────────
maddison = pd.read_excel(MADDISON_FILE, sheet_name="Full data")
fra = maddison[maddison["countrycode"] == "FRA"][["year", "gdppc", "pop"]].copy()
fra = fra.dropna(subset=["gdppc", "pop"]).sort_values("year")
fra = fra.set_index("year")

# Compute total real GDP (GDP per capita × population, already in real terms)
fra["gdp"] = fra["gdppc"] * fra["pop"]

# Real GDP growth factor for each year
gdp_growth = fra["gdp"] / fra["gdp"].shift(1)
gdp_growth = gdp_growth.dropna()

print(f"GDP data range: {fra.index.min()}-{fra.index.max()}")
print(f"GDP growth rates available: {gdp_growth.index.min()}-{gdp_growth.index.max()}")

# Also compute GDP per capita growth for reference
gdppc_growth = fra["gdppc"] / fra["gdppc"].shift(1)
gdppc_growth = gdppc_growth.dropna()

avg_gdp_growth = (gdp_growth.loc[1946:2022].mean() - 1) * 100
avg_gdppc_growth = (gdppc_growth.loc[1946:2022].mean() - 1) * 100
print(f"Average real GDP growth 1946-2022: {avg_gdp_growth:.2f}%")
print(f"Average real GDP/cap growth 1946-2022: {avg_gdppc_growth:.2f}%")

# ── Simulation parameters ────────────────────────────────────────────────────
CONTRIBUTION_BASE = 100  # EUR first year (real euros)
GROWTH_RATE = 0.02       # 2% real growth per year
DURATION = 43            # years of contributions
START_FROM = 1946        # post-WW2

# Pre-compute contribution schedule (real euros)
contributions = [CONTRIBUTION_BASE * (1 + GROWTH_RATE) ** t for t in range(DURATION)]
cumulated_contributions = sum(contributions)

# Find valid starting years
start_years = []
for y in range(START_FROM, gdp_growth.index.max() - DURATION + 2):
    yrs = range(y, y + DURATION)
    if all(yr in gdp_growth.index for yr in yrs):
        start_years.append(y)

print(f"Valid starting years: {start_years[0]}-{start_years[-1]} "
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
        r = gdp_growth.loc[year]  # real GDP growth factor

        # Grow existing capital by real GDP growth, then add new contribution
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

# ── Subtitles ────────────────────────────────────────────────────────────────
sub_en = (f"(Notional account indexed on real GDP growth, "
          f"contributions growing at {GROWTH_RATE:.0%}/year real, "
          f"starting years {start_years[0]}\u2013{start_years[-1]}, "
          f"{len(start_years)} cohorts)")
sub_fr = (f"(Compte notionnel index\u00e9 sur la croissance r\u00e9elle du PIB, "
          f"cotisations croissant de {GROWTH_RATE:.0%}/an en r\u00e9el, "
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
ax.set_title(f"Notional account (GDP growth): {DURATION}-year pension simulation\n"
             f"(contributions growing at {GROWTH_RATE:.0%}/year in real terms, "
             f"compounded at real GDP growth)", fontsize=13)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)
ax.set_xlim(series.index[0] - 1, series.index[-1] + 1)
plt.tight_layout()
plt.savefig(OUT_DIR / "gdp_notional_simulation.png", dpi=150)
plt.savefig(OUT_DIR / "gdp_notional_simulation.svg")
print(f"\nPlot saved")

# ── Plot 2: Multiple histogram (EN) ─────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(12, 8))
values, max_stack = brick_histogram(
    ax2, series, bin_width=1,
    xlabel="Capital / Cumulated investment (real)",
    title=f"Distribution of {DURATION}-year notional account multiples\n{sub_en}",
    median_label="Median: ", mean_label="Mean: ",
    fmt_val=lambda v: f"{v:.1f}x")
ax2.set_ylabel("Number of cohorts", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "gdp_notional_histogram.png", dpi=150)
plt.savefig(OUT_DIR / "gdp_notional_histogram.svg")
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
irr_pct = irr_series * 100

# ── Plot 3: IRR histogram (EN) ──────────────────────────────────────────────
fig3, ax3 = plt.subplots(figsize=(12, 8))
irr_vals, max_stack_irr = brick_histogram(
    ax3, irr_pct, bin_width=0.5,
    xlabel="Real internal rate of return (%)",
    title=f"Distribution of {DURATION}-year notional account real IRR\n{sub_en}",
    median_label="Median: ", mean_label="Mean: ",
    fmt_val=lambda v: f"{v:.1f}%")
ax3.set_ylabel("Number of cohorts", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "gdp_notional_irr_histogram.png", dpi=150)
plt.savefig(OUT_DIR / "gdp_notional_irr_histogram.svg")
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
ax4.set_title(f"Compte notionnel (croissance du PIB) : simulation sur {DURATION} ans\n"
              f"(cotisations croissant de {GROWTH_RATE:.0%}/an en r\u00e9el, "
              f"capitalis\u00e9es \u00e0 la croissance r\u00e9elle du PIB)", fontsize=13)
ax4.legend(fontsize=11)
ax4.grid(True, alpha=0.3)
ax4.set_xlim(series.index[0] - 1, series.index[-1] + 1)
plt.tight_layout()
plt.savefig(OUT_DIR / "gdp_notional_simulation_fr.png", dpi=150)
plt.savefig(OUT_DIR / "gdp_notional_simulation_fr.svg")
print(f"\nFrench time series saved")

# French: multiple histogram
fig5, ax5 = plt.subplots(figsize=(12, 8))
brick_histogram(
    ax5, series, bin_width=1,
    xlabel="Capital / Investissement cumul\u00e9 (r\u00e9el)",
    title=f"Distribution des multiples d\u2019un compte notionnel sur {DURATION} ans\n{sub_fr}",
    median_label="M\u00e9diane : ", mean_label="Moyenne : ",
    fmt_val=lambda v: f"{v:.1f}x")
ax5.set_ylabel("Nombre de cohortes", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "gdp_notional_histogram_fr.png", dpi=150)
plt.savefig(OUT_DIR / "gdp_notional_histogram_fr.svg")
print(f"French multiple histogram saved")

# French: IRR histogram
fig6, ax6 = plt.subplots(figsize=(12, 8))
brick_histogram(
    ax6, irr_pct, bin_width=0.5,
    xlabel="Taux de rendement interne r\u00e9el (%)",
    title=f"Distribution du TRI r\u00e9el d\u2019un compte notionnel sur {DURATION} ans\n{sub_fr}",
    median_label="M\u00e9diane : ", mean_label="Moyenne : ",
    fmt_val=lambda v: f"{v:.1f} %")
ax6.set_ylabel("Nombre de cohortes", fontsize=12)
plt.tight_layout()
plt.savefig(OUT_DIR / "gdp_notional_irr_histogram_fr.png", dpi=150)
plt.savefig(OUT_DIR / "gdp_notional_irr_histogram_fr.svg")
print(f"French IRR histogram saved")
