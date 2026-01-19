"""Resume parsing and profile generation."""

import re
from pathlib import Path
from typing import Any

from freshroles.models.company import MatchingProfile
from freshroles.models.enums import RemoteType


# Common technical skills to detect
TECHNICAL_SKILLS = {
    # Programming languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "sql",
    
    # Frameworks/Libraries
    "react", "angular", "vue", "node.js", "nodejs", "django", "flask", "fastapi",
    "spring", "rails", ".net", "tensorflow", "pytorch", "pandas", "numpy",
    
    # Cloud/DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "k8s", "terraform", "jenkins",
    "ci/cd", "git", "linux", "unix",
    
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb",
    "cassandra", "sqlite",
    
    # Other
    "machine learning", "ml", "deep learning", "ai", "data science", "backend",
    "frontend", "full stack", "fullstack", "devops", "sre", "api", "rest",
    "graphql", "microservices", "agile", "scrum",
}

# Role patterns to detect
ROLE_PATTERNS = [
    r"software engineer",
    r"backend engineer",
    r"frontend engineer",
    r"full[- ]?stack engineer",
    r"data scientist",
    r"data engineer",
    r"machine learning engineer",
    r"ml engineer",
    r"devops engineer",
    r"sre",
    r"site reliability engineer",
    r"product manager",
    r"engineering manager",
    r"software developer",
    r"web developer",
]

# Seniority indicators to exclude
SENIORITY_EXCLUDE = [
    "senior", "sr.", "staff", "principal", "lead", "manager", "director",
    "vp", "head of", "chief", "10+ years", "8+ years", "7+ years",
]


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF file."""
    try:
        import pypdf
        
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text())
            return "\n".join(text_parts)
    except ImportError:
        raise ImportError("pypdf not installed. Install with: pip install pypdf")


def extract_text_from_docx(docx_path: Path) -> str:
    """Extract text from DOCX file."""
    try:
        import docx
        
        doc = docx.Document(docx_path)
        return "\n".join(para.text for para in doc.paragraphs)
    except ImportError:
        raise ImportError("python-docx not installed. Install with: pip install python-docx")


def extract_text_from_txt(txt_path: Path) -> str:
    """Extract text from plain text file."""
    return txt_path.read_text(encoding="utf-8")


def extract_resume_text(resume_path: Path) -> str:
    """
    Extract text from resume file.
    
    Supports: PDF, DOCX, TXT
    """
    suffix = resume_path.suffix.lower()
    
    if suffix == ".pdf":
        return extract_text_from_pdf(resume_path)
    elif suffix in (".docx", ".doc"):
        return extract_text_from_docx(resume_path)
    elif suffix == ".txt":
        return extract_text_from_txt(resume_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def extract_skills(text: str) -> list[str]:
    """Extract technical skills from resume text."""
    text_lower = text.lower()
    found_skills = []
    
    for skill in TECHNICAL_SKILLS:
        # Check for whole word match
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text_lower, re.IGNORECASE):
            found_skills.append(skill)
    
    return sorted(set(found_skills))


def extract_roles(text: str) -> list[str]:
    """Extract job roles from resume text."""
    text_lower = text.lower()
    found_roles = []
    
    for pattern in ROLE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            # Capitalize for display
            role = pattern.replace(r"[- ]?", " ").title()
            found_roles.append(role)
    
    return list(set(found_roles))


def extract_locations(text: str) -> list[str]:
    """Extract location preferences from resume text."""
    # Common US cities
    cities = [
        "San Francisco", "New York", "Seattle", "Austin", "Boston",
        "Los Angeles", "Chicago", "Denver", "Portland", "Atlanta",
        "San Jose", "Palo Alto", "Mountain View", "Remote",
    ]
    
    found = []
    for city in cities:
        if city.lower() in text.lower():
            found.append(city)
    
    return found


class ResumeParser:
    """Parse resume and generate matching profile."""
    
    def __init__(self, embedding_provider=None):
        """
        Initialize resume parser.
        
        Args:
            embedding_provider: Optional embedding provider for semantic extraction.
        """
        self.embedding_provider = embedding_provider
    
    def parse(self, resume_path: Path) -> dict[str, Any]:
        """
        Parse resume and extract relevant information.
        
        Returns:
            Dict with skills, roles, locations, and raw text.
        """
        text = extract_resume_text(resume_path)
        
        return {
            "text": text,
            "skills": extract_skills(text),
            "roles": extract_roles(text),
            "locations": extract_locations(text),
        }
    
    def generate_profile(
        self,
        resume_path: Path,
        profile_name: str = "from_resume",
        add_intern_variants: bool = True,
    ) -> MatchingProfile:
        """
        Generate a matching profile from resume.
        
        Args:
            resume_path: Path to resume file.
            profile_name: Name for the generated profile.
            add_intern_variants: Add intern variants of detected roles.
            
        Returns:
            MatchingProfile ready for job matching.
        """
        parsed = self.parse(resume_path)
        
        # Build desired roles
        desired_roles = []
        for role in parsed["roles"]:
            desired_roles.append(role)
            if add_intern_variants:
                desired_roles.append(f"{role} Intern")
                desired_roles.append(f"{role} Internship")
        
        # If no roles found, add generic ones
        if not desired_roles:
            desired_roles = [
                "Software Engineer",
                "Software Engineer Intern",
                "Software Developer",
            ]
        
        # Use top skills as must-have keywords
        must_have = parsed["skills"][:10]  # Top 10 skills
        
        # Locations
        locations = parsed["locations"] or ["Remote"]
        
        return MatchingProfile(
            name=profile_name,
            desired_roles=desired_roles,
            must_have_keywords=must_have,
            must_not_keywords=SENIORITY_EXCLUDE,
            preferred_locations=locations,
            remote_preference=RemoteType.REMOTE if "Remote" in locations else None,
            min_score_threshold=0.25,  # Slightly lower for broader matching
        )
    
    async def generate_profile_with_embeddings(
        self,
        resume_path: Path,
        profile_name: str = "from_resume",
    ) -> tuple[MatchingProfile, list[float]]:
        """
        Generate profile with embedded resume for semantic matching.
        
        Returns:
            Tuple of (profile, resume_embedding).
        """
        profile = self.generate_profile(resume_path, profile_name)
        
        if self.embedding_provider:
            parsed = self.parse(resume_path)
            embeddings = await self.embedding_provider.embed([parsed["text"]])
            resume_embedding = embeddings[0] if embeddings else []
        else:
            resume_embedding = []
        
        return profile, resume_embedding
