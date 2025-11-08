"""
Visualiseringar för bedömarpanelrapporten
==========================================
Skapar pedagogiska diagram för att illustrera resultaten
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Konfigurera svenska teckenuppsättning och stil
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.2)

# Färgpalett som matchar svensk pedagogisk tradition
COLORS = {
    "primary": "#1B4F72",
    "secondary": "#2874A6",
    "accent": "#E74C3C",
    "mild": "#27AE60",
    "strict": "#E74C3C",
    "neutral": "#95A5A6",
}

# =============================================================================
# Ladda data
# =============================================================================

# True scores
essays_df = pd.read_csv("/mnt/user-data/uploads/ordinal_true_scores_essays.csv")
essays_df["student"] = essays_df["FILE-NAME"].str.extract(r"^(.*?)\s*\(")[0]

# Bedömarstränghet
raters_df = pd.read_csv("/mnt/user-data/uploads/ordinal_rater_severity.csv")

# Trösklar
thresholds_df = pd.read_csv("/mnt/user-data/uploads/ordinal_thresholds.csv")

# Spridning
spread_df = pd.read_csv("/mnt/user-data/uploads/ordinal_essay_spread.csv")

# =============================================================================
# Figur 1: Uppsatsernas true scores med osäkerhetsintervall
# =============================================================================

fig, ax = plt.subplots(figsize=(10, 6))

# Sortera efter latent ability
essays_sorted = essays_df.sort_values("latent_ability")

# Skapa barplot
y_pos = np.arange(len(essays_sorted))
bars = ax.barh(
    y_pos,
    essays_sorted["latent_ability"],
    color=[
        COLORS["primary"] if x >= 0 else COLORS["accent"] for x in essays_sorted["latent_ability"]
    ],
)

# Lägg till elevnamn
ax.set_yticks(y_pos)
ax.set_yticklabels(
    [
        f"{row['ANCHOR-ID']}: {row['student'][:15]}..."
        if len(row["student"]) > 15
        else f"{row['ANCHOR-ID']}: {row['student']}"
        for _, row in essays_sorted.iterrows()
    ]
)

# Lägg till predicerat betyg som text
for i, (_, row) in enumerate(essays_sorted.iterrows()):
    ax.text(
        row["latent_ability"] + 0.1 if row["latent_ability"] >= 0 else row["latent_ability"] - 0.1,
        i,
        f"({row['pred_mode_grade']})",
        va="center",
        ha="left" if row["latent_ability"] >= 0 else "right",
        fontweight="bold",
        fontsize=10,
    )

ax.set_xlabel("Latent kvalitet (true score)", fontsize=12)
ax.set_title(
    "Uppsatsernas beräknade kvalitet efter justering för bedömarbias",
    fontsize=14,
    fontweight="bold",
)
ax.axvline(x=0, color="gray", linestyle="--", alpha=0.5)
ax.grid(axis="x", alpha=0.3)

plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/figur1_uppsatskvalitet.png", dpi=150, bbox_inches="tight")
plt.close()

print("✓ Figur 1: Uppsatskvalitet skapad")

# =============================================================================
# Figur 2: Bedömarstränghet
# =============================================================================

fig, ax = plt.subplots(figsize=(10, 6))

# Sortera bedömare efter stränghet
raters_sorted = raters_df.sort_values("severity")

# Definiera färger baserat på stränghet
colors = []
for sev in raters_sorted["severity"]:
    if sev < -0.5:
        colors.append(COLORS["mild"])
    elif sev > 0.5:
        colors.append(COLORS["strict"])
    else:
        colors.append(COLORS["neutral"])

# Skapa barplot
y_pos = np.arange(len(raters_sorted))
bars = ax.barh(y_pos, raters_sorted["severity"], color=colors)

# Lägg till bedömarnamn med antal bedömningar
ax.set_yticks(y_pos)
ax.set_yticklabels([f"{row['rater']} (n={row['n_rated']})" for _, row in raters_sorted.iterrows()])

ax.set_xlabel("Bedömarstränghet (negativt = mild, positivt = sträng)", fontsize=12)
ax.set_title("Systematiska skillnader i bedömarstränghet", fontsize=14, fontweight="bold")
ax.axvline(x=0, color="black", linestyle="-", linewidth=1)

# Lägg till zoner
ax.axvspan(-3, -0.5, alpha=0.1, color=COLORS["mild"], label="Milda bedömare")
ax.axvspan(-0.5, 0.5, alpha=0.1, color=COLORS["neutral"], label="Neutrala bedömare")
ax.axvspan(0.5, 3, alpha=0.1, color=COLORS["strict"], label="Stränga bedömare")

ax.legend(loc="lower right")
ax.grid(axis="x", alpha=0.3)

plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/figur2_bedömarstränghet.png", dpi=150, bbox_inches="tight")
plt.close()

print("✓ Figur 2: Bedömarstränghet skapad")

# =============================================================================
# Figur 3: Betygströsklar
# =============================================================================

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

# Övre panel: Tröskelvärden
grades = ["F", "F+", "E", "E+", "D-", "D+", "C-", "C+", "B", "A"]
threshold_positions = list(thresholds_df["tau_k"]) + [8]  # Lägg till övre gräns

# Rita betygszoner
colors_grades = [
    "#8B0000",
    "#B22222",
    "#FF6347",
    "#FFA500",
    "#FFD700",
    "#ADFF2F",
    "#90EE90",
    "#32CD32",
    "#228B22",
    "#006400",
]

prev_thresh = -4
for i, (thresh, grade, color) in enumerate(zip(threshold_positions, grades, colors_grades)):
    ax1.axvspan(prev_thresh, thresh, alpha=0.3, color=color, label=grade)
    ax1.text(
        (prev_thresh + thresh) / 2,
        0.5,
        grade,
        ha="center",
        va="center",
        fontweight="bold",
        fontsize=11,
    )
    prev_thresh = thresh

ax1.set_xlim(-4, 8)
ax1.set_ylim(0, 1)
ax1.set_xlabel("Latent kvalitetsskala", fontsize=12)
ax1.set_title("Betygströsklar på den underliggande kvalitetsskalan", fontsize=14, fontweight="bold")
ax1.set_yticks([])

# Markera tröskelvärden
for thresh in thresholds_df["tau_k"]:
    ax1.axvline(x=thresh, color="black", linestyle="--", alpha=0.5, linewidth=0.5)

# Nedre panel: Stegstorlekar
steps = np.diff([-3.1] + list(thresholds_df["tau_k"]))
step_labels = ["F→F+", "F+→E", "E→E+", "E+→D-", "D-→D+", "D+→C-", "C-→C+", "C+→B", "B→A"]

x_pos = np.arange(len(steps))
colors_steps = ["green" if s < 0.5 else "orange" if s < 1.5 else "red" for s in steps]
bars = ax2.bar(x_pos, steps, color=colors_steps, edgecolor="black", linewidth=1)

ax2.set_xticks(x_pos)
ax2.set_xticklabels(step_labels, rotation=45, ha="right")
ax2.set_ylabel("Stegstorlek", fontsize=12)
ax2.set_title("Storlek på kvalitetssteg mellan betygsnivåer", fontsize=12, fontweight="bold")
ax2.axhline(y=1, color="gray", linestyle="--", alpha=0.5, label="Referensstorlek")
ax2.grid(axis="y", alpha=0.3)

# Lägg till värden på staplarna
for bar, step in zip(bars, steps):
    height = bar.get_height()
    ax2.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 0.05,
        f"{step:.2f}",
        ha="center",
        va="bottom",
        fontsize=9,
    )

plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/figur3_betygströsklar.png", dpi=150, bbox_inches="tight")
plt.close()

print("✓ Figur 3: Betygströsklar skapad")

# =============================================================================
# Figur 4: Bedömarsamstämmighet - spridning per uppsats
# =============================================================================

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Vänster panel: Spridning per uppsats
spread_sorted = spread_df.sort_values("range", ascending=False)
colors_spread = [
    "red" if r >= 4 else "orange" if r >= 3 else "green" for r in spread_sorted["range"]
]

y_pos = np.arange(len(spread_sorted))
bars = ax1.barh(y_pos, spread_sorted["range"], color=colors_spread)

ax1.set_yticks(y_pos)
ax1.set_yticklabels(
    [f"{row['ANCHOR-ID']} (n={row['n']})" for _, row in spread_sorted.iterrows()], fontsize=9
)
ax1.set_xlabel("Spridning (antal betygssteg)", fontsize=11)
ax1.set_title("Bedömarspridning per uppsats", fontsize=12, fontweight="bold")
ax1.grid(axis="x", alpha=0.3)

# Lägg till zoner
ax1.axvline(x=2, color="green", linestyle="--", alpha=0.5, label="Låg spridning")
ax1.axvline(x=4, color="red", linestyle="--", alpha=0.5, label="Hög spridning")
ax1.legend(loc="upper right", fontsize=9)

# Höger panel: Fördelning av spridning
spread_counts = spread_df["range"].value_counts().sort_index()
ax2.bar(
    spread_counts.index,
    spread_counts.values,
    color=COLORS["primary"],
    edgecolor="black",
    linewidth=1,
)

ax2.set_xlabel("Spridning (antal betygssteg)", fontsize=11)
ax2.set_ylabel("Antal uppsatser", fontsize=11)
ax2.set_title("Fördelning av bedömarspridning", fontsize=12, fontweight="bold")
ax2.set_xticks(range(6))
ax2.grid(axis="y", alpha=0.3)

# Lägg till procent på staplarna
total = len(spread_df)
for x, count in zip(spread_counts.index, spread_counts.values):
    ax2.text(
        x,
        count + 0.1,
        f"{count}\n({100 * count / total:.0f}%)",
        ha="center",
        va="bottom",
        fontsize=9,
    )

plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/figur4_bedömarspridning.png", dpi=150, bbox_inches="tight")
plt.close()

print("✓ Figur 4: Bedömarspridning skapad")

# =============================================================================
# Figur 5: Sammanfattande dashboard
# =============================================================================

fig = plt.figure(figsize=(14, 10))

# Skapa grid
gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

# Panel 1: Top 5 uppsatser
ax1 = fig.add_subplot(gs[0, :2])
top5 = essays_df.nlargest(5, "latent_ability")
ax1.barh(range(5), top5["latent_ability"], color=COLORS["primary"])
ax1.set_yticks(range(5))
ax1.set_yticklabels(
    [f"{row['ANCHOR-ID']} ({row['pred_mode_grade']})" for _, row in top5.iterrows()]
)
ax1.set_xlabel("True score")
ax1.set_title("Topp 5 uppsatser", fontweight="bold")
ax1.grid(axis="x", alpha=0.3)

# Panel 2: Nyckeltal
ax2 = fig.add_subplot(gs[0, 2])
ax2.axis("off")
metrics_text = """
NYCKELTAL

Krippendorffs α: 0.56

Median bedömningar
per uppsats: 5

Median spridning: 2

Andel med spridning
≥3 steg: 42%
"""
ax2.text(
    0.1,
    0.5,
    metrics_text,
    fontsize=11,
    verticalalignment="center",
    bbox=dict(boxstyle="round", facecolor="lightgray", alpha=0.3),
)

# Panel 3: Bedömare som behöver fler bedömningar
ax3 = fig.add_subplot(gs[1, :])
few_ratings = raters_df[raters_df["n_rated"] < 5].sort_values("n_rated")
if not few_ratings.empty:
    ax3.barh(range(len(few_ratings)), few_ratings["n_rated"], color=COLORS["accent"])
    ax3.set_yticks(range(len(few_ratings)))
    ax3.set_yticklabels(few_ratings["rater"])
    ax3.set_xlabel("Antal bedömda uppsatser")
    ax3.set_title(
        "Bedömare som behöver bedöma fler uppsatser (mål: ≥5)",
        fontweight="bold",
        color=COLORS["accent"],
    )
    ax3.axvline(x=5, color="green", linestyle="--", label="Målnivå")
    ax3.legend()
else:
    ax3.text(0.5, 0.5, "Alla bedömare har ≥5 bedömningar", ha="center", va="center", fontsize=12)
    ax3.set_title("Bedömare som behöver fler bedömningar", fontweight="bold")
ax3.grid(axis="x", alpha=0.3)

# Panel 4: Uppsatser som behöver fler bedömningar
ax4 = fig.add_subplot(gs[2, :])
need_more = spread_df[spread_df["n"] < 5].sort_values("n")
if not need_more.empty:
    ax4.barh(range(len(need_more)), need_more["n"], color=COLORS["accent"])
    ax4.set_yticks(range(len(need_more)))
    ax4.set_yticklabels(need_more["ANCHOR-ID"])
    ax4.set_xlabel("Antal bedömningar")
    ax4.set_title(
        "Uppsatser som behöver fler bedömningar (mål: ≥5)",
        fontweight="bold",
        color=COLORS["accent"],
    )
    ax4.axvline(x=5, color="green", linestyle="--", label="Målnivå")
    ax4.legend()
else:
    ax4.text(0.5, 0.5, "Alla uppsatser har ≥5 bedömningar", ha="center", va="center", fontsize=12)
    ax4.set_title("Uppsatser som behöver fler bedömningar", fontweight="bold")
ax4.grid(axis="x", alpha=0.3)

plt.suptitle(
    "Sammanfattning: Kalibrering av ankaruppsatser", fontsize=16, fontweight="bold", y=1.02
)

plt.savefig("/mnt/user-data/outputs/figur5_dashboard.png", dpi=150, bbox_inches="tight")
plt.close()

print("✓ Figur 5: Dashboard skapad")

# =============================================================================
# Sammanfattning
# =============================================================================

print("\n" + "=" * 50)
print("VISUALISERINGAR KLARA!")
print("=" * 50)
print("\nSkapade filer:")
print("1. figur1_uppsatskvalitet.png - Ranking av uppsatser")
print("2. figur2_bedömarstränghet.png - Bedömarbias")
print("3. figur3_betygströsklar.png - Betygsgränser")
print("4. figur4_bedömarspridning.png - Samstämmighet")
print("5. figur5_dashboard.png - Översikt")
print("\nAlla filer sparade i: /mnt/user-data/outputs/")
