# Bilaga: Exempel på systemutdata

Denna bilaga visar faktisk utdata från HuleEdus bedömningsinstrument, genererad under utveckling och testning med autentiska elevuppsatser från kursen Engelska 5.

---

## 1. Komparativ Bedömning: Ankarvalidering

Följande resultat visar hur systemet validerar sig självt genom att låta AI-bedömaren jämföra ankartexter med kända betyg. En perfekt korrelation (Kendall's τ = 1,0) indikerar att modellen rangordnar texterna i samma ordning som de mänskliga bedömarna.

### Sammanfattning

| Mätvärde | Resultat |
|----------|----------|
| Antal jämförelser | 66 |
| Inversioner | 0 |
| Kendall's τ | 1,000 |

### Ankarresultat

Tabellen visar tolv ankartexter sorterade efter modellens beräknade kvalitetspoäng (θ). Kolumnen "Förväntad" anger den ordning som följer av de kända betygen.

| Ankar-ID | Betyg | θ-poäng | Rang | Förväntad | Vinster | Förluster |
|----------|-------|---------|------|-----------|---------|-----------|
| ANCHOR_78DB411E | A | 5,360 | 1 | 1 | 11 | 0 |
| ANCHOR_8DE763C1 | A | 4,645 | 2 | 2 | 10 | 1 |
| ANCHOR_71E159F0 | B | 3,846 | 3 | 3 | 9 | 2 |
| ANCHOR_426FE254 | B | 2,993 | 4 | 4 | 8 | 3 |
| ANCHOR_B8904D4E | C+ | 2,089 | 5 | 5 | 7 | 4 |
| ANCHOR_C579C625 | C- | 1,125 | 6 | 6 | 6 | 5 |
| ANCHOR_77B700CC | D+ | 0,089 | 7 | 7 | 5 | 6 |
| ANCHOR_EF692795 | D- | −1,040 | 8 | 8 | 4 | 7 |
| ANCHOR_50C4F68E | E+ | −2,292 | 9 | 9 | 3 | 8 |
| ANCHOR_73127661 | E- | −3,718 | 10 | 10 | 2 | 9 |
| ANCHOR_D298E687 | F+ | −5,421 | 11 | 11 | 1 | 10 |
| ANCHOR_363940D5 | F+ | −7,678 | 12 | 12 | 0 | 11 |

*Källa: Körning a259881c, 2025-12-02*

---

## 2. Bedömningsprompt

Systemet använder följande bedömningsmatris vid parvisa jämförelser. Matrisen är utformad för att spegla Skolverkets kunskapskrav för Engelska 5.

### Innehåll

- Uppgiftsuppfyllelse
- Tydlighet i idéer
- Ämnesrelevans och djup
- Rikedom och variation i innehåll
- Anpassning till syfte, mottagare, situation och genre

### Språk och uttryck

- Flyt och naturlighet i uttrycket
- Sofistikering, fraseologi och idiomatik
- Meningsbyggnad och sammanhang
- Lämpligt register och ton
- Korrekthet i stavning och interpunktion

---

## 3. Koppling till systemskisser

Utdatan ovan motsvarar följande delar i systemskisserna (se Bilaga: Systemskisser):

| Utdatatyp | Skisskomponent |
|-----------|----------------|
| Ankarvalidering | Komparativ Bedömning → Statistisk Modellering |
| θ-poäng (Bradley-Terry) | Statistisk Modellering → Bradley-Terry Modell |
| Betygsprognos | Resultat → Härledd från ankartexter |
| Bedömningsmatris | Komparativ Process → AI-Bedömare |
