# treasurer_extractor.py

import os
import re
from typing import Optional, Dict, List
from dataclasses import dataclass
from llm_client import get_llm_client
from serpapi.google_search import GoogleSearch
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import asyncio
from playwright.async_api import async_playwright

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")

LEADERSHIP_KEYWORDS = [
    "leadership", "executive", "management", "officers", "team", "board", "directors"
]

@dataclass
class TreasurerCandidate:
    """Represents a potential treasurer candidate"""
    name: str
    confidence: float  # 0.0 to 1.0
    source: str  # e.g., "leadership_page", "search_results", "linkedin_snippet"
    evidence: str  # Supporting evidence text
    potential_issues: List[str]  # e.g., ["outdated_info", "unclear_current_role"]

@dataclass
class TreasurerDetectionResult:
    """Structured result for treasurer detection"""
    status: str  # "single_confident", "multiple_candidates", "uncertain", "cfo_treasurer_combo", "none_found"
    primary_treasurer: Optional[str]  # Best candidate if confident
    candidates: List[TreasurerCandidate]  # All potential candidates
    confidence_level: str  # "high", "medium", "low"
    recommendation: str  # What to do with this result
    email_strategy: str  # "use_treasurer", "use_cfo_only", "provide_format_only"

# ============================================================================
# SIMPLIFIED HIGH-ACCURACY TREASURER DETECTION SYSTEM
# ============================================================================

class SimplifiedTreasurerDetector:
    """Simplified regex-based treasurer detection for 90%+ accuracy"""
    
    def __init__(self):
        # CFO+Treasurer combination patterns (REJECT these)
        self.cfo_treasurer_patterns = [
            # More specific patterns to avoid false positives
            r'cfo\s+and\s+treasurer',
            r'chief\s+financial\s+officer\s+and\s+treasurer',
            r'cfo\s*&\s*treasurer',
            r'chief\s+financial\s+officer\s*&\s*treasurer',
            # Only detect actual dual roles, not just mentions
            r'chief\s+financial\s+officer.*treasurer.*\b(?:since|serves?|appointed|named)\b',
            r'cfo.*treasurer.*\b(?:since|serves?|appointed|named)\b',
            r'treasurer.*chief\s+financial\s+officer.*\b(?:since|serves?|appointed|named)\b',
            r'treasurer.*cfo.*\b(?:since|serves?|appointed|named)\b'
        ]
        
        # Enhanced treasurer name extraction patterns for real-world data
        self.treasurer_name_patterns = [
            # Handle quoted nicknames first - extract the quoted name + last name
            r'[A-Z][a-z]+\s+"([A-Z][a-z]+)"\s+([A-Z][a-z]+)[^.]{0,30}treasurer',  # Extract "Joe" and "DiSalvo" from 'Giuseppe "Joe" DiSalvo'
            
            # With middle initials - capture first and last, skip middle
            r'^([A-Z][a-z]+)\s+[A-Z]\.?\s+([A-Z][a-z]+)\s*[-–—][^.]*?treasurer',  # "Justin S. Forsberg - VP/Treasurer" → "Justin Forsberg"
            
            # Primary patterns - simple names at start of text
            r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–—]?\s*(?:assistant\s+)?treasurer',  # "John Smith - Treasurer"
            r'^([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,40}(?:serves?\s+as\s+)?(?:assistant\s+)?treasurer',  # "John Smith serves as Treasurer"
            
            # Names at beginning of line/sentence
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+serves\s+as\s+(?:assistant\s+)?treasurer',  # "Michael Savinelli serves as Treasurer"
            
            # Reverse patterns (treasurer comes first)
            r'(?:assistant\s+)?treasurer[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',  # "Treasurer: John Smith"
            r'(?:assistant\s+)?treasurer\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',  # "Assistant Treasurer Sarah Wilson"
            
            # REAL-WORLD PATTERNS (based on actual failing companies)
            # Handle "Name... as Treasurer" format (Bruker Corp)
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,100}as\s+(?:assistant\s+)?treasurer',  # "Michael Knell... as Treasurer"
            
            # Handle email/contact formats (Evolus Inc)  
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)'s\s+email[^|]{0,30}\|\s*[^'s]*treasurer",  # "Michael Suh's email & phone | Evolus's Treasurer"
            
            # Handle "Treasurer at Company" format (Nordson Corp)
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,100}treasurer\s+at\s+[A-Z]',  # "Anand Patel... Treasurer at Nordson Corp"
            
            # Handle more flexible positions
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,100}(?:assistant\s+)?treasurer\s+(?:of|at)',  # "Name... Treasurer of/at Company"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,60}\.\.\.[^.]{0,40}(?:assistant\s+)?treasurer',  # "Name... Treasurer" with ellipsis
            
            # More flexible patterns (not anchored to start)
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,40}(?:assistant\s+)?treasurer',  # General fallback
            
            # NEW: Handle names mentioned near "treasurer" in broader context
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,200}(?:assistant\s+)?treasurer',  # Broader context for names near treasurer
            r'(?:assistant\s+)?treasurer[^.]{0,200}([A-Z][a-z]+\s+[A-Z][a-z]+)',  # Treasurer mentioned before name
        ]
        
        # Outdated information patterns
        self.outdated_patterns = [
            r'former\s+treasurer', r'past\s+treasurer', r'previously\s+treasurer',
            # Only reject if clearly indicates the person is no longer treasurer
            r'until\s+\d{4}', r'through\s+\d{4}', 
            # Be more specific about date ranges - only reject if clearly outdated
            r'(?:201[0-9]|202[0-3])\s*-\s*(?:201[0-9]|202[0-3])\s*(?:until|through|ended)',  # Date ranges with end indicators
            r'from\s+(?:201[0-9]|202[0-3])\s+to\s+(?:201[0-9]|202[0-3])\s*(?:until|through|ended)',  # From-to dates with end indicators
            r'until\s+(?:201[0-9]|202[0-3])',  # Until dates
            r'through\s+(?:201[0-9]|202[0-3])'  # Through dates
        ]
    
    def is_cfo_treasurer_combo(self, text: str) -> bool:
        """Check if text indicates CFO+Treasurer dual role"""
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in self.cfo_treasurer_patterns)
    
    def is_outdated_info(self, text: str) -> bool:
        """Check if text contains outdated treasurer information"""
        text_lower = text.lower()
        
        # Only reject if there are clear indicators the person is no longer treasurer
        outdated_indicators = [
            'former treasurer', 'past treasurer', 'previously treasurer',
            'until 201', 'until 202', 'through 201', 'through 202',
            'ended in 201', 'ended in 202', 'left in 201', 'left in 202'
        ]
        
        return any(indicator in text_lower for indicator in outdated_indicators)
    
    def extract_treasurer_name(self, text: str, company_name: str) -> Optional[str]:
        """Extract treasurer name using simplified patterns (core names only)"""
        
        # First check for disqualifying patterns
        if self.is_cfo_treasurer_combo(text):
            return None
        
        # Extract names using simplified patterns
        for pattern in self.treasurer_name_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                
                # Handle different group patterns
                name = None
                
                if len(groups) == 1:
                    # Single group - already formatted name
                    name = groups[0].strip()
                elif len(groups) == 2:
                    # Two groups - combine first and last name
                    first_name = groups[0].strip()
                    last_name = groups[1].strip()
                    name = f"{first_name} {last_name}"
                elif len(groups) >= 3:
                    # Multiple groups - find the one that looks like a name
                    for group in groups:
                        candidate = group.strip()
                        # Check if this group looks like a person name (First Last format)
                        if (candidate and 
                            len(candidate.split()) == 2 and 
                            all(word[0].isupper() and word[1:].islower() for word in candidate.split() if len(word) > 1)):
                            name = candidate
                            break
                
                if not name:
                    continue
                
                # Validate the extracted name
                if self.is_valid_person_name(name, company_name):
                    # Check if the ACTUAL MATCH TEXT (not context) is outdated
                    match_text = match.group(0)
                    
                    # Only reject if this specific match contains outdated indicators
                    if self.is_outdated_info(match_text):
                        continue  # Try next pattern/match
                    
                    return name
        
        return None
    
    def is_valid_person_name(self, name: str, company_name: str) -> bool:
        """Validate that extracted text is a person name (enhanced to reject company names)"""
        if not name or len(name) < 3:
            return False
        
        # Clean the name (remove quotes, extra spaces)
        name_clean = re.sub(r'["\']', '', name).strip()
        words = name_clean.split()
        
        # Must have exactly 2 words for core name (First Last)
        if len(words) != 2:
            return False
        
        # Each word must be capitalized and reasonably long
        for word in words:
            if not word[0].isupper() or len(word) < 2:
                return False
        
        # ENHANCED: Check against company name parts to avoid extracting company names
        company_words = set(re.findall(r'[A-Za-z]+', company_name.lower()))
        name_words = set(word.lower() for word in words)
        
        # If both words of the extracted name appear in company name, it's likely a company name
        if name_words.issubset(company_words) and len(company_words) > 0:
            return False
        
        # ENHANCED: Expanded list of invalid words including geographic and business terms
        invalid_words = [
            'treasurer', 'chief', 'financial', 'officer', 'company', 'corp', 'inc', 'president', 'vice',
            'global', 'international', 'services', 'corporation', 'incorporated', 'limited', 'group',
            'holdings', 'enterprises', 'solutions', 'technologies', 'systems', 'business', 'industries',
            'santa', 'barbara', 'new', 'york', 'los', 'angeles', 'san', 'francisco',  # Geographic terms that appeared
            'graphics', 'communications', 'consulting', 'capital', 'partners', 'management',
            # Job titles and generic terms that aren't person names
            'assistant', 'resident', 'finance', 'contacts', 'get', 'svp', 'senior', 'executive', 'director'
        ]
        
        # Check if either word is invalid
        if any(word.lower() in invalid_words for word in words):
            return False
        
        # Must look like real names (no numbers, special chars except hyphens/apostrophes)
        if any(char.isdigit() for char in name_clean):
            return False
        
        # ENHANCED: Reject common business name patterns
        business_patterns = [
            r'\b(corp|inc|llc|ltd|co)\b',
            r'\b(global|international|enterprises)\b',
            r'\b(services|solutions|systems)\b'
        ]
        
        name_lower = name_clean.lower()
        if any(re.search(pattern, name_lower) for pattern in business_patterns):
            return False
        
        return True
    
    def get_treasurer_recommendation(self, snippets: str, company_name: str) -> str:
        """Get treasurer recommendation using optimal logic"""
        
        # Check for CFO+Treasurer combination first
        if self.is_cfo_treasurer_combo(snippets):
            return "same"
        
        # Try to extract a name
        treasurer_name = self.extract_treasurer_name(snippets, company_name)
        
        if treasurer_name:
            return treasurer_name
        else:
            return "same"

# Initialize the simplified detector
treasurer_detector = SimplifiedTreasurerDetector()

# ============================================================================
# TREASURER EXTRACTION FUNCTIONS
# ============================================================================

def fetch_serp_results(company_name: str, query: str, num_results: int = 20) -> str:
    """Fetch search results for treasurer extraction"""
    search = GoogleSearch({
        "q": f"{company_name} {query}",
        "api_key": SERPAPI_API_KEY,
        "num": num_results
    })
    results = search.get_dict()
    text_blobs = []
    
    for result in results.get("organic_results", []):
        snippet = result.get("snippet")
        if snippet:
            text_blobs.append(snippet)

    return "\n".join(text_blobs)

def fetch_leadership_page_url(company_name: str) -> str:
    """Get leadership page URL for treasurer extraction"""
    search = GoogleSearch({
        "q": f"{company_name} treasurer executives",
        "api_key": SERPAPI_API_KEY,
        "num": 10
    })
    results = search.get_dict()
    company_domain = None

    # Try to extract the company's domain from the first result
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            parsed = urlparse(link)
            if not company_domain and parsed.netloc:
                company_domain = parsed.netloc

    # Prefer links with leadership-related keywords and from the company domain
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            parsed = urlparse(link)
            if any(keyword in link.lower() for keyword in LEADERSHIP_KEYWORDS):
                if company_domain and parsed.netloc == company_domain:
                    return link  # Best match: keyword + company domain
    # Fallback: any link with a keyword
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link and any(keyword in link.lower() for keyword in LEADERSHIP_KEYWORDS):
            return link
    # Fallback: just return the first result
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            return link
    return ""

async def get_leadership_page_text(url: str) -> str:
    """Scrape and extract plain text from leadership page using Playwright, fallback to requests."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)  # Wait for JS
            html_content = await page.content()
            await browser.close()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            return text
    except Exception as e:
        print(f"Playwright scraping error: {e}")
        # Fallback to requests
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            return text
        except Exception as e2:
            print(f"Requests fallback error: {e2}")
            return ""

def fetch_treasurer_linkedin_search(company_name: str) -> str:
    """
    Simple treasurer search - returns raw snippets for regex analysis.
    """
    search = GoogleSearch({
        "q": f'"{company_name}" "treasurer"',
        "api_key": SERPAPI_API_KEY,
        "num": 10  # First page only
    })
    results = search.get_dict()
    all_snippets = []
    
    for result in results.get("organic_results", []):
        snippet = result.get("snippet", "")
        title = result.get("title", "")
        
        if snippet and "treasurer" in snippet.lower():
            all_snippets.append(f"{title}\n{snippet}")
    
    return "\n---\n".join(all_snippets[:5])  # Top 5 results only

def parse_leadership_page_for_treasurer(leadership_text: str, company_name: str) -> str:
    """
    Step 1: Parse leadership page text using simplified regex approach.
    Returns treasurer name if found, empty string if not found.
    """
    if not leadership_text:
        return ""
    
    # Use the simplified detector
    treasurer_name = treasurer_detector.extract_treasurer_name(leadership_text, company_name)
    
    if treasurer_name:
        return f"Treasurer (or closest): {treasurer_name}"
    
    return ""

async def get_treasurer_info(company_name: str) -> Dict[str, any]:
    """
    Main function to extract treasurer information.
    Returns a dictionary with treasurer information and metadata.
    """
    try:
        # Get leadership page
        leadership_url = fetch_leadership_page_url(company_name)
        leadership_text = await get_leadership_page_text(leadership_url) if leadership_url else ""
        
        # STEP 1: Check leadership page for treasurer first
        treasurer_from_leadership = parse_leadership_page_for_treasurer(leadership_text, company_name)
        
        # STEP 2: If not found, do targeted LinkedIn search
        treasurer_search_text = ""
        if not treasurer_from_leadership:
            treasurer_search_text = fetch_treasurer_linkedin_search(company_name)
        
        # STEP 3: Get treasurer recommendation using simplified detector
        all_treasurer_sources = ""
        if treasurer_from_leadership:
            all_treasurer_sources += treasurer_from_leadership + "\n"
        if treasurer_search_text:
            all_treasurer_sources += treasurer_search_text
        
        treasurer_recommendation = treasurer_detector.get_treasurer_recommendation(all_treasurer_sources, company_name)
        
        # Determine confidence and metadata
        if treasurer_recommendation == "same":
            confidence = "high" if treasurer_detector.is_cfo_treasurer_combo(all_treasurer_sources) else "low"
            status = "cfo_treasurer_combo" if treasurer_detector.is_cfo_treasurer_combo(all_treasurer_sources) else "none_found"
        else:
            confidence = "medium"  # Could be enhanced with more sophisticated confidence scoring
            status = "single_candidate"
        
        return {
            "treasurer": treasurer_recommendation,
            "treasurer_metadata": {
                "confidence": confidence,
                "status": status,
                "email_strategy": "use_cfo_only" if treasurer_recommendation == "same" else "use_treasurer",
                "recommendation": f"Found: {treasurer_recommendation}",
                "candidates": [treasurer_recommendation] if treasurer_recommendation != "same" else []
            }
        }
        
    except Exception as e:
        print(f"Error extracting treasurer for {company_name}: {e}")
        return {
            "treasurer": "same",
            "treasurer_metadata": {
                "confidence": "low",
                "status": "error",
                "email_strategy": "use_cfo_only",
                "recommendation": f"Error occurred: {str(e)}",
                "candidates": []
            }
        }

# Legacy function for backward compatibility
def get_treasurer_recommendation_simple(company_name: str) -> str:
    """Simple function that returns just the treasurer recommendation string"""
    result = asyncio.run(get_treasurer_info(company_name))
    return result.get("treasurer", "same") 