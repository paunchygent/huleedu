1) Skärp praktikproblemet med nationell “hård data” (och flytta upp det tidigt)

I ditt utkast finns redan ett starkt praktiknära motiv (sambedömningen i ämneslaget + α≈0,56). Det du efterfrågar är att göra motivet mindre anekdotiskt och mer systematiskt genom att tidigt visa att problemet är nationellt dokumenterat – och att det gäller just skrivuppgifter.

Föreslagen placering

Lägg in ett nytt stycke direkt efter stycket som börjar “I svensk skolkontext blir dessa frågor extra betydelsefulla…” och innan din lokala sambedömningsövning. Då blir logiken:
 1. nationellt problem (Skolverket + Dalberg) →
 2. lokalt “micro-case” som illustrerar samma mekanism →
 3. varför CJ + AI kan vara en rimlig alternativ logik.

Konkreta siffror att använda (Skolverket + Dalberg)
 • Skolverket (omrättning av NP i engelska, åk 9, Part C writing): av 100 elevtexter fick 8/100 identiskt betyg mellan lärare och ombedömare på den tiogradiga skalan; maxskillnaden var fyra betygssteg (sex texter). Samtidigt låg korrelationerna mellan bedömare och lärare på 0,86–0,93, dvs. man är ofta mer överens om rangordning än om exakt nivå.  ￼
 • Dalberg (nationella skrivprov, npk1/npk3): för npk3 helhetsbetyg var median exakt överensstämmelse 45,7 % (enskilda bedömare; Fleiss κ=0,30) och 60,9 % vid sambedömning (κ=0,48). Inomklasskorrelationen för helhetsbetyget ökade samtidigt från 0,69 till 0,85 när bedömning gjordes i par.  ￼

“Klista in”-stycke (svenska, på rätt abstraktionsnivå)

Empiri från nationella prov visar att bedömning av skrivande ofta ger måttlig interbedömaröverensstämmelse även under standardiserade förhållanden. I Skolverkets omrättningsstudie av nationella prov i engelska (åk 9, Part C – skriftlig produktion) fick endast 8 av 100 elevtexter exakt samma betyg av lärargruppen och ombedömare på en tiogradig skala, och den största differensen var fyra betygssteg (sex texter). Samtidigt låg korrelationerna mellan ombedömare och lärargrupp på 0,86–0,93, vilket indikerar att bedömningen ofta är mer stabil i rangordning än i exakt nivåplacering.  ￼ En liknande bild ges i Dalbergs statistiska analys av nationella skrivprov, där median exakt överensstämmelse för npk3:s helhetsbetyg låg på 45,7 % för enskilda bedömare (Fleiss κ=0,30) men steg till 60,9 % vid sambedömning (κ=0,48); inomklasskorrelationen för helhetsbetyget ökade samtidigt från 0,69 till 0,85.  ￼ Dessa resultat ramar in projektets praktikproblem: skrivbedömning är i grunden bedömarberoende, och likvärdighet kräver verktyg och procedurer som reducerar oönskad variation utan att förlora konstruktets komplexitet.

Bonus: en mini-tabell (om du vill göra problemet “visuellt”)

Du kan lägga in en liten tabell med tre rader (Skolverket, Dalberg, din pilot). Det ger en snabb “evidenskedja” utan att du behöver skriva mer text.

⸻

2) Strama metoddelen: behåll forskningslogiken, flytta ned/ut teknikdetaljer

Din metoddel signalerar hög kompetens – men den riskerar att läsas som överambitiös (för många komponenter, för många datakrav, för mycket “implementation detail”). En forskningsplan brukar vinna på:
 • Vad du ska undersöka (forskningsfrågor + designlogik),
 • Varför designen kan besvara dem,
 • Hur genomförbarhet säkras (data, etik, riskhantering),

…men inte på att specificera exakt vilka bibliotek/modeller/parametrar som ska användas.

Konkret: vad du kan tona ned eller flytta till bilaga

Flytta ned/ut (bilaga eller “Teknisk prototyp”):
 • “XGBoost”, “SHAP”, “DeBERTa”, exakta modellnamn och arkitekturval.
 • “seed”, detaljer om upprepade körningar, exakta loggningspunkter.
 • Långa listor av reliabilitetsmått (håll dig till 2–4 huvudmått i planen; resten kan stå i bilaga).

Behåll i huvudtext (men på 1–3 meningar vardera):
 • CJ + Bradley–Terry som princip.
 • Ankare/benchmarks som länkningsprincip.
 • Ett “transparens-/förklaringslager” som princip (utan att låsa dig vid exakt teknik).

Exempel på “stramare” DS1-formulering (klista in)

Delstudie 1 utvecklar och pilottestar ett AI-stött bedömningsinstrument baserat på komparativ bedömning, där en språkmodell gör parvisa jämförelser som modelleras på en latent kvalitetsskala (Bradley–Terry). Skalan länkas till betygsnivåer med hjälp av ett begränsat ankarmaterial (benchmarks). För att möjliggöra professionell granskning utvecklas ett transparenslager som synliggör vilka kriteriedimensioner och textdrag som driver bedömningen samt var modellen är osäker. Delstudien resulterar i (i) en prototyp, (ii) ett benchmark-/ankarmaterial och (iii) ett utvärderingsprotokoll för reliabilitet, konstruktvaliditet och rättvisa.

Detta säger allt du behöver – och gör att du inte fastnar i att försvara varför du “måste” bygga tre modeller.

⸻

3) Renodla delstudierna enligt din önskade logik (1 = instrument, 2 = lärare, 3 = etik/policy)

Just nu är DS2 delvis “mätkvalitet + implementering”, och DS3 är en ganska stor elevintervention. Din egen målbild (i din punkt 3) blir tydligare om du gör så här:

Föreslagen ny struktur

Delstudie 1: Instrument + benchmarks + mätteoretisk validering
Kärna: bygga och validera själva mätinstrumentet.
Output: prototyp + benchmark/ankare + evidens för reliabilitet/validitet.
Fokus: (a) hur stabil CJ-rankningen är, (b) hur ankarlänkning fungerar, (c) vilka konstruktirrelevanta signaler som riskerar att driva besluten.

Delstudie 2: Läraranvändning och påverkan på bedömningar och normer
Kärna: hur verktyget används, hur det påverkar bedömningar, hur normer förhandlas.
Mätbara nyckelutfall (för att göra studien “hårdare”):
 • förändring i interbedömarreliabilitet med vs utan verktyg,
 • accept-/override-rate (hur ofta AI-förslag ändras),
 • tid/arbetsbelastning (självrapport + logg),
 • “konvergens” i gränsfall efter kalibreringsworkshops.

Delstudie 3: Etik, rättvisa och policykonsekvenser (AI som bedömare + feedback)
Här gör du den “stora” diskussionen du beskriver: bias, skaleffekter, automation bias, acceptabla/icke acceptabla fel, och jämförelsen med dagens lärarvariation.

Det blir extra relevant i ljuset av SOU 2025:18, som bl.a. lyfter att dagens system saknar objektiva referenspunkter och diskuterar modeller där centralt rättade prov spelar en mycket större roll; kortversionen beskriver flera betygsmodeller och betonar att ett centralt provsystem i andra länder normalt hanteras oberoende av den egna skolan.  ￼
Detta ger dig en tydlig policyanknytning utan att du behöver “gissa” exakt hur reformen landar.

⸻

4) Datatillgång: gör det till en kort riskhanteringssektion (inte en teknisk utvecklingsplan)

Du har helt rätt att DS1 riskerar att falla på åtkomst till NP-uppsatser (provsekretess, handskrift). Det ska synas – men det ska stå som genomförbarhetsstrategi, inte som detaljerad pipeline.

Föreslagen “Plan A/B/C” (kort och trovärdig)

Plan A (bästa matchning mot NP-konstrukt):
Korpus av elevtexter som ligger nära NP-genre/uppgifter via samarbete med skolor, med lärarbedömning i metadata + ett mindre ankarmaterial kalibrerat med extern panel.

Plan B (om NP-material inte kan användas i skala):
Använd äldre offentliga provtexter/uppgifter + skoltexter som huvudsaklig tränings-/valideringsbas. Ankare kan fortfarande vara NP-nära.

Plan C (om svensk NP-närhet blir orimlig):
Komplettera med etablerade L2-dataset (t.ex. IELTS) för att testa metodens generaliserbarhet och för att separera “modellens mättegenskaper” från “svenska NP-specifika kriterier”. Här blir DS1 tydligt: metodvalidering först, svensk NP-implementering sedan.

En viktig detalj du kan lägga in utan att bli överteknisk

Eftersom Gy25 ändrar strukturen till nivåer är det rimligt att skriva “Engelska nivå 1–2 (tidigare Engelska 5–6)”, och gärna lägga en fotnot som visar att Engelska 5 motsvaras av Engelska nivå 1 och Engelska 6 av nivå 2.  ￼
Det ökar precisionen och signalerar att du har koll på den administrativa kontexten.

⸻

5) Forskningsfrågor som matchar den renodlade studielogiken (förslag)

Formulera hellre få, hårda frågor än många mjuka. Exempel:

Delstudie 1 (instrument)
 1. I vilken grad är en LLM-baserad CJ-modell stabil (reproducerbar rangordning) över upprepade körningar och varierade bedömningsvillkor?
 2. Vilken evidens finns för att modellen bedömer i linje med avsett skrivkonstrukt, snarare än konstruktirrelevanta proxyvariabler (t.ex. textlängd)?
 3. Hur påverkar ankare/benchmarks länkningen från latent CJ-skala till betygsnivåer (precision nära gränser)?

Delstudie 2 (lärare)
 4. Hur påverkar verktyget lärarnas betygsbeslut (accept/override, riktning, gränsfall), och förändras interbedömarreliabiliteten jämfört med baseline?
 5. Hur används verktyget i praktiken (arbetsflöde, tillit, hantering av oenighet), och hur påverkas bedömningsnormer i praktikgemenskapen?

Delstudie 3 (etik/policy)
 6. Vilka rättvise- och biasmönster uppstår i bedömning och feedback, vilka grupper riskerar att gynnas/missgynnas, och hur ska detta värderas relativt de dokumenterade bristerna i dagens bedömaröverensstämmelse? (Här kan du explicit koppla till den policylogik som SOU 2025:18 driver: ökad likvärdighet genom starkare referenspunkter, men med risk för storskalig systembias om fel skalar.)  ￼

⸻

6) “Relevant vs inte relevant” i din nuvarande text (praktisk redigeringslista)

Behåll (relevant för dina tre kritiska mål)
 • Messick/Bachman & Palmer + utility argument (bra ram för att tala om reliabilitet/validitet/impact).
 • Sadler/indeterminacy + rater types (motiverar varför disagreement inte är “slarv”).
 • CJ-beskrivningen (men kortare) – det är din metodologiska kärna.
 • Din lokala sambedömning (men gör den till illustration, inte huvudbevis).

Korta/flytta (riskerar att trigga “överambitiöst”-läsning)
 • Den detaljerade modellstacken (XGBoost/SHAP/DeBERTa osv.) i huvudtext.
 • DS2:s steg-för-steg-procedur + många specifika mått i listform.
 • DS3 som fullskalig cross-over-intervention (om du vill att DS3 ska bli etik/policy).
 • Om du vill behålla elevperspektivet: gör det till fokusgrupper + analys av feedbacktexter + riskanalys, inte en komplett interventionsdesign.
