"""Which skills a job posting asks for, and which of them your CV backs up.

No model call: the posting and the master CV are searched for a fixed list of
technologies, tools and spoken languages. The result explains a match score in
the job detail view. It is only ever shown - nothing here is added to a CV.
"""
from __future__ import annotations

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
                "Jira", "Confluence", "Azure", "Docker", "Linux", "English", "French"}


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
    text = text or ""
    hits = []
    for name, pattern in _PATTERNS.items():
        m = pattern.search(text)
        if m:
            hits.append((m.start(), name))
    return [name for _pos, name in sorted(hits)]


def compare(description: str, cv_text: str) -> dict[str, list[str]]:
    """Split what the posting asks for into what the CV shows and what it does not."""
    wanted = extract(description)
    have = set(extract(cv_text))
    return {"matched": [k for k in wanted if k in have],
            "missing": [k for k in wanted if k not in have]}
