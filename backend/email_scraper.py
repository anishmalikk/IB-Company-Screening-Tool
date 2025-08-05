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

GENERIC_EMAIL_PREFIXES = {"pr", "info", "privacy", "investor", "investors", "contact", "support", "admin", "help", "careers", "jobs", "media", "press", "webmaster", "office", "general", "ir", "corp", "sustainability", "esg", "environmental", "hr", "humanresources", "legal", "compliance", "marketing", "sales", "business", "service", "services", "team", "hello", "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster", "abuse", "security", "spam", "feedback", "newsletter", "updates", "alerts", "notifications", "system", "ceo", "cfo", "treasurer", "reception", "korea", "austria", "germany", "france", "italy", "spain", "uk", "usa", "canada", "mexico", "brazil", "china", "japan", "india", "australia", "singapore", "cs", "customer", "customerservice", "at", "de", "fr", "it", "es", "jp", "cn", "in", "au", "sg", "br", "mx"}

def is_generic_email(email):
    local = email.split('@')[0].lower()
    # Remove numbers for robust matching
    local_clean = re.sub(r'[^a-z.]', '', local)
    
    # Only filter out emails that are EXACTLY generic prefixes
    # Don't filter out emails that contain these as part of longer names
    if local_clean in GENERIC_EMAIL_PREFIXES:
        return True
    
    # Check for exact matches with dots removed
    if local_clean.replace('.', '') in GENERIC_EMAIL_PREFIXES:
        return True
    
    # Check multi-part emails for generic parts
    parts = local_clean.split('.')
    if len(parts) >= 2:
        # Check if it's a regional pattern (like korea.at.cs)
        if (parts[0] in ["korea", "germany", "france", "italy", "spain", "uk", "usa", "canada", "mexico", "brazil", "china", "japan", "india", "australia", "singapore"] and
            len(parts) >= 2 and parts[1] in ["at", "de", "fr", "it", "es", "uk", "us", "ca", "mx", "br", "jp", "cn", "in", "au", "sg", "kr"]):
            return True
        
        # Check if ANY part is a generic prefix (like company.privacy@domain.com)
        for part in parts:
            if part in GENERIC_EMAIL_PREFIXES:
                return True
    
    return False

# Helper to extract all non-generic emails from snippets with source tracking
def extract_all_non_generic_emails(snippets, domain, actual_names=None, snippet_sources=None):
    # Remove trailing dots from domain for pattern matching
    clean_domain = domain.rstrip('.')
    email_pattern = rf'([a-zA-Z0-9_.+-]+{re.escape(clean_domain)})'
    emails = []
    email_sources = {}
    
    for i, snippet in enumerate(snippets):
        source = snippet_sources[i] if snippet_sources and i < len(snippet_sources) else 'unknown'
        for email in re.findall(email_pattern, snippet):
            # Remove trailing dots from extracted email
            clean_email = email.rstrip('.')
            if not is_generic_email(clean_email) and not is_fake_or_test_email(clean_email, actual_names):
                emails.append(clean_email)
                email_sources[clean_email] = source
    
    return emails, email_sources

def serp_api_search(company_name, query, num_results=20, start=0):
    search = GoogleSearch({
        "q": f"{company_name} {query}",
        "api_key": SERPAPI_API_KEY,
        "num": num_results,
        "start": start
    })
    results = search.get_dict()
    snippets = []
    snippet_sources = []  # Track source URL for each snippet
    
    for result in results.get("organic_results", []):
        snippet = result.get("snippet")
        link = result.get("link", "")
        
        if snippet:
            snippets.append(snippet)
            # Extract domain from the source link
            if link:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(link)
                    domain = parsed.netloc.replace('www.', '') if parsed.netloc else 'unknown'
                    snippet_sources.append(domain)
                except:
                    snippet_sources.append('unknown')
            else:
                snippet_sources.append('unknown')
    
    return {"snippets": snippets, "snippet_sources": snippet_sources}

def extract_email_domain(snippets):
    """Extract the first found email domain from snippets."""
    for snippet in snippets:
        # Try to match standard emails
        match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+)', snippet)
        if match:
            email = match.group(1)
            domain = email[email.index('@'):]
            # Remove trailing dots from domain
            domain = domain.rstrip('.')
            return domain
    return None

def extract_known_emails(snippets, domain, snippet_sources=None):
    """Extract (name, email) pairs from snippets for a given domain."""
    results = []
    email_sources = {}  # Track which source each email came from
    
    # Remove trailing dots from domain for pattern matching
    clean_domain = domain.rstrip('.')
    email_pattern = rf'([a-zA-Z0-9_.+-]+{re.escape(clean_domain)})'
    # Improved regex for names with middle initials, periods, hyphens, etc.
    name_regex = (
        r"([A-Z][a-zA-Z.\'\-]+(?: [A-Z][a-zA-Z.\'\-]+)+)[^\n]{0,100}" + email_pattern
    )
    
    for i, snippet in enumerate(snippets):
        source = snippet_sources[i] if snippet_sources and i < len(snippet_sources) else 'unknown'
        
        for match in re.finditer(name_regex, snippet):
            name = match.group(1)
            email = match.group(2)
            results.append((name, email))
            email_sources[email] = source
            
        # Fallback: just extract all emails with the domain
        for email in re.findall(email_pattern, snippet):
            results.append((None, email))
            if email not in email_sources:
                email_sources[email] = source
    
    return results, email_sources

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
    # Remove trailing dots from domain for pattern matching
    clean_domain = domain.rstrip('.')
    email_pattern = rf'([a-zA-Z0-9_.+-]+{re.escape(clean_domain)})'
    for snippet in snippets:
        for email in re.findall(email_pattern, snippet):
            # Remove trailing dots from extracted email
            clean_email = email.rstrip('.')
            return clean_email  # Return the first found
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
    "smith.john", "doe.jane", "jane.doe", "john.smith",
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

def is_likely_human_name(local_part):
    """
    Check if an email local part looks like a human name.
    Uses various heuristics to detect real person names vs generic/technical emails.
    """
    local_clean = re.sub(r'[^a-z.-]', '', local_part.lower())
    # Remove trailing dots
    local_clean = local_clean.rstrip('.')
    
    # First, check if it contains technical/compound patterns
    if '-' in local_clean:
        # But allow hyphenated names (like daniel-hopgood)
        # Only filter if it contains technical terms
        parts = local_clean.split('-')
        for part in parts:
            if part in ['info', 'support', 'admin', 'contact', 'web', 'tech', 'digital', 'technology', 'analytics', 'service', 'security', 'compliance', 'cloud', 'data', 'ux', 'ui', 'qa', 'pm', 'dev', 'api']:
                return False  # This is a technical compound email
        # If no technical terms found, it might be a hyphenated name
    
    # Remove dots for pattern matching
    local_no_dots = local_clean.replace('.', '')
    
    # Common human name patterns (more restrictive)
    name_patterns = [
        r'^[a-z]{2,}\.[a-z]{2,}$',  # first.last
        r'^[a-z]{1}\.[a-z]{2,}$',   # f.last
        r'^[a-z]{2,}[a-z]{2,}$',    # firstlast (no dot)
        r'^[a-z]{1}[a-z]{2,}$',     # flast (no dot)
    ]
    
    # Check for regional/company patterns first (these are NOT human names)
    regional_patterns = [
        r'^[a-z]{3,}\.[a-z]{2,}$',  # company.generic (like nordson.privacy)
        r'^[a-z]{2,}\.[a-z]{2}$',   # country.code (like germany.de)
        r'^[a-z]{2}\.[a-z]{2,}$',   # code.department (like at.cs)
    ]
    
    # But be more specific about what we consider regional
    # Don't filter out common name patterns
    if re.match(r'^[a-z]{2,}\.[a-z]{2,}$', local_clean):
        # Check if this is actually a regional pattern
        parts = local_clean.split('.')
        if parts[0] in ['germany', 'france', 'korea', 'uk', 'us', 'at', 'de', 'fr', 'it', 'es'] or parts[1] in ['de', 'fr', 'hr', 'cs', 'at']:
            return False  # This is regional
        # Otherwise, it might be a human name
        # Don't return False here - let it continue to human name patterns
    
    # Only check for specific known regional patterns, not broad patterns
    # This avoids filtering out legitimate names like michael.johnson
    specific_regional_patterns = [
        'germany.de', 'france.fr', 'korea.at.cs', 'uk.hr', 'us.sales', 
        'at.cs', 'de.hr', 'nordson.privacy', 'company.info', 'business.hr',
        'corp.legal', 'enterprise.support'
    ]
    
    if local_clean in specific_regional_patterns:
        return False  # This is not a human name
    
    # Check for specific regional patterns that are NOT human names
    if local_clean in ['germany.de', 'france.fr', 'uk.hr', 'us.sales', 'at.cs', 'de.hr']:
        return False  # These are regional patterns, not human names
    
    # Check if it matches human name patterns
    for pattern in name_patterns:
        if re.match(pattern, local_clean):
            # Additional checks to ensure it's not a generic word
            if is_generic_word(local_clean):
                return False
            
            # Check if any part contains generic words (like daniel.info)
            parts = local_clean.split('.')
            for part in parts:
                if part in ['info', 'contact', 'support', 'help', 'service', 'admin', 'user', 'guest', 'test', 'demo', 'example', 'sample', 'fake', 'dummy', 'anonymous', 'unknown', 'placeholder', 'last', 'first', 'name', 'email', 'privacy', 'legal', 'it', 'pr', 'ir', 'media', 'press', 'investor', 'sales', 'marketing', 'finance', 'accounting', 'treasury', 'compliance', 'audit', 'tax', 'corpcomm', 'corp', 'corporate', 'comm', 'communications', 'public', 'relations', 'news', 'newsroom']:
                    return False
            
            return True
    
    # For single words, be more restrictive
    if '.' not in local_clean and len(local_clean) >= 3:
        # Check for random letter patterns first
        if re.match(r'^[a-z]{6,}$', local_clean):
            # Check if it's a common random pattern
            random_patterns = ['abcdef', 'qwerty', 'asdfgh', 'zxcvbn']
            if local_clean in random_patterns:
                return False  # This is not a human name
            
            # Check for consecutive letter patterns (like qwerty, asdfgh)
            if local_clean in ['qwerty', 'asdfgh', 'zxcvbn', 'abcdef']:
                return False  # This is not a human name
        
        # Only allow single words that are clearly human names
        if not is_generic_word(local_clean) and len(local_clean) <= 10:
            return True
    
    # Handle hyphenated names (like daniel-hopgood)
    if '-' in local_clean:
        parts = local_clean.split('-')
        # If both parts look like names, allow it
        if len(parts) == 2 and len(parts[0]) >= 3 and len(parts[1]) >= 3:
            if not is_generic_word(parts[0]) and not is_generic_word(parts[1]):
                return True
    
    # Special case for last.first patterns (like johnson.m, hopgood.d)
    if re.match(r'^[a-z]{2,}\.[a-z]{1}$', local_clean):
        if not is_generic_word(local_clean):
            return True
    
    # Special case for names with numbers (like daniel.hopgood.123)
    if re.match(r'^[a-z]{2,}\.[a-z]{2,}\.[0-9]+$', local_clean):
        # This is likely a real name with numbers
        return True
    
    # Handle names with numbers in various formats
    # Note: local_clean has numbers removed, so we need to check the original
    local_with_numbers = re.sub(r'[^a-z.-]', '', local_part.lower())
    
    if re.match(r'^[a-z]{2,}\.[a-z]{2,}\.[0-9]+$', local_with_numbers):
        return True
    if re.match(r'^[a-z]{2,}[0-9]+$', local_with_numbers):
        return True
    if re.match(r'^[a-z]{2,}\.[a-z]{2,}[0-9]+$', local_with_numbers):
        return True
    
    # Also check the original local part for numbers
    original_local = local_part.lower()
    if re.match(r'^[a-z]{2,}\.[a-z]{2,}\.[0-9]+$', original_local):
        return True
    
    return False

def is_generic_word(word):
    """
    Check if a word is generic/technical rather than a human name.
    """
    # Common generic/technical words that aren't human names
    generic_words = {
        # Common words
        "info", "contact", "support", "help", "service", "admin", "user", "guest",
        "test", "demo", "example", "sample", "fake", "dummy", "anonymous", "unknown",
        "placeholder", "last", "first", "name", "email", "privacy", "legal", "hr",
        "it", "pr", "ir", "media", "press", "investor", "sales", "marketing",
        "finance", "accounting", "treasury", "compliance", "audit", "tax",
        
        # Departmental/Corporate emails
        "corpcomm", "corp", "corporate", "comm", "communications", "public", "relations",
        "investor", "relations", "ir", "pr", "media", "press", "news", "newsroom",
        "marketing", "sales", "support", "help", "service", "info", "contact",
        "general", "main", "primary", "secondary", "backup", "emergency",
        
        # Technical terms
        "web", "www", "api", "dev", "qa", "pm", "ba", "ux", "ui", "data", "analytics",
        "ops", "eng", "cs", "de", "at", "fr", "it", "es", "uk", "us", "ca", "mx",
        "br", "jp", "cn", "in", "au", "sg", "kr", "nl", "se", "no", "dk", "fi",
        "pl", "cz", "hu", "ro", "bg", "hr", "si", "sk", "ee", "lv", "lt",
        
        # Company/department terms
        "corp", "inc", "llc", "ltd", "co", "company", "business", "enterprise",
        "korea", "germany", "france", "italy", "spain", "usa", "canada", "mexico",
        "brazil", "china", "japan", "india", "australia", "singapore",
        
        # Common prefixes/suffixes
        "info", "contact", "support", "help", "service", "admin", "user", "guest",
        "test", "demo", "example", "sample", "fake", "dummy", "anonymous", "unknown",
        "placeholder", "last", "first", "name", "email", "privacy", "legal", "hr",
        "it", "pr", "ir", "media", "press", "investor", "sales", "marketing",
        "finance", "accounting", "treasury", "compliance", "audit", "tax",
        
        # Technical abbreviations
        "web", "www", "api", "dev", "qa", "pm", "ba", "ux", "ui", "data", "analytics",
        "ops", "eng", "cs", "de", "at", "fr", "it", "es", "uk", "us", "ca", "mx",
        "br", "jp", "cn", "in", "au", "sg", "kr", "nl", "se", "no", "dk", "fi",
        "pl", "cz", "hu", "ro", "bg", "hr", "si", "sk", "ee", "lv", "lt",
        
        # Electronics/technical terms (like in "info-electronics")
        "electronics", "technology", "tech", "digital", "online", "web", "internet",
        "software", "hardware", "system", "network", "server", "client", "mobile",
        "cloud", "data", "security", "privacy", "compliance", "regulatory",
    }
    
    # Check if the word itself is generic
    if word in generic_words:
        return True
    
    # Check if it contains generic parts (like "info-electronics")
    parts = word.split('-')
    for part in parts:
        if part in generic_words:
            return True
    
    # Check for compound technical patterns
    if '-' in word:
        # Split by hyphen and check if any part is generic
        compound_parts = word.split('-')
        for part in compound_parts:
            if part in generic_words:
                return True
        # If it's a compound word, it's likely technical
        return True
    
    # Check for technical patterns
    technical_patterns = [
        r'^[a-z]+-[a-z]+$',  # word-word (like info-electronics)
        r'^[a-z]+\d+$',      # word123
        r'^\d+[a-z]+$',      # 123word
        r'^[a-z]{1,2}\d+$',  # short word with numbers
    ]
    
    # Check for departmental email patterns
    departmental_patterns = [
        r'^corp[a-z]+$',      # corpcomm, corpinfo, etc.
        r'^[a-z]+comm$',      # corpcomm, prcomm, etc.
        r'^[a-z]+relations$', # investorrelations, publicrelations, etc.
        r'^[a-z]+room$',      # newsroom, pressroom, etc.
        r'^[a-z]+info$',      # companyinfo, businessinfo, etc.
        r'^[a-z]+contact$',   # generalcontact, maincontact, etc.
    ]
    
    for pattern in departmental_patterns:
        if re.match(pattern, word):
            return True
    
    for pattern in technical_patterns:
        if re.match(pattern, word):
            return True
    
    return False

def is_fake_or_test_email(email, actual_names=None):
    """
    Check if an email is fake/test based on patterns and actual names.
    Now uses human name detection for better accuracy.
    """
    local = email.split('@')[0].lower()
    
    # Remove numbers and special chars for robust matching
    local_clean = re.sub(r'[^a-z.-]', '', local)
    
    # Check for random letter patterns first
    random_patterns = ['abcdef', 'qwerty', 'asdfgh', 'zxcvbn']
    if local_clean in random_patterns:
        return True  # These are clearly fake
    
    # First, check if it looks like a human name
    if is_likely_human_name(local_clean):
        # If it looks like a human name, only filter if it's a known fake pattern
        fake_patterns = [
            r'^john\.smith$',
            r'^jane\.doe$',
            r'^j\.smith$',
            r'^j\.doe$',
            r'^test$',
            r'^demo$',
            r'^example$',
            r'^sample$',
            r'^fake$',
            r'^dummy$',
        ]
        
        for pattern in fake_patterns:
            if re.match(pattern, local_clean):
                return True
        
        # If it looks like a human name and isn't a known fake, allow it
        return False
    
    # If it doesn't look like a human name, it's likely fake/generic
    return True

def assess_source_quality(email: str, snippets: list, snippet_sources: list = None) -> str:
    """Assess the quality of the source containing the email"""
    
    # Find the snippet containing this email and its source
    containing_snippet = None
    containing_source = None
    
    for i, snippet in enumerate(snippets):
        if email.lower() in snippet.lower():
            containing_snippet = snippet.lower()
            if snippet_sources and i < len(snippet_sources):
                containing_source = snippet_sources[i].lower()
            break
    
    if not containing_snippet:
        return 'unknown'
    
    # Check for high quality sources (official/verified sources)
    high_quality_sources = [
        'linkedin.com', 'company.com', 'corporate.com', 'pressroom', 'press-release',
        'investor.relations', 'ir.', 'investor.', 'media.', 'newsroom', 'about.',
        'leadership', 'executive', 'management', 'board', 'director',
        # Official filing sources
        'sec.gov', 'edgar', 'filing', '10-k', '10-q', '8-k', 'proxy', 'def 14a',
        'annual.report', 'quarterly.report', 'financial.report',
        # Company official sources
        'company.website', 'official.website', 'corporate.website',
        'press.release', 'news.release', 'announcement',
        # Professional directories
        'zoominfo.com', 'apollo.io', 'hunter.io', 'rocketreach.co',
        # Industry publications
        'industry.report', 'market.research', 'financial.times', 'wall.street.journal'
    ]
    
    # Check both snippet content and source URL
    for source in high_quality_sources:
        if source in containing_snippet or (containing_source and source in containing_source):
            return 'high'
    
    # Check for medium quality sources (business/financial news)
    medium_quality_sources = [
        'crunchbase', 'bloomberg', 'reuters', 'yahoo.finance', 'marketwatch',
        'seeking.alpha', 'fool.com', 'barrons', 'wsj', 'ft.com',
        'business.insider', 'cnbc', 'forbes', 'fortune', 'fast.company'
    ]
    
    for source in medium_quality_sources:
        if source in containing_snippet or (containing_source and source in containing_source):
            return 'medium'
    
    # Check for low quality sources (people finders, social media, etc.)
    low_quality_sources = [
        'facebook.com', 'twitter.com', 'instagram.com', 'reddit.com', 'quora.com',
        'stackoverflow', 'github.com', 'medium.com', 'blogspot', 'wordpress',
        'forum.', 'discussion.', 'comment.', 'reply.', 'post.',
        # People finder/email finder websites
        'anymailfinder.com', 'zabasearch.com', 'ussearch.com', 'peoplefinder.com',
        'emailfinder.com', 'findemail.com', 'emailhunter.com', 'email-format.com',
        'email-checker.com', 'email-validator.com', 'email-finder.com',
        'peoplelooker.com', 'truthfinder.com', 'beenverified.com', 'spokeo.com',
        'intelius.com', 'radaris.com', 'whitepages.com', 'peoplefinders.com',
        'fastpeoplesearch.com', 'fastbackgroundcheck.com', 'peoplefinders.com',
        'success.ai'  # Add success.ai as low quality
    ]
    
    for source in low_quality_sources:
        if source in containing_snippet or (containing_source and source in containing_source):
            return 'low'
    
    return 'unknown'

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
    known_emails, email_sources = extract_known_emails(result_2['snippets'], domain, result_2['snippet_sources'])
    known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]

    # If not found, try CEO
    if not known_emails and ceo_name:
        query_3 = f'{company_name} "{domain}" {ceo_name} email'
        result_3 = serp_api_search(company_name, query_3, num_results=20)
        known_emails, email_sources = extract_known_emails(result_3['snippets'], domain, result_3['snippet_sources'])
        known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]
        all_snippets = result_2['snippets'] + result_3['snippets']
        all_sources = result_2['snippet_sources'] + result_3['snippet_sources']
    else:
        all_snippets = result_2['snippets']
        all_sources = result_2['snippet_sources']

    # If still not found, try Treasurer (if not 'same' and not empty)
    if not known_emails and treasurer_name and treasurer_name.lower() != "same":
        query_4 = f'{company_name} "{domain}" {treasurer_name} email'
        result_4 = serp_api_search(company_name, query_4, num_results=20)
        known_emails, email_sources = extract_known_emails(result_4['snippets'], domain, result_4['snippet_sources'])
        known_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]
        all_snippets = all_snippets + result_4['snippets']
        all_sources = all_sources + result_4['snippet_sources']
    
    # If still not found, try SEC filing search for high-quality sources
    if not known_emails:
        query_5 = f'{company_name} "{domain}" email site:sec.gov'
        result_5 = serp_api_search(company_name, query_5, num_results=20)
        sec_emails, sec_email_sources = extract_known_emails(result_5['snippets'], domain, result_5['snippet_sources'])
        sec_emails = [(n, e) for n, e in sec_emails if n and detect_email_format(n, e)]
        if sec_emails:
            known_emails = sec_emails
            email_sources = sec_email_sources
        all_snippets = all_snippets + result_5['snippets']
        all_sources = all_sources + result_5['snippet_sources']
    
    # If still not found, try investor relations search
    if not known_emails:
        query_6 = f'{company_name} "{domain}" investor relations email'
        result_6 = serp_api_search(company_name, query_6, num_results=20)
        ir_emails, ir_email_sources = extract_known_emails(result_6['snippets'], domain, result_6['snippet_sources'])
        ir_emails = [(n, e) for n, e in ir_emails if n and detect_email_format(n, e)]
        if ir_emails:
            known_emails = ir_emails
            email_sources = ir_email_sources
        all_snippets = all_snippets + result_6['snippets']
        all_sources = all_sources + result_6['snippet_sources']

    if not known_emails:
        # Fallback: try to extract all non-generic emails and infer format
        actual_names = [name for name in [cfo_name, treasurer_name, ceo_name] if name and name.lower() != "same"]
        
        # Get all snippets and sources from all searches
        all_snippets = []
        all_sources = []
        if 'result_2' in locals():
            all_snippets.extend(result_2['snippets'])
            all_sources.extend(result_2['snippet_sources'])
        if 'result_3' in locals():
            all_snippets.extend(result_3['snippets'])
            all_sources.extend(result_3['snippet_sources'])
        if 'result_4' in locals():
            all_snippets.extend(result_4['snippets'])
            all_sources.extend(result_4['snippet_sources'])
        if 'result_5' in locals():
            all_snippets.extend(result_5['snippets'])
            all_sources.extend(result_5['snippet_sources'])
        if 'result_6' in locals():
            all_snippets.extend(result_6['snippets'])
            all_sources.extend(result_6['snippet_sources'])
        
        all_emails, email_sources = extract_all_non_generic_emails(all_snippets, domain, actual_names, all_sources)
        fmt = None
        source_method = "unknown"
        
        if all_emails:
            # Check if all emails are generic
            all_generic = all(is_generic_email(email) for email in all_emails)
            if all_generic:
                return {"error": "Only generic emails found (no real person emails available)"}
            
            # Prioritize emails by source quality first, then by name matching
            prioritized_emails = []
            for email in all_emails:
                email_local = email.split('@')[0].lower()
                source_quality = assess_source_quality(email, all_snippets, all_sources)
                
                # Check if email might match any of our target names
                name_match = False
                for name in actual_names:
                    if name:
                        name_parts = name.lower().split()
                        if len(name_parts) >= 2:
                            first, last = name_parts[0], name_parts[-1]
                            # Check if email contains parts of the name
                            if (first in email_local or last in email_local or 
                                email_local.startswith(first) or email_local.startswith(last)):
                                name_match = True
                                break
                        else:
                            # Single name - check if it's in the email
                            if name.lower() in email_local:
                                name_match = True
                                break
                
                # Create priority score: high quality (30), medium (20), low (10), unknown (0)
                # Name match adds 5 to the score (less weight than source quality)
                priority_score = 0
                if source_quality == 'high':
                    priority_score = 30
                elif source_quality == 'medium':
                    priority_score = 20
                elif source_quality == 'low':
                    priority_score = 10
                
                if name_match:
                    priority_score += 5
                
                prioritized_emails.append((email, priority_score, source_quality))
            
            # Sort by priority score (highest first)
            prioritized_emails.sort(key=lambda x: x[1], reverse=True)
            
            # Use the highest priority email
            source_email = prioritized_emails[0][0] if prioritized_emails else all_emails[0]
            
            # Try to infer format from the source email with any of the actual names
            # Try with CFO name first
            fmt = infer_format_from_email(source_email, cfo_name)
            if fmt:
                source_method = "inferred from email with CFO name"
            
            # If that didn't work, try with other actual names
            if not fmt and actual_names:
                for name in actual_names:
                    if name != cfo_name:
                        fmt = infer_format_from_email(source_email, name)
                        if fmt:
                            source_method = f"inferred from email with {name}"
                            break
            
            # If still no format, try GPT fallback
            if not fmt:
                fmt = gpt_infer_format(cfo_name, [source_email])
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
                
                # Get actual website source from email_sources
                website_source = "unknown"
                if source_email and source_email in email_sources:
                    website_source = email_sources[source_email]
                
                # Get source quality from the prioritized list
                source_quality = "unknown"
                for email, score, quality in prioritized_emails:
                    if email == source_email:
                        source_quality = quality
                        break
                
                # Add all discovered emails for user reference
                all_discovered_emails = []
                for email, score, quality in prioritized_emails:
                    all_discovered_emails.append({
                        "email": email,
                        "quality": quality,
                        "source": email_sources.get(email, "unknown"),
                        "score": score
                    })
                
                return {
                    "domain": domain,
                    "format": fmt,
                    "cfo_email": cfo_email,
                    "treasurer_email": treasurer_email,
                    "source_email": source_email,
                    "source": source_method,
                    "source_quality": source_quality,
                    "website_source": website_source,
                    "all_discovered_emails": all_discovered_emails
                }
        return {"error": "No real emails found"}

    # Step 4: Detect email format from the best valid pair (prioritized by source quality)
    # Filter known_emails for fake/test emails
    actual_names = [name for name in [cfo_name, treasurer_name, ceo_name] if name and name.lower() != "same"]
    filtered_known_emails = [(n, e) for n, e in known_emails if not is_fake_or_test_email(e, actual_names)]
    if not filtered_known_emails:
        return {"error": "No real emails found (all were fake/test)"}
    
    # Prioritize known emails by source quality
    prioritized_known_emails = []
    for name, email in filtered_known_emails:
        source_quality = assess_source_quality(email, all_snippets, all_sources)
        # Create priority score: high quality (30), medium (20), low (10), unknown (0)
        priority_score = 0
        if source_quality == 'high':
            priority_score = 30
        elif source_quality == 'medium':
            priority_score = 20
        elif source_quality == 'low':
            priority_score = 10
        
        prioritized_known_emails.append((name, email, priority_score, source_quality))
    
    # Sort by priority score (highest first)
    prioritized_known_emails.sort(key=lambda x: x[2], reverse=True)
    
    # Use the highest priority email
    name, email, priority_score, source_quality = prioritized_known_emails[0]
    fmt = detect_email_format(name, email)
    if not fmt:
        # Try GPT fallback with all non-generic emails
        all_emails, _ = extract_all_non_generic_emails(all_snippets, domain, actual_names)
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

    # Get actual website source from email_sources
    website_source = "unknown"
    if email and email in email_sources:
        website_source = email_sources[email]
    
    # Use source quality from the prioritized list
    # source_quality is already available from the prioritized_known_emails[0]
    
    # Add all discovered emails for user reference
    all_discovered_emails = []
    for name, email, score, quality in prioritized_known_emails:
        all_discovered_emails.append({
            "email": email,
            "quality": quality,
            "source": email_sources.get(email, "unknown"),
            "score": score,
            "name": name
        })
    
    return {
        "domain": domain,
        "format": fmt,
        "cfo_email": cfo_email,
        "treasurer_email": treasurer_email,
        "source_name": name,
        "source_email": email,
        "source_quality": source_quality,
        "website_source": website_source,
        "all_discovered_emails": all_discovered_emails
    }

#local testing in IDE:
# if __name__ == "__main__":
#     result = scrape_emails("Alcon AG", "Tim Stonesifer", "Brice Zimmermann", "David J. Endicott")
#     print(result)