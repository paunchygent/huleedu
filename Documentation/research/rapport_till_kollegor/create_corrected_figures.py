"""
Skapa korrigerade figurer för bedömarpanelrapporten
=====================================================
Läser data från Bayesiansk konsensusmodell och genererar figurer med korrekt tolkning
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from pathlib import Path

# Konfigurera matplotlib för svensk text
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 100
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.1)

# Sökvägar
DATA_PATH = Path("output/bayesian_consensus_model/20250924-202445/bias_on")
OUTPUT_PATH = Path("Documentation/research/rapport_till_kollegor/files")
MAP_FILE = Path("Documentation/research/rapport_till_kollegor/files/MAP_OF_RATER_ID_AND_REAL_RATERS.csv")

# Färgpalett
COLORS = {
    'generous': '#27AE60',      # Grön för generösa
    'strict': '#E74C3C',         # Röd för stränga
    'neutral': '#95A5A6',        # Grå för neutrala
    'uncertain': '#D3D3D3',      # Ljusgrå för osäkra
    'positive': '#2E86AB',       # Blå för positiva ability
    'negative': '#A23B72',       # Lila för negativa ability
    'primary': '#1B4F72',        # Mörkblå
    'secondary': '#2874A6'       # Mellanblå
}

def load_data():
    """Ladda all data från CSV-filer"""
    # Bedömarmappning - skip första raden som innehåller "ANONYM_MAP_BEDOMARE"
    map_df = pd.read_csv(MAP_FILE, sep=';', skiprows=1)
    rater_map = dict(zip(map_df['rater_name'], map_df['rater_id']))

    # Ladda data
    essays = pd.read_csv(DATA_PATH / "essay_consensus.csv")
    rater_bias = pd.read_csv(DATA_PATH / "rater_bias_posteriors_eb.csv")
    inter_rater = pd.read_csv(DATA_PATH / "essay_inter_rater_stats.csv")

    # Mappa bedömar-ID
    rater_bias['bedomar_id'] = rater_bias['rater_id'].map(rater_map)

    return essays, rater_bias, inter_rater, rater_map

def create_figure1_essay_ranking(essays):
    """Figur 1: Rankad lista över uppsatser efter ability"""
    fig, ax = plt.subplots(figsize=(12, 8))

    # Sortera efter ability
    essays_sorted = essays.sort_values('ability')

    # Definiera färger baserat på ability
    colors = [COLORS['negative'] if x < 5.5 else COLORS['positive'] for x in essays_sorted['ability']]

    # Skapa horisontellt stapeldiagram
    y_pos = np.arange(len(essays_sorted))
    bars = ax.barh(y_pos, essays_sorted['ability'], color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)

    # Lägg till uppsats-ID och konsensusbetyg
    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"{row['essay_id']}" for _, row in essays_sorted.iterrows()], fontsize=11)

    # Lägg till konsensusbetyg som text
    for i, (_, row) in enumerate(essays_sorted.iterrows()):
        # Betyg till höger om stapeln
        ax.text(row['ability'] + 0.15, i, f"({row['consensus_grade']})",
                va='center', ha='left', fontweight='bold', fontsize=10)
        # Värde inuti stapeln om tillräckligt bred
        if abs(row['ability'] - 5.5) > 0.5:
            ax.text(5.5 + (row['ability'] - 5.5) * 0.5, i, f"{row['ability']:.2f}",
                    va='center', ha='center', color='white', fontweight='bold', fontsize=9)

    # Lägg till referenslinje vid genomsnitt
    ax.axvline(x=5.5, color='gray', linestyle='--', alpha=0.7, linewidth=1.5)
    ax.text(5.5, -0.8, 'Genomsnitt', ha='center', fontsize=10, style='italic')

    ax.set_xlabel('Underliggande kvalitet (ability score)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Uppsats-ID', fontsize=12, fontweight='bold')
    ax.set_title('Uppsatsernas beräknade kvalitet efter justering för bedömarstränghet',
                 fontsize=14, fontweight='bold', pad=20)

    # Justera x-axeln
    ax.set_xlim(2, 10)
    ax.grid(axis='x', alpha=0.3)

    # Lägg till förklaring
    high_patch = mpatches.Patch(color=COLORS['positive'], label='Över genomsnitt', alpha=0.8)
    low_patch = mpatches.Patch(color=COLORS['negative'], label='Under genomsnitt', alpha=0.8)
    ax.legend(handles=[high_patch, low_patch], loc='lower right')

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH / "figur1_uppsatskvalitet.png", dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("✓ Figur 1: Uppsatskvalitet skapad")

def create_figure2_rater_severity(rater_bias):
    """Figur 2: Bedömarstränghet med korrekt tolkning"""
    fig, ax = plt.subplots(figsize=(12, 8))

    # Sortera efter mu_post (justerad bias)
    raters_sorted = rater_bias.sort_values('mu_post')

    # Definiera färger och transparens baserat på värde och antal bedömningar
    colors = []
    alphas = []
    for _, row in raters_sorted.iterrows():
        mu = row['mu_post']
        n = row['n_rated']

        # Färg baserat på stränghet (KORREKT: negativ=sträng, positiv=generös)
        if mu < -0.3:
            color = COLORS['strict']  # Röd för stränga
        elif mu > 0.3:
            color = COLORS['generous']  # Grön för generösa
        else:
            color = COLORS['neutral']  # Grå för neutrala

        # Transparens baserat på säkerhet
        alpha = 0.4 if n <= 3 else 0.8

        colors.append(color)
        alphas.append(alpha)

    # Skapa stapeldiagram
    y_pos = np.arange(len(raters_sorted))
    bars = ax.barh(y_pos, raters_sorted['mu_post'])

    # Applicera färger och transparens individuellt
    for bar, color, alpha in zip(bars, colors, alphas):
        bar.set_color(color)
        bar.set_alpha(alpha)
        bar.set_edgecolor('black')
        bar.set_linewidth(0.5)

    # Lägg till bedömar-ID med antal bedömningar
    ax.set_yticks(y_pos)
    labels = []
    for _, row in raters_sorted.iterrows():
        label = f"{row['bedomar_id']} (n={int(row['n_rated'])})"
        if row['n_rated'] <= 2:
            label += " ⚠"  # Varningssymbol för mycket osäkra
        labels.append(label)
    ax.set_yticklabels(labels, fontsize=10)

    # Lägg till värden som text
    for i, (_, row) in enumerate(raters_sorted.iterrows()):
        value_text = f"{row['mu_post']:.2f}"
        if abs(row['mu_post']) > 0.15:
            # Inne i stapeln om tillräckligt bred
            ax.text(row['mu_post'] * 0.5, i, value_text,
                    va='center', ha='center', color='white', fontweight='bold', fontsize=9)
        else:
            # Bredvid stapeln om för smal
            offset = 0.05 if row['mu_post'] > 0 else -0.05
            ax.text(row['mu_post'] + offset, i, value_text,
                    va='center', ha='left' if row['mu_post'] > 0 else 'right',
                    fontweight='bold', fontsize=9)

    ax.set_xlabel('Bedömarstränghet (negativ = sträng, positiv = generös)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Bedömar-ID', fontsize=12, fontweight='bold')
    ax.set_title('Systematiska skillnader i bedömarstränghet',
                 fontsize=14, fontweight='bold', pad=20)

    # Referenslinje vid 0
    ax.axvline(x=0, color='black', linestyle='-', linewidth=1.5, alpha=0.8)

    # Lägg till zoner
    ax.axvspan(-1, -0.3, alpha=0.1, color=COLORS['strict'])
    ax.axvspan(-0.3, 0.3, alpha=0.1, color=COLORS['neutral'])
    ax.axvspan(0.3, 1, alpha=0.1, color=COLORS['generous'])

    # Legend
    strict_patch = mpatches.Patch(color=COLORS['strict'], label='Stränga bedömare', alpha=0.8)
    neutral_patch = mpatches.Patch(color=COLORS['neutral'], label='Neutrala bedömare', alpha=0.8)
    generous_patch = mpatches.Patch(color=COLORS['generous'], label='Generösa bedömare', alpha=0.8)
    uncertain_patch = mpatches.Patch(color=COLORS['uncertain'], label='Osäkra värden (få bedömningar)', alpha=0.4)

    ax.legend(handles=[strict_patch, neutral_patch, generous_patch, uncertain_patch],
              loc='lower right', fontsize=9)

    ax.grid(axis='x', alpha=0.3)
    ax.set_xlim(-1, 1)

    # Lägg till förklarande text
    ax.text(0.98, 0.02, '⚠ = Mycket osäkert värde (n≤2)',
            transform=ax.transAxes, fontsize=8, ha='right', style='italic')

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH / "figur2_bedömarstränghet.png", dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("✓ Figur 2: Bedömarstränghet skapad")

def create_figure3_grade_thresholds():
    """Figur 3: Avstånd mellan betygsnivåer baserat på faktisk data

    Visar de faktiska avstånden mellan betygsnivåer baserat på
    genomsnittliga ability scores för varje betyg.

    OBS: E+ har bara en uppsats (JP24) som ligger långt från resten.
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    # Faktiska medelvärden från data
    grade_means = {
        'E+': 3.43,  # Endast JP24
        'D+': 4.84,  # Medel av 4 uppsatser
        'C-': 5.80,  # Medel av 3 uppsatser
        'C+': 7.06,  # Medel av 2 uppsatser
        'B': 8.16    # Medel av 2 uppsatser
    }

    # Faktiska övergångar i data
    # E+ till D+ hoppar över D- (1 mellanliggande betygssteg)
    # Normalisera för att visa per betygssteg
    e_plus_to_d_minus = 1.41 / 2  # Dela på 2 steg: E+→D- och D-→D+

    # Skapa betygssteg - både faktiska och uppskattade
    step_labels = ['E+→D-', 'D-→D+', 'D+→C-', 'C-→C+', 'C+→B']
    step_sizes = [
        e_plus_to_d_minus,     # E+ → D- (uppskattat från total)
        e_plus_to_d_minus,     # D- → D+ (uppskattat från total)
        0.96,                  # D+ → C- (faktisk data)
        1.26,                  # C- → C+ (faktisk data)
        1.10,                  # C+ → B (faktisk data)
    ]

    # Markera vilka som är uppskattade
    is_estimated = [True, True, False, False, False]

    # Definiera färger baserat på stegstorlek - använd samma blå palett som andra figurer
    # men med olika nyanser baserat på storlek
    # Normalisera stegstorlekar för färgintensitet
    min_size = min(step_sizes)
    max_size = max(step_sizes)
    normalized_sizes = [(size - min_size) / (max_size - min_size) for size in step_sizes]

    # Använd blå färgskala - ljusare för små steg, mörkare för stora
    # Detta ger en konsekvent och logisk visualisering
    step_colors = []
    for norm_size in normalized_sizes:
        if norm_size < 0.3:
            # Små steg - ljusblå
            color = '#85C1E2'  # Ljusblå
        elif norm_size < 0.7:
            # Medelstora steg - mellanblå
            color = '#2874A6'  # Standardblå
        else:
            # Stora steg - mörkblå
            color = '#1B4F72'  # Mörkblå
        step_colors.append(color)

    # Skapa stapeldiagram - streckade för uppskattade, solida för faktiska
    x_pos = np.arange(len(step_sizes))
    bars = []
    for i, (size, color, estimated) in enumerate(zip(step_sizes, step_colors, is_estimated)):
        if estimated:
            # Uppskattade värden - streckad/transparent
            bar = ax.bar(x_pos[i], size, color=color, alpha=0.5, edgecolor=color,
                        linewidth=2, linestyle='--', fill=False)
        else:
            # Faktiska värden - solid
            bar = ax.bar(x_pos[i], size, color=color, alpha=0.85, edgecolor='none')
        bars.append(bar[0])

    # Lägg till värden ovanpå staplarna
    for i, (bar, size, estimated) in enumerate(zip(bars, step_sizes, is_estimated)):
        label = f'{size:.2f}'
        if estimated:
            label += '*'
        ax.text(bar.get_x() + bar.get_width()/2, size + 0.02,
                label, ha='center', va='bottom', fontweight='bold', fontsize=11)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(step_labels, fontsize=12)
    ax.set_ylabel('Avstånd (ability score enheter)', fontsize=12, fontweight='bold')
    ax.set_title('Faktiska avstånd mellan betygsnivåer baserat på genomsnittliga ability scores',
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_ylim(0, max(step_sizes) * 1.15)
    ax.grid(axis='y', alpha=0.3)

    # Lägg till förklarande text
    ax.text(0.5, -0.15, '* Uppskattat värde (D- saknas i data). E+ baserat på endast en uppsats (JP24).',
            transform=ax.transAxes, ha='center', fontsize=10, style='italic', color='#E74C3C')

    # Lägg till information om antal uppsatser
    info_text = 'Antal uppsatser per betyg: E+ (1), D- (0), D+ (4), C- (3), C+ (2), B (2)'
    ax.text(0.5, -0.20, info_text,
            transform=ax.transAxes, ha='center', fontsize=10, style='italic')

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH / "figur3_betygströsklar.png", dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("✓ Figur 3: Betygströsklar skapad")

def create_figure4_inter_rater_agreement(inter_rater):
    """Figur 4: Bedömarspridning med faktisk data"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))

    # Sortera efter grade_range (spridning)
    inter_sorted = inter_rater.sort_values('grade_range', ascending=False)

    # Vänster panel: Stapeldiagram per uppsats
    y_pos = np.arange(len(inter_sorted))

    # Definiera färger baserat på spridning
    colors = []
    for range_val in inter_sorted['grade_range']:
        if range_val <= 1:
            colors.append('#27AE60')  # Grön = god samstämmighet
        elif range_val <= 2:
            colors.append('#52BE80')  # Ljusgrön
        elif range_val <= 3:
            colors.append('#F39C12')  # Orange = måttlig
        else:
            colors.append('#E74C3C')  # Röd = stor oenighet

    bars = ax1.barh(y_pos, inter_sorted['grade_range'], color=colors, alpha=0.8,
                   edgecolor='black', linewidth=0.5)

    # Lägg till uppsats-ID
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels([f"{row['essay_id']}" for _, row in inter_sorted.iterrows()], fontsize=10)

    # Lägg till värden
    for i, (_, row) in enumerate(inter_sorted.iterrows()):
        ax1.text(row['grade_range'] + 0.1, i, f"{int(row['grade_range'])}",
                va='center', ha='left', fontweight='bold', fontsize=9)

    ax1.set_xlabel('Spridning (antal betygssteg)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Uppsats-ID', fontsize=11, fontweight='bold')
    ax1.set_title('Bedömarspridning per uppsats', fontsize=12, fontweight='bold')
    ax1.set_xlim(0, 6)
    ax1.grid(axis='x', alpha=0.3)

    # Höger panel: Cirkeldiagram med fördelning
    range_counts = inter_rater['grade_range'].value_counts().sort_index()

    # Gruppera för cirkeldiagram
    distribution = {
        'Utmärkt\n(≤1 steg)': sum(range_counts[i] for i in range_counts.index if i <= 1),
        'God\n(2 steg)': sum(range_counts[i] for i in range_counts.index if i == 2),
        'Måttlig\n(3 steg)': sum(range_counts[i] for i in range_counts.index if i == 3),
        'Stor oenighet\n(≥4 steg)': sum(range_counts[i] for i in range_counts.index if i >= 4)
    }

    # Färger för cirkeldiagram
    pie_colors = ['#27AE60', '#52BE80', '#F39C12', '#E74C3C']

    # Skapa cirkeldiagram
    wedges, texts, autotexts = ax2.pie(distribution.values(), labels=distribution.keys(),
                                        colors=pie_colors, autopct='%1.0f%%',
                                        startangle=90, textprops={'fontsize': 10})

    # Förbättra textformatering
    for text in texts:
        text.set_fontsize(11)
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(11)

    ax2.set_title('Fördelning av samstämmighet', fontsize=12, fontweight='bold')

    # Lägg till statistik som text
    median_range = inter_rater['grade_range'].median()
    mean_range = inter_rater['grade_range'].mean()
    ax2.text(0, -1.4, f'Median: {median_range:.1f} steg\nMedel: {mean_range:.1f} steg',
            ha='center', fontsize=10, style='italic')

    # Huvudtitel
    fig.suptitle('Bedömarsamstämmighet - Översikt',
                 fontsize=14, fontweight='bold', y=1.02)

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH / "figur4_bedömarspridning.png", dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print("✓ Figur 4: Bedömarspridning skapad")

def main():
    """Huvudfunktion som kör alla visualiseringar"""
    print("Laddar data...")
    essays, rater_bias, inter_rater, rater_map = load_data()

    print("Skapar figurer...")
    create_figure1_essay_ranking(essays)
    create_figure2_rater_severity(rater_bias)
    create_figure3_grade_thresholds()
    create_figure4_inter_rater_agreement(inter_rater)

    print("\n✅ Alla figurer har skapats framgångsrikt!")
    print(f"Figurerna finns i: {OUTPUT_PATH}")

    # Visa sammanfattning
    print("\n" + "="*60)
    print("SAMMANFATTNING AV DATA:")
    print("="*60)

    print("\n📊 UPPSATSER:")
    print(f"Högst ability: {essays.loc[essays['ability'].idxmax(), 'essay_id']} = {essays['ability'].max():.2f}")
    print(f"Lägst ability: {essays.loc[essays['ability'].idxmin(), 'essay_id']} = {essays['ability'].min():.2f}")

    print("\n👥 BEDÖMARE:")
    most_generous = rater_bias.loc[rater_bias['mu_post'].idxmax()]
    most_strict = rater_bias.loc[rater_bias['mu_post'].idxmin()]
    print(f"Mest generös: {most_generous['bedomar_id']} = {most_generous['mu_post']:.3f}")
    print(f"Mest sträng: {most_strict['bedomar_id']} = {most_strict['mu_post']:.3f}")

    print("\n🎯 SAMSTÄMMIGHET:")
    print(f"Största spridning: {inter_rater['essay_id'].iloc[inter_rater['grade_range'].idxmax()]} = {inter_rater['grade_range'].max()} steg")
    print(f"Minsta spridning: {inter_rater['grade_range'].min()} steg")

if __name__ == "__main__":
    main()
