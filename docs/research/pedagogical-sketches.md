# Bilaga: Systemskisser för AI-stött Bedömningsinstrument

Denna bilaga presenterar fyra modeller som tillsammans utgör det planerade bedömningsinstrumentets uppbyggnad. Modellerna är under utveckling och befinner sig i olika stadier av färdigställande.

---

## 1. Komparativ Bedömning (CJ) med AI-stöd

Komparativ bedömning ersätter absolut betygssättning med parvisa jämförelser. En generativ språkmodell hanterar den stora mängd jämförelser som krävs för att bygga ett nätverk av bedömningar mellan uppsatserna.

```mermaid
graph TD
    subgraph Input [Underlag]
        Essays[Elevuppsatser]
        Anchors["Ankartexter<br/>Kända kvalitetsnivåer"]
    end

    subgraph Process [Komparativ Process]
        Pairing["Pargenerering<br/>Text A vs Text B"]
        Judge["AI-Bedömare<br/>Väljer bästa texten"]
        Decision{Beslut}
        Repeat["Iterativ process<br/>Tusentals jämförelser"]
    end

    subgraph Analysis [Statistisk Modellering]
        Model["Bradley-Terry Modell<br/>Sannolikhetsberäkning"]
        Ranking["Relativ Rangordning<br/>Kvalitetsskala"]
    end

    subgraph Output [Resultat]
        Grades["Betygsprognos<br/>Härledd från ankartexter"]
    end

    Essays --> Pairing
    Anchors --> Pairing
    Pairing --> Judge
    Judge --> Decision
    Decision --> Model
    Decision --> Repeat
    Repeat -.-> Pairing
    Model --> Ranking
    Ranking --> Grades

    style Input fill:#e1f5fe,stroke:#01579b
    style Process fill:#fff3e0,stroke:#ff6f00
    style Analysis fill:#e8f5e9,stroke:#2e7d32
    style Output fill:#f3e5f5,stroke:#7b1fa2
```

---

## 2. Regelbaserad Språkteknisk Analys (NLP)

Den regelbaserade analysen utgör instrumentets objektiva grund. Genom förutbestämda regler mäts formella textegenskaper som stavning, grammatik och läsbarhet—helt oberoende av AI-modellens bedömningar.

```mermaid
graph LR
    Essay[Elevtext]

    subgraph Identification [Identifiering]
        Matcher["Elevmatchning<br/>Koppling mot klasslistor"]
    end

    subgraph Analysis [Analyskomponenter]
        Spell[Stavningskontroll]
        Grammar[Grammatikkontroll]
        Metrics["Textmätning<br/>LIX, meningslängd, ordvariation"]
    end

    subgraph Output [Resultat]
        ObjectiveData[Objektiv Textdata]
    end

    Essay --> Matcher
    Matcher --> Analysis
    Spell --> Output
    Grammar --> Output
    Metrics --> Output

    style Identification fill:#fff9c4,stroke:#fbc02d
    style Analysis fill:#b3e5fc,stroke:#0277bd
    style Output fill:#e1bee7,stroke:#8e24aa
```

---

## 3. Hybridmodell för Konstruktvalidering (ML-Scoring)

Hybridmodellen är utformad för att vara genomskinlig och förklarbar, till skillnad från den komparativa bedömningen där AI-modellens resonemang inte går att knyta till de faktiska bakomliggande besultsprocessserna. Genom att kombinera djupinlärning med definierade textmått går det att spåra vilka textegenskaper som påverkar det slutliga betygsförslaget.

```mermaid
graph TD
    Input[Elevtext]

    subgraph DeepLearning [Spår A: Djupförståelse]
        DeBERTa["Språkmodell<br/>Semantik och sammanhang"]
        Embeddings[Vektorrepresentation]
    end

    subgraph FeatureEng [Spår B: Textmått]
        Tier1["Nivå 1: Ytstruktur<br/>Stavning, läsbarhet"]
        Tier2["Nivå 2: Komplexitet<br/>Syntax, samband"]
        Tier3["Nivå 3: Struktur<br/>Disposition"]
    end

    subgraph Synthesis [Slutsats]
        XGBoost[Sammanvägning]
        SHAP["Förklarbarhetsanalys<br/>XAI"]
    end

    Output[Betygsförslag + Motivering]

    Input --> DeBERTa --> Embeddings
    Input --> Tier1
    Input --> Tier2
    Input --> Tier3

    Embeddings --> XGBoost
    Tier1 --> XGBoost
    Tier2 --> XGBoost
    Tier3 --> XGBoost

    XGBoost --> SHAP
    SHAP --> Output

    style DeepLearning fill:#d1c4e9,stroke:#512da8
    style FeatureEng fill:#c8e6c9,stroke:#388e3c
    style Synthesis fill:#ffccbc,stroke:#d84315
```

---

## 4. Systemöversikt: Integrerad Återkoppling

Systemet sammanställer data från samtliga analysmodeller och omvandlar denna till återkoppling anpassad för respektive mottagare. Systemet är byggt för att möjliggöra jämförande analyser över tid, både på individ- och gruppnivå.

```mermaid
graph TD
    Essay[Elevuppsats]

    subgraph Sources [Analyskällor]
        CJ["Komparativ Bedömning<br/>Relativ nivå"]
        NLP["Språkteknik<br/>Objektiva fel"]
        ML["Hybridmodell<br/>Nivå och textmått"]
    end

    subgraph Aggregation [Databehandling]
        RAS["Datasammanställning"]
    end

    subgraph Generation [Återkopplingsgenerator]
        Context["Urval och anpassning<br/>Elev eller lärare"]
        Generator["Återkopplingstext<br/>Pedagogiskt anpassad"]
    end

    subgraph Output [Mottagare]
        Student["Elevåterkoppling<br/>Formativt stöd"]
        Teacher["Lärarunderlag<br/>Diagnostiskt stöd"]
    end

    Essay --> CJ
    Essay --> NLP
    Essay --> ML

    CJ --> RAS
    NLP --> RAS
    ML --> RAS

    RAS --> Context
    Context --> Generator
    Generator --> Student
    Generator --> Teacher

    style Sources fill:#f0f4c3,stroke:#827717
    style Aggregation fill:#b2dfdb,stroke:#00695c
    style Generation fill:#ffecb3,stroke:#ff8f00
    style Output fill:#e1bee7,stroke:#8e24aa
```
