"""
Recreate the B&W figure originally produced by FigTRI.m.
Reads Fig A2.11 from econ-gen-pib-composante spreadsheet and plots two
series (taux de rendement effectif / implicite) by cohort birth year.
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

DATA_DIR = Path(__file__).parent
XLSX = DATA_DIR / "econ-gen-pib-composante(2) (version 1).xlsx"

raw = pd.read_excel(XLSX, sheet_name="Fig A2.11", header=None)
Y = raw.iloc[9:11, 2:38].to_numpy(dtype=float).T  # 36x2
Year = list(range(1940, 1940 + Y.shape[0]))

plt.rcParams.update({
    "text.usetex": True,
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman"],
    "font.size": 16,
})

fig, ax = plt.subplots(figsize=(7.68, 4.8))

ax.fill_between(Year, Y[:, 0], Y[:, 1], color='gray', alpha=0.3)
ax.plot(Year, Y[:, 0], 'k-',  linewidth=1.8, label="Rendement servi")
ax.plot(Year, Y[:, 1], 'k--', linewidth=1.8, label=r"R\`egle d'or")

ax.set_xlabel(r"Ann\'ee de naissance")
ax.set_xlim(Year[0], Year[-1])
ax.set_ylim(bottom=0)
ax.grid(True, alpha=0.4)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

def pct_fr(v, _):
    s = f"{100*v:.1f}".replace(".", "{,}")
    return rf"${s}\,\%$"

ax.yaxis.set_major_formatter(FuncFormatter(pct_fr))
ax.minorticks_on()

ax.legend(loc="upper right", frameon=True, fontsize=14)

ax.annotate(
    r"\textit{Croissance annuelle du taux de cotisation}" "\n"
    r"\textit{\`a r\'epercuter sur les g\'en\'erations suivantes}",
    xy=(1962, 0.0154), xycoords='data',
    xytext=(1941, 0.0075), textcoords='data',
    fontsize=15, ha='left', va='center',
    arrowprops=dict(arrowstyle='->', color='black', lw=0.8),
)

plt.tight_layout()
plt.savefig(DATA_DIR / "Fig_A2_11.pdf")
plt.savefig(DATA_DIR / "Fig_A2_11.png", dpi=150)
print("Fig_A2_11 saved")
