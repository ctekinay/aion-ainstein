# Capabilities — Samenvatting voor Metamodel (ArchiMate & TOGAF 9.1)

> **Doel:** Deze samenvatting dient als basis om een metamodel te bouwen met ArchiMate-elementen en -relaties, inclusief documentatie. Alle definities en verwijzingen zijn gebaseerd op TOGAF 9.1 en de ArchiMate 3.1-standaard.

---

## 1. Definitie van Capability

### 1.1 TOGAF 9.1 (Definitions, §3.26)

**Definitie:** "An ability that an organization, person, or system possesses. Capabilities are typically expressed in general and high-level terms and typically require a combination of organization, people, processes, and technology to achieve."

**Kenmerken:**
- Drukt uit *wat* een organisatie kan (vermogen), niet *hoe* het is ingericht
- Combinatie van mensen, processen, technologie en organisatie
- Wordt typisch op hoog niveau uitgedrukt
- Is business-driven en ideally business-led (TOGAF Ch.32, §32.3)

### 1.2 ArchiMate 3.1 (Strategy Layer)

**Definitie:** "An ability that an active structure element … possesses."

**Positionering:** Capability is een Strategy-element, niet een passief structuurelement. Het beschrijft vermogen, niet een object waarop gedrag wordt uitgevoerd.

**Let op:** In ArchiMate is Capability geen Motivation-element (zoals Goal of Principle) en ook geen Implementation-element (zoals Work Package). Het is specifiek een Strategy-concept dat wordt gebruikt voor capability-based planning.

---

## 2. Capability direct gekoppeld aan Enterprise — of alternatieven

### 2.1 Enterprise-brede koppeling (de standaardkeuze)

TOGAF stelt dat capabilities direct worden afgeleid van het strategisch bedrijfsplan: "The capabilities are directly derived from the corporate strategic plan by the corporate strategic planners that are and/or include the enterprise architects and satisfy the enterprise goals, objectives, and strategies" (TOGAF Ch.32, §32.4).

Dit maakt enterprise-brede positionering de meest logische keuze:
- Één canonical capability op enterprise niveau op het abstractieniveau dat een ExCo-lid herkent (bijv. "Cyber Security", "Klantbediening", "Datagedreven Werken", "Netwerkbeheer")
- Vormt de stabiele kapstok: naam, definitie, scope, eigenaar, lifecycle-status
- Past bij Strategic Architecture als "organizing framework for direction setting at an executive level" (TOGAF Ch.20, §20.2)
- De enterprise capability map bevat typisch 8–15 capabilities op dit hoogste abstractieniveau; meer duidt op te veel granulariteit voor executive-niveau sturing
- Decompositie vindt plaats binnen deze enterprise capabilities: "Cyber Security" bevat sub-capabilities als Identity & Access Management, Threat Detection, Vulnerability Management, etc.

### 2.2 Alternatieven: Segment- en Capability Architecture levels

TOGAF definieert drie Architecture Landscape levels (Ch.20, §20.2):

| Level | Beschrijving | Capability-perspectief |
|-------|-------------|----------------------|
| **Strategic Architecture** | Executive-niveau, richting en visie | Capability als enterprise-breed vermogen op de capability map |
| **Segment Architecture** | Programma/portfolio-niveau | Capability in de context van een portfolio met segment-specifieke roadmap |
| **Capability Architecture** | Change activity, capability increments | Capability als set concrete veranderstappen/releases |

**Cruciaal:** Dit zijn levels van granulariteit, geen containment-regels. TOGAF schrijft niet voor dat capabilities altijd onder segmenten vallen. "There is no definitive organizing model for architecture, as each enterprise should adopt a model that reflects its own operating model" (TOGAF Ch.20, §20.2).

### 2.3 Cross-cutting capabilities

Veel capabilities zijn "horizontaal" en gaan tegen de verticale corporate governance in (TOGAF Ch.32, §32.3). Dit speelt typisch op het niveau van sub-capabilities: Identity & Access Management (sub-capability van Cyber Security), Data Management (sub-capability van Datagedreven Werken), Integration Services (sub-capability van een platform-capability). Deze sub-capabilities kunnen:
- Enterprise-breed relevant zijn, ook al zijn ze gedecomponeerd vanuit één enterprise capability
- Door meerdere segmenten (programma's/portfolio's) lopen
- Beïnvloed worden door subsidiary principes (bijv. IT/security policies)

TOGAF bevestigt dit expliciet: "Many capabilities are 'horizontal' and go against the grain of normal vertical corporate governance" (Ch.32, §32.3).

---

## 3. Resolutie: dezelfde capability op verschillende detailniveaus

### 3.1 Eén capability, meerdere beschrijvingsniveaus

Wanneer je dezelfde enterprise capability (bijv. "Cyber Security") op de drie Architecture Landscape levels beschrijft, verandert niet de capability zelf — alleen de resolutie en het doel:

| Level | Resolutie | Doel | Voorbeeld (Cyber Security) |
|-------|-----------|------|-----------------|
| **Strategic** | Hoog — enterprise capability map | Richting, prioritering, strategische fit | "Cyber Security is een enterprise capability die bedrijfscontinuïteit en compliance waarborgt" |
| **Segment** | Middel — portfolio/programma context | Roadmap, afhankelijkheden, scope per programma/portfolio | "Cyber Security in Customer Digital: focus op CIAM en API-security" |
| **Capability** | Laag — increments en releases | Concrete change-stappen, deliverables | "Q3: MFA workforce uitrol; Q4: CIAM MVP" |

### 3.2 Resolutie is viewpoint én uitwerkingsgraad

Resolutie is niet alleen een viewpoint-kwestie (welke stakeholder kijkt), maar ook een **uitwerkingskwestie** (hoe ver ben je met detailleren). Niet alles hoeft vanaf het begin op Capability Architecture level te zijn uitgewerkt. Analoog aan de inhoudelijke volwassenheid van een kader (zie kaders-document §5.2): een capability mag op Strategic level volledig beschreven zijn terwijl de uitwerking op Capability Architecture level nog witte vlekken heeft. Dat is geen tekortkoming maar bewuste planning — de uitwerking volgt wanneer het segment of programma dat vereist.

### 3.3 Geen duplicatie

Dit zijn niet drie *andere* capabilities. Het is dezelfde capability bekeken met andere resolutie en governance-focus. In de repository: één canonical capability met meerdere views en detailniveaus. Resolutie is geen metamodel-operatie — er ontstaan geen nieuwe elementen. Het onderscheid met decompositie en specialisatie (zie §4) is dat die wél metamodel-operaties zijn.

---

## 4. Decompositie als verdieping vs. Specialisatie

### 4.1 Decompositie (verdieping)

Dezelfde capability wordt opgesplitst in sub-capabilities voor meer detail. De decompositie kan meerdere lagen bevatten — van enterprise capability tot operationeel detail:

```
Cyber Security                          ← Enterprise capability (capability map)
 ├── Identity & Access Management       ← Sub-capability (eerste decompositie)
 │    ├── Authentication
 │    ├── Authorization
 │    ├── Identity Lifecycle Management
 │    ├── Provisioning
 │    ├── Multi-Factor Authentication (MFA)
 │    └── Privileged Access Management (PAM)
 ├── Threat Detection
 ├── Vulnerability Management
 └── Security Operations
```

- "Cyber Security" is de enterprise capability op de capability map
- IAM is een sub-capability — de eerste decompositelaag
- Authentication, MFA etc. zijn verdere verdieping
- ArchiMate-relatie: Composition (parent → child)

### 4.2 Specialisatie (varianten)

Dezelfde capability-familie wordt gesplitst omdat de context fundamenteel verschilt:

```
Identity & Access Management           ← Sub-capability van Cyber Security
 ├── Workforce IAM (medewerkers)       ← Specialisatie
 ├── Customer IAM - CIAM (klanten)     ← Specialisatie
 └── Partner IAM (ketenpartners)       ← Specialisatie
```

- Niet "random andere capabilities" maar specialisaties van dezelfde sub-capability
- Reden: governance, risicoprofiel of technologiekeuzes lopen sterk uiteen
- ArchiMate-relatie: Specialization (variant → parent)

### 4.3 Beslisregel

| Vraag | Patroon | Metamodel-operatie? |
|-------|---------|---------------------|
| Alleen meer detail nodig binnen dezelfde scope? | → Decompositie (Composition) | Ja — nieuw sub-capability element |
| Andere doelgroep, risicoprofiel, operating model? | → Specialisatie (Specialization) | Ja — nieuw variant-element |
| Ander detailniveau of nog niet uitgewerkt? | → Zelfde capability, andere resolutie/uitwerkingsgraad (zie §3.2) | Nee — viewpoint + volwassenheid |

---

## 5. Capability Increments en Dimensies

**Bron:** TOGAF 9.1, Chapter 32, §32.3.1–32.3.2

### 5.1 Capability Increments

Een capability kost langere tijd om te leveren en omvat doorgaans meerdere projecten. Daarom wordt zij opgedeeld in increments die discrete, zichtbare en kwantificeerbare resultaten opleveren. Deze increments:
- Zijn de drivers voor Transition Architectures (Phase E)
- Structureren project-increments
- Leveren Critical Success Factors voor voortgezette capability-ondersteuning

### 5.2 Capability Dimensies

Capabilities worden geëngineered met verschillende dimensies die corporate functionele portfolios overstijgen (TOGAF Ch.32, §32.3.2). Voorbeelden: Personeel, R&D, Infrastructuur/Faciliteiten, Processen, Informatie Management, Materieel.

**So what:** De dimensies zijn een **compleetheidscheck bij het plannen van capability increments**. Een capability increment die alleen de technologie-dimensie adresseert maar de people- en process-dimensies negeert, levert geen werkend vermogen op. Bij elke increment-definitie: toets of alle relevante dimensies zijn geadresseerd.

**Relatie met Architecture Categories (BDAT):** Capability dimensies zijn niet hetzelfde als de TOGAF Architecture Categories (Business/Data/Application/Technology/Integration/Guiding — TOGAF Ch.34, Content Metamodel). Categories classificeren *architectuurprincipes en -artefacten* vanuit het governance-perspectief. Dimensies beschrijven de *realisatie-ingrediënten* van een capability vanuit het delivery-perspectief. In de praktijk mappen ze gedeeltelijk op elkaar (Processen ≈ Business, Informatie Management ≈ Data, Technologie ≈ Technology), maar dimensies zijn breder — ze omvatten ook Personeel, Faciliteiten en Materieel die geen architectuurdomein zijn. Categories sturen de architectuur; dimensies sturen de delivery.

---

## 6. Relaties naar ArchiMate-elementen

### 6.1 Capability in de ArchiMate Strategy Layer

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Resource** | Association → | **Capability** | Resources (assets) zijn nodig om capability te realiseren |
| **Capability** | Realization → | **Course of Action** | Capability maakt een aanpak/strategie mogelijk |
| **Capability** | Serving → | **Goal / Outcome** | Capability draagt bij aan het bereiken van doelen |
| **Capability** | Composition → | **Capability** | Decompositie in sub-capabilities |
| **Capability** | Specialization → | **Capability** | Specialisatie (Workforce IAM → IAM) |

### 6.2 Relaties met Motivation-elementen

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Driver** | Influence → | **Goal / Outcome** | Drijfveren leiden tot doelen |
| **Goal / Outcome** | (keten via) | **Capability** | Doelen vereisen capabilities |
| **Principle** | Influence → | **Requirement / Constraint** | Principes sturen eisen die capabilities beïnvloeden |

### 6.3 Relaties met Implementation & Migration-elementen

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Work Package** | Realization → | **Capability** (increment) | Projecten/werkpakketten realiseren capability increments |
| **Deliverable** | Association → | **Work Package** | Resultaten van werkpakketten |
| **Plateau** | Composition → | *Architectuurelementen* | Stabiele staat na een increment |
| **Gap** | Association → | **Plateau** | Verschil tussen baseline en target |

### 6.4 Relaties met Core-elementen

| Van | Relatie | Naar | Toelichting |
|-----|---------|------|-------------|
| **Capability** | Realization ← | **Business Process, Application Component, Technology Service, etc.** | Core-elementen realiseren de capability |

### 6.5 Volledige keten (typische view)

```
Driver ──▶ Goal/Outcome
                │
                ▼
           Capability ◄── Resource
           │       │
    (Composition) (Realization)
           ▼       ▼
     Sub-Capability   Course of Action
                          │
                    (Realization)
                          ▼
                    Work Package ──▶ Deliverable
                          │
                    (Aggregation)
                          ▼
                       Plateau
                          │
              Core-elementen (Business Process,
              Application Component, Technology, etc.)
```

---

## 7. Capability-template en Repository Model

### 7.1 Capability-template

**Eigen uitwerking — TOGAF definieert geen standaard capability-template.**

De template is gebaseerd op de TOGAF-definitie (Ch.3, §3.26), Capability-Based Planning (Ch.32), het Architecture Landscape (Ch.20, §20.2) en de classificatiestructuur uit het principes-document.

| Component | Beschrijving | Bron/Analogie |
|---|---|---|
| **Naam** | Kort, herkenbaar, business-taal (geen technologieplatforms) | TOGAF §3.26 |
| **Definitie** | Wat dit vermogen inhoudt — *wat* de organisatie kan, niet *hoe* | TOGAF §3.26 |
| **Abstractieniveau** | Enterprise capability / Sub-capability / Variant (specialisatie) | Decompositie/specialisatie (§4) |
| **Enterprise capability (parent)** | Onder welke enterprise capability valt dit? (alleen bij sub-capability of variant) | Capability map |
| **Eigenaar** | Business owner / Capability lead | Governance |
| **Status** | Planned / In Development / Operational / Retiring | Levenscyclusbeheer |
| **Gerelateerde segmenten** | Welke programma's/portfolio's gebruiken deze capability, met scope-nuances per segment | TOGAF Ch.20, §20.2 |
| **Toepasselijke principes** | Enterprise Principles (altijd), Subsidiary Principles (domein-specifiek), Segment Principles (portfolio-specifiek) | Principes-document |
| **Toepasselijke kaders** | Welke kaders (enterprise/architectuur) gelden voor deze capability | Kaders-document |
| **Increments** | Geplande capability increments met tijdlijn en SMART-criteria | TOGAF Ch.32, §32.3.1 |
| **Dimensies** | Per increment: welke dimensies (People, Process, Technology, Information, Facilities, etc.) zijn geadresseerd | TOGAF Ch.32, §32.3.2 |
| **Resolutie-status** | Per landscape level: hoe ver is de uitwerking? (Analoog aan inhoudelijke volwassenheid van kaders) | §3.2 |

### 7.2 Repository-metadata per capability

| Attribuut | Waarden / Beschrijving |
|-----------|----------------------|
| **Naam** | Canonical naam (bijv. "Cyber Security", "Identity & Access Management") |
| **Definitie** | Wat dit vermogen inhoudt |
| **Type** | Enterprise / Segment-specifiek / Cross-cutting |
| **Patroon** | Parent / Sub-capability (decompositie) / Variant (specialisatie) |
| **Eigenaar** | Business owner / Capability lead |
| **Landscape Level** | Strategic / Segment / Capability Architecture |
| **Status** | Planned / In Development / Operational / Retiring |
| **Gerelateerde segmenten** | Welke portfolio's/programma's |
| **Gerelateerde principes** | Enterprise + Subsidiary + Segment principles |
| **Increments** | Geplande capability increments met tijdlijn |
| **Dimensies** | People, Process, Technology, Information, etc. |

---

## 8. Vuistregels

1. **Eén canonical capability op enterprise niveau.** Vermijd duplicatie door dezelfde capability in meerdere segmenten (programma's/portfolio's) als "ander" item aan te maken. Een segment *gebruikt* capabilities uit de enterprise map met een segment-specifieke lens — scope, prioritering, roadmap. De capability "leeft" niet in het segment; het segment is een *context* waarin de capability wordt ingezet. Gebruik relaties en views.

2. **Capabilities mogen cross-cutting zijn.** Forceer ze niet altijd in precies één segment (programma/portfolio), tenzij je operating model dat vereist — TOGAF geeft expliciet ruimte. Een horizontale sub-capability als IAM kan door meerdere programma's lopen zonder dat het een duplicaat is.

3. **Levels ≠ containment.** Strategic/Segment/Capability Architecture zijn organisatiemechanismes voor granulariteit, geen parent-child hiërarchie.

4. **Decompositie voor detail, specialisatie voor context, resolutie voor uitwerking.** Stel drie checkvragen:
   - Is het alleen meer detail binnen dezelfde scope? → Decompositie (Composition — metamodel-operatie)
   - Is de scope wezenlijk anders (klant vs medewerker, OT vs IT)? → Specialisatie (Specialization — metamodel-operatie)
   - Is het een ander detailniveau of nog niet uitgewerkt? → Zelfde capability, andere resolutie (geen metamodel-operatie — viewpoint + volwassenheid)

5. **Capability ≠ roadmap.** Capability = vermogen (Strategy). Roadmap = Work Packages, Plateaus, Gaps (Implementation & Migration). Houd dit scherp gescheiden.

6. **Capability ≠ Goal.** Capability beschrijft wat je *kunt*, Goal beschrijft wat je *wilt bereiken*. In ArchiMate: Capability (Strategy) ≠ Goal (Motivation).

7. **Capability Increments leveren zichtbare business-waarde.** Definieer increments met SMART-criteria om ambiguïteit te voorkomen (TOGAF Ch.32, §32.3).

8. **Koppel subsidiary aan principes/governance, niet aan containment van capabilities.** De subsidiary-as (IT, HR, OT — organisatie-eenheden) is een governance-mechanisme uit het principes-domein dat bepaalt welke *principes en kaders* van toepassing zijn. Het is niet bedoeld om capabilities te "bezitten" of te "containen". Een organisatie-eenheid *realiseert* een capability (ArchiMate: Business Actor → assigned to → Business Process → realizes → Capability), maar *bevat* haar niet. Voorbeeld: de organisatie-eenheid "Netmanagement" realiseert de enterprise capability "Netwerkbeheer" — maar die capability raakt ook Cyber Security (enterprise kader), Data Management, workforce planning en regulatoire compliance. Als je de capability *contained* in Netmanagement, verlies je die cross-cutting governance. De eigenaar kan best de directeur Netmanagement zijn, maar dat eigenaarschap is een governance-toewijzing met verantwoording naar het enterprise governance-forum, geen autonomie. Als een capability aantoonbaar alleen door één organisatie-eenheid wordt gerealiseerd én geen cross-cutting concerns raakt, kan governance worden gedelegeerd — maar de capability blijft op de enterprise map staan en de delegatie wordt periodiek gereviewed. Dit is geen letterlijk TOGAF-voorschrift maar volgt uit de positionering van capabilities als enterprise-breed (Ch.32, §32.4) en de horizontaliteit die TOGAF expliciet benoemt (Ch.32, §32.3).

9. **Horizontale capabilities vereisen enterprise-niveau governance.** Omdat ze tegen de verticale organisatiestructuur ingaan, is een Architecture Board of vergelijkbaar gremium essentieel voor prioritering en funding.

10. **Gebruik de capability map als strategische taal.** Het is de brug tussen strategie en veranderopgaven — zorg dat business en IT dezelfde map gebruiken.

---

## 9. Inrichtingskeuzes voor het Metamodel

### 9.1 ArchiMate-modellering

| Keuze | Implementatie |
|-------|-------------|
| **Decompositie** | Composition-relatie (Capability → Sub-Capability) |
| **Specialisatie** | Specialization-relatie (Workforce IAM → IAM) |
| **Realisatie door core** | Realization-relatie vanuit Business Process, Application Component, etc. naar Capability |
| **Roadmap-koppeling** | Realization van Work Package naar Capability (increment) |
| **Doel-koppeling** | Serving of Association van Capability naar Goal/Outcome |
| **Principe-invloed** | Influence van Principle → Requirement/Constraint; Requirement → Capability (via Realization) |

### 9.2 Views per scope

| View | Inhoud |
|------|--------|
| **Enterprise Capability Map** | Alle canonical capabilities op hoog niveau, gegroepeerd per domein/thema |
| **Segment Capability View** | Capabilities relevant voor één segment, met segment-specifieke scope en roadmap |
| **Capability Realization View** | Eén capability met alle realiserende core-elementen (processen, applicaties, technologie) |
| **Motivation → Capability View** | Driver → Goal → Capability → Requirement keten |
| **Implementation View** | Capability increments → Work Packages → Deliverables → Plateaus |

### 9.3 Governance

- Capability map wordt beheerd op enterprise niveau, eigenaarschap bij business/strategie.
- Segment-specifieke detaillering wordt beheerd binnen het portfolio/programma.
- Capability increments worden gekoppeld aan projectportfolio-management.
- Periodieke review: is de capability map nog aligned met strategie? Zijn sub-capabilities/specialisaties actueel?

---

## Bronverwijzingen

| Onderwerp | Bron |
|-----------|------|
| Definitie Capability | TOGAF 9.1, Chapter 3, §3.26 |
| Architecture Landscape Levels | TOGAF 9.1, Chapter 20, §20.2 |
| Geen definitief organisatiemodel | TOGAF 9.1, Chapter 20, §20.2 |
| Capability-Based Planning | TOGAF 9.1, Chapter 32, §32.1–32.4 |
| Capability Increments & Dimensies | TOGAF 9.1, Chapter 32, §32.3.1–32.3.2 |
| Capabilities afgeleid van strategisch plan | TOGAF 9.1, Chapter 32, §32.4 |
| Horizontale capabilities | TOGAF 9.1, Chapter 32, §32.3 |
| Federated Architectures | TOGAF 9.1, Chapter 5, §5.5.1 |
| ArchiMate Capability element | ArchiMate 3.1 Specification, Strategy Layer |
| ArchiMate Work Package, Deliverable, Plateau | ArchiMate 3.1 Specification, Implementation & Migration |
| ArchiMate Motivation-elementen | ArchiMate 3.1 Specification, Motivation Aspect |
