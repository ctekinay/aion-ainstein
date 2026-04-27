# Principes — Guideline gebruik in architectuurfunctie

> **Doel:** Voor het goed bedrijven van de architectuurfunctie is het essentieel om te bepalen hoe om te gaan met principes. Daarbij hoort het scopen van principes en ze aan elkaar relateren, zodat ze consistent gemanaged kunnen worden in het architectuurlandschap. Classificatie en break-downs zijn daarvoor een geschikt middel. Deze guideline biedt de structuur om dat te doen op basis van TOGAF 9.1 en de ArchiMate 3.1-standaard.
>
> **Aanbeveling vanuit TOGAF:** Houd principes weinig in aantal — TOGAF adviseert 10 tot maximaal 20 principes per scope (Ch.23, §23.6). Dit geldt des te meer naarmate de break-downs meer scopes introduceren: elke scope moet beheersbaar blijven.

---

## Inleiding

In dit document kijken we naar **enterprise principes** als een stabiele kapstok voor de organisatie, met daarnaast **architectuurprincipes** zoals gedefinieerd in TOGAF 9.1. Architectuurprincipes sturen de ontwikkeling, het onderhoud en het gebruik van de enterprise-architectuur.

We zijn ons er echter van bewust dat naast architectuur ook andere disciplines bestaan — zoals engineering — die op basis van gelijksoortige frameworks opereren, met meer focus op realisatie en operationalisering. Dit document moet daarom met een open houding gelezen worden: enterprise principes vormen de stabiele kapstok, maar in een vervolgversie kan het werken met principes meer algemeen gericht worden op engineering én architectuur, in plaats van architectuur als enige sturende discipline te positioneren.

Ofwel: architectuurprincipes zijn nu nodig omdat ze het best uitgewerkte instrument zijn dat we hebben. Maar architectuurprincipes zijn niet de holy grail en geven niet op alles antwoord.

> **Terminologie:** TOGAF 9.1 (Ch.23, §23.1) spreekt over *"two key domains"* die architectuurontwikkeling informeren. In dit document gebruiken we deze Engelse term "key domains" onvertaald om verwarring te voorkomen met *architecture domains* (Business, Data, Application, Technology), die in TOGAF een andere, formeel gedefinieerde betekenis hebben (Ch.3, §3.12: *"Architecture Domain: The architectural area being considered. There are four architecture domains within TOGAF: business, data, application, and technology."*).

---

## 1. Overzicht: Twee key domains en hun classificatie-assen

TOGAF 9.1 (Ch.23, §23.1) onderscheidt twee fundamenteel verschillende key domains die architectuurontwikkeling informeren: **Enterprise Principes** en **Architectuurprincipes**. Elk key domain heeft eigen classificatie-mechanismen. Het is essentieel om deze key domains en hun classificaties niet door elkaar te gebruiken.

### 1.1 De twee key domains

![Principe-classificatie TOGAF 9.1 — twee key domains met classificatie-assen en voorbeelden](togaf_principe_classificatie_v4.svg)

### 1.2 Classificatie-assen — gebonden aan key domain

| Classificatie | Key domain | Vraag | Karakter |
|---------------|------------|-------|----------|
| **Subsidiary** | Enterprise principes | Welke org-eenheid? (IT, HR, OT…) | Permanent |
| **Category** | Architectuurprincipes | Welk architecture domain? (Bus/Data/App/Tech/Integration/Guiding) | Permanent (attribuut, geen hiërarchie) |
| **Segment** | Overkoepelend | Welk programma/portfolio? | Tijdelijk, concretiserend |

**Subsidiary** is een hiërarchische decompositie binnen enterprise principes: enterprise principes worden uitgewerkt in subsidiary principes per organisatie-eenheid.

**Category** is een classificatie-attribuut (Content Metamodel, Ch.34) op architectuurprincipes: het labelt een architectuurprincipe naar architecture domain. Het is geen hiërarchische decompositie — er is geen parent-child relatie van "architectuurprincipe" naar "data-principe" in het metamodel.

**Segment** is een overkoepelend scope-mechanisme dat TOGAF op het niveau van de principe-hiërarchie positioneert (Ch.23, §23.1), niet binnen één specifiek key domain. In de praktijk kan het op beide key domains worden toegepast.

**Kernpunt:** Subsidiary en Category zijn niet uitwisselbaar — ze zitten in verschillende key domains. Een HR subsidiary principe heeft geen Category Business/Data/App/Tech: het is geen architectuurprincipe. Het wordt pas architectuurrelevant wanneer het een architectuurprincipe *informeert* of *begrenst* via de relatie tussen de key domains.

### 1.3 Relatie tussen de key domains

TOGAF 9.1 Ch.23 §23.1 stelt: *"Architecture principles will be informed and constrained by enterprise principles."* Dit zijn twee gelijktijdig werkende relaties:

- **Informeert** = het enterprise principe geeft richting aan het architectuurprincipe (positief, richtinggevend)
- **Begrenst** = het enterprise principe legt grenzen op waarbuiten het architectuurprincipe niet mag treden (negatief, beperkend)

#### 1.3.1 Relaties in actie — voorbeelden

**Informeert (richtinggevend):**
- Subsidiary IT: "Data wordt bij de bron beheerd" → informeert architectuurprincipe: "Single source of truth per entity" (Category: Data, Segment: alle)
- Subsidiary HR: "Elke medewerker heeft een ontwikkelplan" → informeert architectuurprincipe: "HR-systeem faciliteert IDP-workflow" (Category: Application, Segment: HR Digitaal)

**Begrenst (beperkend):**
- Enterprise: "Wij opereren alleen binnen de EU" → begrenst architectuurprincipe: "Cloud hosting uitsluitend EU-regio" (Category: Technology, Segment: alle)

Het HR-voorbeeld benadrukt dat elk enterprise principe — binnen een segment of niet — gereflecteerd moet worden in de architectuurprincipes. Dat kan zo expliciet als in het voorbeeld, of via meer generieke principes die aansluiten op de business en waaraan requirements gerelateerd kunnen worden. Al met al is de expliciete vertaalslag altijd nodig.

#### 1.3.2 Noodzaak relaties en risico's

Het borgen van architectuurprincipes naar de praktijk is essentieel voor de waarde van de architectuur. Architectuurprincipes die niet traceerbaar zijn naar enterprise principes missen hun verankering in de organisatie. Wanneer architectuurprincipes worden opgesteld zonder dat enterprise principes bestaan of expliciet zijn gemaakt, ontstaan de volgende risico's:

1. **Strategische drift — in twee richtingen.** Zonder verankering in enterprise principes kunnen architectuurprincipes ongemerkt afwijken van de organisatiestrategie. Maar het omgekeerde komt evenzeer voor: architectuur is een aantrekkelijk onderwerp dat gemakkelijk disproportioneel budget en aandacht naar zich toetrekt. Zonder de begrenzing door enterprise principes kan architectuurwerk een eigen leven gaan leiden — technisch excellent maar strategisch ontkoppeld, met investeringen die niet in verhouding staan tot de business-waarde.
2. **Conflicterende principes zonder arbiter.** Wanneer twee architectuurprincipes met elkaar concurreren (bijv. accessibility vs. security), bieden enterprise principes het kader om te arbitreren. Dit geldt ook wanneer de architectuurprincipes van gelijk gewicht zijn — ook dan is de informeert- en begrenst-relatie met enterprise principes nodig om een weloverwogen keuze te maken. Zonder dat kader vervalt de beslissing tot persoonlijke voorkeur of politieke macht.
3. **Gebrek aan legitimiteit.** Architectuurprincipes zonder traceerbare link naar enterprise principes hebben geen mandaat vanuit de organisatie. Ze worden dan ervaren als technische regels van de architectuurafdeling, niet als organisatiebreed gedragen richtlijnen.

---

## 2. Definities en kenmerken

### 2.1 Enterprise Principes

**Bron:** TOGAF 9.1, Chapter 23, §23.1

**Definitie:** Enterprise principes bieden een basis voor besluitvorming in de gehele organisatie en bepalen hoe de organisatie haar missie vervult. Ze zijn een middel om besluitvorming te harmoniseren en vormen een kernelement in een succesvolle architectuur-governance strategie (zie ook TOGAF Chapter 50).

**Kenmerken:**
- Duurzaam en zelden gewijzigd ("enduring and seldom amended")
- Organisatiebreed van toepassing
- Sturen op inrichten en besluitvormen op het hoogste niveau
- Vormen de bovenliggende context waarbinnen alle andere principes moeten passen
- Zijn niet per definitie architectuurspecifiek — ze kunnen ook bedrijfsvoering, HR, finance etc. betreffen

**Hiërarchie:** Het is gebruikelijk dat principes een hiërarchie vormen: segmentprincipes worden geïnformeerd door en werken enterprise principes verder uit. Architectuurprincipes worden op hun beurt geïnformeerd en begrensd door enterprise principes (TOGAF 9.1, Ch.23, §23.1).

#### 2.1.1 Subsidiary Principes

**Bron:** TOGAF 9.1, Chapter 23, §23.1

**Definitie:** Binnen het brede key domain van enterprise principes is het gebruikelijk om *subsidiary principles* te hebben binnen een business- of organisatie-eenheid. Voorbeelden: IT, HR, domestic operations, overseas operations.

**Kenmerken:**
- Bieden een besluitvormingsbasis binnen het betreffende (sub)domein
- Informeren architectuurontwikkeling binnen dat domein
- Moeten aligned zijn met de organisatorische context van de Architecture Capability
- Mogen niet conflicteren met enterprise principes
- Hebben een permanent karakter — ze gelden zolang de organisatie-eenheid bestaat

**Koppeling aan metamodel:** Subsidiary principes zijn een subset/specialisatie van enterprise principes, georganiseerd per organisatie-eenheid of functiedomein. Ze zijn geen architectuurprincipes — ze worden pas architectuurrelevant via de informeert/begrenst-relatie (zie §1.3).

**Overweging: organisatie-eenheid vs. capability.** TOGAF 9.1 is expliciet dat subsidiary principes worden georganiseerd per *"business or organizational unit"* (Ch.23, §23.1). In de praktijk zijn organisatie-eenheden echter niet altijd stabiel — reorganisaties verschuiven verantwoordelijkheden. Overweeg daarom om subsidiary principes te koppelen aan het vermogen van de organisatie (capability) in plaats van aan de organisatie-eenheid. Capabilities zijn stabieler dan organogrammen en bieden een duurzamere kapstok. Dit is een praktische aanvulling, geen TOGAF-voorschrift.

**Let op terminologie:** In de praktijk worden subsidiary principes vaak "domeinprincipes" genoemd. Dit is verwarrend omdat TOGAF het woord "domain" ook gebruikt voor architecture domains (Business, Data, Application, Technology) — zie Category in §2.2. Gebruik bij voorkeur de term "subsidiary principes" of label ze expliciet als "domein (subsidiary)".

### 2.2 Architectuurprincipes

**Bron:** TOGAF 9.1, Chapter 23, §23.1–23.5

**Definitie:** Architectuurprincipes zijn een set principes die betrekking hebben op architectuurwerk. Ze weerspiegelen een niveau van consensus binnen de enterprise en belichamen de geest en het denken van bestaande enterprise principes. Ze sturen het architectuurproces: ontwikkeling, onderhoud en gebruik van de enterprise-architectuur.

**Kenmerken:**
- Duurzaam, toekomstgericht, gedragen door senior management
- Weinig in aantal (TOGAF adviseert 10–20 per scope)
- Traceerbaar naar bedrijfsdoelstellingen en architectuurdrivers
- Moeten voldoen aan vijf kwaliteitscriteria: Understandable, Robust, Complete, Consistent, Stable (TOGAF Ch.23, §23.4.1)

**Category (Content Metamodel, Ch.34):** Architectuurprincipes worden geclassificeerd via het attribuut *Category* in het TOGAF Content Metamodel. De zes categorieën zijn: Guiding Principle, Business Principle, Data Principle, Application Principle, Integration Principle, Technology Principle. Dit zijn de architecture domains (Ch.3, §3.12) — niet te verwarren met subsidiary organisatie-eenheden (zie §2.1.1). Category is een classificatie-attribuut, geen hiërarchische decompositie: er is geen parent-child relatie in het metamodel.

**Template (TOGAF Ch.23, §23.3):**

| Component    | Beschrijving |
|-------------|-------------|
| **Name**        | Kort, onthoudbaar, geen technologieplatforms noemen |
| **Statement**   | Ondubbelzinnige formulering van de fundamentele regel |
| **Rationale**   | Business-voordelen, relatie met andere principes, balans |
| **Implications** | Vereisten voor business en IT: resources, kosten, taken, impact |

**Toepassingen (TOGAF Ch.23, §23.5):**
1. Kader voor bewuste besluitvorming over architectuur en projecten
2. Evaluatiecriteria voor selectie van producten/oplossingen
3. Drivers voor functionele requirements
4. Input voor compliance-toetsing van bestaande portfolio
5. Onderbouwing bij conflicterende drivers via Rationale
6. Input voor transitieplanning via Implications
7. Back-stop in Architecture Governance (incl. dispensatieproces)

### 2.3 Segment Principes

**Bron:** TOGAF 9.1, Chapter 23, §23.1

**Definitie:** Segmentprincipes werken enterprise principes concreter uit voor een specifiek portfolio of programma. TOGAF Ch.23 §23.1: *"segment principles will be informed by, and elaborate on, the principles at the enterprise level."*

**Positionering:** TOGAF plaatst segmentprincipes op het overkoepelende niveau van de principe-hiërarchie — niet expliciet binnen één van beide key domains. De zin over segmentprincipes staat in Ch.23 §23.1 buiten de twee bullets die de key domains definiëren. In de praktijk kan het segment-mechanisme op beide key domains worden toegepast, maar dat is een plausibele toepassing, geen letterlijke TOGAF-uitspraak.

**Kenmerken:**
- Tijdelijk karakter — gebonden aan de levensduur van het segment (programma/portfolio)
- Concretisering van enterprise principes, geen vervanging
- Moeten aligned zijn met enterprise principes
- 10-20 principes per segment als bovengrens (TOGAF-aanbeveling)

**Verschil met subsidiary:** Subsidiary principes zijn permanent en gebonden aan een organisatie-eenheid (wie je bent). Segmentprincipes zijn tijdelijk en gebonden aan een programma/portfolio (wat je doet). Bij het afsluiten van een programma kunnen segmentprincipes gearchiveerd worden; subsidiary principes niet.

---

## 3. Relaties en decompositie tussen principetypen

### 3.1 Hiërarchie / Decomposities

```
Enterprise Principes (key domain 1)
 ├── Subsidiary Principes (per organisatie-eenheid: IT, HR, OT, Security…)
 │
 │   informeert + begrenst
 │   ─────────────────────▶
 │
Architectuurprincipes (key domain 2)
 │   Category: Business | Data | Application | Technology | Integration | Guiding
 │   (classificatie-attribuut, geen hiërarchie)

Segment Principes (overkoepelend scope-mechanisme)
 └── Concretisering van enterprise principes per portfolio/programma
     In de praktijk toepasbaar op beide key domains
```

- **Enterprise → Subsidiary:** Subsidiary principes zijn afgeleid binnen een organisatie-eenheid en moeten aligned zijn met enterprise principes.
- **Enterprise → Architectuurprincipes:** Architectuurprincipes worden geïnformeerd en begrensd door enterprise principes; ze herformuleren enterprise-richtlijnen in een vorm die architectuurontwikkeling effectief stuurt.
- **Enterprise → Segment:** Segmentprincipes werken enterprise principes concreter uit voor een specifiek portfolio/programma.

### 3.2 Influence-relaties

- Principes beïnvloeden elkaar: ze moeten als set worden toegepast; soms concurreren ze (bijv. accessibility vs. security).
- Bij conflicten wordt bepaald welk principe voorrang krijgt. Dit geldt ook wanneer principes van gelijk gewicht zijn — ook dan is de informeert- en begrenst-relatie met enterprise principes nodig als arbiter. De rationale voor de beslissing moet altijd gedocumenteerd worden (TOGAF Ch.23, §23.5).

---

## 4. Toepassing van principes op het Architecture Landscape

De voorgaande hoofdstukken beschrijven hoe principes worden geclassificeerd en aan elkaar gerelateerd. Dit hoofdstuk beschrijft *waar* principes landen: op het Architecture Landscape.

### 4.1 Architecture Landscape Levels

**Bron:** TOGAF 9.1, Chapter 20, §20.2

Het Architecture Landscape kent drie niveaus van granulariteit voor het organiseren van architectuurwerk:

| Level | Omschrijving | Focus |
|-------|-------------|-------|
| **Strategic Architecture Level** | Organizing framework voor operational & change activity op executive niveau | Richting, visie, enterprise-brede capability map |
| **Segment Architecture Level** | Organizing framework op programma/portfolio niveau | Roadmaps, portfolio-sturing, programma-governance |
| **Capability Architecture Level** | Organizing framework voor change activity die capability increments realiseert | Concrete veranderstappen, releases |

**Belangrijk:** Dit zijn niveaus van granulariteit, geen containment-hiërarchie. TOGAF stelt expliciet: *"There is no definitive organizing model for architecture, as each enterprise should adopt a model that reflects its own operating model"* (TOGAF Ch.20, §20.2).

**Let op dubbelzinnigheid "Segment":** Het woord "segment" komt in TOGAF in twee contexten voor die onderscheiden moeten worden. *Segment Architecture Level* (Ch.20, §20.2) is een granulariteitsniveau in het Architecture Landscape — het organiseert architectuurwerk op programma/portfolio-niveau. *Segment principes* (Ch.23, §23.1) zijn principes die enterprise principes concretiseren voor een programma/portfolio. Ze raken hetzelfde concept (programma/portfolio-scope) maar vanuit een ander perspectief: het level beschrijft hoe je architectuurwerk organiseert, het principe beschrijft welke beslisregels daarbinnen gelden. In dit document gebruiken we consequent "Segment Architecture Level" voor het landscape level en "segment principes" voor het principe-type.

### 4.2 Hoe principes het landschap raken

Elk niveau in het Architecture Landscape wordt geraakt door principes uit de classificatie van §1-2:

| Landscape Level | Enterprise | Subsidiary | Segment | Architectuur |
|-----------------|:---:|:---:|:---:|:---:|
| **Strategic Architecture Level** | ● | | | ● |
| **Segment Architecture Level** | ● | ● | ● | ● |
| **Capability Architecture Level** | ● | ● | ● | ● |

**Leeswijzer:**
- Enterprise principes en architectuurprincipes gelden altijd op elk level.
- Subsidiary principes worden relevant op Segment en Capability level, waar de scope specifiek genoeg is om org-eenheid-gebonden principes te raken (bijv. IT/security-beleid).
- Segmentprincipes gelden per definitie vanaf het Segment Architecture Level — op Strategic level is er nog geen segment gedefinieerd.

Een Capability increment kan enterprise-breed relevant zijn, door meerdere segmenten lopen, én beïnvloed worden door subsidiary principes — dit zijn geen tegenstrijdigheden, maar verschillende classificaties die tegelijkertijd werken.

### 4.3 Federated architectures als aanpak

Wanneer architecturen onafhankelijk van elkaar worden ontwikkeld (bijv. bij fusies, joint ventures, of sterk gedecentraliseerde organisaties), beschrijft TOGAF (Ch.5, §5.5.1) een *federated* aanpak. Dit is geen scope-niveau of landscape level, maar een andere manier van werken: onafhankelijk ontwikkelde architecturen worden geïntegreerd via een framework dat principes specificeert voor interoperabiliteit, migratie en conformance. De principe-classificatie uit §1-2 en de landscape levels uit §4.1 blijven binnen elke gefedereerde architectuur van toepassing.

---

## 5. Scope: wat bepaalt hoeveel principesets je krijgt?

De voorgaande hoofdstukken introduceren de concepten enterprise, subsidiary, segment, category en landscape levels. De vraag is nu: hoe bepaal je hoeveel principesets je nodig hebt?

TOGAF 9.1 (Ch.5, §5.5) definieert vier dimensies om de scope van architectuurwerk af te bakenen. De onderstaande matrix toont hoe deze dimensies de concepten uit dit document raken:

| Dimensie | Enterprise | Subsidiary | Segment | Category | Landscape Level |
|----------|:---:|:---:|:---:|:---:|:---:|
| **Breadth** | ● | ● | ● | | |
| **Depth** | | | | | ● |
| **Time Period** | | | ● | | ● |
| **Architecture Domains** | | | | ● | |

**Leeswijzer:**
- **Breadth** bepaalt welke enterprise, subsidiaries en segmenten in scope vallen — en genereert daarmee de meeste principesets.
- **Depth** correleert met het landscape level: strategisch = minder detail, capability = meer detail.
- **Time Period** raakt zowel segment (levensduur programma/portfolio) als landscape level (tijdhorizon per level).
- **Architecture Domains** bepaalt welke categories (BDAT) in scope zijn.

Elke combinatie van scope-dimensies en classificatie kan in theorie een eigen set van 10-20 principes opleveren (TOGAF Ch.23, §23.6). Dat maakt discipline essentieel: zonder bewuste scoping ontstaat een onbeheersbaar aantal principesets.

**Richtlijn:** Definieer de scopes vooraf en bewust. Elke scope die je introduceert, moet ook gemanaged worden — inclusief eigenaarschap, review-cyclus en alignment met bovenliggende principes. Hoe meer scopes, hoe meer governance-overhead.

---

## 6. Relaties naar ArchiMate-elementen

### 6.1 ArchiMate Principle (Motivation-aspect)

**ArchiMate-definitie:** "A statement of intent that describes a general property that applies to any system in a certain context in the architecture."

**Positionering:** Het ArchiMate Principle-element zit in het Motivation-aspect, samen met Driver, Goal, Outcome, Requirement, Constraint, Stakeholder, Assessment, Value.

### 6.2 Typische ArchiMate-relaties vanuit Principle

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Driver** | Influence → | **Goal / Outcome** | Externe/interne drijfveren leiden tot doelen |
| **Goal / Outcome** | Influence → | **Principle** | Doelen informeren principes |
| **Principle** | Influence → | **Requirement** | Principes leiden tot concrete eisen |
| **Principle** | Influence → | **Constraint** | Principes leggen beperkingen op |
| **Requirement / Constraint** | Realization → | *Core-elementen (Application, Technology, etc.)* | Eisen worden gerealiseerd in ontwerp |
| **Stakeholder** | Association → | **Principle** | Stakeholders zijn eigenaar/gebruiker van principes |
| **Principle** | Composition → | **Principle** | Decompositie: enterprise → subsidiary / segment |

### 6.3 Motivatieketen (typische view)

```
Stakeholder
    │ (Association)
    ▼
Driver ──(Influence)──▶ Goal / Outcome
                              │ (Influence)
                              ▼
                         Principle
                         │         │
              (Influence)▼         ▼(Influence)
          Requirement          Constraint
                │                    │
        (Realization)         (Realization)
                ▼                    ▼
        [Core-elementen: Application Component, Business Process, Technology, etc.]
```

### 6.4 Onderscheid TOGAF vs ArchiMate

| Aspect | TOGAF | ArchiMate |
|--------|-------|-----------|
| **Rol** | Governance-instrument (spelregel, beleid) | Informatiedrager (traceability, communicatie) |
| **Inhoud** | Name + Statement + Rationale + Implications | Eén element met naam + documentatie |
| **Beheer** | Principeset met eigenaar, status, review, dispensatieproces | Modelelement met relaties |
| **Gebruik** | Toetsen, beslissen, governance | Visualiseren, traceren, analyseren |

**Aanbeveling:** TOGAF = bron van waarheid (tekst, status, eigenaar, rationale/implications, governance). ArchiMate = visualisatie/traceability: modelleer dezelfde principes als Principle-elementen met relaties naar Goals, Requirements, Constraints.

---

## 7. Vuistregels

1. **TOGAF-principes = spelregels** om besluiten consistent te nemen en te toetsen. **ArchiMate Principle = hetzelfde principe**, maar gemodelleerd zodat je waarom → wat → hoe kunt herleiden.

2. **Enterprise principes zijn altijd leidend.** Subsidiary en segment principes moeten hiermee aligned zijn en mogen niet conflicteren. Architectuurprincipes worden geïnformeerd én begrensd door enterprise principes.

3. **Houd principes weinig in aantal: 10–20 per scope** (TOGAF Ch.23, §23.6). Dit geldt per scope-niveau — enterprise, per subsidiary, per segment, per architecture domain. Te veel principes reduceren de flexibiliteit en bestuurbaarheid, zeker naarmate de break-downs meer scopes introduceren.

4. **Elk principe heeft Name, Statement, Rationale, Implications** — ook als het "vanzelfsprekend" lijkt (TOGAF: het feit dat een principe vanzelfsprekend lijkt, betekent niet dat het wordt nageleefd).

5. **Principes zijn interrelated en moeten als set worden toegepast.** Documenteer de rationale wanneer één principe voorrang krijgt boven een ander — ook wanneer ze van gelijk gewicht zijn.

6. **Gebruik consequente termen in je repository:**
   - Enterprise Principles (organisatiebreed)
   - Subsidiary Principles (IT/HR/…) — niet "domeinprincipes" tenzij gelabeld als "domein (subsidiary)"
   - Segment Principles (per portfolio/programma)
   - Architecture Principles (sturen EA-proces) met Category (Bus/Data/App/Tech/Integration/Guiding)

7. **Checkvraag per classificatie:**
   - "Geldt dit principe voor een organisatie-eenheid?" → Subsidiary (enterprise key domain)
   - "Welk architecture domain betreft het?" → Category (architecture key domain)
   - "Geldt het voor een specifiek programma/portfolio?" → Segment (overkoepelend)
   - "Stuurt het het EA-proces?" → Architecture Principle

8. **Federated architectures zijn een aanpak, geen scope-niveau.** Wanneer architecturen onafhankelijk worden ontwikkeld, specificeer een integratie-framework met principes voor interoperabiliteit, migratie en conformance. Binnen elke gefedereerde architectuur gelden de normale scope-niveaus (enterprise, subsidiary).

9. **Waak voor strategische drift in beide richtingen.** Architectuur zonder enterprise-verankering dwaalt af. Maar architectuur die te veel aandacht en budget naar zich toetrekt zonder proportionele business-waarde, dwaalt ook af — alleen in de andere richting.

---

## 8. Inrichtingskeuzes voor het Metamodel

### 8.1 Principe-classificatie als metadata

Geef elk principe in de repository minimaal:

| Attribuut | Waarden | Key domain |
|-----------|---------|------------|
| **Key Domain** | Enterprise / Architecture | Bepaalt welke classificaties van toepassing zijn |
| **Scope Type** | Enterprise / Subsidiary | Enterprise key domain |
| **Category** | Business / Data / Application / Technology / Integration / Guiding | Architecture key domain (Ch.34) |
| **Segment** | Enterprise-breed / Portfolio X / Programma Y | Overkoepelend |
| **TOGAF Template** | Name, Statement, Rationale, Implications | Beide key domains |
| **Eigenaar** | Persoon/rol verantwoordelijk voor het principe | Beide key domains |
| **Status** | Draft / Approved / Under Review / Retired | Beide key domains |
| **Bron** | Verwijzing naar governance-document of beleidsdocument | Beide key domains |
| **Brug-relatie** | Welk enterprise principe informeert/begrenst dit architectuurprincipe? | Alleen architectuurprincipes |

### 8.2 ArchiMate-modellering

- Gebruik **Composition-relatie** van enterprise Principle naar subsidiary/segment Principle om de hiërarchie expliciet te maken.
- Gebruik **Influence-relaties** om de keten Driver → Goal → Principle → Requirement/Constraint te modelleren.
- Gebruik **Influence-relatie** van enterprise Principle naar architectuur Principle om de informeert/begrenst-brug te modelleren.
- Gebruik **Association** tussen Stakeholder en Principle voor eigenaarschap.
- Maak een **Motivation View** per scope (enterprise, per subsidiary, per segment) zodat traceability per context zichtbaar is.

### 8.3 Governance-inrichting

- Beheer de TOGAF-principeset (met volledige template) in een governance-tool of wiki als bron van waarheid.
- Synchroniseer ArchiMate-modellen periodiek met de principeset.
- Richt een uitzonderingsproces (dispensatie) in voor afwijkingen.
- Review principes bij wijzigingen in strategie, fusies, reorganisaties of nieuwe regelgeving.
- Monitor of architectuurinvesteringen proportioneel zijn aan business-waarde (tegengaan van strategische drift).

---

## Bronverwijzingen

| Onderwerp | Bron |
|-----------|------|
| Enterprise & Architecture Principles, Subsidiary, Hiërarchie | TOGAF 9.1, Chapter 23, §23.1 |
| Scope dimensies (Breadth, Depth, Time, Architecture Domains) | TOGAF 9.1, Chapter 5, §5.5 |
| Architecture Domain (formele definitie) | TOGAF 9.1, Chapter 3, §3.12 |
| Template (Name/Statement/Rationale/Implications) | TOGAF 9.1, Chapter 23, §23.3 |
| Kwaliteitscriteria principes | TOGAF 9.1, Chapter 23, §23.4.1 |
| Toepassingen van principes | TOGAF 9.1, Chapter 23, §23.5 |
| Voorbeeldprincipes, 10-20 per scope | TOGAF 9.1, Chapter 23, §23.6 |
| Principle Category attribuut (Content Metamodel) | TOGAF 9.1, Chapter 34, §34.6 |
| Architecture Landscape Levels | TOGAF 9.1, Chapter 20, §20.2 |
| Federated Architectures | TOGAF 9.1, Chapter 5, §5.5.1 |
| Architecture Governance | TOGAF 9.1, Chapter 50 |
| ArchiMate Principle element | ArchiMate 3.1 Specification, Motivation Aspect |
| ArchiMate Influence-relatie | ArchiMate 3.1 Specification, Relationships |
