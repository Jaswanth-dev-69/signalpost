from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any


def generate_company_synthesis(profile: dict[str, Any]) -> str:
    """Generate a concise, evidence-grounded profile summary for a Norwegian company.

    This function uses deterministic facts from verified evidence layers and explicitly
    highlights what is known, what is unknown, and what changed.
    """
    name = profile.get("name") or "Unknown Entity"
    org = profile.get("organisation_number") or ""
    form = profile.get("legal_form") or "Entity"
    muni = profile.get("municipality") or "Norway"
    ind = profile.get("industry_label") or "Unspecified sector"
    emp = profile.get("employees")

    # Header sentence
    parts = [f"{name} (Org.nr {org}) is a registered Norwegian {form} based in {muni}, operating within {ind}."]

    # Status / Employees
    if profile.get("bankrupt"):
        parts.append("The company is registered as bankrupt.")
    elif profile.get("liquidating"):
        parts.append("The company is currently in liquidation.")

    if emp is not None:
        parts.append(f"The official registry records {emp} employee(s).")
    else:
        parts.append("The registry record does not report employee count.")

    # Financials
    evidence = profile.get("evidence", {})
    fin = evidence.get("financials", {})
    fin_status = fin.get("status")
    acc_ob = evidence.get("accounting_obligation", {}).get("value", {})
    classification = acc_ob.get("classification")

    if fin_status == "available" and fin.get("value"):
        recs = (fin.get("value") or {}).get("records") or []
        if recs:
            latest = recs[0]
            rev = latest.get("revenue")
            res = latest.get("annual_result")
            cur = latest.get("currency") or "NOK"
            period = latest.get("period") or {}
            year = period.get("tilDato", "")[:4] if isinstance(period, dict) else ""
            year_str = f" for FY{year}" if year else ""

            fin_str = f"For the latest filed annual accounts{year_str}, the company reported "
            items = []
            if rev is not None:
                items.append(f"revenue of {rev:,.0f} {cur}")
            if res is not None:
                items.append(f"annual result of {res:,.0f} {cur}")
            if items:
                fin_str += ", ".join(items) + "."
                parts.append(fin_str)
            else:
                parts.append("Annual accounts were returned but numerical breakdown was omitted.")
        else:
            parts.append("Financial records endpoint returned an empty record set.")
    elif classification == "required_by_legal_form":
        parts.append("Financial filings are required by legal form but no normalized annual account was returned in this check.")
    elif classification == "threshold_or_activity_dependent":
        parts.append("Filing obligation is activity/threshold dependent; no public annual account was returned.")
    else:
        parts.append("No normalized annual accounts record was returned; missing filing is not interpreted as zero revenue.")

    # Roles & Locations
    roles = (evidence.get("roles", {}).get("value") or {}).get("roles") or []
    active_roles = [r for r in roles if not r.get("inactive")]
    if active_roles:
        key_people = [f"{r.get('name')} ({r.get('role') or r.get('group')})" for r in active_roles[:3] if r.get("name")]
        if key_people:
            parts.append(f"Key registered role holders include: {', '.join(key_people)}.")

    subunits = (evidence.get("locations", {}).get("value") or {}).get("locations") or []
    if len(subunits) > 1:
        parts.append(f"The company operates {len(subunits)} registered subunits/establishments.")
    elif len(subunits) == 1:
        parts.append("The company has 1 registered subunit.")

    # Website & Public Footprint
    web = evidence.get("website", {}) or evidence.get("website_discovered", {})
    web_status = web.get("status")
    web_val = web.get("value") or {}
    publishable = (web_val.get("identity_assessment") or {}).get("publishable", False)

    if web_status == "available" and publishable:
        final_url = web_val.get("final_url") or web.get("source_url")
        desc = web_val.get("description")
        parts.append(f"Official verified website: {final_url}.")
        if desc:
            parts.append(f"Site overview: \"{desc[:200]}\"")
        socials = web_val.get("social_links") or []
        if socials:
            platforms = sorted({s.get("platform") for s in socials if s.get("platform")})
            parts.append(f"Declared social profiles: {', '.join(platforms)}.")
    elif web_status == "available" and not publishable:
        parts.append("A registry-linked website was checked, but exact legal-entity identity could not be verified; website claims are quarantined.")
    else:
        parts.append("No verified official company website was available during this check.")

    # Summary of Unknowns
    unknowns = []
    if fin_status != "available":
        unknowns.append("annual financial metrics")
    if not active_roles:
        unknowns.append("public leadership registry entries")
    if not (web_status == "available" and publishable):
        unknowns.append("verified online web presence")

    if unknowns:
        parts.append(f"Currently unconfirmed or unavailable: {', '.join(unknowns)}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------------------------
# Envelope summary: built only from the envelope's own published claims.
#
# Every sentence below is assembled from claims with `availability: available` (their values and
# their evidence items) or, for the unknowns, from the explicit availability state of a claim.
# Nothing is inferred beyond arithmetic on published figures (changes between reported years).
# Markers like [2] point at the numbered source list; each source carries the evidence ids it
# stands for, so a reader can go from a sentence to the quoted span and the fetched page.
# ---------------------------------------------------------------------------------------------

LEGAL_FORMS = {
    "AS": "private limited company",
    "ASA": "public limited company",
    "ENK": "sole proprietorship",
    "NUF": "Norwegian-registered foreign enterprise",
    "ANS": "general partnership",
    "DA": "partnership with shared liability",
    "KS": "limited partnership",
    "SA": "cooperative",
    "BA": "company with limited liability",
    "STI": "foundation",
    "FLI": "association",
    "SPA": "savings bank",
    "GFS": "mutual insurance company",
    "BRL": "housing cooperative",
    "ESEK": "condominium owners' association",
    "IKS": "inter-municipal company",
    "KF": "municipal enterprise",
    "FKF": "county municipal enterprise",
    "HF": "health trust",
    "SF": "state enterprise",
    "PK": "pension fund",
    "SAM": "co-ownership",
    "KBO": "bankruptcy estate",
    "TVAM": "entity under compulsory dissolution",
    "PRE": "partnership company",
    "KOMM": "municipality",
    "FYLK": "county authority",
    "STAT": "state body",
    "ORGL": "organisational unit",
}
SOURCE_LABELS = {
    "official_registry_live": "Enhetsregisteret entity record (Brønnøysund Register Centre)",
    "official_registry_bulk": "Enhetsregisteret bulk register snapshot",
    "official_roles": "Enhetsregisteret roles record",
    "official_subunits": "Enhetsregisteret sub-unit records",
    "official_annual_accounts": "Regnskapsregisteret annual accounts",
    "official_job_register": "NAV public vacancy register",
    "company_owned": "company-owned website",
}
PLATFORM_NAMES = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn", "youtube": "YouTube",
                  "x": "X (Twitter)", "twitter": "X (Twitter)", "tiktok": "TikTok", "pinterest": "Pinterest",
                  "vimeo": "Vimeo", "github": "GitHub", "snapchat": "Snapchat", "threads": "Threads"}
CHANGE_NAMES = {"registry.name": "legal name", "registry.legal_form": "legal form", "registry.employees": "employee count",
                "registry.municipality": "municipality", "registry.website": "registered homepage",
                "registry.latest_submitted_accounts": "latest filed accounts year", "financials.records": "annual accounts",
                "financial_history.years": "filed accounts years", "roles.roles": "registered roles", "locations.locations": "sub-units",
                "website.title": "website title", "website.description": "website description", "website.social_links": "website social links",
                "claims.official_website": "official website", "claims.social_profile": "social profiles", "claims.dated_news": "dated news",
                "claims.hiring_signal": "hiring signals", "claims.company_description": "website description"}
MAX_QUOTE = 240
SUMMARY_FIELD = "summary_profile"


def _quote(text: Any, limit: int = MAX_QUOTE) -> str:
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.")
        text = cut + " …"
    return f"“{text}”"


def _place(name: Any) -> str:
    """BRREG prints municipalities in capitals ("NORD-FRON"); show them as names ("Nord-Fron")."""
    words = re.split(r"([ \-])", str(name or ""))
    return "".join(w if w in (" ", "-") else (w[:1].upper() + w[1:].lower()) for w in words)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and str(value).strip() not in ("", "None") else None
    except (TypeError, ValueError):
        return None


def _money(value: float, currency: str | None = "NOK") -> str:
    cur = currency or "NOK"
    size = abs(value)
    if size >= 1e9:
        text = f"{value / 1e9:.2f} billion"
    elif size >= 1e6:
        text = f"{value / 1e6:.1f} million"
    elif size >= 1e4:
        text = f"{value / 1e3:,.0f} thousand"
    elif size >= 1e3:
        text = f"{value / 1e3:.1f} thousand"
    else:
        text = f"{value:,.0f}"
    return f"{cur} {text}"


def _name(value: Any) -> str:
    """Role holders that are entities carry their name as a list of lines in the roles API."""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value if v)
    return str(value or "")


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class _Sources:
    """Numbered source list keyed by page URL; a marker names every source a sentence rests on."""

    def __init__(self, evidence: dict[str, dict[str, Any]]):
        self.evidence = evidence
        self.items: list[dict[str, Any]] = []
        self.by_url: dict[str, dict[str, Any]] = {}

    def cite(self, claims: list[dict[str, Any]] | dict[str, Any] | None, label: str | None = None) -> tuple[str, list[int], list[str]]:
        claims = [claims] if isinstance(claims, dict) else (claims or [])
        refs: list[int] = []
        ids: list[str] = []
        for claim in claims:
            for eid in claim.get("evidence_ids") or []:
                item = self.evidence.get(eid)
                if not item or not item.get("source_url"):
                    continue
                url = item["source_url"]
                source = self.by_url.get(url)
                if source is None:
                    source = {"n": len(self.items) + 1, "url": url,
                              "label": label or SOURCE_LABELS.get(item.get("source_class"), item.get("source_class") or "source"),
                              "source_class": item.get("source_class"), "retrieved_at": item.get("retrieved_at"),
                              "evidence_ids": []}
                    self.items.append(source)
                    self.by_url[url] = source
                if eid not in source["evidence_ids"]:
                    source["evidence_ids"].append(eid)
                if source["n"] not in refs:
                    refs.append(source["n"])
                if eid not in ids:
                    ids.append(eid)
        refs.sort()
        marker = f" [{', '.join(str(n) for n in refs)}]" if refs else ""
        return marker, refs, ids


NACE_DIVISIONS = {
    "01": "crop and animal production, hunting and related services", "02": "forestry and logging", "03": "fishing/aquaculture",
    "05": "mining of coal and lignite", "06": "extraction of crude petroleum and natural gas", "07": "mining of metal ores",
    "08": "other mining and quarrying", "09": "mining support services", "10": "manufacture of food products",
    "11": "manufacture of beverages", "12": "manufacture of tobacco products", "13": "manufacture of textiles",
    "14": "manufacture of wearing apparel", "15": "manufacture of leather and related products",
    "16": "manufacture of wood and wood products, except furniture", "17": "manufacture of paper and paper products",
    "18": "printing and reproduction of recorded media", "19": "manufacture of coke and refined petroleum products",
    "20": "manufacture of chemicals and chemical products", "21": "manufacture of pharmaceutical products",
    "22": "manufacture of rubber and plastic products", "23": "manufacture of other non-metallic mineral products",
    "24": "manufacture of basic metals", "25": "manufacture of fabricated metal products, except machinery and equipment",
    "26": "manufacture of computer, electronic and optical products", "27": "manufacture of electrical equipment",
    "28": "manufacture of other machinery and equipment", "29": "manufacture of motor vehicles, trailers and semi-trailers",
    "30": "manufacture of other transport equipment", "31": "manufacture of furniture", "32": "other manufacturing",
    "33": "repair, maintenance and installation of machinery and equipment", "35": "electricity, gas, steam and air conditioning supply",
    "36": "water collection, treatment and supply", "37": "sewerage", "38": "waste collection, treatment and disposal; materials recovery",
    "39": "remediation and other waste management services", "41": "construction of buildings", "42": "civil engineering",
    "43": "specialised construction activities", "45": "trade and repair of motor vehicles and motorcycles", "46": "wholesale trade",
    "47": "retail trade", "49": "land transport and transport via pipelines", "50": "water transport", "51": "air transport",
    "52": "warehousing and support activities for transportation", "53": "postal and courier activities", "55": "accommodation",
    "56": "food and beverage service activities", "58": "publishing activities",
    "59": "film, video and television production, sound recording and music publishing",
    "60": "programming, broadcasting and other content distribution", "61": "telecommunication",
    "62": "computer programming, consultancy and related activities",
    "63": "computing infrastructure, data processing, hosting and other information services",
    "64": "financial services, except insurance and pension funding", "65": "insurance, reinsurance and pension funding",
    "66": "activities auxiliary to financial services and insurance", "68": "real estate activities",
    "69": "legal and accounting activities", "70": "head offices and management consultancy",
    "71": "architectural and engineering activities; technical testing and analysis", "72": "scientific research and development",
    "73": "advertising, market research and public relations", "74": "other professional, scientific and technical activities",
    "75": "veterinary activities", "77": "rental and leasing activities", "78": "employment activities",
    "79": "travel agency, tour operator and reservation services", "80": "investigation and security activities",
    "81": "services to buildings and landscape activities", "82": "office administration and other business support activities",
    "84": "public administration and defence; compulsory social security", "85": "education", "86": "human health activities",
    "87": "residential care activities", "88": "social work activities without accommodation", "90": "arts creation and performing arts",
    "91": "libraries, archives, museums and other cultural activities", "92": "gambling and betting activities",
    "93": "sports activities and amusement and recreation", "94": "activities of membership organisations",
    "95": "repair and maintenance of computers, personal and household goods and vehicles", "96": "personal service activities",
    "97": "households as employers of domestic personnel", "98": "own-use production of private households",
    "99": "extraterritorial organisations and bodies",
}
ROLE_NAMES = {"DAGL": "chief executive", "LEDE": "chair of the board", "NEST": "deputy chair", "MEDL": "board member",
              "VARA": "deputy board member", "OBS": "board observer", "REVI": "auditor", "REGN": "accountant",
              "KONT": "contact person", "DTPR": "partner with shared liability", "DTSO": "partner with joint liability",
              "INNH": "owner", "FFØR": "business manager", "KOMP": "general partner", "BEST": "managing owner",
              "REPR": "Norwegian representative", "PROK": "procuration holder", "SIGN": "signatory"}
ROLE_ORDER = ("DAGL", "LEDE", "NEST", "MEDL", "VARA", "OBS", "DTPR", "DTSO", "INNH", "KOMP", "BEST", "FFØR", "REPR", "REVI", "REGN", "KONT")
NAMED_ROLES = {"DAGL", "LEDE", "NEST", "REVI", "REGN", "INNH", "FFØR", "KOMP", "BEST", "REPR", "KONT", "DTPR", "DTSO"}
GROUP_NAMES = {"STYR": "board", "DAGL": "chief executive", "REVI": "auditor", "REGN": "accountant", "DELT": "partners",
               "KONT": "contact person", "FFØR": "business manager", "INNH": "owner", "KOMP": "general partner",
               "BEST": "managing owner", "REPR": "Norwegian representative", "PROK": "procuration", "SIGN": "signature right"}
PLACEHOLDER_TITLES = {"hello world!", "hello world", "hei, verden!", "hei verden!", "hei, verden", "blog title", "post title",
                      "sample page", "eksempelside", "untitled", "uten tittel", "ny side", "new page"}
MATERIAL_NEWS = re.compile(r"avtale|kontrakt|oppdrag|tildel|signer|lanser|launch|åpner|etabler|kjøper|oppkjøp|fusjon|investe|"
                           r"resultat|kvartal|årsrapport|årsregnskap|daglig leder|administrerende|ansetter|utvider|vinner|award|"
                           r"partner|contract|agreement|acquisition|quarter|results|appoint|opens|expands|wins", re.I)
SEASONAL_NEWS = re.compile(r"god sommer|god jul|godt nytt|sommerstengt|påske|winter is coming|åpningstid|stengt|ferie|helg|"
                           r"konferanse|conference|\bmesse\b|webinar|seminar|investor day|\bshow 20|meet us|\bmeet [\w-]+ at\b|møt oss|"
                           r"merry christmas|happy new year|happy holidays|julebord|sommerfest", re.I)
JUNK_TITLE = re.compile(r"lorem ipsum|^test\b|testpost|^alle (børs|presse|nyhet|artikl|meldinger)|arkiv|archive|"
                        r"^hvorfor bruker vi det|^hvor kommer det fra|^hva er lorem|^hvor kan jeg få", re.I)
HOLDING_TEXT = re.compile(r"investering|eie (og forvalte )?aksjer|eierskap|aksjer og andeler|aksjer, andeler|kjøp og salg av aksjer|"
                          r"(deltakelse|delta|deltagelse) i andre (selskap|virksomhet|foretak)|holding", re.I)
PROPERTY_TEXT = re.compile(r"(utleie|kjøp og salg|forvaltning|drift|utvikling|eie) av (egen |fast )?(fast )?eiendom|eiendomsdrift|eiendomsutvikling|utleie av bolig", re.I)
# English for common terms in Norwegian activity texts (a reader aid: the original text is quoted next to it).
ACTIVITY_TERMS = (
    (r"barnehage", "kindergarten"), (r"tannleg|tannhelse|tannklinikk", "dental care"), (r"\blege(senter|kontor|tjenest|praksis)|legevakt|medisinske tjenester", "medical services"),
    (r"medisinsk(e)? (utstyr|produkt|forbruksmateriell|teknisk)|diagnosti|reagens", "medical equipment/supplies"), (r"\bmedisinsk", "medical"),
    (r"fysioterapi", "physiotherapy"), (r"psykolog", "psychology"), (r"frisør", "hairdressing"), (r"hudpleie|skjønnhet|kosmetisk", "beauty care"),
    (r"restaurant|servering|kafé|kafe\b|catering|take-?out", "restaurants/catering"), (r"hotell|overnatting|utleie av hytte", "accommodation"),
    (r"borettslag|boligsameie", "housing cooperative"), (r"eiendom", "real estate"), (r"oppføring av|bygg(e|virksomhet|arbeid)|entrepren", "construction"),
    (r"tømrer|snekker", "carpentry"), (r"maler|malearbeid", "painting"), (r"rørlegg|vvs", "plumbing"), (r"elektronikk", "electronics"), (r"elektriker|elektroinstallasjon|elektrisk installasjon|elektroentrepren", "electrical installation"),
    (r"grunnarbeid|graving|anleggsarbeid|maskinentrepren", "groundworks"), (r"taxi|drosje", "taxi services"),
    (r"transport|frakt|budtjenest|logistikk|spedisjon", "transport/logistics"), (r"regnskap|bokføring", "accounting"), (r"revisjon", "auditing"),
    (r"konsulent|rådgivning", "consulting"), (r"programvare|software|systemutvikling", "software"), (r"\bit[- ]|informasjonsteknologi|datasystem|ikt\b", "IT"),
    (r"detaljhandel|butikk|nettbutikk|netthandel", "retail"), (r"\bhandel\b|handelsvirksomhet", "trade"), (r"engros|agentur", "wholesale"),
    (r"import\w* og eksport|eksport\w* og import", "import/export"), (r"\bimport", "import"), (r"eksport", "export"),
    (r"tilvirkning|fabrikasjon|fabrikk|industri", "manufacturing"), (r"produksjon", "production"), (r"landbruk|jordbruk|gårdsdrift|husdyr", "agriculture"),
    (r"skogbruk|skogsdrift|skogsentrepren|tømmer", "forestry"), (r"fiske|havbruk|oppdrett", "fishing/aquaculture"), (r"reklame|markedsføring", "marketing"),
    (r"undervisning|opplæring|kurs\b|skole", "education/training"), (r"arbeidstrening|arbeidsmarkedstiltak|arbeidsinkludering|attføring|tilrettelagt arbeid", "work training/job inclusion"),
    (r"(?<!arbeids)trening|treningssenter|idrett", "sports/fitness"),
    (r"reiseliv|reisebyrå|turisme|opplevelse", "tourism"), (r"forsikring", "insurance"), (r"utlån|kreditt|finansier", "finance"),
    (r"renhold|vask\b|rengjøring", "cleaning"), (r"vakthold|vaktselskap|sikkerhetstjenest", "security services"), (r"sikkerhet|overvåking|alarm", "security/surveillance"), (r"bilverksted|bilsalg|kjøretøy|\bbil(er)?\b", "motor vehicles"),
    (r"båt", "boats"), (r"reparasjon|verksted|vedlikehold", "repair/maintenance"), (r"rederi|skipsfart", "shipping"), (r"maritim", "maritime activities"),
    (r"petroleum|olje|naturgass", "oil/gas"), (r"energi|kraftproduksjon|strøm", "energy"), (r"arkitekt", "architecture"),
    (r"ingeniør", "engineering"), (r"advokat|juridisk", "legal services"), (r"helse|omsorg|pleie", "health/care"),
    (r"design", "design"), (r"foto", "photography"), (r"musikk|konsert", "music"), (r"film|tv-produksjon", "film/TV"),
    (r"forlag|utgivelse", "publishing"), (r"utleie av (maskiner|utstyr)", "equipment rental"),
    (r"matvare|matprodukt|næringsmiddel|\bmat\b", "food"), (r"dagligvare", "groceries"), (r"klær|tekstil", "clothing/textiles"),
    (r"møbler|interiør", "furniture/interiors"), (r"\bdyr\b|veterinær", "animals/veterinary"),
    (r"næringsbygg|forretningsbygg|kontorbygg|næringslokal|utleie av lokaler", "real estate"), (r"trykkeri|trykking|grafisk produksjon", "printing"),
    (r"kosttilskudd", "dietary supplements"), (r"batteri", "batteries"), (r"ladestasjon|ladestolpe|ladeutstyr|ladeinfrastruktur|lading av elbil", "EV charging"),
)
HOUSING_FORMS = {"BRL", "ESEK", "SAM"}
PASS_THROUGH_FORMS = {"DA", "ANS", "KS", "ENK", "IS"}  # taxed through the owners, not as an entity
OWNED_FORMS = {"AS", "ASA"}
OWNER_TEXT = re.compile(r"\b(eies|eid|eiet) (og drives )?av\b|\bowned (and (run|operated) )?by\b", re.I)
SLIDER_WORDS = re.compile(r"^(?:(?:forrige|neste|previous|next|prev)\s+)+", re.I)
READABLE_ENTITY = "https://virksomhet.brreg.no/nb/oppslag/enheter/{org}"
RECENT_DAYS = 730
INITIAL_ROLE_DAYS = 120
MAX_NEWS = 20
SMALL_AMOUNT = 50_000
ROLE_IMPORTANCE = {"DAGL": 0, "STYR": 1, "DELT": 2, "INNH": 2, "KOMP": 2, "BEST": 2, "FFØR": 3, "REPR": 3, "REVI": 4, "REGN": 4, "KONT": 5}


def _days(period: Any) -> int | None:
    try:
        return (date.fromisoformat(str(period["tilDato"])[:10]) - date.fromisoformat(str(period["fraDato"])[:10])).days + 1
    except (KeyError, TypeError, ValueError):
        return None


def _comparable(period: Any) -> bool:
    """A twelve-month accounting period (11 to 13 months): only such periods are compared."""
    days = _days(period)
    return days is not None and 335 <= days <= 396


def _period_label(period: Any) -> str:
    if not isinstance(period, dict):
        return "the latest reported period"
    start, end = str(period.get("fraDato") or ""), str(period.get("tilDato") or "")
    if start[5:] == "01-01" and end[5:] == "12-31" and start[:4] == end[:4]:
        return end[:4]
    if start and end and _comparable(period):
        return f"the financial year {start} to {end}" if 364 <= (_days(period) or 0) <= 366 else f"the period {start} to {end}"
    days = _days(period)
    if start and end and days:
        return f"the {max(1, round(days / 30.44))}-month period {start} to {end}"
    return end or "the latest reported period"


def _result_noun(period: Any) -> str:
    return "annual result" if _comparable(period) else "result for the period"


def _pl(value: float, currency: str | None) -> str:
    """A result in words: a profit of NOK X, a loss of NOK X, or NOK 0."""
    if value > 0:
        return f"a profit of {_money(value, currency)}"
    if value < 0:
        return f"a loss of {_money(abs(value), currency)}"
    return _money(0, currency)


def activity_terms(activity: str, form: str | None = None) -> list[str]:
    """English terms for the register's activity text, in the order they appear (at most three): the
    longest glossary term at each place wins, and boilerplate share-holding clauses are skipped."""
    matches = []
    for pattern, english in (*ACTIVITY_TERMS, (HOLDING_TEXT.pattern, "owning shares in other companies"), (PROPERTY_TEXT.pattern, "real estate")):
        for match in re.finditer(pattern, activity, re.I):
            matches.append((match.start(), -(match.end() - match.start()), match.end(), english))
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for start, _neg, end, english in sorted(matches):
        if any(start < b and end > a for a, b in taken):
            continue  # the longest term at a place wins ("skogsentreprenør" is forestry, not construction)
        taken.append((start, end))
        if english == "owning shares in other companies" and start > 60 and len(matches) > 1:
            continue  # "... herunder delta i andre selskaper" at the end is boilerplate, not the activity
        if form in HOUSING_FORMS and english == "housing cooperative":
            continue
        if english not in [e for _, e in found]:
            found.append((start, english))
    return [e for _, e in sorted(found)][:3]


def _kind_pl(kind: str, value: float, currency: str | None, article: str = "an") -> str:
    """'an operating profit of NOK X', 'an annual loss of NOK X', or 'an annual result of NOK 0'."""
    if value == 0:
        return f"{article} {kind} result of {_money(0, currency)}".strip()
    return f"{article} {kind} {'loss' if value < 0 else 'profit'} of {_money(abs(value), currency)}".strip()


def _result_move(subject: str, old: float, new: float, old_label: str) -> str:
    """The brief's words for a large move between two results of the same sign: a profit rises or
    falls, a loss narrows or widens."""
    if old < 0 and new < 0:
        verb = ("more than tripled" if new < 3 * old else "more than doubled" if new < 2 * old else "widened sharply") if new < old else "narrowed sharply"
        return f"{subject} annual loss {verb} from {old_label}"
    verb = ("more than tripled" if new > 3 * old else "more than doubled" if new > 2 * old else "rose sharply") if new > old else "fell sharply"
    return f"{subject} annual profit {verb} from {old_label}"


def _change(old: float, new: float, currency: str | None, noun: str, old_label: str, new_label: str, result: bool = False,
            small: float = SMALL_AMOUNT) -> str:
    """One sentence on how a published figure moved between two comparable periods: direction always,
    a percentage only when both amounts are large enough and the move is below tenfold, a multiple
    between two- and tenfold, and results as profits or losses in words."""
    show = (lambda v: _pl(v, currency)) if result else (lambda v: _money(v, currency))
    span = f"from {show(old)} in {old_label} to {show(new)} in {new_label}"
    if old == new:
        return f"{noun} was {show(new)} in both {old_label} and {new_label}"
    if _money(old, currency) == _money(new, currency):
        if result:
            return f"{noun} was a {'loss' if new < 0 else 'profit'} of about {_money(abs(new), currency)} in both {old_label} and {new_label}"
        return f"{noun} was about {_money(new, currency)} in both {old_label} and {new_label}"
    tiny = min(abs(old), abs(new)) < small
    if old > 0 and new > 0:
        if tiny or new >= 10 * old or old >= 10 * new:
            return f"{noun} {'rose' if new > old else 'fell'} {span}"
        if new >= 2 * old:
            return f"{noun} rose to {new / old:.1f} times its {old_label} level ({span})"
        pct = (new - old) / old * 100
        return f"{noun} {'rose' if new > old else 'fell'} {abs(pct):.0f}% {span}"
    if result and old < 0 and new < 0:
        return f"{noun} was a loss in both periods; the loss {'narrowed' if new > old else 'widened'} from {_money(abs(old), currency)} in {old_label} to {_money(abs(new), currency)} in {new_label}"
    if result and old < 0 <= new:
        return f"{noun} turned {span}"
    if result and new < 0 <= old:
        return f"{noun} turned {span}"
    return f"{noun} {'rose' if new > old else 'fell'} {span}"


ROLE_PLURALS = {"DTPR": "partners with shared liability", "DTSO": "partners with joint liability", "OBS": "board observers",
                "REPR": "Norwegian representatives", "PROK": "procuration holders"}


def _role_label(code: str | None, norwegian: str | None, count: int = 1) -> str:
    english = ROLE_NAMES.get(code or "")
    if not english:
        return norwegian or "role"
    if count != 1:
        english = ROLE_PLURALS.get(code or "") or (english if english.endswith("s") else english + "s")
    return f"{english} ({str(norwegian).lower()})" if norwegian else english


def _clean_name(value: Any) -> str:
    return re.sub(r"[\s\-–—,;:]+$", "", _name(value)).strip()


def _names(names: list[str], limit: int = 3) -> str:
    """'A, B and C' or 'A, B, C and 4 others'."""
    names = [n for n in names if n]
    if len(names) <= limit:
        return _join(names)
    return ", ".join(names[:limit]) + f" and {len(names) - limit} other{'s' if len(names) - limit != 1 else ''}"


def _placeholder(claim: dict[str, Any]) -> bool:
    title = " ".join(str(claim.get("title") or "").split())
    return title.casefold() in PLACEHOLDER_TITLES or bool(JUNK_TITLE.search(title))


def _days_between(early: str, late: str) -> int | None:
    try:
        return (date.fromisoformat(late[:10]) - date.fromisoformat(early[:10])).days
    except ValueError:
        return None


def envelope_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """Summary sections, text and numbered sources for one envelope, from its published claims."""
    org = envelope.get("organisation_number") or ""
    claims = [c for c in envelope.get("claims") or [] if c.get("field") != SUMMARY_FIELD]
    evidence = {e.get("id"): e for e in envelope.get("evidence") or []}
    by_field: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        by_field.setdefault(str(claim.get("field")), []).append(claim)
    run = envelope.get("run") or {}
    run_text = str(run.get("completed_at") or envelope.get("completed_at") or "")[:10]
    try:
        run_day = date.fromisoformat(run_text)
    except ValueError:
        run_day = None

    def first(field: str) -> dict[str, Any] | None:
        items = by_field.get(field) or []
        return items[0] if items else None

    def available(field: str) -> list[dict[str, Any]]:
        return [c for c in by_field.get(field) or [] if c.get("availability") == "available"]

    def value(field: str) -> Any:
        items = available(field)
        return items[0].get("value") if items else None

    def state(field: str) -> str | None:
        claim = first(field)
        return claim.get("availability") if claim else None

    def recent(stamp: str) -> bool:
        return bool(run_day and stamp and _within(stamp, run_day, RECENT_DAYS))

    sources = _Sources(evidence)
    sections: list[dict[str, Any]] = []

    def build(key: str, label: str, sentences: list[tuple[str, Any]]) -> dict[str, Any] | None:
        texts, refs, ids = [], [], []
        for sentence, cited in sentences:
            if not sentence:
                continue
            marker, s_refs, s_ids = sources.cite(cited)
            texts.append(sentence.rstrip(".") + marker + ".")
            refs.extend(r for r in s_refs if r not in refs)
            ids.extend(i for i in s_ids if i not in ids)
        if not texts:
            return None
        return {"key": key, "label": label, "text": " ".join(texts), "refs": sorted(refs), "evidence_ids": ids}

    def section(key: str, label: str, sentences: list[tuple[str, Any]]) -> None:
        built = build(key, label, sentences)
        if built:
            sections.append(built)

    name = _clean_name(value("legal_name")) or (envelope.get("profile") or {}).get("name") or f"Organisation {org}"
    unknowns: list[tuple[Any, ...]] = []
    fin_items_gap = None

    # Shared facts --------------------------------------------------------------------------------
    form = value("legal_form")
    form_text = f"a {LEGAL_FORMS[form]} ({form})" if form in LEGAL_FORMS else (f"an entity of legal form {form}" if form else "a registered entity")
    muni = value("municipality")
    founded = str(value("founded_date") or "")
    code, label = value("industry_code"), value("industry_label")
    division = str(code or "")[:2]
    division_text = NACE_DIVISIONS.get(division) if division and division != "00" and not (form in HOUSING_FORMS and division in ("97", "98")) else None
    employees = _number(value("registry_employees"))
    fin_fields = ("revenue", "operating_result", "annual_result", "assets", "debt")
    latest = {f: _number(value(f)) for f in fin_fields}
    period_claim = (available("reporting_period") or [None])[0]
    period = period_claim.get("value") if period_claim else None
    history = sorted((c for c in available("financial_history") if isinstance(c.get("value"), dict)),
                     key=lambda c: str(((c["value"].get("period") or {}).get("tilDato")) or ""), reverse=True)
    currency = history[0]["value"].get("currency") if history else None
    has_accounts = any(v is not None for v in latest.values())
    latest_label = _period_label(period)
    result_noun = _result_noun(period)
    group = available("group_accounts")
    parent_only = bool(group)
    group_years = sorted((c for c in available("group_financials") if isinstance(c.get("value"), dict)),
                         key=lambda c: str(((c["value"].get("period") or {}).get("tilDato")) or ""), reverse=True)
    group_latest = group_years[0]["value"] if group_years else None
    group_label = _period_label(group_latest.get("period")) if group_latest else ""
    g_currency = (group_latest or {}).get("currency")
    roles = [r for r in (value("registered_roles") or []) if isinstance(r, dict) and not r.get("inactive")]
    site = value("official_website")
    socials = available("social_profile")
    signals = available("hiring_signal")
    pages = [c for c in signals if c.get("kind") == "careers_page"]
    postings = [c for c in signals if c.get("kind") == "job_posting"]
    news = sorted((c for c in available("dated_news") if c.get("published_at")), key=lambda c: str(c.get("published_at")), reverse=True)
    stamped = len(news) >= 2 and all(str(c.get("published_at"))[:10] == run_text for c in news)  # pages that print today's date
    junk_news = [c for c in news if _placeholder(c) or stamped]
    news = [c for c in news if not _placeholder(c) and not stamped]
    real_news = [c for c in news if not SEASONAL_NEWS.search(str(c.get("title") or ""))
                 and not (str(c.get("published_at"))[:10] == run_text and c.get("date_source") in ("page_text_date", "listing_text_date"))]
    # The item named in "What changed": the newest one about the business (contracts, launches,
    # results, appointments) from the last year, else the newest item.
    year_ago = str(run_day - timedelta(days=365)) if run_day else ""
    notable = next((c for c in real_news if MATERIAL_NEWS.search(str(c.get("title") or "")) and str(c.get("published_at"))[:10] >= year_ago), None)
    prev = history[0]["value"] if history else None
    comparable = bool(prev and has_accounts and _comparable(period) and _comparable(prev.get("period")))
    fin_claims = [c for f in fin_fields for c in available(f)] + ([period_claim] if period_claim else [])
    activity_value = value("registered_activity")
    activity = " ".join(" ".join(str(x) for x in activity_value).split()) if isinstance(activity_value, list) else str(activity_value or "")
    description = str(value("company_description") or "")
    terms = activity_terms(activity, form)
    activity_gloss = f"mentions {_join(terms)}" if terms else None
    material: list[tuple[int, str, Any]] = []  # (priority, sentence, claims): the brief names the most important

    # 1. Company ----------------------------------------------------------------------------------
    identity = f"{name} (organisation number {org}) is {form_text}"
    identity += f" registered in {_place(muni)}" if muni else ""
    identity += f", founded on {founded}" if founded else ""
    status_sentences: list[tuple[str, Any]] = []
    if value("status_bankrupt") is True:
        status_sentences.append(("The register lists it as bankrupt (konkurs)", available("status_bankrupt")))
    if value("status_liquidating") is True:
        status_sentences.append(("The register lists it as being wound up (under avvikling)", available("status_liquidating")))
    former: list[dict[str, Any]] = []
    for item in value("former_names") or []:
        if isinstance(item, dict) and item.get("name") and _clean_name(item.get("name")).casefold() != name.casefold() \
                and _clean_name(item.get("name")).casefold() not in {_clean_name(f.get("name")).casefold() for f in former}:
            former.append(item)
    if former:
        def until_text(f: dict[str, Any]) -> str:
            until = str(f.get("until") or "")[:10]
            if not until:
                return ""
            return f" (until {until}, before the founding date in the register)" if founded and until < founded[:10] else f" (until {until})"
        listed = "; ".join(_clean_name(f.get("name")) + until_text(f) for f in former[:8])
        status_sentences.append((f"Earlier names in the register: {listed}", available("former_names")))
    section("identity", "Company", [(identity, [c for c in (first("organisation_number"), *available("legal_form"), *available("municipality"), *available("founded_date")) if c]), *status_sentences])

    # 2. What it does -----------------------------------------------------------------------------
    does: list[tuple[str, Any]] = []
    industry_claims = available("industry_code") + available("industry_label")
    if code and str(code).startswith("00"):
        does.append((f"Its industry is not specified in the register (code {code} {_quote(label, 60)})", industry_claims))
    elif label:
        gloss = f" (broad NACE division {division}: {division_text})" if division_text else ""
        does.append((f"Its registered industry is {code + ' ' if code else ''}{_quote(label, 160)}{gloss}", industry_claims))
    if activity:
        does.append((f"Its registered business activity reads, in Norwegian, {_quote(activity)}" + (f"; in English, this text {activity_gloss}" if activity_gloss else ""),
                     available("registered_activity")))
    if description:
        shown = SLIDER_WORDS.sub("", description)
        does.append((f"Its verified website says {_quote(shown if len(shown) >= 30 else description)}", available("company_description")))
    if not activity and not description:
        unknowns.append(("what the company does beyond its industry code (no registered activity text or verified website description)", None))
    section("activity", "What it does", does)

    # 3. Size and finances --------------------------------------------------------------------------
    money: list[tuple[str, Any]] = []
    if employees is not None:
        money.append((f"The register reports {employees:,.0f} employee{'s' if employees != 1 else ''}", available("registry_employees")))
    elif form not in HOUSING_FORMS:
        unknowns.append(("employee count (not reported to the register)", available("registry_employees") or [first("registry_employees")] if first("registry_employees") else None))
    small_result = max(SMALL_AMOUNT, 0.02 * abs(latest["revenue"] or 0))
    if has_accounts:
        parts = []
        if latest["revenue"] is not None:
            parts.append(f"revenue of {_money(latest['revenue'], currency)}")
        if latest["operating_result"] is not None:
            op = latest["operating_result"]
            parts.append(_kind_pl("operating", op, currency))
        if latest["annual_result"] is not None:
            res = latest["annual_result"]
            kind = "loss" if res < 0 else "profit" if res > 0 else "result"
            parts.append(_kind_pl("annual", res, currency) if result_noun == "annual result" else f"a {kind} for the period of {_money(abs(res), currency)}")
        tail = []
        if latest["assets"] is not None:
            tail.append(f"total assets of {_money(latest['assets'], currency)}")
        if latest["debt"] is not None:
            tail.append(f"debt of {_money(latest['debt'], currency)}")
        whose = "own (parent-company) accounts" if parent_only else "annual accounts"
        sentence = f"Its latest filed {whose} ({latest_label}) report {_join(parts)}" if parts else f"Its latest filed {whose} cover {latest_label}"
        if tail:
            sentence += f", with {_join(tail)}"
        parent_at = len(money)
        money.append((sentence, fin_claims))
        operating, annual = latest["operating_result"], latest["annual_result"]
        if operating is not None and annual is not None and abs(annual - operating) > max(100_000, 0.25 * abs(operating)):
            gap = annual - operating
            op_text = _kind_pl("operating", operating, currency)
            an_text = _kind_pl("annual", annual, currency) if result_noun == "annual result" else \
                f"a {'loss' if annual < 0 else 'profit' if annual > 0 else 'result'} for the period of {_money(abs(annual), currency)}"
            verb = "turned" if (operating < 0) != (annual < 0) else ("lifted" if gap > 0 else "reduced") if operating >= 0 else ("narrowed" if gap > 0 else "deepened")
            link = "into" if verb == "turned" else "to"
            taxless = form in PASS_THROUGH_FORMS
            what = ("Net financial income" if taxless else "Financial income, net of tax,") if gap > 0 else ("Net financial costs" if taxless else "Financial costs and tax")
            whose_items = " in the parent company's accounts" if parent_only else ""
            money.append((f"In {latest_label}, {what[:1].lower() + what[1:]} of {_money(abs(gap), currency)} {verb} {op_text} {link} {an_text}{whose_items}",
                          available("operating_result") + available("annual_result")))
            fin_items_gap = gap
        if group_latest:
            g_parts = []
            if group_latest.get("revenue") is not None:
                g_parts.append(f"revenue of {_money(group_latest['revenue'], g_currency)}")
            for field, kind in (("operating_result", "operating"), ("annual_result", "annual")):
                value_ = group_latest.get(field)
                if value_ is not None:
                    g_parts.append(_kind_pl(kind, value_, g_currency))
            g_tail_parts = [f"total assets of {_money(group_latest[k], g_currency)}" if k == "assets" else f"debt of {_money(group_latest[k], g_currency)}"
                            for k in ("assets", "debt") if group_latest.get(k) is not None]
            g_tail = f", with {_join(g_tail_parts)}" if g_tail_parts else ""
            money.insert(parent_at, (f"The group (konsern) accounts for {group_label} report {_join(g_parts)}{g_tail}", group_years[:1]))
        elif parent_only:
            years = sorted({str(p)[:4] for p in (group[0].get("value") or []) if p}, reverse=True)
            money.append(("The register also holds group (konsern) accounts" + (f" for {_join(years[:3])}" if years else ""), group))
        if latest["assets"] is not None and latest["debt"] is not None and latest["debt"] > latest["assets"]:
            money.append((f"Its debt exceeds its total assets, so its equity at the end of {latest_label} was negative", available("assets") + available("debt")))
            material.append((6, "Its equity is negative", available("assets") + available("debt")))
        elif latest["assets"] is not None and latest["debt"] is not None and latest["assets"] >= 1_000_000 \
                and 0 <= latest["assets"] - latest["debt"] < 0.02 * latest["assets"]:
            thin = f"Its equity is thin: {_money(latest['assets'] - latest['debt'], currency)} against total assets of {_money(latest['assets'], currency)}"
            money.append((thin, available("assets") + available("debt")))
            material.append((7, "Its equity is thin", available("assets") + available("debt")))
        if latest["revenue"] is None:
            unknowns.append(("revenue (not reported in the filed accounts)", available("reporting_period")))
    else:
        fin_state = state("revenue")
        obligation = value("accounting_obligation") or {}
        if fin_state == "not_applicable":
            unknowns.append(("annual accounts (this legal form is not required to file them)", [first("revenue")] if first("revenue") else None))
        elif fin_state in ("failed", "blocked"):
            unknowns.append(("annual accounts (the accounts register could not be read in this run)", [first("revenue")] if first("revenue") else None))
        else:
            reason = obligation.get("reason") if isinstance(obligation, dict) else None
            unknowns.append(("annual accounts (none returned by Regnskapsregisteret" + (f"; {reason.rstrip('.')}" if reason else "") + "); missing figures are not zero",
                             [first("revenue")] if first("revenue") else None))
    section("finances", "Size and finances", money)

    # 4. What changed -----------------------------------------------------------------------------
    changed: list[tuple[str, Any]] = []
    moves_to_explain: list[str] = []
    op_fall = None
    revenue_move = None
    group_compared = len(group_years) > 1 and all(_comparable(g["value"].get("period")) for g in group_years[:2])
    if prev and has_accounts:
        prev_label = _period_label(prev.get("period"))
        cited = [history[0]] + ([period_claim] if period_claim else [])
        whose = "In its own (parent-company) accounts, revenue" if parent_only else "Revenue"
        if comparable and not group_compared:
            for field, noun in (("revenue", whose), ("annual_result", f"the parent company's {result_noun}" if group_years else f"the {result_noun}")):
                old, new = _number(prev.get(field)), latest[field]
                if old is not None and new is not None:
                    text = _change(old, new, currency, noun, prev_label, latest_label, result=field == "annual_result",
                                   small=small_result if field == "annual_result" else SMALL_AMOUNT)
                    changed.append((text[:1].upper() + text[1:], cited + available(field)))
                    swing = old * new < 0 and max(abs(old), abs(new)) >= small_result
                    big = old != 0 and abs(new - old) >= 0.5 * abs(old) and min(abs(old), abs(new)) >= small_result
                    if field == "annual_result" and (swing or big) and not group_years:
                        if swing:
                            material.append((1, f"It swung from a {'loss' if old < 0 else 'profit'} in {prev_label} to a {'loss' if new < 0 else 'profit'} in {latest_label}", cited + available(field)))
                        else:
                            material.append((2, _result_move("Its", old, new, prev_label), cited + available(field)))
                        moves_to_explain.append(f"the change in the annual result from {prev_label} to {latest_label}")
                    if field == "revenue" and old > 0 and new > 0 and abs(new - old) >= 0.3 * old and min(old, new) >= SMALL_AMOUNT:
                        moves_to_explain.append(f"the {'rise' if new > old else 'fall'} in revenue from {prev_label} to {latest_label}")
                        if max(old, new) < 10 * min(old, new) and not group_years:
                            material.append((3, f"Revenue {'rose' if new > old else 'fell'} {abs((new - old) / old * 100):.0f}% in {latest_label}", cited + available(field)))
                if field == "annual_result":
                    old_op, new_op = _number(prev.get("operating_result")), latest["operating_result"]
                    if old_op is not None and new_op is not None and old_op != 0 and abs(new_op - old_op) >= 0.5 * abs(old_op) and (old_op, new_op) != (old, new) \
                            and max(abs(old_op), abs(new_op)) >= small_result:
                        op_change = _change(old_op, new_op, currency, "the parent company's operating result" if group_years else "the operating result",
                                            prev_label, latest_label, result=True, small=small_result)
                        changed.append((op_change[:1].upper() + op_change[1:], cited + available("operating_result")))
                        if new_op < old_op:
                            op_fall = (old_op, new_op, prev_label)
                    if field == "revenue":
                        revenue_move = (old, new, prev_label)
            if len(history) > 1 and all(_comparable((h["value"] or {}).get("period")) for h in history) and not group_years:
                oldest = history[-1]["value"]
                old, new = _number(oldest.get("revenue")), latest["revenue"]
                first_year, last_year = str((oldest.get("period") or {}).get("tilDato") or "")[:4], str((period or {}).get("tilDato") or "")[:4]
                if old is not None and new is not None and min(old, new) >= SMALL_AMOUNT and first_year and last_year:
                    if _money(old, currency) == _money(new, currency):
                        trend = "was about the same"
                    elif new >= 10 * old or old >= 10 * new:
                        trend = f"moved from {_money(old, currency)} to {_money(new, currency)}"
                    elif new >= 2 * old:
                        trend = f"rose to {new / old:.1f} times its {first_year} level"
                    else:
                        trend = f"{'grew' if new > old else 'declined'} {abs((new - old) / old * 100):.0f}% in total"
                    changed.append((f"From {first_year} to {last_year}, {'own (parent-company) ' if parent_only else ''}revenue {trend}", [history[-1]] + available("revenue")))
        elif not comparable:
            old = _number(prev.get("revenue"))
            prev_period = prev.get("period") or {}
            start_gap = _days_between(founded, str(prev_period.get("fraDato") or "")) if founded else None
            first_accounts = start_gap is not None and 0 <= start_gap <= INITIAL_ROLE_DAYS
            long_first = (_days_between(str(prev_period.get("fraDato") or ""), str(prev_period.get("tilDato") or "")) or 0) > 366
            figures = f" (revenue {_money(old, currency)} then, {_money(latest['revenue'], currency)} in {latest_label})" if old is not None and latest["revenue"] is not None else ""
            if first_accounts and _comparable(period):
                changed.append((f"{latest_label[:1].upper() + latest_label[1:]} was its first " + ("twelve-month accounting year; its first accounts covered " if long_first else "full accounting year; its first accounts covered only ")
                                + f"{prev_label}{figures}", cited + available("revenue")))
            else:
                changed.append((f"The latest accounts ({latest_label}) and the previous ones ({prev_label}) cover periods of different length, so they are not compared{figures}", cited + available("revenue")))
    group_move = None
    if len(group_years) > 1:
        g_new, g_old = group_years[0]["value"], group_years[1]["value"]
        if _comparable(g_new.get("period")) and _comparable(g_old.get("period")):
            g_new_label, g_old_label = _period_label(g_new.get("period")), _period_label(g_old.get("period"))
            group_sentences = []
            for field, noun in (("revenue", "Group revenue"), ("annual_result", "the group's annual result")):
                old, new = _number(g_old.get(field)), _number(g_new.get(field))
                if old is not None and new is not None:
                    g_small = max(SMALL_AMOUNT, 0.02 * abs(_number(g_new.get("revenue")) or 0))
                    text = _change(old, new, g_currency, noun, g_old_label, g_new_label, result=field == "annual_result",
                                   small=g_small if field == "annual_result" else SMALL_AMOUNT)
                    group_sentences.append((text[:1].upper() + text[1:], group_years[:2]))
                    if field == "revenue":
                        group_move = (old, new, g_old_label)
                    elif old * new < 0 and max(abs(old), abs(new)) >= g_small:
                        material.append((1, f"The group swung from a {'loss' if old < 0 else 'profit'} in {g_old_label} to a {'loss' if new < 0 else 'profit'} in {g_new_label}", group_years[:2]))
                    elif old != 0 and abs(new - old) >= 0.5 * abs(old) and min(abs(old), abs(new)) >= g_small:
                        material.append((2, _result_move("The group's", old, new, g_old_label), group_years[:2]))
            changed[0:0] = group_sentences
    dated_groups: dict[str, tuple[str, str]] = {}
    for role in roles:
        stamp = str(role.get("last_changed") or "")[:10]
        group_code = str(role.get("group_code") or role.get("role_code") or "")
        if stamp and group_code and stamp > dated_groups.get(group_code, ("", ""))[0]:
            dated_groups[group_code] = (stamp, str(role.get("group") or role.get("role") or ""))
    def initial(stamp: str) -> bool:
        gap = _days_between(founded, stamp) if founded else None
        return gap is not None and gap <= INITIAL_ROLE_DAYS
    changes_after_start = {g: v for g, v in dated_groups.items() if not initial(v[0])}
    def holders_of(group_code: str) -> list[str]:
        return [_clean_name(r["name"]) for r in roles if str(r.get("group_code") or r.get("role_code")) == group_code and r.get("name")]
    def what_group(group_code: str, norwegian: str) -> str:
        english = GROUP_NAMES.get(group_code)
        return f"{english} ({norwegian.lower()})" if english and norwegian else (norwegian or group_code)
    if changes_after_start:
        recent_groups = [(g, v) for g, v in changes_after_start.items() if recent(v[0])]
        recent_groups = sorted(sorted(recent_groups, key=lambda kv: kv[1][0], reverse=True), key=lambda kv: ROLE_IMPORTANCE.get(kv[0], 9))[:2]
        if recent_groups:
            updates = []
            for group_code, (stamp, norwegian) in recent_groups:
                current = holders_of(group_code)
                updates.append(f"the {what_group(group_code, norwegian)} on {stamp}" + (f" (now {_names(current)})" if current else ""))
            sentence = f"In the last two years the register recorded changes to {_join(updates)}"
            shown_codes = {g for g, _ in recent_groups}
            others = sorted(((g, v) for g, v in changes_after_start.items() if recent(v[0]) and g not in shown_codes), key=lambda kv: kv[1][0], reverse=True)
            if others:
                sentence += "; " + _join([f"the {what_group(g, v[1])} on {v[0]}" for g, v in others[:2]]) + " also changed"
            changed.append((sentence, available("registered_roles")))
            if any(g in ("DAGL", "STYR") for g, _ in recent_groups):
                unknowns.append(("who joined or left in those changes (the register lists the current holders, not the history)", available("registered_roles")))
            top_code = recent_groups[0][0]
            if top_code in ("DAGL", "STYR"):
                material.append((4 if top_code == "DAGL" else 5, f"The register recorded a change to the {what_group(top_code, recent_groups[0][1][1])} on {recent_groups[0][1][0]}", available("registered_roles")))
        else:
            group_code, (stamp, norwegian) = max(changes_after_start.items(), key=lambda kv: kv[1][0])
            changed.append((f"No registered role has changed in the last two years; the latest change was to the {what_group(group_code, norwegian)} on {stamp}", available("registered_roles")))
    elif dated_groups and founded and not (run_day and _within(founded, run_day, 550)):
        changed.append((f"The registered roles have not changed since the company was founded in {founded[:4]}", available("registered_roles")))
    if founded and run_day and _within(founded, run_day, 550):
        changed.insert(0, (f"It is a new company, founded on {founded}" + (f"; its first accounts cover {latest_label}" if has_accounts and not prev else ""),
                           [c for c in (*available("founded_date"), *([period_claim] if period_claim and not prev else [])) if c]))
    renamed = [f for f in former if recent(str(f.get("until") or ""))]
    if renamed:
        until = str(renamed[0].get("until") or "")[:10]
        rename = f"It changed its name on {until}; it was previously registered as {_clean_name(renamed[0].get('name'))}"
        changed.append((rename, available("former_names")))
        material.append((0, rename, available("former_names")))
        if isinstance(period, dict) and str(period.get("tilDato") or "") and until > str(period.get("tilDato")):
            changed.append((f"Its latest accounts ({latest_label}) cover a period before that name change", available("former_names") + ([period_claim] if period_claim else [])))
    stale_cut = str(run_day - timedelta(days=365)) if run_day else ""
    if notable and str(notable.get("published_at"))[:10] < stale_cut:
        notable = None
    if notable:
        what = "The newest business news item on its website (about a contract, launch, result, appointment or similar)"
        changed.append((f"{what} is {_quote(notable.get('title') or notable.get('value'), 140)} ({str(notable.get('published_at'))[:10]})", [notable]))
    refresh = envelope.get("refresh") or {}
    changes = envelope.get("changes") or []
    if refresh.get("previous_run_id"):
        when = str(refresh.get("previous_completed_at") or "")[:10]
        since = f"the previous check{' on ' + when if when else ''}"
        if changes:
            fields = sorted({CHANGE_NAMES.get(str(c.get("field")), str(c.get("field") or "").replace("claims.", "").replace("_", " ")) for c in changes})
            examples = []
            for change in changes:
                kind = change.get("change_type") or ("removed" if change.get("new_value") is None else "added" if change.get("old_value") is None else "changed")
                shown = change.get("new_value") if change.get("new_value") is not None else change.get("old_value")
                if isinstance(shown, str) and len(examples) < 3:
                    examples.append(f"{kind} {CHANGE_NAMES.get(str(change.get('field')), 'item')} {_quote(shown, 80)}")
            changed.append((f"Compared with {since}, {len(changes)} material change{'s were' if len(changes) != 1 else ' was'} found ({_join(fields[:6])})"
                            + (f", for example {_join(examples)}" if examples else "") + "; each is listed with its source under changes", None))
        else:
            changed.append((f"No material change was found compared with {since}", None))
    if not changed:
        changed.append(("No dated change is recorded in the sources checked", None))
    section("changes", "What changed", changed)

    # 5. Leadership and locations -------------------------------------------------------------------
    people: list[tuple[str, Any]] = []
    if roles:
        by_code: dict[str, list[dict[str, Any]]] = {}
        for role in roles:
            by_code.setdefault(str(role.get("role_code") or ""), []).append(role)
        ceo = [_clean_name(r["name"]) for r in by_code.get("DAGL", []) if r.get("name")]
        chair = [_clean_name(r["name"]) for r in by_code.get("LEDE", []) if r.get("name")]
        parts = []
        both = len(ceo) == 1 and chair[:1] == ceo
        if both:
            parts.append(f"{ceo[0]} is both chief executive (daglig leder) and chair of the board (styrets leder)")
        for role_code in [*ROLE_ORDER, *sorted(set(by_code) - set(ROLE_ORDER))]:
            holders = by_code.get(role_code) or []
            if not holders or (both and role_code in ("DAGL", "LEDE")):
                continue
            norwegian = holders[0].get("role") or holders[0].get("group")
            names = [_clean_name(r.get("name")) for r in holders if r.get("name")]
            if role_code in NAMED_ROLES and names and len(names) <= 4:
                parts.append(f"{_role_label(role_code, norwegian, len(names))} {_join(names)}")
            else:
                parts.append(f"{len(holders)} {_role_label(role_code, norwegian, len(holders))}")
        people.append((f"The register lists {len(roles)} active role{'s' if len(roles) != 1 else ''}: {'; '.join(parts)}", available("registered_roles")))
    elif state("registered_roles") in ("available", "not_available"):
        unknowns.append(("leadership (no active role holders are registered)", [first("registered_roles")] if first("registered_roles") else None))
    else:
        unknowns.append(("leadership (the roles register could not be read in this run)", None))
    subunits = value("registered_subunits") or []
    if subunits:
        places = []
        for unit in subunits:
            place = _place(((unit.get("address") or {}) if isinstance(unit, dict) else {}).get("kommune") or "")
            if place and place not in places:
                places.append(place)
        where = f" in {_join(places[:4])}" + (f" and {len(places) - 4} other municipalities" if len(places) > 4 else "") if places else ""
        people.append((f"It has {len(subunits)} registered sub-unit{'s' if len(subunits) != 1 else ''} (establishment{'s' if len(subunits) != 1 else ''}){where}", available("registered_subunits")))
    section("people", "Leadership and locations", people)

    # 6. Online presence ------------------------------------------------------------------------------
    online: list[tuple[str, Any]] = []
    platforms = sorted({PLATFORM_NAMES.get(str(c.get("platform") or "").lower(), str(c.get("platform") or "other")) for c in socials})
    if site:
        spans = [str((evidence.get(i) or {}).get("claim_span") or "") for c in available("official_website") for i in c.get("evidence_ids") or []]
        digits = re.compile(rf"{org[:3]}\s?\.?{org[3:6]}\s?\.?{org[6:]}") if len(org) == 9 else None
        proof = []
        name_tokens = [t for t in re.split(r"[^0-9a-zæøå]+", name.casefold()) if len(t) >= 3 and t not in ("asa", "norge", "norway", "holding", "group", "gruppen")]
        if any(sp.startswith('"hjemmeside":') for sp in spans):
            proof.append("it is the homepage listed in the register")
        if digits and any(digits.search(sp) for sp in spans):
            proof.append("the site prints the organisation number")
        elif any(not sp.startswith('"') and any(t in sp.casefold() for t in name_tokens) for sp in spans):
            proof.append("the site names the company")
        online.append((f"Its website is {site}" + (f" ({_join(proof)})" if proof else ""), available("official_website")))
        if socials:
            online.append((f"It links to company profiles on {_join(platforms)}", socials))
        else:
            unknowns.append(("social media profiles (no company profile links were found on its verified website)", available("official_website")))
    else:
        web_state = state("official_website")
        web_claim = [first("official_website")] if first("official_website") else None
        if web_state == "ambiguous":
            unknowns.append(("the official website (a candidate site was found but could not be confirmed as this exact legal entity, so nothing from it is published)", web_claim,
                             "candidate website, not confirmed as this entity"))
        elif web_state in ("blocked", "failed"):
            unknowns.append((f"the official website (the site could not be read in this run: {web_state})", web_claim))
        elif form not in HOUSING_FORMS:
            unknowns.append(("an official website (none is registered or could be verified)", web_claim))
    section("online", "Online presence", online)

    # 7. Hiring -----------------------------------------------------------------------------------------
    hiring: list[tuple[str, Any]] = []
    if pages:
        says_none = any(c.get("openings_listed") is False for c in pages)
        hiring.append((f"It has a careers page, {pages[0].get('value')}" + ("; the page says there are no open positions at the moment" if says_none else ""), pages[:1]))
    if postings:
        dated = sorted(postings, key=lambda c: str(c.get("posted_date") or ""), reverse=True)
        top = dated[0]
        stamp = str(top.get("posted_date") or "")[:10]
        where = "NAV's vacancy register" if top.get("platform") == "arbeidsplassen.nav.no" else "its website"
        hiring.append((f"{len(postings)} job posting{'s were' if len(postings) != 1 else ' was'} found, most recently {_quote(top.get('title') or top.get('value'), 100)}" + (f" (posted {stamp})" if stamp else "") + f" on {where}", dated[:3]))
    employing = (employees or 0) > 0 or bool(site)
    if not signals and employing and form not in HOUSING_FORMS:
        found = ("no careers page or job posting was found on the checked pages of its website or in NAV's vacancy register" if site
                 else "NAV's vacancy register lists no posting for it, and it has no verified website to check")
        unknowns.append((f"whether it is hiring ({found})", [first("hiring_signal")] if first("hiring_signal") else None))
    section("hiring", "Hiring", hiring)

    # 8. Dated public activity on the company's own site ------------------------------------------
    activity_sentences: list[tuple[str, Any]] = []
    if news:
        stamps = [str(c.get("published_at"))[:10] for c in news]
        span_text = f"from {stamps[-1]} to {stamps[0]}" if stamps[-1] != stamps[0] else f"dated {stamps[0]}"
        if len(news) >= MAX_NEWS:
            activity_sentences.append((f"Its website has at least {MAX_NEWS} dated news items; the {MAX_NEWS} most recent run {span_text}", news[:1] + news[-1:]))
        else:
            activity_sentences.append((f"Its website has {len(news)} dated news item{'s' if len(news) != 1 else ''} {span_text}", news[:1] + news[-1:]))
        if stale_cut and stamps[0] < stale_cut:
            activity_sentences[-1] = (activity_sentences[-1][0] + "; none is from the last twelve months", activity_sentences[-1][1])
        others = [c for c in real_news if c is not notable]
        others = sorted(others, key=lambda c: (not MATERIAL_NEWS.search(str(c.get("title") or "")), [-ord(ch) for ch in str(c.get("published_at"))[:10]]))[:2]
        if others:
            headlines = "; ".join(f"{_quote(c.get('title') or c.get('value'), 90)} ({str(c.get('published_at'))[:10]})" for c in others)
            activity_sentences.append((f"Other items include {headlines}", others))
    elif site and junk_news:
        unknowns.append(("dated news (its website shows only template or test posts, or pages stamped with the current date)", junk_news[:1]))
    elif site:
        unknowns.append(("dated news (none found on the checked pages of its website)", [first("dated_news")] if first("dated_news") else None))
    section("activity_log", "Recent activity", activity_sentences)

    explicit_holding = bool(re.search(r"holding", activity, re.I)) or str(code or "").startswith(("64.2", "70.1"))
    if explicit_holding:
        unknowns.append(("which companies it holds shares in (shareholdings are not among the sources checked)", available("registered_activity") + available("industry_code")))
    elif activity_gloss and "owning shares" in activity_gloss and (latest["assets"] or 0) >= 100_000:
        unknowns.append(("whether and in which companies it holds shares (shareholdings are not among the sources checked)", available("registered_activity")))
    loss_cause = has_accounts and (latest["annual_result"] or 0) < -100_000
    if loss_cause:
        moves_to_explain = [m for m in moves_to_explain if "annual result" not in m]
    if moves_to_explain:
        unknowns.append((f"what drove {_join(moves_to_explain[:2])} (the accounts give the figures, not the reasons)", available("annual_result") + available("revenue")))
    if has_accounts and (latest["annual_result"] or 0) < -100_000:
        costs_larger = fin_items_gap is not None and fin_items_gap < 0 and (not op_fall or abs(fin_items_gap) > op_fall[0] - op_fall[1])
        if op_fall and not costs_larger:
            unknowns.append((f"why the operating result fell from {_pl(op_fall[0], currency)} in {op_fall[2]} to {_pl(op_fall[1], currency)} in {latest_label} (the accounts give the figures, not the reasons)", available("operating_result")))
        elif costs_larger:
            unknowns.append((f"what the {'net financial costs' if form in PASS_THROUGH_FORMS else 'financial costs and tax'} of {_money(abs(fin_items_gap), currency)} consist of (the accounts give totals only)", available("annual_result")))
        else:
            unknowns.append((f"what caused the loss of {_money(abs(latest['annual_result']), currency)} in {latest_label} (the accounts give the figures, not the reasons)", available("annual_result")))
    if form in OWNED_FORMS and not OWNER_TEXT.search(description):
        unknowns.append(("who owns it (not in the sources checked)", None))
    if parent_only:
        unknowns.append(("which companies belong to the group (the accounts give the group's totals, not its members)" if group_latest
                         else "the group's consolidated figures and which companies belong to the group", group))

    # 0. In brief (built last from the same claims, shown first) ---------------------------------------
    brief: list[tuple[str, Any]] = []
    opening = f"{name} is {form_text}" + (f" in {_place(muni)}" if muni else "")
    opening_claims = [c for c in (*available("legal_form"), *available("municipality")) if c]
    if division_text:
        opening += f", in broad NACE division {division} ({division_text})"
        opening_claims += available("industry_code")
    if employees is not None:
        opening += f", with {employees:,.0f} employee{'s' if employees != 1 else ''} in the register"
        opening_claims += available("registry_employees")
    if activity_gloss:
        opening += f"; its registered activity text {activity_gloss}"
        opening_claims += available("registered_activity")
    brief.append((opening, opening_claims))
    if value("status_bankrupt") is True or value("status_liquidating") is True:
        brief.append(("It is registered as " + ("bankrupt" if value("status_bankrupt") is True else "being wound up"), available("status_bankrupt") + available("status_liquidating")))
    if group_latest and (group_latest.get("revenue") or 0) > 0:
        g_rev = group_latest["revenue"]
        gc = g_currency or currency
        sentence = f"The group (konsern) had revenue of {_money(g_rev, gc)} in {group_label}"
        if group_move and min(group_move[0], group_move[1]) >= SMALL_AMOUNT and _money(group_move[0], gc) != _money(group_move[1], gc) \
                and max(group_move[0], group_move[1]) < 10 * min(group_move[0], group_move[1]):
            old, new = group_move[0], group_move[1]
            sentence += f", {new / old:.1f} times the {group_move[2]} level" if new >= 2 * old else f", {'up' if new > old else 'down'} {abs((new - old) / old * 100):.0f}% on {group_move[2]}"
        if group_latest.get("annual_result") is not None:
            sentence += f", with {_kind_pl('annual', group_latest['annual_result'], gc)}"
        if latest["revenue"] is not None:
            sentence += f"; the parent company's own revenue was {_money(latest['revenue'], currency)}"
        brief.append((sentence, group_years[:2] + available("revenue")))
    elif has_accounts and (latest["revenue"] or 0) > 0:
        whose = "In its own (parent-company) accounts, revenue" if parent_only else "Revenue"
        sentence = f"{whose} was {_money(latest['revenue'], currency)} in {latest_label}"
        if revenue_move and min(revenue_move[0], revenue_move[1]) >= SMALL_AMOUNT and _money(revenue_move[0], currency) != _money(revenue_move[1], currency):
            old, new = revenue_move[0], revenue_move[1]
            if new >= 10 * old or old >= 10 * new:
                sentence += f", {'up' if new > old else 'down'} from {_money(old, currency)} in {revenue_move[2]}"
            else:
                sentence += f", {new / old:.1f} times the {revenue_move[2]} level" if new >= 2 * old else f", {'up' if new > old else 'down'} {abs((new - old) / old * 100):.0f}% on {revenue_move[2]}"
        if latest["annual_result"] is not None:
            res = latest["annual_result"]
            sentence += f", with {_kind_pl('annual', res, currency)}" if result_noun == "annual result" \
                else f", with a {'loss' if res < 0 else 'profit' if res > 0 else 'result'} for the period of {_money(abs(res), currency)}"
        brief.append((sentence, fin_claims + history[:1]))
    elif has_accounts and latest["annual_result"] is not None:
        revenue_note = "" if latest["revenue"] is None else " and no revenue" if latest["revenue"] == 0 else f" and negative revenue of {_money(latest['revenue'], currency)}"
        result_text = _pl(latest["annual_result"], currency) if latest["annual_result"] else f"an annual result of {_money(0, currency)}"
        brief.append((f"Its latest accounts ({latest_label}) show {result_text}{revenue_note}", fin_claims))
    if material:
        ordered = sorted(material, key=lambda m: m[0])
        brief.append((ordered[0][1], ordered[0][2]))
        if ordered[0][0] < 6 and any(m[0] == 6 for m in ordered):  # negative equity is always worth saying
            brief.append(next((m[1], m[2]) for m in ordered if m[0] == 6))
    presence = []
    presence_claims: list[dict[str, Any]] = []
    if site:
        presence.append("a verified website" + (f" with {len(socials)} linked social profile{'s' if len(socials) != 1 else ''}" if socials else ""))
        presence_claims += available("official_website") + socials[:1]
    if pages:
        presence.append("a careers page")
        presence_claims += pages[:1]
    if postings:
        presence.append(f"{len(postings)} job posting{'s' if len(postings) != 1 else ''}")
        presence_claims += postings[:1]
    if real_news:
        presence.append(f"{len(news)}{'+' if len(news) >= MAX_NEWS else ''} dated news item{'s' if len(news) != 1 else ''} (latest {str(news[0].get('published_at'))[:10]})")
        presence_claims += news[:1]
    if presence and not (material and presence == ["a verified website"]):
        brief.append((f"It has {_join(presence)}", presence_claims))

    built = build("brief", "In brief", brief)
    if built:
        sections.insert(0, built)

    # 9. What is not known, stated as such ------------------------------------------------------------
    if unknowns:
        texts, refs, ids = [], [], []
        for i, item in enumerate(unknowns):
            text, cited = item[0], item[1]
            marker, s_refs, s_ids = sources.cite([c for c in (cited or []) if c], label=item[2] if len(item) > 2 else None)
            texts.append((text[:1].upper() + text[1:] if i == 0 else text) + marker)
            refs.extend(r for r in s_refs if r not in refs)
            ids.extend(x for x in s_ids if x not in ids)
        sections.append({"key": "unknowns", "label": "Not known or not established", "text": "; ".join(texts) + ".", "refs": sorted(refs), "evidence_ids": ids})
    else:
        sections.append({"key": "unknowns", "label": "Not known or not established", "text": "Nothing material among the facts checked; the sources do not cover ownership, reviews or the press.", "refs": [], "evidence_ids": []})

    readable = READABLE_ENTITY.format(org=org) if org else None
    lines = [f"{s['label']}: {s['text']}" for s in sections]
    if sources.items:
        lines.append("Sources: " + "; ".join(f"[{s['n']}] {s['label']}, {s['url']}" for s in sources.items) + "."
                     + (f" Readable register page: {readable}" if readable else ""))
    cited_ids = [eid for s in sources.items for eid in s["evidence_ids"]]
    return {"text": "\n".join(lines), "sections": sections, "sources": sources.items, "evidence_ids": cited_ids, "readable_url": readable}


def _within(stamp: str, day: date, days: int) -> bool:
    try:
        return 0 <= (day - date.fromisoformat(stamp[:10])).days <= days
    except ValueError:
        return False


def apply_envelope_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """Replace the envelope's summary with one built from its published claims (in place).

    The summary claim moves to the front of `claims` and is mirrored in a top-level `summary` and in
    `profile.synthesis_summary`. Nothing else in the envelope changes. On any error the envelope keeps
    the summary it had, so a summary problem can never cost an envelope."""
    try:
        summary = envelope_summary(envelope)
    except Exception as exc:  # the profile-level summary stays in place
        envelope.setdefault("errors", []).append({"field": SUMMARY_FIELD, "type": "SummaryError", "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
        return envelope
    if not summary["evidence_ids"]:
        return envelope
    claims = [c for c in envelope.get("claims") or [] if c.get("field") != SUMMARY_FIELD]
    # Like every earlier version, the summary claim cites the envelope's whole evidence list (so every
    # item stays cited by a claim); `sources` and each section name the items a sentence rests on.
    every_id = [e.get("id") for e in envelope.get("evidence") or [] if e.get("id")]
    claim = {"field": SUMMARY_FIELD, "value": summary["text"], "availability": "available", "confidence": 0.95,
             "evidence_ids": every_id, "sections": summary["sections"], "sources": summary["sources"],
             "method": "template_over_published_claims"}
    envelope["claims"] = [claim, *claims]
    if isinstance(envelope.get("profile"), dict):
        envelope["profile"]["synthesis_summary"] = summary["text"]
    ordered = {"organisation_number": envelope.get("organisation_number"),
               "summary": {"text": summary["text"], "sections": [{k: s[k] for k in ("key", "label", "text", "refs")} for s in summary["sections"]],
                           "sources": [{k: s[k] for k in ("n", "label", "url")} for s in summary["sources"]],
                           "readable_register_page": summary.get("readable_url")}}
    rest = {k: v for k, v in envelope.items() if k not in ordered}
    envelope.clear()
    envelope.update({**ordered, **rest})
    return envelope
