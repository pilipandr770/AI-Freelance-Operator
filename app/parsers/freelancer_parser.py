"""
Freelancer.com email digest parser.

Parses the "latest projects matching your skills" digest emails
into individual project records with structured fields.

Deterministic (regex-based) — no AI tokens needed.
Strips boilerplate (greeting header, social media links, footer)
so downstream AI agents only see clean project data.
"""
import re
from typing import List, Dict


# ── Boilerplate patterns to strip ──
_HEADER_PATTERNS = [
    re.compile(r'^.*?Hi\s+\w+.*?\n', re.IGNORECASE),
    re.compile(r'^.*?Hallo\s+\w+.*?\n', re.IGNORECASE),
    re.compile(r'Here are the latest.*?\n', re.IGNORECASE),
    re.compile(r'Hier sind die neuesten.*?\n', re.IGNORECASE),
    re.compile(r'We found.*?matching your skills.*?\n', re.IGNORECASE),
    re.compile(r'Wir haben.*?passende.*?\n', re.IGNORECASE),
]

_FOOTER_MARKERS = [
    'View more jobs',
    'Mehr Jobs ansehen',
    'Weitere Projekte',
    'Regards,',
    'Mit freundlichen',
    'Viele Grüße',
    'The Freelancer Team',
    'Das Freelancer Team',
    'Freelancer.com',
    'Download Freelancer',
    'Get it on Google Play',
    'Download on the App Store',
    'Im App Store laden',
    'Bei Google Play laden',
    'Privacy Policy',
    'Datenschutz',
    'Terms and Conditions',
    'Nutzungsbedingungen',
    'Unsubscribe',
    'Abmelden',
    'Abbestellen',
    '\u00a9 20',   # © 20xx
    'Copyright 20',
    'facebook.com',
    'twitter.com',
    'x.com/freelancer',
    'instagram.com',
    'youtube.com',
    'linkedin.com',
    'tiktok.com',
]

_SOCIAL_LINK_RE = re.compile(
    r'https?://(?:www\.)?(?:facebook|twitter|instagram|youtube|linkedin|tiktok|x)\.com/[^\s]*',
    re.IGNORECASE,
)

_BOILERPLATE_LINE_RE = re.compile(
    r'(?:privacy\s*policy|terms\s*(?:and|&)\s*conditions|unsubscribe|'
    r'download\s*(?:the\s*)?app|get\s*it\s*on|app\s*store|google\s*play|'
    r'all\s*rights\s*reserved|you\s*are\s*receiving\s*this)',
    re.IGNORECASE,
)


def strip_boilerplate(text: str) -> str:
    """
    Strip freelancer.com email boilerplate — social links, greeting,
    footer, app download links, copyright.
    Returns clean text suitable for AI models.
    """
    if not text:
        return ''

    # Remove social-media URLs
    text = _SOCIAL_LINK_RE.sub('', text)

    # Remove lines matching boilerplate patterns
    lines = text.split('\n')
    clean_lines = []
    footer_hit = False
    for line in lines:
        stripped = line.strip()
        # Once we hit a footer marker, drop the rest
        if not footer_hit:
            for marker in _FOOTER_MARKERS:
                if marker.lower() in stripped.lower():
                    footer_hit = True
                    break
        if footer_hit:
            continue
        # Skip individual boilerplate lines
        if _BOILERPLATE_LINE_RE.search(stripped):
            continue
        clean_lines.append(line)

    text = '\n'.join(clean_lines)

    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def is_freelancer_digest(subject: str, body: str) -> bool:
    """Check if an email is a freelancer.com project digest (EN + DE)."""
    if not body:
        return False
    # Match both English "Projects" and German "Projekte"
    has_projects_header = bool(re.search(
        r'={3,}\s*\n?\s*(?:Projects|Projekte)\s*\n?\s*={3,}', body
    ))
    has_urls = '/projects/' in body
    return has_projects_header and has_urls


def parse_digest(body: str) -> List[Dict]:
    """
    Parse a freelancer.com digest email body into individual project dicts.

    Returns list of dicts:
        title, description, budget_min, budget_max, currency, is_hourly,
        tech_stack, freelancer_url, category, budget_raw
    """
    if not body:
        return []

    # Find the projects section (EN: Projects, DE: Projekte)
    match = re.search(r'={3,}\s*\n?\s*(?:Projects|Projekte)\s*\n?\s*={3,}', body)
    if not match:
        return []

    content = body[match.end():]

    # Cut off footer (use expanded list)
    for marker in _FOOTER_MARKERS:
        idx = content.lower().find(marker.lower())
        if idx > 0:
            content = content[:idx]
            break

    # ── Strategy: find each project block by "Budget:" anchor ──
    # Split content into chunks, each starting with a title line before "Budget:"
    #
    # Each project block looks like:
    #   [Title]
    #   Budget: [amount]
    #   Skills: [comma list]
    #   Description:
    #   [text...]
    #   /projects/[category]/[slug].html?utm_...

    # Find all project blocks using regex (EN + DE keywords)
    # Skills → Fähigkeiten, Description → Beschreibung
    pattern = re.compile(
        r'([^\n]+?)\n'                              # title
        r'Budget:\s*([^\n]+)\n'                     # budget line
        r'(?:Skills|Fähigkeiten):\s*([^\n]+)\n'     # skills line (EN/DE)
        r'(?:Description|Beschreibung):\s*\n'        # description header (EN/DE)
        r'([\s\S]+?)'                               # description text
        r'\n(/projects/[^\s\n]+)',                   # URL
    )

    projects = []
    for m in pattern.finditer(content):
        title = m.group(1).strip()
        budget_str = m.group(2).strip()
        skills_str = m.group(3).strip()
        description = strip_boilerplate(m.group(4).strip())
        url_path = m.group(5).strip()

        # Skip if title looks like garbage
        if not title or len(title) < 3:
            continue

        # Parse budget
        budget_min, budget_max, currency, is_hourly = _parse_budget(budget_str)

        # Parse skills into list
        tech_stack = [s.strip() for s in skills_str.split(',') if s.strip()]

        # Build full URL (strip UTM params for cleaner display)
        clean_path = url_path.split('?')[0]
        freelancer_url = f"https://www.freelancer.com{clean_path}"

        # Extract category from URL path: /projects/<category>/<slug>.html
        url_parts = url_path.split('/')
        category = url_parts[2] if len(url_parts) > 2 else 'general'
        category = category.replace('-', '_')

        projects.append({
            'title': title,
            'description': description,
            'budget_min': budget_min,
            'budget_max': budget_max,
            'currency': currency,
            'is_hourly': is_hourly,
            'tech_stack': tech_stack,
            'freelancer_url': freelancer_url,
            'category': category,
            'budget_raw': budget_str,
        })

    return projects


def _parse_budget(budget_str: str) -> tuple:
    """
    Parse budget string into (min, max, currency, is_hourly).

    Examples:
        '€25 - €212 EUR'       → (25.0, 212.0, 'EUR', False)
        '€13 - €21 EUR/hr'     → (13.0, 21.0, 'EUR', True)
        '$250 - $750 USD'       → (250.0, 750.0, 'USD', False)
        '₹12500 INR'            → (12500.0, 12500.0, 'INR', False)
    """
    is_hourly = ('/hr' in budget_str.lower() or 'per hour' in budget_str.lower()
                 or '/std' in budget_str.lower() or 'pro stunde' in budget_str.lower())

    # Detect currency
    if '€' in budget_str or 'EUR' in budget_str:
        currency = 'EUR'
    elif '£' in budget_str or 'GBP' in budget_str:
        currency = 'GBP'
    elif '₹' in budget_str or 'INR' in budget_str:
        currency = 'INR'
    elif 'AUD' in budget_str:
        currency = 'AUD'
    elif 'CAD' in budget_str:
        currency = 'CAD'
    else:
        currency = 'USD'

    # Extract numbers (handle commas in numbers like 1,500)
    numbers = re.findall(r'[\d,]+(?:\.\d+)?', budget_str)
    numbers = [float(n.replace(',', '')) for n in numbers]

    budget_min = numbers[0] if numbers else 0
    budget_max = numbers[1] if len(numbers) > 1 else budget_min

    return budget_min, budget_max, currency, is_hourly
