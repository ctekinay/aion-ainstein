# Doel- en Transitiearchitecturen — Samenvatting voor Metamodel (TOGAF & ArchiMate)

> **Doel:** Deze samenvatting dient als basis om doel- en transitiearchitecturen correct te interpreteren en te positioneren binnen het architectuurlandschap. Alle definities en verwijzingen zijn gebaseerd op TOGAF 9.1 (G116), TOGAF 10 en de ArchiMate 3.1-standaard.
>
> **Afbakening:** Dit document beschrijft wat TOGAF en ArchiMate definiëren over baseline, target en transition architectures, en hoe deze zich verhouden tot het Architecture Landscape, de ADM en het ArchiMate Implementation & Migration-aspect. Het bevat geen organisatiespecifieke keuzes over governance-inrichting, goedkeuringsniveaus of werkwijzen.

---

## Inleiding

TOGAF onderscheidt drie architectuurtoestanden die het verandertraject van een enterprise beschrijven: de **Baseline Architecture** (huidige toestand), de **Target Architecture** (gewenste toestand) en eventuele **Transition Architectures** (tussentoestanden). Dit onderscheid is fundamenteel voor het Architecture Development Method (ADM) en raakt de manier waarop architectuurwerk wordt georganiseerd, gepland en bestuurd.

ArchiMate 3.1 biedt via het Implementation & Migration-aspect de elementen om deze toestanden te modelleren: Plateau, Gap, Work Package en Deliverable.

> **Relatie met principes-document:** Doel- en transitiearchitecturen worden gestuurd door enterprise principes en architectuurprincipes. De informeert/begrenst-relatie (TOGAF Ch.23, §23.1) geldt ook hier: enterprise principes informeren en begrenzen de inhoud van doelarchitecturen. Zie `references/principes-samenvatting-metamodel.md`.
>
> **Relatie met capabilities-document:** Capability increments zijn de drivers voor Transition Architectures (TOGAF Ch.32, §32.3.1). Zie `references/capabilities-samenvatting-metamodel.md`. *Let op: dit bestand bestaat in het project maar is nog niet geplaatst in de references-directory van de oracle skill.*
>
> **Relatie met kaders-document:** Kaders zijn altijd normatief geldig, ook in transitie. De afdwingbaarheid verandert; de geldigheid niet. Zie `references/kaders-samenvatting-metamodel.md`.

---

## 1. Definities

### 1.1 Baseline Architecture

**Bron:** TOGAF 9.1, Definitions, §3.14

**Definitie:** *"The existing defined architecture (or set of architectures), before any changes are applied."* De baseline is de vastgelegde beschrijving van de huidige toestand.

**Kenmerken:**
- Beschrijft de "as-is" situatie
- Kan op verschillende niveaus van detail worden beschreven; TOGAF stelt dat baseline en target niet op hetzelfde detailniveau hoeven te worden beschreven (Ch.7, §7.4.6)
- Dient als vertrekpunt voor gap-analyse met de target architecture

### 1.2 Target Architecture (Doelarchitectuur)

**Bron:** TOGAF 10, ADM Phases B, C, D; ISO/IEC/IEEE 42010:2011

**Definitie:** De Target Architecture beschrijft de gewenste toekomstige toestand van de architectuur. TOGAF beschrijft deze als *"the future state of the architecture being developed"* in ADM Phases B (Business), C (Information Systems) en D (Technology).

**Kenmerken:**
- Beschrijft de "to-be" situatie — wat de enterprise wil zijn
- Wordt ontwikkeld in ADM Phases B, C en D, gescheiden van de transitieplanning in Phase E
- Belichaamt de strategische architectuurbeslissingen (TOGAF Ch.5, §5.5.3: *"They embody only the key strategic architectural decisions"*)
- Is evolutionair van aard en vereist periodieke review op basis van veranderende business requirements en technologie-ontwikkelingen (TOGAF Ch.5, §5.5.3)
- Blijft relatief generiek en is daardoor minder kwetsbaar voor veroudering dan transitiearchitecturen (TOGAF Ch.5, §5.5.3)
- ISO/IEC/IEEE 42010:2011 definieert de target architecture als de "intended architecture" die voldoet aan stakeholder concerns

**Relatie met stakeholder commitment:** TOGAF Phase A (Architecture Vision) vereist stakeholder commitment als prerequisite voor architectuurontwikkeling. Een doelarchitectuur zonder stakeholder buy-in mist de strategische verankering om gerealiseerd te worden (TOGAF Ch.7, §7.1–7.2).

### 1.3 Transition Architecture (Transitiearchitectuur)

**Bron:** TOGAF 10, ADM Phase E; TOGAF 9.1, Ch.5, §5.5.3

**Definitie:** TOGAF 10 beschrijft Transition Architectures als architecturen die *"the enterprise at architecturally significant points in time between the Baseline and Target Architectures"* tonen.

**Kenmerken:**
- Beschrijft tussentoestanden op weg van baseline naar target
- Wordt ontwikkeld in ADM Phase E (Opportunities and Solutions), ná de target architecture
- Is incrementeel van aard en zou in principe niet moeten evolueren tijdens de implementatiefase van het betreffende increment, om het "moving target syndrome" te voorkomen (TOGAF Ch.5, §5.5.3)
- Bevat gedetailleerdere architectuurbeslissingen dan de target architecture; deze beslissingen worden bewust zo laat mogelijk genomen om responsiviteit te behouden (TOGAF Ch.5, §5.5.3)
- Is per definitie tijdelijk: elke transitiearchitectuur is een tussenstap, geen einddoel

**Fundamentele relatie met target:** Transitiearchitecturen zijn middelen om de doelarchitectuur te bereiken. TOGAF positioneert ze als *"increments or plateaus, each in line with and converging on the Target Architecture Descriptions"* (Ch.5, §5.5.3).

### 1.4 Onderscheid samengevat

| Aspect | Baseline | Target | Transition |
|---|---|---|---|
| **Beschrijft** | Huidige toestand | Gewenste eindtoestand | Tussentoestand |
| **Karakter** | Feitelijk, vastgesteld | Aspiratief, strategisch | Pragmatisch, tijdelijk |
| **ADM-fase** | Input voor alle fasen | Phases B, C, D | Phase E |
| **Evolutie** | Verandert met de realiteit | Periodieke review bij strategiewijziging | Stabiel tijdens implementatie van het increment |
| **Detailniveau** | Naar behoefte | Relatief generiek, strategische keuzes | Gedetailleerder, operationele keuzes |
| **Houdbaarheid** | Veroudert continu | Minder kwetsbaar voor veroudering | Meer kwetsbaar voor veroudering |

---

## 2. Positionering in het Architecture Landscape

### 2.1 Architecture Landscape Levels

**Bron:** TOGAF 9.1, Chapter 20, §20.2

Het Architecture Landscape kent drie niveaus van granulariteit:

| Level | Omschrijving | Focus |
|-------|-------------|-------|
| **Strategic Architecture** | Organizing framework voor operational & change activity op executive niveau | Richting, visie, enterprise-brede capability map |
| **Segment Architecture** | Organizing framework op programma/portfolio niveau | Roadmaps, portfolio-sturing, programma-governance |
| **Capability Architecture** | Organizing framework voor change activity die capability increments realiseert | Concrete veranderstappen, releases |

**Belangrijk:** Dit zijn niveaus van granulariteit, geen containment-hiërarchie. TOGAF stelt expliciet: *"There is no definitive organizing model for architecture, as each enterprise should adopt a model that reflects its own operating model"* (TOGAF Ch.20, §20.2).

### 2.2 Baseline, Target en Transition op elk level

TOGAF beschrijft dat een enterprise door meerdere architectuurinstanties kan worden gerepresenteerd, elk op een specifiek punt in de tijd: *"One architecture instance will represent the current enterprise state (the 'as-is', or baseline). Another architecture instance, perhaps defined only partially, will represent the ultimate target end-state (the 'vision'). In-between, intermediate or 'Transition Architecture' instances may be defined"* (Ch.5, §5.5.3).

Dit geldt op elk landscape level:
- Op **Strategic level** beschrijft de target architecture de enterprise-brede gewenste eindtoestand; transitiearchitecturen zijn macro-plateaus over meerdere jaren.
- Op **Segment level** beschrijft de target architecture de gewenste eindtoestand voor een portfolio of programma; transitiearchitecturen zijn programma-plateaus.
- Op **Capability level** beschrijft de target architecture de gewenste eindtoestand per capability; transitiearchitecturen zijn capability increments.

### 2.3 Scope-dimensies

**Bron:** TOGAF 9.1, Chapter 5, §5.5

TOGAF definieert vier dimensies om de scope van architectuurwerk af te bakenen:

| Dimensie | Raakt baseline/target/transition | Toelichting |
|----------|:---:|---|
| **Breadth** | ● | Welk deel van de enterprise is in scope? |
| **Depth** | ● | Op welk detailniveau? Correleert met landscape level. |
| **Time Period** | ● | Welke tijdshorizon? Bepaalt of transitiearchitecturen nodig zijn. |
| **Architecture Domains** | ● | Welke domeinen (B/D/A/T) zijn in scope? |

De time period-dimensie is specifiek relevant voor het onderscheid target/transition: een korte tijdshorizon kan een directe overgang (big-bang) toelaten; een langere tijdshorizon vereist typisch transitiearchitecturen.

### 2.4 Twee ontwikkelingsbenaderingen

**Bron:** TOGAF 9.1, Chapter 19, §19.4

TOGAF beschrijft twee benaderingen voor architectuurontwikkeling:

**Baseline First:** Een assessment van het baseline-landschap wordt gebruikt om probleemgebieden en verbetermogelijkheden te identificeren. Geschikt wanneer de baseline complex is, niet goed begrepen of niet overeengekomen. Gebruikelijk bij hoge mate van autonomie.

**Target First:** De target solution wordt eerst uitgewerkt en vervolgens teruggemapped naar de baseline om veranderactiviteit te identificeren. Geschikt wanneer een target state op hoog niveau is overeengekomen.

TOGAF stelt dat wanneer de baseline breed begrepen is, een target-first benadering typisch meer waarde oplevert (Ch.19, §19.4).

---

## 3. ADM-fasen en het onderscheid target/transition

### 3.1 Phase A: Architecture Vision

Phase A ontwikkelt een high-level aspirational vision en vereist stakeholder commitment (Ch.7, §7.1). De scope wordt bepaald, inclusief de tijdsperiode en het aantal tussentijdse periodes (Ch.7, §7.4.6). De Business Transformation Readiness Assessment (Ch.30) wordt hier uitgevoerd om de verandercapaciteit van de organisatie te beoordelen.

**Relevant voor target/transition:** Phase A bepaalt of transitiearchitecturen nodig zijn (scope-beslissing) en assesst de readiness van de organisatie om verandering te absorberen.

### 3.2 Phases B, C, D: Architecture Development

In deze fasen wordt de Target Architecture ontwikkeld per domein: Business (B), Information Systems (C), Technology (D). TOGAF beschrijft dit expliciet als het ontwikkelen van de *future state*.

**Relevant voor target/transition:** Dit is waar de doelarchitectuur ontstaat. Transitieoverwegingen spelen hier nog geen formele rol — die komen in Phase E.

### 3.3 Phase E: Opportunities and Solutions

Phase E vertaalt de Target Architecture naar een implementatie- en migratiestrategie. Hier worden Transition Architectures gedefinieerd als *"architecturally significant points in time between the Baseline and Target Architectures"*.

**Activiteiten in Phase E:**
- Gap-analyse tussen baseline en target
- Identificatie van werk pakketten en projecten
- Definiëren van transitiearchitecturen als plateaus
- Consolidatie van het geheel in een Architecture Roadmap

### 3.4 Phase F: Migration Planning

Phase F vertaalt de Architecture Roadmap naar een gedetailleerd migratieplan, inclusief het prioriteren van projecten en het toewijzen van resources aan de transitiestappen.

**Relevant voor target/transition:** Phase F is waar de transitiearchitecturen worden vertaald naar uitvoerbare plannen. De architectuurbeslissingen zijn genomen; nu volgt de planning.

---

## 4. ArchiMate-modellering

### 4.1 Implementation & Migration-aspect

ArchiMate 3.1 biedt vier elementen in het Implementation & Migration-aspect die direct relevant zijn voor het modelleren van baseline, target en transition:

| Element | Definitie | Rol |
|---|---|---|
| **Plateau** | *"A relatively stable state of the architecture that exists during a limited period of time."* | Modelleert elke stabiele toestand: baseline, elke transitie, en target. |
| **Gap** | *"A statement of difference between two plateaus."* | Modelleert het verschil tussen opeenvolgende plateaus, en daarmee de veranderactiviteit. |
| **Work Package** | *"A series of actions identified and designed to achieve specific results within specified time and resource constraints."* | Modelleert de projecten/initiatieven die een plateau realiseren. |
| **Deliverable** | *"A precisely-defined outcome of a work package."* | Modelleert de concrete resultaten van een work package. |

### 4.2 Typische relaties

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Plateau** | Composition → | *Architectuurelementen* | Een plateau bevat de elementen die in die toestand bestaan |
| **Plateau** | Triggering → | **Plateau** | Het ene plateau triggert het volgende (sequentie) |
| **Gap** | Association → | **Plateau** (2x) | Een gap beschrijft het verschil tussen twee plateaus |
| **Work Package** | Realization → | **Plateau** | Work packages realiseren de overgang naar een plateau |
| **Work Package** | Realization → | **Deliverable** | Work packages leveren deliverables op |

### 4.3 Modelleren van baseline, transition en target als Plateaus

In ArchiMate is een Plateau het modelleringselement voor elke stabiele toestand — zowel baseline, transitietoestanden als target:

```
Plateau (Baseline)
    │
    │  Gap 1 ──── Work Package(s)
    ▼
Plateau (Transitie 1)
    │
    │  Gap 2 ──── Work Package(s)
    ▼
Plateau (Transitie 2)
    │
    │  Gap 3 ──── Work Package(s)
    ▼
Plateau (Target)
```

**Elk Plateau** bevat via Composition de architectuurelementen (Business Process, Application Component, Technology Service, etc.) die in die toestand bestaan. De **Gap** tussen twee opeenvolgende Plateaus beschrijft wat er verandert. De **Work Packages** beschrijven hoe de verandering wordt gerealiseerd.

### 4.4 Relatie met Motivation-elementen

De motivatieketen (Driver → Goal → Principle → Requirement/Constraint) stuurt de inhoud van doelarchitecturen. Via de Realization-relatie van Requirements/Constraints naar core-elementen die in het target Plateau zijn opgenomen, is traceerbaarheid geborgd van "waarom" naar "wat".

```
Driver ──▶ Goal ──▶ Principle ──▶ Requirement
                                        │
                                  (Realization)
                                        ▼
                              Core-element (in Plateau Target)
```

### 4.5 Relatie met Strategy-elementen

Capability increments zijn de drivers voor Transition Architectures (TOGAF Ch.32, §32.3.1). In ArchiMate wordt dit gemodelleerd via:

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Capability** | Serving → | **Goal / Outcome** | Capability draagt bij aan doelen |
| **Work Package** | Realization → | **Capability** (increment) | Werkpakketten realiseren capability increments |
| **Work Package** | Realization → | **Plateau** | Werkpakketten realiseren de overgang naar een plateau |

De keten is: Capability → (increment via) Work Package → Plateau. Hierdoor zijn capability increments traceerbaar naar specifieke transitie-plateaus.

---

## 5. Governance-elementen en het onderscheid target/transition

**Logische conclusie uit TOGAF:** TOGAF beschrijft governance-instrumenten (principes, standaarden, patronen, ADR's) als onderdeel van het Architecture Governance Framework (Ch.50) en het Content Metamodel (Ch.34). TOGAF beschrijft daarnaast dat target architectures strategisch en generiek zijn, terwijl transition architectures gedetailleerd en tijdelijk zijn (Ch.5, §5.5.3). De onderstaande differentiatie per perspectief is niet letterlijk in TOGAF beschreven, maar volgt logisch uit deze twee TOGAF-posities: als de aard van target en transition fundamenteel verschilt, dan functioneren dezelfde governance-instrumenten daarbinnen ook fundamenteel anders. Bij het toepassen van deze paragraaf dient altijd te worden benoemd dat het een logische conclusie uit TOGAF betreft, geen letterlijk voorschrift.

### 5.1 Governance-instrumenten functioneren anders per perspectief

Governance-instrumenten (principes, kaders, ADR's, patronen, standaarden, richtlijnen) functioneren fundamenteel anders in een doelarchitectuur dan in een transitiearchitectuur:

| Instrument | In doelarchitectuur | In transitiearchitectuur |
|---|---|---|
| **Enterprise principes** | Volledig van toepassing, zonder compromis | Leidend, maar tijdelijke afwijkingen mogelijk met dispensatie |
| **Architectuurprincipes** | Volledig geïmplementeerd en gehandhaafd | Gefaseerd ingevoerd; twee-sporen aanpak (greenfield vs. brownfield) |
| **Kaders** | Normatief geldig en volledig afdwingbaar | Normatief geldig; afdwingbaarheid groeit gefaseerd |
| **ADR's** | Historische documenten — beslissingen zijn geabsorbeerd in standaarden | Primair governance-instrument — documenteren beslissingen onder onzekerheid |
| **Patronen (Architecture)** | Stabiel in de pattern library, breed toegepast | Ontstaan bottom-up uit projectpraktijk; groeiende library |
| **Patronen (Design)** | Gestandaardiseerd, organisatiebreed consistent | Per project/domein geïntroduceerd; tijdelijke inconsistentie acceptabel |
| **Standaarden** | Volledig geadopteerd; afwijkingen zijn uitzonderingen | Twee standaarden kunnen tijdelijk naast elkaar bestaan (technische schuld) |
| **Richtlijnen** | Volledig uitgewerkt en up-to-date | Gefaseerd uitgewerkt; witte vlekken tijdelijk acceptabel |
| **RACI** | Stabiel, geïnternaliseerd in organisatiecultuur | Dynamisch, expliciet sturend bij organisatieverandering |
| **Governance mechanismen (ARB/EARB)** | Lichtgewicht, routinematig | Zwaarder belast; meer uitzonderingen en escalaties |

### 5.2 ADR's als transitie-instrument

**Kernobservatie:** ADR's (Architecture Decision Records) zijn van nature transitie-instrumenten. Ze documenteren bewuste keuzes *onder onzekerheid en constraint*. In een stabiele doelarchitectuur zijn die keuzes geabsorbeerd in principes, standaarden en tooling. Een doelarchitectuur met veel actieve ADR's is feitelijk nog een transitiearchitectuur.

### 5.3 Patronen als verbindende schakel

Patronen verbinden transitie en doel. Ze ontstaan in de transitie (bottom-up, uit projectpraktijk) en worden verankerd in de doelarchitectuur (top-down, als stabiel referentiemodel). De pattern library groeit van transitie-instrument naar doelarchitectuur-fundament.

---

## 6. Business Transformation Readiness Assessment

**Bron:** TOGAF 9.1, Chapter 30; ADM Phase A (Ch.7, §7.4.5)

TOGAF schrijft voor dat in Phase A een Business Transformation Readiness Assessment wordt uitgevoerd. Dit assessment beoordeelt readiness factors die de verandercapaciteit van de organisatie bepalen:

1. Bepaal readiness factors die de organisatie zullen beïnvloeden
2. Presenteer readiness factors met maturity models
3. Beoordeel de readiness factors inclusief ratings
4. Beoordeel risico's per readiness factor en identificeer verbeteracties
5. Werk deze acties uit in Phase E en F (Implementation and Migration Plans)

**Relevantie voor target/transition:** Het assessment wordt uitgevoerd *vóór* architectuurontwikkeling (Phases B, C, D) start. De resultaten bepalen de scope van het architectuurwerk, identificeren activiteiten binnen het architectuurproject, en leggen risicogebieden bloot. De readiness van de organisatie — inclusief het vermogen om verandering te absorberen — is daarmee een bepalende factor voor de noodzaak en omvang van transitiearchitecturen.

---

## 7. Vuistregels

1. **Target Architecture ontstaat in Phase B–D, Transition Architecture in Phase E.** Dit is een bewuste scheiding in TOGAF: eerst bepalen waar je heen wilt, dan bepalen hoe je er komt.

2. **Transition Architectures convergeren altijd op de Target Architecture.** TOGAF stelt dit expliciet (Ch.5, §5.5.3). Een transitiearchitectuur die niet traceerbaar bijdraagt aan de target is per definitie niet aligned.

3. **Target Architectures zijn generiek, Transition Architectures zijn gedetailleerd.** De target belichaamt strategische keuzes; de transitie bevat operationele keuzes die zo laat mogelijk worden genomen (TOGAF Ch.5, §5.5.3).

4. **Transition Architectures zijn stabiel tijdens implementatie.** TOGAF waarschuwt voor het "moving target syndrome": transitiearchitecturen zouden niet moeten evolueren tijdens de implementatie van het betreffende increment (Ch.5, §5.5.3). Dit vereist korte implementatiecycli (typisch minder dan twee jaar).

5. **Target Architectures zijn minder kwetsbaar voor veroudering.** Doordat ze generiek blijven en alleen strategische keuzes bevatten, zijn ze duurzamer dan de gedetailleerde transitiearchitecturen (TOGAF Ch.5, §5.5.3).

6. **Readiness Assessment vóór architectuurontwikkeling.** De Business Transformation Readiness Assessment in Phase A bepaalt of en hoeveel transitiestappen nodig zijn. Dit is geen optionele stap.

7. **In ArchiMate is elk stabiel punt een Plateau.** Baseline, elke transitietoestand en target worden alle gemodelleerd als Plateau. Het verschil zit in de tijdelijkheid en de Composition: welke elementen bevat het Plateau?

8. **Gaps beschrijven verandering, niet tekortkomingen.** Een Gap in ArchiMate is het verschil tussen twee Plateaus — het beschrijft wat er verandert, niet wat er "fout" is. Gaps zijn neutraal.

9. **Capability increments drijven Transition Architectures.** De link tussen capability-based planning en transitieplanning loopt via: Capability → Work Package → Plateau (TOGAF Ch.32, §32.3.1).

10. **Governance-instrumenten functioneren anders per perspectief.** Dezelfde instrumenten (principes, kaders, standaarden) gedragen zich anders in target (stabiel, geïnternaliseerd) versus transition (dynamisch, expliciet sturend). Dit is geen inconsistentie maar inherent aan het verschil.

---

## Bronverwijzingen

| Onderwerp | Bron |
|-----------|------|
| Baseline Architecture definitie | TOGAF 9.1, Definitions, §3.14 |
| Target Architecture (ADM Phase B, C, D) | TOGAF 10, ADM Phases B–D |
| Transition Architectures (ADM Phase E) | TOGAF 10, ADM Phase E |
| Scope-dimensies (Breadth, Depth, Time, Architecture Domains) | TOGAF 9.1, Chapter 5, §5.5 |
| Time Period en target/transition splitsing | TOGAF 9.1, Chapter 5, §5.5.3 |
| Architecture Landscape Levels | TOGAF 9.1, Chapter 20, §20.2 |
| Approaches to Architecture Development (Baseline First / Target First) | TOGAF 9.1, Chapter 19, §19.4 |
| Phase A: Architecture Vision, scope, readiness | TOGAF 9.1, Chapter 7, §7.1–7.4 |
| Business Transformation Readiness Assessment | TOGAF 9.1, Chapter 30 |
| Capability Increments als drivers voor Transition Architectures | TOGAF 9.1, Chapter 32, §32.3.1 |
| Architecture Governance | TOGAF 9.1, Chapter 50 |
| ArchiMate Plateau, Gap, Work Package, Deliverable | ArchiMate 3.1 Specification, Implementation & Migration Aspect |
| ArchiMate Capability (Strategy Layer) | ArchiMate 3.1 Specification, Strategy Elements |
| ArchiMate Motivation-elementen | ArchiMate 3.1 Specification, Motivation Aspect |
| ISO/IEC/IEEE 42010:2011 (intended architecture) | Systems and software engineering — Architecture description |
| Principes-guideline | `references/principes-samenvatting-metamodel.md` |
| Capabilities-guideline | `references/capabilities-samenvatting-metamodel.md` |
| Kaders-guideline | `references/kaders-samenvatting-metamodel.md` |
