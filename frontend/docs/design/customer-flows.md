---
type: design-spec
id: DESIGN-001
status: accepted
created: 2025-12-08
last_updated: 2025-12-08
---

# Kundflöden och designmotivering

> Dokumentation av målgrupper, kundresor och hur dessa motiverar designval i frontend-prototyperna.

## Målgrupper

### Persona A: Enskild lärare

**Beskrivning:**  
Språklärare (svenska eller engelska) på högstadiet eller gymnasiet som vill effektivisera sin bedömning av elevtexter. Arbetar ofta ensam med sina klasser och fattar egna beslut om vilka verktyg som används.

**Behov:**

- Administrera kurser och klasser
- Få analys och återkoppling på elevtexter
- Skicka pålitlig feedback till elever från ett och samma ställe
- Jämföra resultat mellan elever, kurser och läsår

**Köpbeteende:**

- Låg tröskel, vill testa själv
- Betalar inget under provperiod, endast för dataförbrukning (pris per token + pålägg)
- Beslutar snabbt och självständigt

**Konverteringsspår:**  
Landing page → "Anmäl intresse" → Väntlisteformulär → Inbjudan när kapacitet finns → Skapa konto → Användning

---

### Persona B: Ämneslag / Skolledning

**Beskrivning:**  
Grupp av lärare inom samma ämne (svenska/engelska) som tillsammans utvärderar och beslutar om inköp av läromedel och verktyg. Kan också vara skolledning eller kommun som utvärderar för bredare utrullning.

**Behov:**

- Samordna bedömning av nationella prov (NP) för hela skolan
- Få överblick över resultat på gruppnivå
- Kostnadseffektiv lösning för många användare
- Underlag för att övertyga kollegor och ledning

**Köpbeteende:**

- Kollektivt beslut, längre utvärderingscykel
- Behöver presentation och demo innan beslut
- Priskänsliga för totalbelopp men värdesätter låg anslutningsavgift + användningsbaserad debitering
- Skolor och kommuner har högre trösklar men större LTV

**Konverteringsspår:**  
Landing page → "För skolor och kommuner" → Kontaktformulär → Möte/demo → Avtal → Utrullning

---

## Prismodell (kontext för designval)

| Segment | Anslutning | Användning |
|---------|------------|------------|
| Enskild lärare | Gratis provperiod | Pris per token + pålägg |
| Skola/ämneslag | Låg anslutningsavgift per skola | Användningsbaserad debitering |

Denna modell motiverar två separata CTA:er – enskilda lärare kan prova utan kostnad (låg friktion), medan organisationer behöver formell kontakt för att diskutera avtal.

---

## Smoke test-fas

Vi befinner oss i tidig fas och kan inte hantera stora kundströmmar. Strategin är därför:

1. **Enskilda lärare** samlas på en väntlista (e-post, yrkesroll, användningsområde)
2. **Organisationer** kontaktas för personlig demo och avtalsförhandling
3. Användare släpps in successivt när kapacitet finns

---

## Designmotiveringar

### Landing page (`huleedu-landing-final.html`)

#### Hero-sektion

| Element | Val | Motivering |
|---------|-----|------------|
| Rubrik | "Bedömning med precision." | Kort, konkret löfte. Undviker jargong. |
| Brödtext | "Ladda upp elevtexter, få tillförlitliga bedömningsunderlag och skicka återkoppling som eleverna förstår." | Beskriver vad läraren kan *göra*, inte teknisk implementation. |
| Understrykning | "Du behåller kontrollen – vi läser, jämför och analyserar." | Adresserar oro för AI-verktyg. Konkreta verb (läser, jämför, analyserar) istället för vaga ("sköter det repetitiva"). |

#### CTA-knappar

| Element | Val | Motivering |
|---------|-----|------------|
| Primär CTA | "Anmäl intresse" (stor, fylld) | Riktar sig till Persona A. Minimal friktion. |
| Sekundär CTA | "För skolor och kommuner →" (liten länk) | Riktar sig till Persona B. Tydlig hierarki – primär CTA dominerar. |
| Placering | Vertikalt stackade | Brutalistisk asymmetri. Undviker balansproblem med olika textlängder. |

**Varför inte "Starta demo"?**  

- Oklart vem som klickar och vad som händer
- I smoke test-fas finns ingen demo att starta direkt
- Väntlista + personlig kontakt är rätt för nuvarande kapacitet

#### Funktioner ("Så fungerar det")

| Funktion | Värde | Motivering |
|----------|-------|------------|
| Rangordning | Betygsstöd | Vad läraren får ut, inte teknisk implementation (CJ, Bradley-Terry). |
| Textanalys | Överblick | Fokus på jämförelsemöjlighet (elever, kurser, läsår). |
| Återkoppling | Utveckling | Konkret: "vad som fungerar och vad nästa utmaning är". |
| Tidsbesparande | Fokus | Smärtpunkt: "Slipp läsa varje text flera gånger." |

**Princip:** Beskrivningar ska vara begripliga för universitetsutbildade utan domänkunskap. Varken för tekniska (obegripliga) eller för enkla (banala).

#### Språkval

- **Ingen svengelska:** "feedback" → "återkoppling", "Changelog" → "Ändringslogg"
- **Fullständiga meningar:** Undviker subjektslösa fraser som "Kopplar bedömningen till..."
- **Svenska termer konsekvent:** Målgruppen är svenska lärare

---

## Kommande sidor

### `/anmal-intresse.html` (Persona A)

**Syfte:** Samla in kontaktuppgifter för väntlista.

**Fält:**

- E-post (obligatoriskt)
- Yrkesroll (dropdown: Svensklärare / Engelsklärare / Annat)
- "Vad vill du använda tjänsten till i första hand?" (fritext)

**Efter submit:**  
Förklaring att vi hör av oss med inbjudan när kapacitet finns.

---

### `/for-skolor.html` (Persona B)

**Syfte:** Generera leads för organisationer.

**Innehåll:**

- Kort beskrivning av värde för skolor (samordning, kostnadseffektivitet)
- Prismodell (anslutningsavgift + användning)
- Kontaktformulär (namn, organisation, e-post, telefon, meddelande)

**Efter submit:**  
Bekräftelse att vi kontaktar dem för att boka presentation.

---

## Tekniska beslut

### Self-contained prototyper

Prototypfilerna ska fungera utan extern byggprocess:

- All CSS som behövs för hover-states etc. inkluderas i `<style>`-block
- Inga beroenden på Tailwind watch/compile för att förhandsgranska
- Underlättar snabb iteration och delning med stakeholders

### Brutalistisk design

Designspråket (hårda kanter, offset-skuggor, registerestetik) valdes för att:

- Signalera precision och pålitlighet
- Skilja sig från "mjuka" EdTech-produkter
- Passa målgruppens förväntningar (professionellt verktyg, inte leksak)

---

## Sammanfattning

| Persona | CTA | Flöde | Friktion |
|---------|-----|-------|----------|
| Enskild lärare | "Anmäl intresse" | Väntlista → Inbjudan → Konto | Minimal |
| Ämneslag/skola | "För skolor och kommuner" | Kontakt → Demo → Avtal | Högre (men motiverad) |

Designvalen är direkt kopplade till dessa två personas och deras olika köpbeteenden.
