# Kaders (Frameworks) — Guideline gebruik in architectuurfunctie

> **Doel:** Voor het goed bedrijven van de architectuurfunctie is het essentieel om te bepalen hoe om te gaan met kaders (frameworks). Kaders zijn samengestelde, normatieve governance-instrumenten die richting geven aan architectuur- en engineeringwerk. Deze guideline biedt de structuur om kaders te definiëren, te classificeren, te modelleren en te beheren op basis van TOGAF 9.1, de ArchiMate 3.1-standaard, en expliciet te interpreteren vanuit TOGAF en ArchiMate.
>
> **Afbakening:** TOGAF definieert geen formele "framework-template" als apart concept. Deze guideline is daarom een eigen uitwerking, geworteld in TOGAF-concepten en -structuren maar niet letterlijk voorgeschreven door de standaard. Waar de uitwerking eigen interpretatie betreft, is dit expliciet gelabeld.

---

## Inleiding

Dit document beschrijft **kaders** als een specifiek type governance-instrument binnen de architectuurfunctie. Een kader is niet hetzelfde als een principe, een richtlijn of een standaard — het is een samengesteld instrument dat principes, requirements, constraints en optioneel patronen bundelt tot een coherent, normatief geheel voor een afgebakend domein.

Net als bij het principes-document (zie `references/principes-samenvatting-metamodel.md`) geldt dat naast architectuur ook andere disciplines bestaan — zoals engineering — die op basis van gelijksoortige instrumenten opereren. Enterprise kaders vormen de stabiele kapstok; architectuurkaders zijn het best uitgewerkte instrument dat we nu hebben, maar zijn niet de enige discipline die met kaders werkt.

> **Relatie met principes-document:** Dit document bouwt voort op de principes-guideline en herhaalt geen definities die daar zijn vastgelegd. Kennis van de twee key domains, classificatie-assen (Subsidiary, Category, Segment) en de motivatieketen wordt als bekend verondersteld.
>
> **Relatie met capabilities-document:** Kaders sturen de realisatie van capabilities. De relatie loopt via de motivatieketen: Principle → Requirement/Constraint → Realization door core-elementen die capabilities realiseren. Zie `references/capabilities-samenvatting-metamodel.md` voor de capability-kant.

---

## 1. Definitie en afbakening

### 1.1 Wat is een kader?

**Eigen uitwerking — geen formele TOGAF-definitie.**

Een kader (framework) is een **samengesteld, normatief governance-instrument** dat voor een afgebakend domein een coherente set van principes, requirements en constraints bundelt, inclusief de governance om naleving te waarborgen. Een kader kan daarnaast verwijzen naar patronen uit de pattern library als aanbevolen oplossingsrichtingen.

**Kenmerken:**
- Normatief: naleving is niet vrijblijvend maar verplicht, met een formeel dispensatieproces voor afwijkingen
- Samengesteld: het bestaat uit meerdere gerelateerde elementen (principes, requirements, constraints)
- Coherent: de elementen binnen het kader zijn onderling consistent en versterken elkaar
- Domein-gebonden: elk kader heeft een afgebakende scope (welk domein, welke organisatie-eenheid, welk segment)
- Governance-vereisend: een kader zonder eigenaar, dispensatieproces en review-cyclus is geen kader maar een document

### 1.2 Onderscheid met verwante instrumenten

| Instrument | Normatief? | Samengesteld? | Governance-vereisend? | Karakter |
|---|---|---|---|---|
| **Kader (Framework)** | Ja — comply or explain | Ja — bundelt principes, requirements, constraints | Ja — eigenaar, dispensatie, review | Schuld bij niet-naleving |
| **Principe** | Richtinggevend — governance-gestuurd | Nee — één element met Name/Statement/Rationale/Implications | Ja — maar lichter | Spelregel voor besluitvorming |
| **Richtlijn (Guideline)** | Nee — vrijblijvend | Kan samengesteld zijn | Minimaal | Keuze bij niet-naleving |
| **Standaard** | Ja — per geadopteerde clausule, met lifecycle | Extern: vaak lijvig, intern: gerichte selectie | Ja — compliance, deviation, lifecycle review | Harde eis op geadopteerde scope; deviatie via governance |
| **Patroon (Pattern)** | Nee — aanbevolen | Nee — één oplossingsmodel | Via pattern library | Best practice |

**Lakmoestest kader vs. guideline:** Bij een guideline is niet-naleving een keuze. Bij een kader is niet-naleving een schuld die je aflost. Als een team kan zeggen "we volgen het kader niet en dat is prima" dan heb je geen kader maar een guideline. Bij een kader is het antwoord altijd: "we volgen het kader niet *en dit is ons plan om dat te herstellen*."

**Standaarden en adoptie-scope:** Een standaard wordt pas normatief door expliciete adoptie van specifieke clausules of secties — niet door het hele document te omarmen (TOGAF §41.4.4: standaarden worden gekoppeld aan metamodel-entiteiten, niet aan documenten). De bindingskracht varieert met de lifecycle-status: een Provisional Standard bindt alleen binnen pilot-scope, pas een Active Standard is breed normatief (TOGAF §41.4.3). Afwijkingen worden beheerst als "standards deviations" in de Governance Log (TOGAF §41.5.2), een lichter mechanisme dan kaderdispensatie.

### 1.3 Relatie met TOGAF Management Frameworks

TOGAF 9.1 (Preliminary Phase, §6.2.5) stelt dat TOGAF moet coëxisteren met vier management frameworks:

- **Business Capability Management** — bepaalt welke business capabilities nodig zijn inclusief ROI en performance measures
- **Portfolio/Project Management Methods** — bepaalt hoe een organisatie haar veranderinitiatieven beheert
- **Operations Management Methods** — beschrijft hoe een organisatie haar dagelijkse operatie runt, inclusief IT
- **Solution Development Methods** — formaliseert hoe business systems worden geleverd conform IT-architectuur

Kaders in de zin van dit document kunnen betrekking hebben op elk van deze vier domeinen, of cross-cutting zijn. De enterprise architect kan zich niet beperken tot IT-implementatie maar moet de impact op de gehele enterprise begrijpen (TOGAF §6.2.5).

---

## 2. Positionering in de twee key domains

### 2.1 De twee key domains

Kaders bestaan in **beide key domains** die TOGAF 9.1 (Ch.23, §23.1) onderscheidt. De classificatie volgt dezelfde structuur als bij principes:

| Key domain | Type kader | Classificatie-as | Voorbeeld |
|---|---|---|---|
| **Enterprise** | Kaders die de hele organisatie raken, ongeacht of het IT betreft | — | Risk Management Framework, Compliance Framework |
| **Architecture** | Kaders die het architectuurwerk sturen | Category (Bus/Data/App/Tech/Integration/Guiding) | Data Governance Framework, Integration Framework |

#### 2.1.1 Subsidiary kaders

**Binnen het enterprise key domain** is het — analoog aan subsidiary principes (TOGAF Ch.23, §23.1) — gebruikelijk om kaders te hebben per organisatie-eenheid. Voorbeelden: IT Governance Framework, HR Policy Framework, OT Security Framework.

**Kenmerken:**
- Bieden een governance-basis binnen het betreffende (sub)domein
- Moeten aligned zijn met enterprise kaders en enterprise principes
- Mogen niet conflicteren met enterprise kaders
- Hebben een permanent karakter — ze gelden zolang de organisatie-eenheid bestaat

**Koppeling aan metamodel:** Subsidiary kaders zijn een subset/specialisatie van enterprise kaders, georganiseerd per organisatie-eenheid of functiedomein. Ze zijn geen architectuurkaders — ze worden pas architectuurrelevant wanneer ze een architectuurkader *informeren* of *begrenzen* via de relatie tussen de key domains (zie §2.3).

**Overweging: organisatie-eenheid vs. capability.** Analoog aan de overweging bij subsidiary principes (zie principes-document §2.1.1): overweeg om subsidiary kaders te koppelen aan capabilities in plaats van aan organisatie-eenheden. Capabilities zijn stabieler dan organogrammen en bieden een duurzamere kapstok.

#### 2.1.2 Segment-kaders

Analoog aan segmentprincipes kunnen kaders tijdelijk worden geconcretiseerd voor een specifiek portfolio of programma. Een segmentkader werkt een enterprise- of architectuurkader uit voor een specifieke context en heeft een tijdelijk karakter, gebonden aan de levensduur van het segment.

**Verschil met subsidiary:** Subsidiary kaders zijn permanent en gebonden aan een organisatie-eenheid (wie je bent). Segmentkaders zijn tijdelijk en gebonden aan een programma/portfolio (wat je doet).

### 2.2 Digitalisering als classificatievoorbeeld

Een digitaliseringskader is typisch een **architectuurkader** met Category "Application" of "Integration" — het stuurt architectuurwerk in het applicatie- en integratiedomein. Het is géén subsidiary IT-kader, tenzij het specifiek gaat over hoe de IT-organisatie-eenheid zichzelf bestuurt.

Het onderscheid volgt de checkvraag uit het principes-document:
- "Gaat het over hoe een organisatie-eenheid zichzelf bestuurt?" → Subsidiary (enterprise key domain)
- "Gaat het over welk architectuurdomein wordt gestuurd?" → Category (architecture key domain)

Een digitaliseringskader bestuurt een architectuurdomein, niet een organisatie-eenheid.

### 2.3 Relatie tussen de key domains

Analoog aan principes (TOGAF Ch.23, §23.1: *"Architecture principles will be informed and constrained by enterprise principles"*) worden architectuurkaders **geïnformeerd en begrensd** door enterprise kaders en enterprise principes. Dit zijn twee gelijktijdig werkende relaties:

- **Informeert** = het enterprise kader/principe geeft richting aan het architectuurkader (positief, richtinggevend)
- **Begrenst** = het enterprise kader/principe legt grenzen op waarbuiten het architectuurkader niet mag treden (negatief, beperkend)

**Risico's bij ontbreken van deze relatie** — dezelfde risico's als bij principes gelden hier versterkt, omdat een kader een zwaarder instrument is:

1. **Strategische drift** — een kader zonder enterprise-verankering kan een eigen leven gaan leiden
2. **Conflicten zonder arbiter** — wanneer twee kaders concurreren, bieden enterprise principes en enterprise kaders het arbitragekader
3. **Gebrek aan legitimiteit** — een kader zonder enterprise-link wordt ervaren als bureaucratie van de architectuurafdeling

### 2.4 Hiërarchie en samenhang tussen kaders

Kaders vormen — net als principes — een hiërarchie. De samenhang-verantwoordelijkheid loopt van boven naar beneden:

```
Enterprise Kaders
 ├── Subsidiary Kaders (per organisatie-eenheid: IT, HR, OT…)
 │
 │   informeert + begrenst
 │   ─────────────────────▶
 │
Architectuurkaders (per Category: Bus/Data/App/Tech/Integration/Guiding)
 │
 └── Segment-kaders (per portfolio/programma — tijdelijk, concretiserend)
```

**Samenhang-verantwoordelijkheid:**
- Enterprise kaders zijn altijd leidend. Subsidiary en segment-kaders moeten hiermee aligned zijn en mogen niet conflicteren.
- Architectuurkaders worden geïnformeerd én begrensd door enterprise kaders en enterprise principes.
- Elk lager gelegen kader moet verantwoording afleggen aan het hoger gelegen kader: is de concretisering aligned met de bovenliggende intent?
- De eigenaar van het hoger gelegen kader heeft de verantwoordelijkheid om samenhang te bewaken en conflicten te signaleren.

**Checkvraag per classificatie:**
- "Geldt dit kader voor de hele organisatie?" → Enterprise kader
- "Geldt dit kader voor een organisatie-eenheid?" → Subsidiary (enterprise key domain)
- "Welk architecture domain stuurt het?" → Category (architecture key domain)
- "Geldt het voor een specifiek programma/portfolio?" → Segment-kader

---

## 3. Samenstellende elementen van een kader

### 3.1 Elementen

Een kader is een **coherente bundeling** van de volgende elementen:

| Element | Rol in het kader | Verplicht? |
|---|---|---|
| **Principes** | De toepasselijke principes (enterprise en/of architectuur) die het kader implementeert. Dit zijn bestaande principes uit de principes-repository — geen nieuw type. | Ja |
| **Requirements** | Concrete eisen die binnen de scope van dit kader gelden. Dit zijn requirements in de zin van het TOGAF/ArchiMate metamodel, gebundeld door het kader. | Ja |
| **Constraints** | Beperkingen die binnen de scope van dit kader gelden. Dit zijn constraints in de zin van het TOGAF/ArchiMate metamodel, gebundeld door het kader. | Ja |
| **Patronen (referentie)** | Verwijzingen naar de pattern library: welke patronen worden aanbevolen als oplossingsrichtingen binnen dit kader. Patronen zitten niet *in* het kader maar worden *gerefereerd vanuit* het kader. | Nee — optioneel |
| **Standaarden (referentie)** | Verwijzingen naar geadopteerde clausules van standaarden die binnen de scope van dit kader gelden. De verwijzing betreft altijd specifieke secties, niet het standaarddocument als geheel. De lifecycle-status van de geadopteerde clausules (Provisional/Active/Phasing-Out) bepaalt mede de afdwingbaarheid van dat deel van het kader. Het kader-eigenaarschap omvat het monitoren van lifecycle-wijzigingen in gerefereerde standaarden. | Nee — optioneel |

**Toelichting principes:** Het kader introduceert geen nieuwe principe-typen. Het verwijst naar bestaande enterprise principes en architectuurprincipes die van toepassing zijn binnen de scope van het kader. De coherentie zit in de bundeling: het kader maakt expliciet welke set principes samen van toepassing is op dit domein.

**Toelichting requirements en constraints:** Het kader introduceert geen nieuwe requirement- of constraint-typen. Het bundelt de requirements en constraints die binnen de scope van dit kader gelden tot een coherent geheel. De requirements en constraints zijn de concretisering van de toepasselijke principes voor dit specifieke domein.

**Toelichting patronen:** Patronen zijn aanbevolen oplossingsrichtingen, geen verplichte kader-elementen. Een kader kan bestaan zonder patronen (bijv. een compliance framework in een vroege fase). De relatie is een verwijzing vanuit het kader naar de pattern library, niet een containment-relatie. De pattern library is een zelfstandig instrument.

### 3.2 Relatie met de motivatieketen

De elementen binnen een kader volgen de motivatieketen zoals beschreven in het principes-document (§6.3):

```
Enterprise Principes / Enterprise Kaders
    │ (informeert + begrenst)
    ▼
KADER (scope-afbakening)
    │
    ├── Toepasselijke Principes (uit principes-repository)
    │       │ (Influence)
    │       ▼
    ├── Requirements (binnen scope van dit kader)
    │       │
    ├── Constraints (binnen scope van dit kader)
    │       │
    │       │ (Realization)
    │       ▼
    │   Core-elementen (Application, Process, Technology...)
    │
    └── Referentie → Pattern Library (optioneel)
```

**Kernpunt:** Het kader is de coherente bundeling en de scope-afbakening. De individuele elementen bestaan ook los in het metamodel — het kader voegt de samenhang, de scope en de normatieve governance toe. Het diagram hierboven is conceptueel (TOGAF-perspectief); de ArchiMate-modellering volgt in §4.

---

## 4. ArchiMate-modellering

### 4.1 Geen native "Framework"-element

**Eigen uitwerking — ArchiMate heeft geen "Framework"-element.**

ArchiMate 3.1 biedt geen enkelvoudig element voor een kader. Een kader is een samengesteld governance-instrument dat meerdere Motivation-elementen bundelt. De modellering vereist daarom een pragmatische aanpak.

### 4.2 Modellering als Grouping

Gebruik een ArchiMate **Grouping**-element om de bij elkaar horende principes, requirements en constraints visueel te bundelen als "Framework X". Dit is geen formeel metamodel-element maar maakt het kader zichtbaar als coherent geheel.

**Implementatie:**
- Maak een Grouping-element met de naam van het kader
- Plaats de toepasselijke Principles, Requirements en Constraints binnen de Grouping
- Leg relaties van de Grouping-inhoud naar core-elementen via Realization
- Leg relaties van enterprise Principles naar de toepasselijke Principles binnen het kader via Influence (informeert/begrenst)
- Leg bij patronen een Association-relatie van het kader (Grouping) naar het betreffende patroon in de pattern library — het patroon zit buiten de Grouping

### 4.3 Typische relaties

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Enterprise Principle** | Influence → | **Toepasselijk Principle (binnen kader)** | Enterprise principes informeren/begrenzen het kader |
| **Toepasselijk Principle** | Influence → | **Requirement (binnen kader)** | Principes leiden tot concrete eisen |
| **Toepasselijk Principle** | Influence → | **Constraint (binnen kader)** | Principes leggen beperkingen op |
| **Requirement / Constraint** | Realization → | *Core-elementen* | Eisen worden gerealiseerd in ontwerp |
| **Stakeholder** | Association → | **Grouping (Kader)** | Eigenaarschap van het kader |
| **Grouping (Kader)** | Association → | **Patroon (Pattern Library)** | Referentie naar aanbevolen patronen (optioneel) |

### 4.4 Typische views

| View | Inhoud |
|------|--------|
| **Kader Overzicht** | Grouping met alle toepasselijke principes, requirements, constraints; relaties naar enterprise principes |
| **Kader Realisatie** | Vanuit requirements (binnen kader) naar realiserende core-elementen |
| **Kader Motivatieketen** | Driver → Goal → Enterprise Principle → Toepasselijk Principle → Requirement → Realisatie |
| **Kader Transitie** | Requirements (binnen kader) met GAP-analyse: welke requirements zijn gerealiseerd per plateau |

### 4.5 Onderscheid TOGAF vs ArchiMate voor kaders

| Aspect | TOGAF | ArchiMate |
|--------|-------|-----------|
| **Rol** | Governance-instrument (normatief, comply or explain) | Informatiedrager (traceability, communicatie) |
| **Inhoud** | Template met alle metadata inclusief normatieve status, dispensaties, levenscyclus (zie §6) | Grouping met Motivation-elementen en relaties |
| **Beheer** | Kader-repository als bron van waarheid: eigenaar, status, dispensatieproces, versioning, adoption roadmap | Modelelementen gesynchroniseerd met de repository |
| **Gebruik** | Toetsen, handhaven, dispenseren, verantwoorden | Visualiseren, traceren, analyseren |

**Aanbeveling:** TOGAF = bron van waarheid voor alles wat het kader als governance-instrument betreft (normatieve status, dispensaties, eigenaarschap, levenscyclus, review-cyclus). ArchiMate = visualisatie en traceability: modelleer hetzelfde kader als Grouping zodat de relaties naar de motivatieketen en core-elementen zichtbaar en traceerbaar zijn. Synchroniseer periodiek.

**Concreet:** De normatieve status ("dit kader is approved"), het dispensatieregister ("deze teams hebben een dispensatie-ADR") en de levenscyclusinformatie ("inhoudelijke volwassenheid: 70%, adoptie: 40%") leven in de TOGAF governance-tooling, niet in het ArchiMate-model. Het ArchiMate-model toont de architecturale relaties — het is geen governance-administratie.

---

## 5. Kaders in doelarchitectuur vs. transitiearchitectuur

### 5.1 Het kader als entiteit met levenscyclus

**Eigen uitwerking — van belang bij transitie-architecturen op weg naar de doelarchitectuur.**

Een kader is een **stabiele entiteit** waarvan de inhoud en adoptie zich ontwikkelen over tijd. De entiteit zelf — naam, scope, domein — blijft constant. Wat verandert zijn twee dimensies die samen de levenscyclus beschrijven.

Dit is analoog aan hoe TOGAF Capability Increments behandelt (Ch.32, §32.3.1): de capability blijft dezelfde entiteit, maar wordt via increments stapsgewijs opgebouwd. Voor kaders: elk plateau kan een increment in inhoudelijke completheid én in adoptie opleveren.

### 5.2 Twee levenscyclusdimensies

| Dimensie | Beschrijving | Meetbaar via |
|---|---|---|
| **1. Inhoudelijke volwassenheid** | Hoe compleet, coherent en actueel is het kader? Welke principes, requirements, constraints zijn uitgewerkt, welke zijn nog wit vlak? | Completheidspercentage per element-type; aantal witte vlekken; datum laatste review |
| **2. Organisatorische adoptie & handhaving** | Hoe breed wordt het kader nageleefd, en wordt naleving actief gehandhaafd? | Percentage teams/domeinen op naleving; aantal actieve dispensatie-ADR's; gemiddelde resterende tijdshorizon van dispensaties |

**Waarom twee dimensies en niet drie:** Handhaving is een **kwaliteitskenmerk van adoptie**, geen onafhankelijke dimensie. Adoptie zonder handhaving is schijnadoptie — het kader is formeel ingevoerd maar wordt niet nageleefd. Handhaving zonder adoptie is scope-beperking — het kader geldt strikt maar bij een klein deel van de organisatie. In beide gevallen beschrijft de adoptie-as de werkelijke situatie; handhaving is metadata op die as (*waar* geadopteerd, *hoe strikt*, *hoeveel dispensaties*).

**Anti-patterns bij verwarring van dimensies:**
- **Inhoud volgt adoptie:** Het kader wordt inhoudelijk afgezwakt om het adopteerbaar te maken. Resultaat: een kader dat niemand uitdaagt.
- **Adoptie moet inhoud volgen:** Een compleet kader wordt door de strot van de organisatie geduwd die er niet klaar voor is. Resultaat: weerstand, schaduwprocessen, schijnadoptie.

### 5.3 Rol per architectuurperspectief

| Perspectief | Inhoudelijke volwassenheid | Organisatorische adoptie & handhaving |
|---|---|---|
| **Doelarchitectuur** | Volledig uitgewerkt, coherent, compleet. Alle principes, requirements en constraints zijn gedefinieerd. | Breed geadopteerd en gehandhaafd. Dispensaties zijn uitzonderingen. Kader is geïnternaliseerd in de organisatiecultuur. |
| **Transitiearchitectuur** | Mag incompleet zijn. Witte vlekken zijn acceptabel. Prioritering welke onderdelen eerst, op basis van urgentie en risico. | Gefaseerde adoptie. Dispensatie-ADR's documenteren bewuste, tijdelijke afwijkingen met tijdshorizon en herstelplan. |

**Transitie-realiteit:** Een kader kan bestaan als "aspiratief document" terwijl de praktijk er nog niet is. Dit is acceptabel, zolang twee dingen expliciet zijn: (1) dat het aspiratief is, en (2) dat er een adoption roadmap bij hoort.

### 5.4 Normatieve geldigheid vs. afdwingbaarheid

**Kernprincipe:** Een kader is **altijd normatief geldig** — ook in transitie, ook waar het (nog) niet volledig afdwingbaar is. Het zegt op elk moment: "dit is hoe het moet." Dat verandert niet.

Wat verandert is de **afdwingbaarheid**, en daarmee de manier waarop met afwijkingen wordt omgegaan:

| Fase | Normatieve geldigheid | Afdwingbaarheid | Omgang met afwijkingen |
|---|---|---|---|
| **Doelstaat** | Volledig geldig | Volledig afdwingbaar | Afwijkingen zijn uitzonderingen met formeel dispensatieproces. Default = naleving. |
| **Transitie** | Volledig geldig | Niet overal afdwingbaar | Afwijkingen worden beheerst via dispensatie-ADR's met tijdshorizon, eigenaar en herstelplan. Default = naleving waar mogelijk. |

**Drie governance-posities en hun beoordeling:**

1. **"Het kader geldt nog niet"** — Fout. Dan is het geen kader maar een guideline. De normatieve kracht en sturingsfunctie gaan verloren. Teams gaan cherry-picken.

2. **"Het kader geldt volledig, geen uitzonderingen"** — Fout. Negeert de transitierealiteit. Teams gaan het kader omzeilen of het wordt een papieren tijger. Of erger: naleving wordt geforceerd waar de organisatie het niet aankan, met weerstand als gevolg.

3. **"Het kader geldt, afwijkingen worden beheerst"** — Correct. Het kader is normatief. Elk team weet dat naleving de verwachting is. Maar als je er op dit moment niet aan kunt voldoen, documenteer je dat als een bewuste, tijdelijke afwijking (dispensatie-ADR) met een plan om te herstellen.

**Bij een guideline is niet-naleving een keuze. Bij een kader is niet-naleving een schuld die je aflost.**

### 5.5 ADR's als dispensatie-instrument

ADR's zijn van nature transitie-instrumenten — van belang bij transitie-architecturen op weg naar de doelarchitectuur. Voor kaders functioneren ze specifiek als **dispensatie-instrument**:

- Elke significante afwijking van het kader wordt vastgelegd als dispensatie-ADR
- De dispensatie-ADR bevat: welke requirement of constraint binnen het kader wordt afgeweken, waarom, welk risico dat meebrengt, wat het herstelplan is, en wanneer de dispensatie wordt herzien
- Dispensatie-ADR's hebben een expliciete **tijdshorizon** — ze zijn per definitie tijdelijk
- Het aantal actieve dispensatie-ADR's is een directe maat voor de adoptie & handhavingsdimensie

**In de doelstaat** zijn dispensatie-ADR's historische documenten: de afwijkingen zijn hersteld en de rationale is archief. Een doelstaat met veel actieve dispensatie-ADR's is eigenlijk nog een transitiestaat.

### 5.6 De governance-paradox

De governance-paradox stelt: governance is het meest nodig in transitie, maar ook het minst volwassen dan. Voor kaders vertaalt dit zich naar: het normatieve gehalte van het kader creëert de meeste governance-last (dispensatiebeheer) precies op het moment dat de governance-capaciteit het laagst is.

Dit is geen fout — het is een bewuste investering. De dispensatie-ADR's zijn het bewijs dat de governance werkt, niet dat ze faalt. De governance-intensiteit van het kader schaalt mee met de fase: investeer governance-capaciteit waar de onzekerheid het grootst is (transitie), niet waar het kader al geïnternaliseerd is (doelstaat).

---

## 6. Kader-template

### 6.1 Template

**Eigen uitwerking — TOGAF definieert geen standaard framework-template.**

De template is gebaseerd op de principes-template (TOGAF Ch.23, §23.3), het TOGAF Content Metamodel (Ch.34, §34.6), de classificatie uit het principes-document en de levenscyclusdimensies uit §5.

| Component | Beschrijving | Bron/Analogie |
|---|---|---|
| **Name** | Kort, herkenbaar, domein-identificerend | Principes-template (Ch.23, §23.3) |
| **Key Domain** | Enterprise / Architecture | TOGAF Ch.23, §23.1 |
| **Scope** | Enterprise / Subsidiary (+ org-eenheid) / Segment (+ portfolio/programma). Bij architecture key domain aanvullend: Category (Bus/Data/App/Tech/Integration/Guiding) | Principes-classificatie |
| **Statement** | Wat het kader regelt, voor wie, en waarom het normatief is | Principes-template |
| **Rationale** | Business-voordelen, relatie met enterprise principes en hoger gelegen kaders, strategische noodzaak | Principes-template |
| **Toepasselijke principes** | Welke bestaande principes (enterprise en/of architectuur) het kader bundelt (verwijzingen naar principes-repository) | Motivatieketen |
| **Requirements** | Concrete eisen die binnen de scope van dit kader gelden | TOGAF/ArchiMate Motivation |
| **Constraints** | Beperkingen die binnen de scope van dit kader gelden | TOGAF/ArchiMate Motivation |
| **Referentie patronen** | Verwijzingen naar pattern library: welke patronen worden aanbevolen (optioneel) | Pattern library |
| **Eigenaar** | Persoon/rol verantwoordelijk voor het kader | Governance-inrichting |
| **Governance-forum** | ARB/EARB of ander gremium dat dispensaties accordeert | TOGAF Ch.50 |
| **Status** | Draft / Approved / Under Review / Retired | Principes-metadata |
| **Versie** | Versienummer van de huidige inhoud | Levenscyclusbeheer |
| **Inhoudelijke volwassenheid** | Completheidspercentage per element-type; witte vlekken; datum laatste review | Levenscyclusdimensie 1 (§5.2) |
| **Organisatorische adoptie & handhaving** | Percentage teams/domeinen op naleving; aantal actieve dispensatie-ADR's; gemiddelde resterende tijdshorizon | Levenscyclusdimensie 2 (§5.2) |
| **Doelstaat-beschrijving** | Hoe ziet volledige adoptie eruit? Wanneer is het kader "klaar"? | Van belang bij transitie-architecturen op weg naar de doelarchitectuur |
| **Adoption roadmap** | Gefaseerd plan voor adoptie: welke teams/domeinen wanneer, welke afhankelijkheden | Van belang bij transitie-architecturen op weg naar de doelarchitectuur |
| **Relatie met management frameworks** | Hoe verhoudt dit kader zich tot Portfolio Mgmt, Operations, Solution Dev, Business Capability Mgmt? | TOGAF §6.2.5 |
| **Brug-relatie** | Welke enterprise principes en hoger gelegen kaders informeren/begrenzen dit kader? | Principes-document §1.3; hiërarchie §2.4 |

### 6.2 Repository-metadata per kader

| Attribuut | Waarden / Beschrijving |
|-----------|----------------------|
| **ID** | Unieke identifier |
| **Naam** | Canonical naam (bijv. "Digitaliseringskader") |
| **Key Domain** | Enterprise / Architecture |
| **Scope Type** | Enterprise / Subsidiary / Segment |
| **Category** | Bus/Data/App/Tech/Integration/Guiding (alleen bij architecture key domain) |
| **Eigenaar** | Persoon/rol |
| **Governance-forum** | ARB/EARB/ander gremium |
| **Status** | Draft / Approved / Under Review / Retired |
| **Versie** | Huidige versie-aanduiding |
| **Inhoudelijke volwassenheid** | Score of kwalificatie |
| **Adoptie & handhaving** | Score of kwalificatie |
| **Aantal actieve dispensaties** | Getal |
| **Toepasselijke principes** | Verwijzingen naar principes-repository |
| **Referentie patronen** | Verwijzingen naar pattern library |
| **Brug-relatie enterprise principes** | Welke enterprise principes informeren/begrenzen |
| **Brug-relatie hoger gelegen kaders** | Welke kaders informeren/begrenzen |
| **Datum laatste review** | Datum |
| **Volgende geplande review** | Datum |

---

## 7. Governance-inrichting

### 7.1 Eigenaarschap

| Kader-type | Eigenaar | Goedkeurend orgaan |
|---|---|---|
| **Enterprise kader** | ExCo/Board-niveau of gedelegeerd aan Chief Architect | EARB of equivalent |
| **Subsidiary kader** | Hoofd van de organisatie-eenheid (CIO, CHRO, etc.) | Subsidiary governance board |
| **Architectuurkader** | Domeinarchitect als inhoudelijk eigenaar | ARB |
| **Segment-kader** | Portfolio/programma-architect | Segment governance board |

### 7.2 Samenhang-verantwoordelijkheid

De eigenaar van een hoger gelegen kader is verantwoordelijk voor het bewaken van de samenhang met lager gelegen kaders:

- **Enterprise kader-eigenaar** bewaakt alignment van subsidiary kaders en architectuurkaders met het enterprise kader
- **Architectuurkader-eigenaar** bewaakt alignment van segment-kaders met het architectuurkader
- Bij conflicten tussen kaders op hetzelfde niveau escaleert de governance naar het hoger gelegen kader of het governance-forum (ARB/EARB)

Dit is analoog aan de hiërarchie bij principes: enterprise principes zijn altijd leidend, subsidiary en segment principes moeten hiermee aligned zijn (principes-document §7, vuistregel 2).

### 7.3 Dispensatieproces

Het dispensatieproces voor kaders is zwaarder dan voor individuele principes, omdat een kaderafwijking per definitie meerdere samenhangende requirements raakt:

1. **Aanvraag:** Team documenteert welke requirement(s) of constraint(s) binnen het kader worden afgeweken en waarom
2. **Impact-analyse:** Welke principes worden geraakt? Welke risico's ontstaan? Is er impact op hoger gelegen kaders?
3. **Herstelplan:** Concreet plan met tijdshorizon om de afwijking te herstellen
4. **Accordering:** Door governance-forum (ARB/EARB) met expliciete tijdshorizon
5. **Registratie:** Als dispensatie-ADR met eigenaar, tijdshorizon en herzieningsmoment
6. **Herziening:** Op het afgesproken herzieningsmoment: is de dispensatie nog nodig? Kan het herstelplan worden versneld?

### 7.4 Review-cyclus

- Review kaders bij wijzigingen in strategie, fusies, reorganisaties of nieuwe regelgeving
- Periodieke review: minimaal jaarlijks, of bij significante verandering in het domein
- Monitor of de governance-last proportioneel is aan de business-waarde die het kader beschermt
- Monitor het aantal actieve dispensatie-ADR's als indicator voor adoptie-voortgang

### 7.5 Proportionaliteit

Een kader moet proportioneel zijn aan de business-waarde die het beschermt. Te veel kaders of te zware kaders reduceren flexibiliteit en creëren governance-overhead die niet in verhouding staat tot het risico dat wordt gemitigeerd. Dit geldt des te meer in transitie, waar de governance-capaciteit beperkt is.

**Richtlijn:** Definieer het minimale aantal kaders dat nodig is om de strategische risico's beheersbaar te houden. Elk kader dat je introduceert, moet ook gemanaged worden — inclusief eigenaarschap, dispensatieproces, review-cyclus en adoption roadmap.

---

## 8. Vuistregels

1. **Een kader is normatief, geen guideline.** Bij een guideline is niet-naleving een keuze. Bij een kader is niet-naleving een schuld die je aflost. Als teams het kader vrijblijvend kunnen negeren, herdefinieer het als guideline of versterk de governance.

2. **Een kader is samengesteld, geen principe.** Een kader bundelt toepasselijke principes, requirements en constraints tot een coherent geheel. Een losstaand principe is geen kader — het mist de samenhang en het normatieve gewicht van de bundeling.

3. **Een kader volgt dezelfde key domains als principes.** Enterprise kaders en architectuurkaders zijn fundamenteel verschillende instrumenten met verschillende eigenaren en classificatie-assen. Verwar ze niet.

4. **Een kader is een entiteit met levenscyclus.** De entiteit blijft constant; inhoudelijke volwassenheid en organisatorische adoptie & handhaving ontwikkelen zich over tijd. Beheer het kader als één entiteit door plateaus heen.

5. **Een kader is altijd normatief geldig, ook in transitie.** Wat verandert is de afdwingbaarheid, niet de geldigheid. Afwijkingen in transitie worden beheerst via dispensatie-ADR's, niet getolereerd als keuze.

6. **Modelleer een kader als Grouping in ArchiMate.** Er is geen native element. Gebruik Grouping om de coherente bundeling zichtbaar te maken en leg relaties naar de motivatieketen. De bron van waarheid blijft TOGAF/governance-tooling.

7. **Koppel elk kader aan enterprise principes en hoger gelegen kaders.** Een kader zonder traceerbare link naar enterprise principes mist mandaat. De informeert/begrenst-relatie is niet optioneel. De eigenaar van het hoger gelegen kader bewaakt de samenhang.

8. **Houd het aantal kaders beheersbaar: maximaal 5 tot 8 actieve kaders per governance-forum.** Elk kader vereist governance-capaciteit (eigenaarschap, dispensatieproces, review-cyclus, adoption roadmap). Een governance-forum dat meer dan 8 kaders actief beheert, riskeert dat dispensatieverzoeken, review-cycli en samenhangbewaking verwatert. Bij meer dan 8: evalueer of kaders geconsolideerd kunnen worden of het governance-forum opgesplitst moet worden. Dit getal is geen TOGAF-voorschrift maar afgeleid uit het proportionaliteitsprincipe en span-of-control-logica voor governance-aandacht.

9. **Gebruik dispensatie-ADR's als adoptie-indicator.** Het aantal actieve dispensaties, hun resterende tijdshorizon en het herstelpercentage zijn directe maten voor de voortgang van het kader.

10. **Waak voor de twee anti-patterns.** Zwak het kader niet inhoudelijk af om het adopteerbaar te maken (inhoud volgt adoptie). Forceer geen naleving waar de organisatie er niet klaar voor is (adoptie moet inhoud volgen). De twee levenscyclusdimensies mogen uit de pas lopen — dat is transitierealiteit.

11. **Patronen zijn optioneel, niet verplicht.** Een kader kan bestaan zonder patronen. Patronen worden gerefereerd vanuit het kader, niet gecontaineerd door het kader. De pattern library is een zelfstandig instrument.

---

## Bronverwijzingen

| Onderwerp | Bron |
|-----------|------|
| Management Frameworks, coëxistentie met TOGAF | TOGAF 9.1, Preliminary Phase, §6.2.5 |
| Enterprise & Architecture Principles, twee key domains | TOGAF 9.1, Chapter 23, §23.1 |
| Subsidiary Principles | TOGAF 9.1, Chapter 23, §23.1 |
| Segment Principles | TOGAF 9.1, Chapter 23, §23.1 |
| Principle Template (Name/Statement/Rationale/Implications) | TOGAF 9.1, Chapter 23, §23.3 |
| Principle Category attribuut (Content Metamodel) | TOGAF 9.1, Chapter 34, §34.6 |
| Capability Increments (analogie voor levenscyclus) | TOGAF 9.1, Chapter 32, §32.3.1 |
| Architecture Landscape Levels | TOGAF 9.1, Chapter 20, §20.2 |
| Architecture Governance | TOGAF 9.1, Chapter 50 |
| Architecture Definition Document (baseline/transition/target) | TOGAF 9.1, Part IV, §36.2.3 |
| ArchiMate Principle element | ArchiMate 3.1 Specification, Motivation Aspect |
| ArchiMate Grouping element | ArchiMate 3.1 Specification, Relationships and Grouping |
| ArchiMate Influence-relatie | ArchiMate 3.1 Specification, Relationships |
| Doelarchitectuur vs. Transitiearchitectuur | Expliciet te interpreteren vanuit TOGAF en ArchiMate — governance paradox, dispensatie-ADR's als transitie-instrument |
| Principes-guideline | `references/principes-samenvatting-metamodel.md` |
| Capabilities-guideline | `references/capabilities-samenvatting-metamodel.md` |

---

**Versie:** 1.2
**Datum:** 1 april 2026
**Status:** Concept voor review

**Eigen uitwerkingen in dit document (niet TOGAF-voorschrift):**
- Kader-definitie als samengesteld, normatief governance-instrument (§1.1)
- Lakmoestest kader vs. guideline (§1.2)
- Hiërarchie en samenhang-verantwoordelijkheid tussen kaders (§2.4)
- Samenstellende elementen met onderscheid verplicht/optioneel (§3.1)
- Onderscheid normatieve geldigheid vs. afdwingbaarheid (§5.4)
- Twee levenscyclusdimensies (§5.2)
- Kader-template (§6.1)
- ArchiMate Grouping-benadering (§4.2)
