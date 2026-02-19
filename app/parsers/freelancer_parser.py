"""
Freelancer.com email digest parser.

Parses the "latest projects matching your skills" digest emails
into individual project records with structured fields.

Deterministic (regex-based) — no AI tokens needed.
"""
import re
from typing import List, Dict


def is_freelancer_digest(subject: str, body: str) -> bool:
    """Check if an email is a freelancer.com project digest."""
    if not body:
        return False
    has_projects_header = bool(re.search(r'={3,}\s*\n?\s*Projects\s*\n?\s*={3,}', body))
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

    # Find the projects section (after ========\nProjects\n========)
    match = re.search(r'={3,}\s*\n?\s*Projects\s*\n?\s*={3,}', body)
    if not match:
        return []

    content = body[match.end():]

    # Cut off footer
    for marker in ['View more jobs', 'Regards,', 'The Freelancer Team', '\u00a9 20']:
        idx = content.find(marker)
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

    # Find all project blocks using regex
    pattern = re.compile(
        r'([^\n]+?)\n'                    # title (non-empty line before Budget)
        r'Budget:\s*([^\n]+)\n'           # budget line
        r'Skills:\s*([^\n]+)\n'           # skills line
        r'Description:\s*\n'              # "Description:" header
        r'([\s\S]+?)'                     # description text (non-greedy)
        r'\n(/projects/[^\s\n]+)',         # URL starting with /projects/
    )

    projects = []
    for m in pattern.finditer(content):
        title = m.group(1).strip()
        budget_str = m.group(2).strip()
        skills_str = m.group(3).strip()
        description = m.group(4).strip()
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
    is_hourly = '/hr' in budget_str.lower() or 'per hour' in budget_str.lower()

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
