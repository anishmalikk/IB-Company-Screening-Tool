import re
from serpapi.google_search import GoogleSearch
from nameparser import HumanName
import os
from dotenv import load_dotenv
from openai import OpenAI
import unicodedata

load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm_client = OpenAI(api_key=OPENAI_API_KEY)

# At the top of the file, ensure openai is imported (if not already)
try:
    import openai
except ImportError:
    openai = None

def serp_api_search(company_name, query, num_results=20):
    search = GoogleSearch({
        "q": f"{company_name} {query}",
        "api_key": SERPAPI_API_KEY,  # Fixed typo here
        "num": num_results
    })
    results = search.get_dict()
    snippets = []
    for result in results.get("organic_results", []):
        snippet = result.get("snippet")
        if snippet:
            snippets.append(snippet)
    return {"snippets": snippets}

def extract_email_domain(snippets):
    """Extract the first found email domain from snippets."""
    for snippet in snippets:
        # Try to match standard emails
        match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', snippet)
        if match:
            email = match.group(1)
            domain = email[email.index('@'):]
            return domain
    return None

def extract_known_emails(snippets, domain):
    """Extract (name, email) pairs from snippets for a given domain."""
    results = []
    email_pattern = rf'([a-zA-Z0-9_.+-]+{re.escape(domain)})'
    # Improved regex for names with middle initials, periods, hyphens, etc.
    name_regex = (
        r"([A-Z][a-zA-Z.\'\-]+(?: [A-Z][a-zA-Z.\'\-]+)+)[^\n]{0,100}" + email_pattern
    )
    for snippet in snippets:
        for match in re.finditer(name_regex, snippet):
            name = match.group(1)
            email = match.group(2)
            results.append((name, email))
        # Fallback: just extract all emails with the domain
        for email in re.findall(email_pattern, snippet):
            results.append((None, email))
    return results

def detect_email_format(name, email):
    """Determine email format based on name and email."""
    if not name:
        return None
    name_obj = HumanName(name)
    first = name_obj.first.lower()
    last = name_obj.last.lower()
    # Defensive: skip if first or last is empty
    if not first or not last:
        return None
    format_patterns = [
        (f"{first}.{last}", "first.last"),
        (f"{first}{last}", "firstlast"),
        (f"{first[0]}.{last}", "f.last") if first else ("", None),
        (f"{first}", "first"),
        (f"{last}", "last"),
    ]
    local_part = email.split('@')[0].lower()
    for username, fmt in format_patterns:
        if not username or not fmt:
            continue
        if local_part == username:
            return fmt
    return None


def normalize_name(name):
    # Replace non-breaking spaces and normalize unicode
    if not name:
        return name
    return unicodedata.normalize("NFKD", name.replace('\u00A0', ' ')).strip()


def construct_email(name, domain, fmt):
    """Construct email from name and format."""
    if not name or not fmt:
        return None
    name = normalize_name(name)
    name_obj = HumanName(name)
    first = name_obj.first.lower()
    last = name_obj.last.lower()
    # Defensive: skip if first or last is empty when needed
    if fmt in ["first.last", "firstlast", "f.last", "first_initial.last", "first_initiallast", "first.last_initial", "first_initiallast_initial"] and (not first or not last):
        return None
    if fmt == "first.last":
        return f"{first}.{last}{domain}"
    elif fmt == "firstlast":
        return f"{first}{last}{domain}"
    elif fmt == "f.last":
        return f"{first[0]}.{last}{domain}" if first else None
    elif fmt == "first_initial.last":
        return f"{first[0]}.{last}{domain}" if first else None
    elif fmt == "first_initiallast":
        return f"{first[0]}{last}{domain}" if first else None
    elif fmt == "first":
        return f"{first}{domain}" if first else None
    elif fmt == "last":
        return f"{last}{domain}" if last else None
    elif fmt == "first.last_initial":
        return f"{first}.{last[0]}{domain}" if first and last else None
    elif fmt == "first_initiallast_initial":
        return f"{first[0]}{last[0]}{domain}" if first and last else None
    return None

def extract_any_email(snippets, domain):
    """Extract any email with the domain from snippets."""
    email_pattern = rf'([a-zA-Z0-9_.+-]+{re.escape(domain)})'
    for snippet in snippets:
        for email in re.findall(email_pattern, snippet):
            return email  # Return the first found
    return None

def infer_format_from_email(email, name=None):
    local = email.split('@')[0].lower()
    if name:
        name = normalize_name(name)
        from nameparser import HumanName
        name_obj = HumanName(name)
        first = name_obj.first.lower()
        last = name_obj.last.lower()
        first_initial = first[0] if first else ''
        last_initial = last[0] if last else ''
        patterns = [
            (f"{first}.{last}", "first.last"),
            (f"{first}{last}", "firstlast"),
            (f"{first_initial}.{last}", "first_initial.last"),
            (f"{first_initial}{last}", "first_initiallast"),
            (f"{first}", "first"),
            (f"{last}", "last"),
            (f"{first}.{last_initial}", "first.last_initial"),
            (f"{first_initial}{last_initial}", "first_initiallast_initial"),
        ]
        for pattern, fmt in patterns:
            if local == pattern:
                return fmt
    # Fallback: try to infer from structure
    if '.' in local:
        parts = local.split('.')
        if len(parts) == 2:
            return "first.last"
    if len(local) >= 2 and local[1] == '.':
        return "first_initial.last"
    return None

# GPT fallback for email format inference

def gpt_infer_format(name, email):
    """Call GPT to infer the email format given a name and an email."""
    try:
        # Try to use llm_client if available
        try:
            from llm_client import get_llm_client
            client = get_llm_client()
            use_llm_client = True
        except ImportError:
            use_llm_client = False
        prompt = f"""
Given the name '{name}' and the email '{email}', what is the most likely email format used by this company? Reply with only the format string, e.g., 'first_initiallast', 'first.last', 'firstlast', 'first', 'last', 'first_initial.last', etc. Do not explain, just reply with the format string.

Examples:
Name: John Smith, Email: john.smith@company.com -> first.last
Name: Jane Doe, Email: jdoe@company.com -> first_initiallast
Name: Robert Brown, Email: rbrown@company.com -> first_initiallast
Name: Mary Ann Lee, Email: mary.lee@company.com -> first.last
Name: Sarah Prillman, Email: sprillman@company.com -> first_initiallast
"""
        if use_llm_client:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content if response.choices and response.choices[0].message and response.choices[0].message.content else None
        else:
            if openai is None:
                print("OpenAI module not available.")
                return None
            response = llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content if response.choices and response.choices[0].message and response.choices[0].message.content else None
        if content:
            return content.split()[0].strip().replace('"', '').replace("'", "")
        else:
            return None
    except Exception as e:
        print(f"GPT fallback failed: {e}")
        return None


def scrape_emails(company_name, cfo_name, treasurer_name):
    # Step 1: Find email domain
    query_1 = f"{company_name} email format"
    result_1 = serp_api_search(company_name, query_1, num_results=60)
    domain = extract_email_domain(result_1['snippets'])
    if not domain:
        # Fallback: search for investor relations/pr email
        fallback_query = f"{company_name} investor relations pr email"
        result_1b = serp_api_search(company_name, fallback_query, num_results=60)
        domain = extract_email_domain(result_1b['snippets'])
    if not domain:
        return {"error": "Could not find domain"}

    # Step 2: Search known emails with domain
    query_2 = f'{company_name} "{domain}" {cfo_name} email'
    result_2 = serp_api_search(company_name, query_2, num_results=60)

    # Step 3: Extract real emails/names from snippets
    known_emails = extract_known_emails(result_2['snippets'], domain)
    # Only keep those with a name and a valid email format
    known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]
    if not known_emails:
        # Fallback: try to extract any email and infer format
        any_email = extract_any_email(result_2['snippets'], domain)
        fmt = None
        if any_email:
            fmt = infer_format_from_email(any_email, cfo_name)
            if not fmt:
                # Try GPT fallback
                fmt = gpt_infer_format(cfo_name, any_email)
            if fmt:
                cfo_email = construct_email(cfo_name, domain, fmt) if cfo_name and cfo_name.lower() != "same" else None
                treasurer_email = construct_email(treasurer_name, domain, fmt) if treasurer_name and treasurer_name.lower() != "same" else None
                return {
                    "domain": domain,
                    "format": fmt,
                    "cfo_email": cfo_email,
                    "treasurer_email": treasurer_email,
                    "source_email": any_email,
                    "source": "gpt-inferred format" if not infer_format_from_email(any_email, cfo_name) else "inferred from email local part"
                }
        return {"error": "No real emails found"}

    # Step 4: Detect email format from the first valid pair
    name, email = known_emails[0]
    fmt = detect_email_format(name, email)
    if not fmt:
        # Try GPT fallback
        fmt = gpt_infer_format(name, email)
        if not fmt:
            return {"error": "Could not detect email format"}
    # Step 5: Construct emails
    cfo_email = construct_email(cfo_name, domain, fmt) if cfo_name and cfo_name.lower() != "same" else None
    treasurer_email = construct_email(treasurer_name, domain, fmt) if treasurer_name and treasurer_name.lower() != "same" else None

    return {
        "domain": domain,
        "format": fmt,
        "cfo_email": cfo_email,
        "treasurer_email": treasurer_email,
        "source_name": name,
        "source_email": email
    }

if __name__ == "__main__":
    result = scrape_emails("Urban One", "Peter D. Thompson", "same")
    print(result)