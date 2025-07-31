import re
from serpapi.google_search import GoogleSearch
from nameparser import HumanName
import os
from dotenv import load_dotenv
from openai import OpenAI
import unicodedata

load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm_client = OpenAI(api_key=OPENAI_API_KEY)

try:
    import openai
except ImportError:
    openai = None

GENERIC_EMAIL_PREFIXES = {"pr", "info", "privacy", "investor", "investors", "contact", "support", "admin", "help", "careers", "jobs", "media", "press", "webmaster", "office", "general", "ir", "corp", "sustainability", "esg", "environmental", "hr", "humanresources", "legal", "compliance", "marketing", "sales", "business", "service", "services", "team", "hello", "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster", "abuse", "security", "spam", "feedback", "newsletter", "updates", "alerts", "notifications", "system", "ceo", "cfo", "treasurer"}

def is_generic_email(email):
    local = email.split('@')[0].lower()
    # Remove numbers for robust matching
    local_clean = re.sub(r'[^a-z.]', '', local)
    # Split on dots and check each part
    parts = local_clean.split('.')
    for part in parts:
        if part in GENERIC_EMAIL_PREFIXES:
            return True
    # Also check if the whole local part (with/without dots) matches any prefix
    if local_clean in GENERIC_EMAIL_PREFIXES or local_clean.replace('.', '') in GENERIC_EMAIL_PREFIXES:
        return True
    return False

# Helper to extract all non-generic emails from snippets
def extract_all_non_generic_emails(snippets, domain, actual_names=None):
    email_pattern = rf'([a-zA-Z0-9_.+-]+{re.escape(domain)})'
    emails = set()
    for snippet in snippets:
        for email in re.findall(email_pattern, snippet):
            if not is_generic_email(email) and not is_fake_or_test_email(email, actual_names):
                emails.add(email)
    return list(emails)

def serp_api_search(company_name, query, num_results=20, start=0):
    search = GoogleSearch({
        "q": f"{company_name} {query}",
        "api_key": SERPAPI_API_KEY,
        "num": num_results,
        "start": start
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

def gpt_infer_format(name, emails):
    """Call GPT to infer the email format given a name and a list of emails."""
    try:
        if not emails:
            return None
        # Try to use llm_client if available
        try:
            from llm_client import get_llm_client
            client = get_llm_client()
            use_llm_client = True
        except ImportError:
            use_llm_client = False
        email_list_str = "\n".join(emails)
        prompt = f"""
Given the name '{name}' and the following emails from the same company, determine the email format pattern used by this company. 

IMPORTANT: 
1. Reply with ONLY one of these exact format strings:
   - first.last (e.g., john.smith@company.com)
   - firstlast (e.g., johnsmith@company.com) 
   - first_initiallast (e.g., jsmith@company.com)
   - first_initial.last (e.g., j.smith@company.com)
   - first (e.g., john@company.com)
   - last (e.g., smith@company.com)
   - first.last_initial (e.g., john.s@company.com)
   - first_initiallast_initial (e.g., js@company.com)

2. IGNORE generic/department emails like info@, pr@, sustainability@, contact@, etc.
3. IGNORE random/fake emails like abcdefg@, qwerty@, test123@, etc.
4. Focus ONLY on emails that appear to be real person names.
5. Do NOT reply with the email local part (like "justins" or "marc"). Reply ONLY with the format pattern.

Emails:
{email_list_str}

Examples:
Name: John Smith, Emails: john.smith@company.com, info@company.com -> first.last
Name: Jane Doe, Emails: jdoe@company.com, pr@company.com -> first_initiallast  
Name: Robert Brown, Emails: rbrown@company.com, support@company.com -> first_initiallast
Name: Mary Ann Lee, Emails: mary.lee@company.com, contact@company.com -> first.last
Name: Sarah Prillman, Emails: sprillman@company.com, admin@company.com -> first_initiallast
Name: Justin Smith, Emails: justins@company.com, info@company.com -> firstlast

If all emails are generic or fake (like info@, abcdefg@, etc.), reply with "NO_VALID_FORMAT"
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
            format_str = content.split()[0].strip().replace('"', '').replace("'", "")
            # Handle case where GPT says no valid format found
            if format_str == "NO_VALID_FORMAT":
                print(f"GPT found no valid format from generic emails")
                return None
            # Validate that the format is one we can actually construct
            elif format_str in VALID_EMAIL_FORMATS:
                return format_str
            else:
                print(f"GPT returned invalid format: {format_str}, falling back to inference")
                return None
        else:
            return None
    except Exception as e:
        print(f"GPT fallback failed: {e}")
        return None

# Valid email formats that can be constructed
VALID_EMAIL_FORMATS = {
    "first.last", "firstlast", "f.last", "first_initial.last", "first_initiallast", 
    "first", "last", "first.last_initial", "first_initiallast_initial"
}

# Add a comprehensive set of fake/test names and patterns to filter
FAKE_TEST_NAMES = {
    "jane.doe", "john.smith", "test.user", "test", "example", "demo", "foo.bar", "foo", "bar", 
    "sample.user", "sample", "user", "admin", "guest", "anonymous", "unknown", "placeholder",
    "smith.john", "doe.jane", "smith", "doe", "jane", "john", "jane.doe", "john.smith",
    "testuser", "example.user", "demo.user", "sample.user", "fake.user", "dummy.user",
    "last", "first", "name", "email", "contact", "info", "support", "help", "service"
}

# Common fake email patterns that should be filtered out
FAKE_EMAIL_PATTERNS = [
    r'^test',  # anything starting with test
    r'^demo',  # anything starting with demo
    r'^example',  # anything starting with example
    r'^sample',  # anything starting with sample
    r'^fake',  # anything starting with fake
    r'^dummy',  # anything starting with dummy
    r'^user$',  # just "user"
    r'^admin$',  # just "admin"
    r'^guest$',  # just "guest"
    r'^anonymous$',  # just "anonymous"
    r'^unknown$',  # just "unknown"
    r'^placeholder$',  # just "placeholder"
    r'^last$',  # just "last"
    r'^first$',  # just "first"
    r'^name$',  # just "name"
    r'^email$',  # just "email"
    r'^contact$',  # just "contact"
    r'^info$',  # just "info"
    r'^support$',  # just "support"
    r'^help$',  # just "help"
    r'^service$',  # just "service"
    r'^smith\.john$',  # specific fake patterns
    r'^doe\.jane$',
    r'^jane\.doe$',
    r'^john\.smith$',
    r'^j\.smith$',  # j.smith (unless actual person is John Smith)
    r'^j\.doe$',    # j.doe (unless actual person is Jane Doe)
]

def is_fake_or_test_email(email, actual_names=None):
    """
    Check if an email is fake/test based on patterns and actual names.
    
    Args:
        email: The email to check
        actual_names: List of actual names to compare against (to avoid filtering real names)
    """
    local = email.split('@')[0].lower()
    
    # Remove numbers and special chars for robust matching
    local_clean = re.sub(r'[^a-z.]', '', local)
    
    # Quick check: if it's just a common word, it's likely fake
    common_words = {"last", "first", "name", "email", "contact", "info", "support", "help", "service", "user", "admin", "guest", "test", "demo", "example", "sample"}
    if local_clean in common_words:
        return True
    
    # Check for random/fake emails (like abcdefg, qwerty, etc.)
    # These are clearly not real person names
    random_patterns = [
        r'^[a-z]{6,}$',  # 6+ consecutive letters (like abcdefg)
        r'^[a-z]{3,}[0-9]{2,}$',  # letters followed by numbers (like abc123)
        r'^[0-9]{2,}[a-z]{3,}$',  # numbers followed by letters (like 123abc)
        r'^[a-z]+[0-9]+[a-z]+$',  # alternating letters and numbers
        r'^[a-z]{3,}[0-9]{1,}[a-z]*$',  # letters + numbers + optional letters
        r'^[0-9]{1,}[a-z]{3,}[0-9]*$',  # numbers + letters + optional numbers
        r'^qwerty$',  # common fake patterns
        r'^asdfgh$',
        r'^zxcvbn$',
        r'^abcdef$',
        r'^abcdefg$',
        r'^test123$',
        r'^demo123$',
        r'^user123$',
        r'^admin123$'
    ]
    
    for pattern in random_patterns:
        if re.match(pattern, local_clean):
            return True
    
    # Check for emails that are too short to be real names (likely fake)
    if len(local_clean) < 3:
        return True
    
    # Check for emails that are too long to be real names (likely fake)
    if len(local_clean) > 20:
        return True
    
    # Check for emails with no vowels (likely fake)
    if not any(vowel in local_clean for vowel in 'aeiou'):
        return True
    
    # If we have actual names, check if this might be a real person first
    if actual_names:
        for name in actual_names:
            if name:
                name_obj = HumanName(name)
                first = name_obj.first.lower() if name_obj.first else ""
                last = name_obj.last.lower() if name_obj.last else ""
                
                # Check if the email matches the actual person's name
                if first and last:
                    possible_formats = [
                        f"{first}.{last}",
                        f"{first}{last}",
                        f"{first[0]}.{last}",
                        f"{first[0]}{last}",
                        f"{first}",
                        f"{last}"
                    ]
                    if local_clean in possible_formats:
                        return False  # This is likely a real person
    
    # Check against fake test names
    if local_clean in FAKE_TEST_NAMES:
        return True
    
    # Check against fake patterns (but be more careful with j.smith, j.doe patterns)
    for pattern in FAKE_EMAIL_PATTERNS:
        if re.match(pattern, local_clean):
            # Special handling for j.smith and j.doe patterns
            if pattern in [r'^j\.smith$', r'^j\.doe$']:
                # Only filter if we don't have actual names that could match
                if not actual_names or not any(
                    name and HumanName(name).first and HumanName(name).first.lower().startswith('j')
                    for name in actual_names
                ):
                    return True
            else:
                return True
    
    # Check for patterns like 'test', 'demo', etc. in the local part
    for fake in FAKE_TEST_NAMES:
        if fake in local_clean:
            return True
    
    return False

def scrape_emails(company_name, cfo_name, treasurer_name, ceo_name):
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

    # Step 2: Search known emails with domain (first page, CFO)
    query_2 = f'{company_name} "{domain}" {cfo_name} email'
    result_2 = serp_api_search(company_name, query_2, num_results=20)
    known_emails = extract_known_emails(result_2['snippets'], domain)
    known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]

    # If not found, try CEO
    if not known_emails and ceo_name:
        query_3 = f'{company_name} "{domain}" {ceo_name} email'
        result_3 = serp_api_search(company_name, query_3, num_results=20)
        known_emails = extract_known_emails(result_3['snippets'], domain)
        known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]
        all_snippets = result_2['snippets'] + result_3['snippets']
    else:
        all_snippets = result_2['snippets']

    # If still not found, try Treasurer (if not 'same' and not empty)
    if not known_emails and treasurer_name and treasurer_name.lower() != "same":
        query_4 = f'{company_name} "{domain}" {treasurer_name} email'
        result_4 = serp_api_search(company_name, query_4, num_results=20)
        known_emails = extract_known_emails(result_4['snippets'], domain)
        known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]
        all_snippets = all_snippets + result_4['snippets']

    if not known_emails:
        # Fallback: try to extract all non-generic emails and infer format
        actual_names = [name for name in [cfo_name, treasurer_name, ceo_name] if name and name.lower() != "same"]
        all_emails = extract_all_non_generic_emails(all_snippets, domain, actual_names)
        fmt = None
        source_method = "unknown"
        
        if all_emails:
            # Check if all emails are generic
            all_generic = all(is_generic_email(email) for email in all_emails)
            if all_generic:
                return {"error": "Only generic emails found (no real person emails available)"}
            
            # First, try to infer format from the source email with any of the actual names
            fmt = None
            source_method = "unknown"
            
            # Try with CFO name first
            fmt = infer_format_from_email(all_emails[0], cfo_name)
            if fmt:
                source_method = "inferred from email with CFO name"
            
            # If that didn't work, try with other actual names
            if not fmt and actual_names:
                for name in actual_names:
                    if name != cfo_name:
                        fmt = infer_format_from_email(all_emails[0], name)
                        if fmt:
                            source_method = f"inferred from email with {name}"
                            break
            
            # If still no format, try GPT fallback
            if not fmt:
                fmt = gpt_infer_format(cfo_name, all_emails)
                if fmt:
                    source_method = "gpt-inferred format"
            
            # If GPT failed, try common formats as last resort
            if not fmt:
                # Try common formats that might work
                for test_fmt in ["firstlast", "first.last", "first_initiallast", "first"]:
                    test_email = construct_email(cfo_name, domain, test_fmt)
                    if test_email:
                        fmt = test_fmt
                        source_method = f"fallback format: {test_fmt}"
                        break
            
            if fmt:
                cfo_email = construct_email(cfo_name, domain, fmt) if cfo_name and cfo_name.lower() != "same" else None
                treasurer_email = construct_email(treasurer_name, domain, fmt) if treasurer_name and treasurer_name.lower() != "same" else None
                return {
                    "domain": domain,
                    "format": fmt,
                    "cfo_email": cfo_email,
                    "treasurer_email": treasurer_email,
                    "source_email": all_emails[0] if all_emails else None,
                    "source": source_method
                }
        return {"error": "No real emails found"}

    # Step 4: Detect email format from the first valid pair
    # Filter known_emails for fake/test emails
    actual_names = [name for name in [cfo_name, treasurer_name, ceo_name] if name and name.lower() != "same"]
    filtered_known_emails = [(n, e) for n, e in known_emails if not is_fake_or_test_email(e, actual_names)]
    if not filtered_known_emails:
        return {"error": "No real emails found (all were fake/test)"}
    name, email = filtered_known_emails[0]
    fmt = detect_email_format(name, email)
    if not fmt:
        # Try GPT fallback with all non-generic emails
        all_emails = extract_all_non_generic_emails(all_snippets, domain, actual_names)
        fmt = gpt_infer_format(name, all_emails) if all_emails else None
        
        # If GPT failed, try common formats as last resort
        if not fmt:
            for test_fmt in ["firstlast", "first.last", "first_initiallast", "first"]:
                test_email = construct_email(cfo_name, domain, test_fmt)
                if test_email:
                    fmt = test_fmt
                    break
        
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

#local testing in IDE:
# if __name__ == "__main__":
#     result = scrape_emails("Alcon AG", "Tim Stonesifer", "Brice Zimmermann", "David J. Endicott")
#     print(result)