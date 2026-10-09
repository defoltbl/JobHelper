"""Which skills a job posting asks for, and which of them your CV backs up.

No model call: the posting and the master CV are searched for a fixed list of
skills, tools and spoken languages. The list covers software first (it grew
there) and the most telling terms of other professions; an ordinary word that
any posting may use ("compliance", "onboarding") is left out on purpose. The result explains a match score in
the job detail view. It is only ever shown - nothing here is added to a CV.
"""
from __future__ import annotations

import functools
import re

# canonical name -> spellings to look for (the canonical name is always included)
VOCABULARY: dict[str, list[str]] = {
    # languages
    "Python": [], "Java": [], "Kotlin": [], "JavaScript": ["JS"], "TypeScript": ["TS"],
    "C#": ["C sharp", "csharp"], "C++": ["cpp"], "C": [], "Go": ["Golang"], "Rust": [], "PHP": [],
    "Ruby": [], "Swift": [], "Scala": [], "R": [], "Bash": ["shell scripting", "shell script"],
    "PowerShell": [], "SQL": [], "HTML": [], "CSS": [],
    # frameworks / libraries
    "FastAPI": [], "Django": [], "Flask": [], "Spring": ["Spring Boot"], ".NET": ["dotnet", "ASP.NET"],
    "Node.js": ["NodeJS", "Node"], "React": ["React.js", "ReactJS"], "Angular": [], "Vue": ["Vue.js"],
    "Next.js": [], "Express": ["Express.js"], "Android": [], "Jetpack Compose": [], "iOS": [],
    "Pandas": [], "NumPy": [], "PyTorch": [], "TensorFlow": [], "scikit-learn": ["sklearn"],
    "LangChain": [], "Hugging Face": ["HuggingFace"], "Selenium": [], "Playwright": [], "Cypress": [],
    "pytest": [], "JUnit": [],
    # AI
    "LLM": ["LLMs", "large language model", "large language models"],
    "RAG": ["retrieval-augmented", "retrieval augmented"], "NLP": [], "Machine Learning": ["ML"],
    "Deep Learning": [], "Computer Vision": [], "Prompt Engineering": [], "OpenAI": [],
    # data
    "PostgreSQL": ["Postgres"], "MySQL": [], "SQLite": [], "MongoDB": [], "Redis": [], "Oracle": [],
    "SQL Server": ["MSSQL"], "Elasticsearch": [], "Kafka": [], "RabbitMQ": [], "Spark": [], "Airflow": [],
    "ETL": [], "Power BI": [], "Tableau": [], "Excel": [], "Snowflake": [], "Databricks": [], "dbt": [],
    # cloud / devops
    "AWS": ["Amazon Web Services"], "Azure": [], "GCP": ["Google Cloud"], "Docker": [],
    "Kubernetes": ["k8s"], "Terraform": [], "Ansible": [], "Jenkins": [], "GitHub Actions": [],
    "GitLab CI": ["GitLab"], "CI/CD": ["CI CD", "continuous integration"], "Git": [], "Linux": [],
    "Windows Server": [], "Active Directory": [], "Nginx": [], "Grafana": [], "Prometheus": [],
    # ways of working / other
    "REST": ["RESTful", "REST API", "REST APIs"], "GraphQL": [], "gRPC": [], "Microservices": [],
    "Agile": [], "Scrum": [], "Jira": [], "Confluence": [], "ITIL": [], "ServiceNow": [], "SAP": [],
    "Salesforce": [], "Unit testing": ["unit tests"], "Test automation": ["automated testing", "automated tests"],
    "Networking": ["TCP/IP"], "Troubleshooting": [], "Office 365": ["Microsoft 365", "M365", "O365"],
    # ── other professions: terms that are telling, not ordinary words ──
    # finance and accounting
    "IFRS": [], "GAAP": ["US GAAP"], "Accounts payable": [], "Accounts receivable": [],
    "Financial modelling": ["financial modeling"], "Bookkeeping": [], "VAT": [], "Payroll": [],
    "Reconciliation": ["reconciliations"], "QuickBooks": [], "Xero": [], "Bloomberg": [], "AML": [], "KYC": [],
    # sales and marketing
    "CRM": [], "HubSpot": [], "Google Analytics": ["GA4"], "SEO": [], "PPC": ["SEM"], "Google Ads": [],
    "Content marketing": [], "Email marketing": [], "Lead generation": [], "Cold calling": [], "B2B": [],
    "Account management": [], "Copywriting": [], "Market research": [], "Mailchimp": [], "Canva": [],
    # customer support
    "Zendesk": [], "Intercom": [], "Freshdesk": [],
    # people and recruiting
    "Talent acquisition": [], "Workday": [], "SuccessFactors": [], "Employer branding": [],
    "Labour law": ["labor law", "employment law"], "Performance management": [],
    # law
    "Due diligence": [], "GDPR": [], "Litigation": [], "Contract law": [], "Corporate law": [], "Legal research": [],
    # engineering and manufacturing
    "AutoCAD": [], "SolidWorks": [], "CATIA": [], "Siemens NX": [], "PLC": [], "SCADA": [], "Six Sigma": [],
    "Kaizen": [], "ISO 9001": [], "CNC": [], "GD&T": [], "FMEA": [], "MATLAB": [], "Simulink": [], "Revit": [],
    "Technical drawing": ["technical drawings"], "Welding": [], "Hydraulics": [], "Pneumatics": [],
    # logistics
    "Supply chain": [], "Warehouse management": ["WMS"], "Forklift": [], "Incoterms": [],
    "Inventory management": [], "Freight forwarding": [], "Driving licence": ["driving license", "driver's license"],
    # care and health
    "Patient care": [], "First aid": [], "CPR": [], "Medication administration": [],
    "Electronic health records": ["EHR"], "Phlebotomy": [], "Clinical trials": [], "Pharmacovigilance": [],
    # hospitality
    "HACCP": [], "Food safety": [], "Barista": [], "Front desk": [], "Menu planning": [], "Bartending": [],
    # language and teaching
    "Proofreading": [], "Interpreting": [], "TEFL": ["TESOL", "CELTA"], "Lesson planning": [],
    "Classroom management": [], "Subtitling": [], "CAT tools": ["Trados", "memoQ"],
    # design and media
    "Figma": [], "Photoshop": [], "Illustrator": ["Adobe Illustrator"], "InDesign": [], "After Effects": [],
    "Premiere Pro": [], "Typography": [], "Wireframing": ["wireframes"], "Blender": [], "UX": ["user experience"],
    # science and laboratory
    "PCR": [], "HPLC": [], "Cell culture": [], "GLP": [], "GMP": [], "Spectroscopy": [], "Microscopy": [],
    "SPSS": [], "Chromatography": [],
    # construction and trades
    "BIM": [], "Site management": [], "Quantity surveying": [], "Health and safety": ["HSE", "BOZP"],
    "Building regulations": [], "Cost estimation": [],
    # office and public administration
    "Public procurement": [], "Grant writing": [], "Policy analysis": [], "Project management": [],
    "MS Office": ["Microsoft Office"], "PowerPoint": [],
    # spoken languages
    "English": [], "Czech": [], "German": [], "French": [],
}

# Names that are also ordinary words: single letters need language context, the
# rest must be written with their capital letter ("React", not "react to").
_STRICT = {
    "C": r"\bC\s*[/,]\s*C\+\+|\b(?:[Ee]mbedded|ANSI)\s+C\b(?![+#])|\bC\s+(?:programming|language)\b",
    "R": r"\bR\s+(?:programming|language|Shiny)\b|\bRStudio\b"
         r"|\b(?:Python|SQL|SAS)\s*(?:,|/|or|and)\s*R\b(?![&\w])|\bR\s*(?:,|/|or|and)\s*(?:Python|SQL|SAS)\b",
    "Go": r"\bGolang\b|\bGo\s*(?:\(|lang\b|developer|engineer|programming)|\bGo\s*[,/]\s*(?:Python|Java|Rust|Kotlin|C\+\+)"
          r"|(?:Python|Java|Rust|Kotlin|C\+\+)\s*(?:,|/|or|and)\s*Go\b",
    "Spring": r"\bSpring\s*(?:Boot|Framework|MVC|Security|Cloud|Data)\b|\bSpring\b(?=\s*[,/)])",
    "Czech": r"\bCzech\b(?!\s+Republic|\s+market|\s+office|\s+branch|\s+team)",
    "German": r"\bGerman\b(?!y)",
}
_CAPITALISED = {"React", "Swift", "Express", "Spark", "Rust", "Ruby", "Oracle", "Scala",
                "Excel", "Vue", "Flask", "Angular", "Android", "Git", "Redis", "Kafka", "Airflow",
                "Jira", "Confluence", "Azure", "Docker", "Linux", "English", "French",
                "Xero", "Bloomberg", "Canva", "Intercom", "Workday", "Illustrator", "Blender", "Barista", "Forklift"}


def _pattern(name: str, spellings: list[str]) -> re.Pattern:
    if name in _STRICT:
        return re.compile(_STRICT[name])               # case-sensitive on purpose
    parts = []
    for word in [name, *spellings]:
        body = re.escape(word).replace(r"\ ", r"[\s-]+")
        parts.append(rf"(?<![\w+#.]){body}(?![\w+#])")
    return re.compile("|".join(parts), 0 if name in _CAPITALISED else re.IGNORECASE)


_PATTERNS = {name: _pattern(name, alts) for name, alts in VOCABULARY.items()}


def extract(text: str) -> list[str]:
    """Vocabulary items mentioned in text, in order of first appearance."""
    return list(_extract(text or ""))


@functools.lru_cache(maxsize=4096)          # the same descriptions are read again on every Insights view
def _extract(text: str) -> tuple[str, ...]:
    hits = []
    for name, pattern in _PATTERNS.items():
        m = pattern.search(text)
        if m:
            hits.append((m.start(), name))
    return tuple(name for _pos, name in sorted(hits))


def compare(description: str, cv_text: str) -> dict[str, list[str]]:
    """Split what the posting asks for into what the CV shows and what it does not."""
    wanted = extract(description)
    have = set(extract(cv_text))
    return {"matched": [k for k in wanted if k in have],
            "missing": [k for k in wanted if k not in have]}
