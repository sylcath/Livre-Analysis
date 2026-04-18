"""
Decomposition of average salary evolution in France: Net, Gross, Cost to Employer.
Data from INSEE 2020 files.

Methodology:
  1. Reconstruct net salary series from EQTP01 (1996-2018) + EVO_CR growth rates (back to 1950)
  2. Build employee contribution rates by tranche from CS3 (non-cadre, incl. CSG/CRDS)
  3. Build employer contribution rates by tranche from CP2 (non-cadre)
  4. Solve for gross salary using two-tranche formula, with plafond from PLAFOND.xlsx
  5. Compute cost to employer
  6. Deflate to constant 2026 euros
"""

import zipfile
import re
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

DATA_DIR = "C:/Users/Windows/Dropbox/Livre/Analysis/INSEE 2020/"


# =====================================================================
# Helpers
# =====================================================================
def fix_strict_xlsx(path):
    replacements = {
        'http://purl.oclc.org/ooxml/spreadsheetml/main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'http://purl.oclc.org/ooxml/officeDocument/relationships': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'http://purl.oclc.org/ooxml/drawingml/main': 'http://schemas.openxmlformats.org/drawingml/2006/main',
        'http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet',
        'http://purl.oclc.org/ooxml/officeDocument/relationships/sharedStrings': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings',
        'http://purl.oclc.org/ooxml/officeDocument/relationships/styles': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles',
        'http://purl.oclc.org/ooxml/officeDocument/relationships/theme': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme',
    }
    tmp = path + '.tmp.xlsx'
    with zipfile.ZipFile(path, 'r') as zin, zipfile.ZipFile(tmp, 'w') as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith('.xml') or item.filename.endswith('.rels'):
                text = data.decode('utf-8')
                text = re.sub(r' conformance="strict"', '', text)
                for old, new in replacements.items():
                    text = text.replace(old, new)
                data = text.encode('utf-8')
            zout.writestr(item, data)
    return tmp


def read_xlsx(path, **kwargs):
    tmp = fix_strict_xlsx(path)
    try:
        df = pd.read_excel(tmp, header=None, **kwargs)
    finally:
        os.remove(tmp)
    return df


def safe_float(val):
    """Convert a cell value to float, treating 'so', 'nd', NaN as 0."""
    if isinstance(val, (int, float)) and not np.isnan(val):
        return float(val)
    return 0.0


# =====================================================================
# 1. Reconstruct net annual salary series (1950-2018)
# =====================================================================
print("=" * 70)
print("STEP 1: Net salary reconstruction")
print("=" * 70)

# 1a. Read EQTP01: actual average net annual salary (1996-2018)
df_eqtp = read_xlsx(DATA_DIR + "EQTP01.xlsx")
eqtp_net = {}
for _, row in df_eqtp.iterrows():
    try:
        y = int(row.iloc[0])
        s = float(row.iloc[1])
        if 1950 <= y <= 2030:
            eqtp_net[y] = s
    except (ValueError, TypeError):
        continue
print(f"  EQTP01: actual net salary for {min(eqtp_net)}-{max(eqtp_net)}")

# 1a-bis. Replace EQTP01 (base 2018) with the INSEE BDM revised series
# (série 010752333, last updated 2025-12-18). This series is consistent
# across all years 1996-2023 and avoids the base-revision break.
bdm_revised = {
    1996: 18459, 1997: 18795, 1998: 19088, 1999: 19484, 2000: 19893,
    2001: 20356, 2002: 20786, 2003: 21224, 2004: 21704, 2005: 22323,
    2006: 22733, 2007: 23454, 2008: 24176, 2009: 24497, 2010: 24992,
    2011: 25611, 2012: 26000, 2013: 26166, 2014: 26435, 2015: 26743,
    2016: 26901, 2017: 27426, 2018: 28024, 2019: 28631, 2020: 29649,
}
eqtp_net.update(bdm_revised)
print(f"  Updated with INSEE BDM revised series (010752333): 1996-2020")

# 1b. Read EVO_CR: year-over-year % growth of average net salary (col 9)
df_evo = read_xlsx(DATA_DIR + "EVO_CR.xlsx")
evo_growth = {}
for _, row in df_evo.iterrows():
    try:
        y = int(row.iloc[0])
        g = float(row.iloc[9])
        if 1950 <= y <= 2030:
            evo_growth[y] = g
    except (ValueError, TypeError):
        continue
print(f"  EVO_CR: growth rates for {min(evo_growth)}-{max(evo_growth)}")

# 1c. Back-extrapolate from 1996 using growth rates
net_annual = dict(eqtp_net)
for y in range(min(eqtp_net), 1950, -1):
    if y in evo_growth and y in net_annual:
        net_annual[y - 1] = net_annual[y] / (1 + evo_growth[y] / 100.0)

print(f"  Net salary series: {min(net_annual)}-{max(net_annual)}")


# =====================================================================
# 2. Read contribution rates by tranche
# =====================================================================
print()
print("=" * 70)
print("STEP 2: Contribution rates by tranche")
print("=" * 70)

# --- CS3: Employee rates by tranche (incl. CSG+CRDS), % of gross ---
# Col 1: <= 1 plafond (non-cadres)
# Col 3: 1-3 plafonds (non-cadres)
df_cs3 = read_xlsx(DATA_DIR + "CS3.xlsx")
emp_rate_t1 = {}  # tranche 1: <= 1 plafond
emp_rate_t2 = {}  # tranche 2: 1-3 plafonds

for _, row in df_cs3.iterrows():
    try:
        y = int(row.iloc[0])
    except (ValueError, TypeError):
        continue
    if 1950 <= y <= 2030:
        emp_rate_t1[y] = safe_float(row.iloc[1])
        emp_rate_t2[y] = safe_float(row.iloc[3])

print("  CS3 (employee, non-cadre, incl. CSG+CRDS):")
for y in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018]:
    if y in emp_rate_t1:
        print(f"    {y}: T1(<= plafond)={emp_rate_t1[y]:.2f}%  T2(1-3 plaf)={emp_rate_t2[y]:.2f}%")

# --- CP2: Employer rates by tranche, % of gross ---
# Col 1: <= 1 plafond (non-cadres)
# Col 3: 1-3 plafonds (non-cadres)
df_cp2 = read_xlsx(DATA_DIR + "CP2.xlsx")
pat_rate_t1 = {}
pat_rate_t2 = {}

for _, row in df_cp2.iterrows():
    try:
        y = int(row.iloc[0])
    except (ValueError, TypeError):
        continue
    if 1950 <= y <= 2030:
        pat_rate_t1[y] = safe_float(row.iloc[1])
        pat_rate_t2[y] = safe_float(row.iloc[3])

print()
print("  CP2 (employer, non-cadre):")
for y in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018]:
    if y in pat_rate_t1:
        print(f"    {y}: T1(<= plafond)={pat_rate_t1[y]:.2f}%  T2(1-3 plaf)={pat_rate_t2[y]:.2f}%")

# --- PLAFOND: monthly ceiling ---
df_plaf = read_xlsx(DATA_DIR + "PLAFOND.xlsx")
plafond_brut_monthly = {}
for _, row in df_plaf.iterrows():
    try:
        y = int(row.iloc[0])
        p = float(row.iloc[1])
        if 1950 <= y <= 2030:
            plafond_brut_monthly[y] = p
    except (ValueError, TypeError):
        continue

# Annual plafond = monthly × 12
plafond_brut_annual = {y: p * 12 for y, p in plafond_brut_monthly.items()}


# =====================================================================
# 3. Solve for gross salary (two-tranche calculation)
# =====================================================================
print()
print("=" * 70)
print("STEP 3: Solve for gross salary (two-tranche)")
print("=" * 70)

# Given: net, plafond P, employee rate tranche1 (t1), tranche2 (t2)
#
# Case A: gross <= P
#   net = gross × (1 - t1/100)
#   gross = net / (1 - t1/100)
#   → verify gross <= P
#
# Case B: gross > P
#   net = gross - P × t1/100 - (gross - P) × t2/100
#   net = gross × (1 - t2/100) - P × (t1 - t2) / 100
#   gross = (net + P × (t1 - t2) / 100) / (1 - t2/100)

all_years = sorted(
    set(net_annual.keys()) & set(emp_rate_t1.keys()) & set(pat_rate_t1.keys())
    & set(plafond_brut_annual.keys())
)

gross_annual = {}
tranche_used = {}

print(f"\n  {'Year':>4}  {'Net/mo':>10}  {'Gross/mo':>10}  {'Plafond':>10}  {'Ratio':>7}  {'Tranche':>8}")
print(f"  {'----':>4}  {'------':>10}  {'--------':>10}  {'-------':>10}  {'-----':>7}  {'-------':>8}")

for y in all_years:
    net = net_annual[y]
    P = plafond_brut_annual[y]
    t1 = emp_rate_t1[y] / 100.0
    t2 = emp_rate_t2[y] / 100.0

    # Try Case A first: gross <= P
    gross_a = net / (1 - t1)

    if gross_a <= P:
        gross_annual[y] = gross_a
        tranche_used[y] = 1
    else:
        # Case B: gross > P
        gross_b = (net + P * (t1 - t2)) / (1 - t2)
        gross_annual[y] = gross_b
        tranche_used[y] = 2

    g = gross_annual[y]
    gm = g / 12
    pm = P / 12
    ratio = gm / pm

    if y % 10 == 0 or y in [min(all_years), max(all_years)]:
        tr_label = "1 only" if tranche_used[y] == 1 else "1 + 2"
        print(f"  {y:>4}  {net/12:>10,.0f}€  {gm:>10,.0f}€  {pm:>10,.0f}€  {ratio:>6.1%}  {tr_label:>8}")

# Verify: recompute net from gross and check it matches
max_err = 0
for y in all_years:
    g = gross_annual[y]
    P = plafond_brut_annual[y]
    t1 = emp_rate_t1[y] / 100.0
    t2 = emp_rate_t2[y] / 100.0
    if g <= P:
        net_check = g * (1 - t1)
    else:
        net_check = g - P * t1 - (g - P) * t2
    err = abs(net_check - net_annual[y])
    max_err = max(max_err, err)
print(f"\n  Verification: max |net_recomputed - net_original| = {max_err:.6f}€")


# =====================================================================
# 4. Compute cost to employer (two-tranche)
# =====================================================================
print()
print("=" * 70)
print("STEP 4: Cost to employer (two-tranche)")
print("=" * 70)

# cost = gross + P × tp1/100 + max(0, gross - P) × tp2/100

years = []
net_vals = []
gross_vals = []
cost_vals = []

for y in all_years:
    g = gross_annual[y]
    P = plafond_brut_annual[y]
    tp1 = pat_rate_t1[y] / 100.0
    tp2 = pat_rate_t2[y] / 100.0

    if g <= P:
        cost = g * (1 + tp1)
    else:
        cost = g + P * tp1 + (g - P) * tp2

    years.append(y)
    net_vals.append(net_annual[y])
    gross_vals.append(g)
    cost_vals.append(cost)

years = np.array(years)
net_vals = np.array(net_vals)
gross_vals = np.array(gross_vals)
cost_vals = np.array(cost_vals)

# Effective blended rates
for y_show in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018]:
    idx = np.where(years == y_show)[0]
    if len(idx) > 0:
        i = idx[0]
        eff_emp = (1 - net_vals[i] / gross_vals[i]) * 100
        eff_pat = (cost_vals[i] / gross_vals[i] - 1) * 100
        tr = "2-tranche" if tranche_used[y_show] == 2 else "1-tranche"
        print(f"  {y_show}: eff. employee={eff_emp:.1f}%  eff. employer={eff_pat:.1f}%  ({tr})")


# =====================================================================
# 5. Deflate to constant 2026 euros
# =====================================================================
print()
print("=" * 70)
print("STEP 5: Deflation to constant 2026 euros")
print("=" * 70)

df_infl = read_xlsx(DATA_DIR + "inflation.xlsx")
cpi_index = {}
for _, row in df_infl.iterrows():
    try:
        y = int(row.iloc[0])
        idx = float(row.iloc[1])
        if 1950 <= y <= 2030:
            cpi_index[y] = idx
    except (ValueError, TypeError):
        continue

# Extend CPI from 2020 to 2026
post_2020_inflation = {2021: 1.6, 2022: 5.2, 2023: 4.9, 2024: 2.0, 2025: 0.9, 2026: 1.5}
for y in range(2021, 2027):
    cpi_index[y] = cpi_index[y - 1] * (1 + post_2020_inflation[y] / 100.0)

# Add 1950 (inflation 1951 = 16.7% from EVO_CR)
if 1950 not in cpi_index and 1951 in cpi_index:
    cpi_index[1950] = cpi_index[1951] / (1 + 16.7 / 100.0)

CPI_2026 = cpi_index[2026]
print(f"  CPI index 2026: {CPI_2026:.1f} (base 100 in 1951)")

deflator = np.array([CPI_2026 / cpi_index[y] for y in years])

net_monthly = (net_vals / 12) * deflator
gross_monthly = (gross_vals / 12) * deflator
cost_monthly = (cost_vals / 12) * deflator


# =====================================================================
# 6. Plot
# =====================================================================
print()
print("=" * 70)
print("STEP 6: Plotting")
print("=" * 70)

fig, ax = plt.subplots(figsize=(12, 7))

ax.plot(years, cost_monthly, color='#c0392b', linewidth=2, label='Coût employeur (super-brut)')
ax.plot(years, gross_monthly, color='#2980b9', linewidth=2, label='Salaire brut')
ax.plot(years, net_monthly, color='#27ae60', linewidth=2, label='Salaire net')

ax.fill_between(years, gross_monthly, cost_monthly, alpha=0.15, color='#c0392b',
                label='Cotisations patronales')
ax.fill_between(years, net_monthly, gross_monthly, alpha=0.15, color='#2980b9',
                label='Cotisations salariales')

ax.set_xlabel('Année', fontsize=12)
ax.set_ylabel('Euros constants 2026 (mensuel)', fontsize=12)
ax.set_title('Décomposition du salaire moyen mensuel en France\n(temps complet, euros constants 2026)',
             fontsize=14, fontweight='bold')

ax.legend(loc='upper left', fontsize=10, framealpha=0.9)
ax.grid(True, alpha=0.3)
ax.set_xlim(years[0], years[-1])
ax.set_ylim(0)

ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f} €'))

plt.tight_layout()
plt.savefig('salary_decomposition.png', dpi=150, bbox_inches='tight')
plt.savefig('salary_decomposition.svg', bbox_inches='tight')
print("  Saved salary_decomposition.png and .svg")

# Summary table
print(f"\n  {'Year':>4}  {'Net':>8}  {'Gross':>8}  {'Cost':>8}  {'eff t_s':>8}  {'eff t_p':>8}")
print(f"  {'----':>4}  {'---':>8}  {'-----':>8}  {'----':>8}  {'-------':>8}  {'-------':>8}")
for y in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018]:
    idx_list = np.where(years == y)[0]
    if len(idx_list) > 0:
        i = idx_list[0]
        eff_emp = (1 - net_vals[i] / gross_vals[i]) * 100
        eff_pat = (cost_vals[i] / gross_vals[i] - 1) * 100
        print(f"  {y:>4}  {net_monthly[i]:>7,.0f}€  {gross_monthly[i]:>7,.0f}€  {cost_monthly[i]:>7,.0f}€"
              f"  {eff_emp:>7.1f}%  {eff_pat:>7.1f}%")


# =====================================================================
# 7. FIGURE 2: Contribution breakdown by category
# =====================================================================
print()
print("=" * 70)
print("STEP 7: Contribution breakdown by category (Figure 2)")
print("=" * 70)

# Read CS1 and CP1 for individual component rates
df_cs1 = read_xlsx(DATA_DIR + "CS1.xlsx")
df_cp1 = read_xlsx(DATA_DIR + "CP1.xlsx")


def two_tranche_amount(gross, plafond, rate_t1, rate_t2):
    """Compute EUR contribution amount with two-tranche logic."""
    under = min(gross, plafond)
    over = max(0.0, gross - plafond)
    return under * rate_t1 / 100.0 + over * rate_t2 / 100.0


# Build per-year, per-category contribution amounts (annual EUR, current)
cat_retirement = {}
cat_healthcare = {}
cat_csg = {}
cat_other = {}

for y in all_years:
    G = gross_annual[y]
    P = plafond_brut_annual[y]

    # --- Find the CS1 and CP1 rows for this year ---
    cs1_row = None
    for _, row in df_cs1.iterrows():
        try:
            if int(row.iloc[0]) == y:
                cs1_row = row
                break
        except (ValueError, TypeError):
            continue

    cp1_row = None
    for _, row in df_cp1.iterrows():
        try:
            if int(row.iloc[0]) == y:
                cp1_row = row
                break
        except (ValueError, TypeError):
            continue

    if cs1_row is None or cp1_row is None:
        continue

    # === EMPLOYEE CONTRIBUTIONS (CS1) ===
    # Healthcare: col 1 (Maladie ≤1P), col 2 (Maladie >1P)
    emp_health = two_tranche_amount(G, P, safe_float(cs1_row.iloc[1]), safe_float(cs1_row.iloc[2]))

    # Retirement: SS Vieillesse + Veuvage + Retraite comp + AGFF (or fusion post-2019)
    if y < 2019:
        emp_ret = (
            two_tranche_amount(G, P, safe_float(cs1_row.iloc[3]), safe_float(cs1_row.iloc[4]))    # Vieillesse
            + two_tranche_amount(G, P, safe_float(cs1_row.iloc[5]), safe_float(cs1_row.iloc[6]))  # Veuvage
            + two_tranche_amount(G, P, safe_float(cs1_row.iloc[9]), safe_float(cs1_row.iloc[10])) # Ret comp (≤1P / 1-3P non-cadre)
            + two_tranche_amount(G, P, safe_float(cs1_row.iloc[13]), safe_float(cs1_row.iloc[14]))# AGFF (≤1P / 1-3P non-cadre)
        )
    else:
        emp_ret = (
            two_tranche_amount(G, P, safe_float(cs1_row.iloc[3]), safe_float(cs1_row.iloc[4]))    # Vieillesse
            + two_tranche_amount(G, P, safe_float(cs1_row.iloc[5]), safe_float(cs1_row.iloc[6]))  # Veuvage
            + two_tranche_amount(G, P, safe_float(cs1_row.iloc[18]), safe_float(cs1_row.iloc[19]))# Fusion Agirc-Arrco (≤1P / 1-8P)
            + two_tranche_amount(G, P, safe_float(cs1_row.iloc[20]), safe_float(cs1_row.iloc[21]))# Fusion CEG (≤1P / 1-8P)
        )

    # CSG+CRDS: col 27 (≤4P — effectively full salary for our range)
    emp_csg = G * safe_float(cs1_row.iloc[27]) / 100.0

    # Other: Chômage (≤1P and 1-4P)
    emp_other = two_tranche_amount(G, P, safe_float(cs1_row.iloc[23]), safe_float(cs1_row.iloc[24]))

    # === EMPLOYER CONTRIBUTIONS (CP1) ===
    # Note: CP1 reports "Total SS hors taux accidents du travail". The AT rate is
    # not listed as a separate column. We compute it as a residual:
    #   AT = CP2_total - sum(CP1 components)
    # and add it to the Healthcare category.

    # Healthcare: col 1 (Maladie ≤1P), col 2 (Maladie >1P), col 9 (CSA, totalité)
    pat_health = (
        two_tranche_amount(G, P, safe_float(cp1_row.iloc[1]), safe_float(cp1_row.iloc[2]))
        + G * safe_float(cp1_row.iloc[9]) / 100.0  # CSA on full salary
    )

    # Retirement: SS Vieillesse + Ret comp + AGFF (or fusion post-2019)
    if y < 2019:
        pat_ret = (
            two_tranche_amount(G, P, safe_float(cp1_row.iloc[3]), safe_float(cp1_row.iloc[4]))    # Vieillesse
            + two_tranche_amount(G, P, safe_float(cp1_row.iloc[10]), safe_float(cp1_row.iloc[11]))# Ret comp (≤1P / 1-3P non-cadre)
            + two_tranche_amount(G, P, safe_float(cp1_row.iloc[14]), safe_float(cp1_row.iloc[15]))# AGFF (≤1P / 1-3P non-cadre)
        )
    else:
        pat_ret = (
            two_tranche_amount(G, P, safe_float(cp1_row.iloc[3]), safe_float(cp1_row.iloc[4]))    # Vieillesse
            + two_tranche_amount(G, P, safe_float(cp1_row.iloc[19]), safe_float(cp1_row.iloc[20]))# Fusion (≤1P / 1-8P)
            + two_tranche_amount(G, P, safe_float(cp1_row.iloc[21]), safe_float(cp1_row.iloc[22]))# Fusion CEG (≤1P / 1-8P)
        )

    # CSG: employer pays 0
    pat_csg = 0.0

    # Other: Alloc familiales + Chômage + Fonds gar. + Construction + FNAL + Apprentissage + Formation + Pénibilité + Dialogue social
    pat_other = (
        two_tranche_amount(G, P, safe_float(cp1_row.iloc[5]), safe_float(cp1_row.iloc[6]))   # Alloc familiales
        + two_tranche_amount(G, P, safe_float(cp1_row.iloc[24]), safe_float(cp1_row.iloc[25]))  # Chômage (≤1P / 1-4P)
        + G * safe_float(cp1_row.iloc[26]) / 100.0                                            # Fonds de garantie (≤4P ≈ full)
        + G * safe_float(cp1_row.iloc[27]) / 100.0                                            # Construction (totalité)
        + two_tranche_amount(G, P, safe_float(cp1_row.iloc[28]), safe_float(cp1_row.iloc[29]))  # FNAL
        + G * safe_float(cp1_row.iloc[30]) / 100.0                                            # Apprentissage (totalité)
        + G * safe_float(cp1_row.iloc[31]) / 100.0                                            # Formation (totalité)
        + G * safe_float(cp1_row.iloc[35]) / 100.0                                            # Pénibilité (totalité)
        + G * safe_float(cp1_row.iloc[36]) / 100.0                                            # Dialogue social (totalité)
    )

    # Compute AT (accidents du travail) as residual: total from CP2 minus sum of CP1 components
    pat_sum_excl_at = pat_health + pat_ret + pat_csg + pat_other
    pat_total_from_cp2 = two_tranche_amount(G, P, pat_rate_t1[y], pat_rate_t2[y])
    pat_at = pat_total_from_cp2 - pat_sum_excl_at
    # Add AT to Healthcare (it's accident/injury insurance, part of SS Maladie)
    pat_health += pat_at

    # Sum employee + employer per category
    cat_retirement[y] = emp_ret + pat_ret
    cat_healthcare[y] = emp_health + pat_health
    cat_csg[y] = emp_csg + pat_csg
    cat_other[y] = emp_other + pat_other

# ---------------------------------------------------------------------
# 7b. Pre-1967 correction: split the undifferentiated "Maladie" rate
#     into Healthcare and Retirement using DREES spending ratios.
#
#     Before 1967, CS1/CP1 report a single "Maladie" rate that funded
#     both health and old-age pensions. We use the DREES Comptes de la
#     Protection Sociale (1959-2018) spending breakdown by risk to
#     compute the share of Santé vs Vieillesse-survie, and reallocate
#     accordingly. For 1950-1958, we extrapolate from the 1959 ratio.
# ---------------------------------------------------------------------
print("\n  Pre-1967 correction using DREES spending ratios:")

# Read DREES CPS data
df_drees = pd.read_excel('drees_cps_2020.xlsx', sheet_name='prestations_1959_2018', header=None)

# Extract Santé and Vieillesse-survie spending series
drees_sante = {}
drees_vieil = {}
for col_idx in range(1, df_drees.shape[1]):
    year_str = str(df_drees.iloc[0, col_idx]).replace('R', '').replace('D', '').replace('SD', '')
    try:
        yr = int(year_str)
    except ValueError:
        continue
    # Row 2 = SANTÉ, Row 87 = VIEILLESSE-SURVIE (identified earlier)
    sante_row = None
    vieil_row = None
    for r in range(df_drees.shape[0]):
        label = str(df_drees.iloc[r, 0]).strip().upper()
        if label in ['SANTÉ', 'SANT\xc9'] and sante_row is None:
            sante_row = r
        if label == 'VIEILLESSE-SURVIE' and vieil_row is None:
            vieil_row = r
    if sante_row is not None and vieil_row is not None:
        s = safe_float(df_drees.iloc[sante_row, col_idx])
        v = safe_float(df_drees.iloc[vieil_row, col_idx])
        if s + v > 0:
            drees_sante[yr] = s
            drees_vieil[yr] = v

# Compute vieillesse share = vieillesse / (santé + vieillesse) for each year
vieil_share = {}
for yr in sorted(drees_sante.keys()):
    s = drees_sante[yr]
    v = drees_vieil[yr]
    vieil_share[yr] = v / (s + v)

# For 1950-1958: extrapolate from 1959 ratio
ratio_1959 = vieil_share[1959]
for yr in range(1950, 1959):
    vieil_share[yr] = ratio_1959

print(f"    1959 ratio: Vieillesse/(Santé+Vieillesse) = {ratio_1959:.1%}")
for yr in [1950, 1955, 1960, 1965]:
    if yr in vieil_share:
        print(f"    {yr}: vieillesse share = {vieil_share[yr]:.1%}")

# Apply correction: for years before 1967, the "Maladie" columns in CS1/CP1
# contain both health and retirement. Retirement shows as 0 in those years.
# We need to transfer a fraction of cat_healthcare to cat_retirement.
for y in all_years:
    if y <= 1967 and y in vieil_share:
        # Include 1967: the Jeanneney reform took effect Oct 1, 1967,
        # so the undifferentiated system applied for 9 out of 12 months.
        # Before 1967: all SS employee contributions are in "Maladie" (= healthcare)
        # and retirement shows 0. The total SS contribution funds both risks.
        # Split the SS portion (excluding non-SS items like CSG, chômage, ret comp)
        # using the spending ratio.
        #
        # What's currently misclassified:
        #   - emp_health includes the full employee SS "Maladie" rate (should be split)
        #   - pat_health includes the full employer SS "Maladie" rate + AT (should be split)
        #   - emp_ret and pat_ret are 0 for SS vieillesse (correctly 0 in data, but should receive a share)
        #
        # The amounts to reallocate = cat_healthcare (which is all SS health-related)
        # We keep cat_other unchanged (famille, chômage, etc.)
        total_health_plus_ret = cat_healthcare[y] + cat_retirement[y]
        share_v = vieil_share[y]
        cat_retirement[y] = total_health_plus_ret * share_v
        cat_healthcare[y] = total_health_plus_ret * (1 - share_v)

print("\n  After correction:")
for yr in [1950, 1955, 1960, 1965, 1967, 1970]:
    if yr in cat_retirement:
        total = cat_retirement[yr] + cat_healthcare[yr] + cat_csg[yr] + cat_other[yr]
        print(f"    {yr}: Ret={cat_retirement[yr]:,.0f}  Health={cat_healthcare[yr]:,.0f}  "
              f"CSG={cat_csg[yr]:,.0f}  Other={cat_other[yr]:,.0f}  Total={total:,.0f}")

# Verify: sum of categories = cost - net
print("\n  Verification: sum of categories vs total wedge (cost - net)")
max_cat_err = 0
for y in all_years:
    total_cat = cat_retirement[y] + cat_healthcare[y] + cat_csg[y] + cat_other[y]
    total_wedge = cost_vals[list(years).index(y)] - net_annual[y]
    err = abs(total_cat - total_wedge)
    max_cat_err = max(max_cat_err, err)
    if y % 10 == 0:
        print(f"    {y}: categories={total_cat:,.0f}€  wedge={total_wedge:,.0f}€  diff={err:.2f}€")
print(f"  Max error: {max_cat_err:.2f}€")

# Convert to monthly constant 2026 euros
ret_monthly = np.array([cat_retirement[y] / 12 * CPI_2026 / cpi_index[y] for y in years])
health_monthly = np.array([cat_healthcare[y] / 12 * CPI_2026 / cpi_index[y] for y in years])
csg_monthly = np.array([cat_csg[y] / 12 * CPI_2026 / cpi_index[y] for y in years])
other_monthly = np.array([cat_other[y] / 12 * CPI_2026 / cpi_index[y] for y in years])

# Plot Figure 2: stacked area
fig2, ax2 = plt.subplots(figsize=(12, 7))

# Stack from net upward
layer1 = net_monthly + ret_monthly
layer2 = layer1 + health_monthly
layer3 = layer2 + csg_monthly
layer4 = layer3 + other_monthly  # should equal cost_monthly

ax2.fill_between(years, net_monthly, layer1, alpha=0.7, color='#2c3e50', label='Retraite')
ax2.fill_between(years, layer1, layer2, alpha=0.7, color='#c0392b', label='Maladie')
ax2.fill_between(years, layer2, layer3, alpha=0.7, color='#f39c12', label='CSG + CRDS')
ax2.fill_between(years, layer3, layer4, alpha=0.7, color='#7f8c8d', label='Autre')

ax2.plot(years, net_monthly, color='#27ae60', linewidth=2, label='Salaire net')
ax2.plot(years, cost_monthly, color='#c0392b', linewidth=1.5, linestyle='--', label='Coût employeur')

ax2.set_xlabel('Année', fontsize=12)
ax2.set_ylabel('Euros constants 2026 (mensuel)', fontsize=12)
ax2.set_title('Décomposition des cotisations sociales par catégorie\n(salaire moyen, temps complet, euros constants 2026)',
              fontsize=14, fontweight='bold')

ax2.legend(loc='upper left', fontsize=10, framealpha=0.9)
ax2.grid(True, alpha=0.3)
ax2.set_xlim(years[0], years[-1])
ax2.set_ylim(0)

ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f} €'))

plt.tight_layout()
plt.savefig('contribution_breakdown.png', dpi=150, bbox_inches='tight')
plt.savefig('contribution_breakdown.svg', bbox_inches='tight')
print("\n  Saved contribution_breakdown.png and .svg")

# Category summary
print(f"\n  {'Year':>4}  {'Retraite':>10}  {'Maladie':>10}  {'CSG':>10}  {'Autre':>10}  {'Total':>10}")
print(f"  {'----':>4}  {'--------':>10}  {'-------':>10}  {'---':>10}  {'-----':>10}  {'-----':>10}")
for y_show in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018]:
    i = list(years).index(y_show)
    print(f"  {y_show:>4}  {ret_monthly[i]:>9,.0f}€  {health_monthly[i]:>9,.0f}€"
          f"  {csg_monthly[i]:>9,.0f}€  {other_monthly[i]:>9,.0f}€"
          f"  {ret_monthly[i]+health_monthly[i]+csg_monthly[i]+other_monthly[i]:>9,.0f}€")


# =====================================================================
# 8. FIGURE 3: Net, Net + Retirement, Cost to employer
# =====================================================================
print()
print("=" * 70)
print("STEP 8: Net / Net+Retraite / Coût employeur (Figure 3)")
print("=" * 70)

net_plus_ret = net_monthly + ret_monthly

fig3, ax3 = plt.subplots(figsize=(12, 7))

ax3.plot(years, cost_monthly, color='#c0392b', linewidth=2, label='Coût employeur')
ax3.plot(years, net_plus_ret, color='#2c3e50', linewidth=2, label='Salaire net + cotisations retraite')
ax3.plot(years, net_monthly, color='#27ae60', linewidth=2, label='Salaire net')

ax3.fill_between(years, net_plus_ret, cost_monthly, alpha=0.12, color='#c0392b',
                 label='Cotisations hors retraite')
ax3.fill_between(years, net_monthly, net_plus_ret, alpha=0.25, color='#2c3e50',
                 label='Cotisations retraite')

ax3.set_xlabel('Année', fontsize=12)
ax3.set_ylabel('Euros constants 2026 (mensuel)', fontsize=12)
ax3.set_title('Salaire net, salaire net + retraite et coût employeur\n(temps complet, euros constants 2026)',
              fontsize=14, fontweight='bold')

ax3.legend(loc='upper left', fontsize=10, framealpha=0.9)
ax3.grid(True, alpha=0.3)
ax3.set_xlim(years[0], years[-1])
ax3.set_ylim(0)

ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f} €'))

plt.tight_layout()
plt.savefig('net_retirement_cost.png', dpi=150, bbox_inches='tight')
plt.savefig('net_retirement_cost.svg', bbox_inches='tight')
print("  Saved net_retirement_cost.png and .svg")

# --- Figure 3b: Black & white version for print ---
import locale
try:
    locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'French_France.1252')
    except locale.Error:
        pass  # fallback: manual formatting


def fmt_euro_fr(x, _):
    """Format euros with French conventions: non-breaking space as thousands separator."""
    if x >= 1000:
        return f'{x:,.0f}\N{NO-BREAK SPACE}€'.replace(',', '\N{NARROW NO-BREAK SPACE}')
    return f'{x:,.0f}\N{NO-BREAK SPACE}€'


# Enable LaTeX rendering for Computer Modern font (matching Matlab TeX style)
plt.rcParams.update({
    'text.usetex': True,
    'text.latex.preamble': r'\usepackage{eurosym}',
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman'],
    'axes.labelsize': 27,
    'xtick.labelsize': 22.5,
    'ytick.labelsize': 22.5,
})


def fmt_euro_fr_tex(x, _):
    """Format euros with French conventions for LaTeX rendering."""
    if x >= 1000:
        # Use \, for thin space in LaTeX
        s = f'{x:,.0f}'.replace(',', r'\,')
    else:
        s = f'{x:.0f}'
    return s + r'\,\euro{}'


fig3b, ax3b = plt.subplots(figsize=(12, 10.5))

# --- Compute income tax before plotting (needs to be available for figure) ---
# Read IPP income tax schedule
if not os.path.exists('ipp_ir_fixed.xlsx'):
    fix_strict_xlsx('ipp_ir.xlsx')
    os.rename('ipp_ir.xlsx.tmp.xlsx', 'ipp_ir_fixed.xlsx')
_ipp_xls = pd.ExcelFile('ipp_ir_fixed.xlsx')
# Sheet name may be mangled due to encoding; find the IR schedule sheet
_ir_sheet = [s for s in _ipp_xls.sheet_names if 'IR' in s and 'IGR' not in s][0]
df_ir = pd.read_excel(_ipp_xls, sheet_name=_ir_sheet, header=None)

ir_schedules = {}
for r in range(3, 72):
    try:
        rev_year = int(df_ir.iloc[r, 1])
    except (ValueError, TypeError):
        continue
    thresholds_ir = []
    rates_ir = []
    for i in range(14):
        t = df_ir.iloc[r, 2 + i]
        m = df_ir.iloc[r, 16 + i]
        # Handle Excel date-parsing bug: some thresholds are misread as datetime
        import datetime
        if isinstance(t, (datetime.datetime, pd.Timestamp)):
            # Convert back: Excel serial date = days since 1899-12-30
            t = float((t - pd.Timestamp('1899-12-30')).days)
        if isinstance(t, (int, float)) and not np.isnan(t):
            thresholds_ir.append(float(t))
            rates_ir.append(float(m) if isinstance(m, (int, float)) and not np.isnan(m) else 0.0)
    if rev_year <= 1959:
        thresholds_ir = [t / 655.957 for t in thresholds_ir]
    elif rev_year <= 2000:
        thresholds_ir = [t / 6.55957 for t in thresholds_ir]
    ir_schedules[rev_year] = (thresholds_ir, rates_ir)

# Extend with known schedules for 2014-2020
ir_schedules[2014] = ([0, 6011, 11991, 26631, 71397, 151200], [0, 0.055, 0.14, 0.30, 0.41, 0.45])
for rev_y, bounds in [(2015, [0, 9690, 26764, 71754, 151956]),
                       (2016, [0, 9700, 26791, 71826, 152108]),
                       (2017, [0, 9710, 26818, 71898, 152260]),
                       (2018, [0, 9964, 27519, 73779, 156244])]:
    ir_schedules[rev_y] = (bounds, [0, 0.14, 0.30, 0.41, 0.45])
ir_schedules[2019] = ([0, 10064, 27794, 74517, 157806], [0, 0.11, 0.30, 0.41, 0.45])
ir_schedules[2020] = ([0, 10084, 25710, 73516, 158122], [0, 0.11, 0.30, 0.41, 0.45])

def compute_ir(taxable_income, thresholds, rates):
    tax = 0.0
    for i in range(len(thresholds)):
        upper = thresholds[i + 1] if i + 1 < len(thresholds) else float('inf')
        bracket_income = min(taxable_income, upper) - thresholds[i]
        if bracket_income <= 0:
            break
        tax += bracket_income * rates[i]
    return tax

# Read supplementary deduction (abattement de 20%, then 15%, 10%) from Déductions sheet
# The IPP file only lists years when the rate changed; we forward-fill for intermediate years.
_deduc_sheet = [s for s in _ipp_xls.sheet_names if 'duction' in s][0]
df_deduc = pd.read_excel(_ipp_xls, sheet_name=_deduc_sheet, header=None)
supp_deduction_raw = {}  # rev_year -> rate
for r in range(3, len(df_deduc)):
    try:
        rev_y = int(df_deduc.iloc[r, 1])
        tx = df_deduc.iloc[r, 2]
        if isinstance(tx, (int, float)) and not np.isnan(tx):
            supp_deduction_raw[rev_y] = tx
    except (ValueError, TypeError):
        continue

# Forward-fill: for each year from earliest to 2005, carry forward the last known rate
supp_deduction = {}
if supp_deduction_raw:
    earliest = min(supp_deduction_raw.keys())
    last_rate = supp_deduction_raw[earliest]
    for y in range(earliest, 2006):  # ends in 2005 (removed in 2006)
        if y in supp_deduction_raw:
            last_rate = supp_deduction_raw[y]
        supp_deduction[y] = last_rate

ir_annual = {}
for y in all_years:
    if y not in ir_schedules:
        continue
    # 10% deduction for professional expenses (all years)
    taxable = net_annual[y] * 0.90
    # Additional supplementary deduction (20% on salaries, until 2005)
    if y in supp_deduction:
        taxable *= (1 - supp_deduction[y])
    th, ra = ir_schedules[y]
    ir_annual[y] = compute_ir(taxable, th, ra)

net_after_tax_monthly = np.array([
    (net_annual[y] - ir_annual.get(y, 0)) / 12 * CPI_2026 / cpi_index[y]
    for y in years
])
print(f"  Income tax computed for {len(ir_annual)} years")

ax3b.plot(years, cost_monthly, color='black', linewidth=2.5)
ax3b.plot(years, net_plus_ret, color='black', linewidth=2.5, linestyle='--')
ax3b.plot(years, net_monthly, color='black', linewidth=2.5, linestyle='-.')
ax3b.plot(years, net_after_tax_monthly, color='black', linewidth=1.2, linestyle='-')

ax3b.set_xlabel(r'Ann\'{e}e', fontsize=27)
ax3b.set_ylabel(r'Euros de 2026', fontsize=27)

ax3b.grid(True, alpha=0.4, color='grey', linewidth=0.5)
ax3b.set_xlim(years[0], years[-1])
ax3b.set_ylim(0)

# Remove top and right spines (box)
ax3b.spines['top'].set_visible(False)
ax3b.spines['right'].set_visible(False)

ax3b.yaxis.set_major_formatter(mticker.FuncFormatter(
    lambda x, _: f'{x:,.0f}'.replace(',', r'\,') + r'\,\euro{}' if x >= 1000
    else f'{x:.0f}' + r'\,\euro{}'))

# Place labels between the lines
x_label = 2005
i_label = list(years).index(x_label)
y_ret_mid = (net_monthly[i_label] + net_plus_ret[i_label]) / 2
y_other_mid = (net_plus_ret[i_label] + cost_monthly[i_label]) / 2
ax3b.text(x_label, y_ret_mid, r'\textit{Cotisations retraite}', fontsize=24,
          ha='center', va='center')
ax3b.text(x_label, y_other_mid, r'\textit{Autres cotisations sociales}', fontsize=24,
          ha='center', va='center')

# Place curve labels at the right end of each line
x_end = years[-1]
i_end = len(years) - 1
ax3b.annotate(r'\textbf{Co\^{u}t employeur}', xy=(x_end, cost_monthly[i_end]),
              xytext=(8, 0), textcoords='offset points',
              fontsize=22.5, va='center')
ax3b.annotate(r'Salaire net +' + '\n' + r'cotisations retraite',
              xy=(x_end, net_plus_ret[i_end]),
              xytext=(8, 0), textcoords='offset points',
              fontsize=22.5, va='center')
ax3b.annotate(r'Salaire net', xy=(x_end, net_monthly[i_end]),
              xytext=(8, 6), textcoords='offset points',
              fontsize=22.5, va='bottom')
ax3b.annotate(r"Salaire net apr\`{e}s" + '\n' + r"imp\^{o}t sur le revenu",
              xy=(x_end, net_after_tax_monthly[i_end]),
              xytext=(8, -6), textcoords='offset points',
              fontsize=22.5, va='top')

# Label for income tax zone: place below with arrow pointing into the gap
x_ir_label = 1985
i_ir_label = list(years).index(x_ir_label)
y_ir_mid = (net_after_tax_monthly[i_ir_label] + net_monthly[i_ir_label]) / 2
y_ir_target = (net_after_tax_monthly[i_ir_label] + net_monthly[i_ir_label]) / 2 + 100
ax3b.annotate(r"\textit{Imp\^{o}t sur le revenu}",
              xy=(x_ir_label + 5, y_ir_target),
              xytext=(x_ir_label - 3, net_after_tax_monthly[i_ir_label] - 350),
              fontsize=21, ha='center', va='top',
              arrowprops=dict(arrowstyle='->', color='black', lw=0.7,
                              shrinkB=0))

# Add right margin for labels
fig3b.subplots_adjust(right=0.78)

plt.savefig('net_retirement_cost_bw.png', dpi=300, bbox_inches='tight')
plt.savefig('net_retirement_cost_bw.svg', bbox_inches='tight')
try:
    plt.savefig('net_retirement_cost_bw.pdf', bbox_inches='tight')
except PermissionError:
    print("  WARNING: could not write PDF (file locked)")
print("  Saved net_retirement_cost_bw.png/.svg/.pdf")

# Reset rcParams for subsequent figures
plt.rcParams.update({
    'text.usetex': False,
    'font.family': 'sans-serif',
})

# Summary
print(f"\n  {'Year':>4}  {'Net':>8}  {'Net+Ret':>8}  {'Cost':>8}  {'Ret share':>10}")
print(f"  {'----':>4}  {'---':>8}  {'-------':>8}  {'----':>8}  {'---------':>10}")
for y_show in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018, 2020]:
    idx_list = np.where(years == y_show)[0]
    if len(idx_list) > 0:
        i = idx_list[0]
        wedge = cost_monthly[i] - net_monthly[i]
        ret_share = ret_monthly[i] / wedge * 100 if wedge > 0 else 0
        print(f"  {y_show:>4}  {net_monthly[i]:>7,.0f}€  {net_plus_ret[i]:>7,.0f}€  {cost_monthly[i]:>7,.0f}€"
              f"  {ret_share:>9.1f}%")


# =====================================================================
# 9. FIGURE 4: Retirement contributions as % of net salary
# =====================================================================
print()
print("=" * 70)
print("STEP 9: Retirement contributions as % of net salary (Figure 4)")
print("=" * 70)

ret_pct_of_net = ret_monthly / net_monthly * 100

fig4, ax4 = plt.subplots(figsize=(12, 5))

ax4.plot(years, ret_pct_of_net, color='black', linewidth=2)
ax4.fill_between(years, 0, ret_pct_of_net, alpha=0.15, color='black')

ax4.set_xlabel('Année', fontsize=18)
ax4.set_ylabel('% du salaire net', fontsize=18)
ax4.set_title('Cotisations retraite en pourcentage du salaire net\n(temps complet)',
              fontsize=21, fontweight='bold')

ax4.tick_params(axis='both', labelsize=15)
ax4.grid(True, alpha=0.3)
ax4.set_xlim(years[0], years[-1])
ax4.set_ylim(0)

ax4.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.0f}\N{NO-BREAK SPACE}%'))

plt.tight_layout()
plt.savefig('retirement_pct_net.png', dpi=150, bbox_inches='tight')
plt.savefig('retirement_pct_net.svg', bbox_inches='tight')
print("  Saved retirement_pct_net.png and .svg")

print(f"\n  {'Year':>4}  {'Ret/Net':>8}")
print(f"  {'----':>4}  {'-------':>8}")
for y_show in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018, 2020]:
    idx_list = np.where(years == y_show)[0]
    if len(idx_list) > 0:
        i = idx_list[0]
        print(f"  {y_show:>4}  {ret_pct_of_net[i]:>7.1f}%")


# =====================================================================
# 9b. FIGURE 4b: Retirement contributions as % of post-tax income
# =====================================================================
print()
print("=" * 70)
print("STEP 9b: Retirement contributions as % of post-tax income")
print("=" * 70)

ret_pct_of_posttax = ret_monthly / net_after_tax_monthly * 100

fig4b, ax4b = plt.subplots(figsize=(12, 5))

ax4b.plot(years, ret_pct_of_posttax, color='black', linewidth=2)
ax4b.fill_between(years, 0, ret_pct_of_posttax, alpha=0.15, color='black')

ax4b.set_xlabel('Année', fontsize=18)
ax4b.set_ylabel(r"\% du revenu net d'imp\^{o}t", fontsize=18)
ax4b.set_title(r"Cotisations retraite en pourcentage du revenu net d'imp\^{o}t" + '\n'
               + r'(temps complet, c\'{e}libataire)',
               fontsize=21, fontweight='bold')

ax4b.tick_params(axis='both', labelsize=15)
ax4b.grid(True, alpha=0.3)
ax4b.set_xlim(years[0], years[-1])
ax4b.set_ylim(0)
ax4b.spines['top'].set_visible(False)
ax4b.spines['right'].set_visible(False)

ax4b.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.0f}\N{NO-BREAK SPACE}\\%'))

plt.tight_layout()
plt.savefig('retirement_pct_posttax.png', dpi=150, bbox_inches='tight')
plt.savefig('retirement_pct_posttax.svg', bbox_inches='tight')
print("  Saved retirement_pct_posttax.png and .svg")

print(f"\n  {'Year':>4}  {'Ret/PostTax':>12}")
print(f"  {'----':>4}  {'-----------':>12}")
for y_show in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018, 2020]:
    idx_list = np.where(years == y_show)[0]
    if len(idx_list) > 0:
        i = idx_list[0]
        print(f"  {y_show:>4}  {ret_pct_of_posttax[i]:>11.1f}%")


# Print income tax summary
print()
print("=" * 70)
print("Income tax summary (single person, 1 part, 10% deduction)")
print("=" * 70)
print(f"\n  {'Year':>4}  {'Net/mo':>8}  {'IR/mo':>8}  {'After IR':>8}  {'IR rate':>8}")
print(f"  {'----':>4}  {'------':>8}  {'-----':>8}  {'--------':>8}  {'-------':>8}")
for y_show in [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2018, 2020]:
    idx = np.where(years == y_show)[0]
    if len(idx) > 0:
        i = idx[0]
        ir_mo = ir_annual.get(y_show, 0) / 12 * CPI_2026 / cpi_index[y_show]
        rate = ir_annual.get(y_show, 0) / net_annual[y_show] * 100 if net_annual[y_show] > 0 else 0
        print(f"  {y_show:>4}  {net_monthly[i]:>7,.0f}€  {ir_mo:>7,.0f}€  "
              f"{net_after_tax_monthly[i]:>7,.0f}€  {rate:>7.1f}%")
