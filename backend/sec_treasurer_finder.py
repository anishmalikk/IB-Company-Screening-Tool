"""
SEC Treasurer Finder
===================
Focused approach using SEC filings and company websites to find current treasurers.
Prioritizes recent, official information over LinkedIn snippets.
"""

import os
import re
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from serpapi.google_search import GoogleSearch
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

@dataclass
class TreasurerCandidate:
    """Represents a treasurer candidate with source and confidence"""
    name: str
    title: str  # e.g., "Vice President and Treasurer"
    source: str  # e.g., "sec_filing", "company_website", "linkedin"
    confidence: float  # 0.0 to 1.0
    evidence: str  # Supporting text
    date_found: Optional[str] = None  # Date of the filing/document
    is_current: bool = True  # Whether this appears to be current

@dataclass
class TreasurerResult:
    """Result of treasurer search"""
    candidates: List[TreasurerCandidate]
    primary_candidate: Optional[TreasurerCandidate] = None
    recommendation: str = ""
    needs_verification: bool = True

class SECFilingSearcher:
    """Searches SEC filings for current treasurer information"""
    
    def __init__(self):
        self.current_year = datetime.now().year
        self.recent_years = [self.current_year, self.current_year - 1]
    
    async def search_recent_sec_filings(self, company_name: str) -> List[TreasurerCandidate]:
        """Search recent SEC filings for treasurer information"""
        candidates = []
        
        # More targeted search queries
        search_queries = [
            f'"{company_name}" "executive officers" "treasurer"',
            f'"{company_name}" "officers" "treasurer"',
            f'"{company_name}" "vice president treasurer"',
            f'"{company_name}" "assistant treasurer"',
        ]
        
        for query in search_queries:
            try:
                print(f"      🔍 Searching: {query}")
                search = GoogleSearch({
                    "q": query,
                    "api_key": SERPAPI_API_KEY,
                    "num": 10
                })
                results = search.get_dict()
                
                print(f"         Found {len(results.get('organic_results', []))} results")
                
                for result in results.get("organic_results", []):
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")
                    link = result.get("link", "")
                    
                    print(f"         📄 Result: {title[:50]}...")
                    print(f"         📝 Snippet: {snippet[:100]}...")
                    
                    # Extract treasurer information from snippet
                    treasurer_info = self._extract_treasurer_from_text(snippet, company_name)
                    if treasurer_info:
                        print(f"         ✅ Found treasurer: {treasurer_info['name']}")
                        candidates.append(TreasurerCandidate(
                            name=treasurer_info['name'],
                            title=treasurer_info['title'],
                            source="sec_filing",
                            confidence=0.9,  # High confidence for SEC filings
                            evidence=snippet[:200],
                            date_found=f"{self.current_year}",
                            is_current=True
                        ))
                    else:
                        print(f"         ❌ No treasurer found in snippet")
                        
            except Exception as e:
                print(f"         ❌ Error searching SEC filings: {e}")
        
        return candidates
    
    def _extract_treasurer_from_text(self, text: str, company_name: str) -> Optional[Dict]:
        """Extract treasurer name and title from SEC filing text with strict validation"""
        
        # Very specific patterns for treasurer mentions in SEC filings
        patterns = [
            # "John Smith, Vice President and Treasurer"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:vice\s+president\s+and\s+)?treasurer',
            
            # "Vice President and Treasurer: John Smith"
            r'(?:vice\s+president\s+and\s+)?treasurer[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            
            # "John Smith serves as Treasurer"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+serves\s+as\s+(?:vice\s+president\s+and\s+)?treasurer',
            
            # "Treasurer - John Smith"
            r'treasurer\s*[-–]\s*([A-Z][a-z]+\s+[A-Z][a-z]+)',
            
            # "John Smith, Treasurer"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+treasurer',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                name = match.group(1).strip()
                
                # Strict validation - must be a real person name
                if self._is_valid_person_name(name, company_name):
                    # Determine title based on context
                    title = self._extract_title_from_context(match.group(0))
                    
                    return {
                        'name': name,
                        'title': title
                    }
        
        return None
    
    def _is_valid_person_name(self, name: str, company_name: str) -> bool:
        """Strict validation that extracted text is a real person name"""
        if not name or len(name) < 3:
            return False
        
        words = name.split()
        if len(words) < 2:
            return False
        
        # Must be exactly 2 words (First Last)
        if len(words) != 2:
            return False
        
        # Each word must be capitalized and reasonably long
        for word in words:
            if not word[0].isupper() or len(word) < 2:
                return False
        
        # Reject common non-names and business terms
        invalid_words = [
            'treasurer', 'officer', 'president', 'vice', 'company', 'corp', 'inc',
            'director', 'manager', 'assistant', 'senior', 'executive', 'chief',
            'financial', 'investor', 'relations', 'registrant', 'trust', 'fund',
            'senior', 'director', 'investor', 'relations', 'the', 'registrant'
        ]
        
        name_lower = name.lower()
        if any(invalid in name_lower for invalid in invalid_words):
            return False
        
        # Reject if it looks like a title or department
        if any(word.lower() in ['director', 'manager', 'officer', 'president'] for word in words):
            return False
        
        # Must look like a real person name (no numbers, special chars except hyphens/apostrophes)
        if any(char.isdigit() for char in name):
            return False
        
        # Check against company name to avoid extracting company names
        company_words = set(re.findall(r'[A-Za-z]+', company_name.lower()))
        name_words = set(word.lower() for word in words)
        
        # If both words of the extracted name appear in company name, it's likely a company name
        if name_words.issubset(company_words) and len(company_words) > 0:
            return False
        
        return True
    
    def _extract_title_from_context(self, context: str) -> str:
        """Extract the full title from the context"""
        context_lower = context.lower()
        
        if 'vice president and treasurer' in context_lower:
            return "Vice President and Treasurer"
        elif 'assistant treasurer' in context_lower:
            return "Assistant Treasurer"
        else:
            return "Treasurer"

class CompanyWebsiteSearcher:
    """Searches company websites for treasurer information"""
    
    async def search_company_website(self, company_name: str) -> List[TreasurerCandidate]:
        """Search company website for treasurer information"""
        candidates = []
        
        # More targeted search queries
        search_queries = [
            f'"{company_name}" "executive team" "treasurer"',
            f'"{company_name}" "leadership team" "treasurer"',
            f'"{company_name}" "officers" "treasurer"',
            f'"{company_name}" "vice president treasurer"',
        ]
        
        for query in search_queries:
            try:
                print(f"      🔍 Searching: {query}")
                search = GoogleSearch({
                    "q": query,
                    "api_key": SERPAPI_API_KEY,
                    "num": 5
                })
                results = search.get_dict()
                
                print(f"         Found {len(results.get('organic_results', []))} results")
                
                for result in results.get("organic_results", []):
                    link = result.get("link", "")
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")
                    
                    print(f"         🌐 Link: {link}")
                    print(f"         📄 Title: {title[:50]}...")
                    
                    if self._is_company_website(link, company_name):
                        print(f"         ✅ Company website detected")
                        website_content = await self._scrape_website(link)
                        if website_content:
                            print(f"         📝 Scraped {len(website_content)} characters")
                            treasurer_info = self._extract_treasurer_from_website(website_content, company_name)
                            if treasurer_info:
                                print(f"         ✅ Found treasurer: {treasurer_info['name']}")
                                candidates.append(TreasurerCandidate(
                                    name=treasurer_info['name'],
                                    title=treasurer_info['title'],
                                    source="company_website",
                                    confidence=0.8,  # High confidence for company website
                                    evidence=treasurer_info['context'][:200],
                                    is_current=True
                                ))
                            else:
                                print(f"         ❌ No treasurer found on website")
                        else:
                            print(f"         ❌ Failed to scrape website")
                    else:
                        print(f"         ❌ Not a company website")
                        
            except Exception as e:
                print(f"         ❌ Error searching company website: {e}")
        
        return candidates
    
    def _is_company_website(self, url: str, company_name: str) -> bool:
        """Check if URL is likely the company's website"""
        if not url:
            return False
        
        # Extract domain from URL
        domain = urlparse(url).netloc.lower()
        company_words = company_name.lower().split()
        
        # Check if company name appears in domain
        for word in company_words:
            if len(word) > 2 and word in domain:
                return True
        
        # Also check for common company website patterns
        company_indicators = ['investor', 'ir', 'corporate', 'about', 'leadership', 'management']
        if any(indicator in url.lower() for indicator in company_indicators):
            return True
        
        return False
    
    async def _scrape_website(self, url: str) -> Optional[str]:
        """Scrape website content"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except Exception as e:
            print(f"Error scraping website {url}: {e}")
            return None
    
    def _extract_treasurer_from_website(self, content: str, company_name: str) -> Optional[Dict]:
        """Extract treasurer information from website content with strict validation"""
        
        # Very specific patterns for treasurer mentions on company websites
        patterns = [
            # "John Smith - Vice President and Treasurer"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–]\s*(?:vice\s+president\s+and\s+)?treasurer',
            
            # "Treasurer: John Smith"
            r'(?:vice\s+president\s+and\s+)?treasurer[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)',
            
            # "John Smith, Treasurer"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:vice\s+president\s+and\s+)?treasurer',
            
            # "John Smith serves as Treasurer"
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+serves\s+as\s+(?:vice\s+president\s+and\s+)?treasurer',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                name = match.group(1).strip()
                
                # Strict validation - must be a real person name
                if self._is_valid_person_name(name, company_name):
                    # Determine title based on context
                    title = self._extract_title_from_context(match.group(0))
                    
                    return {
                        'name': name,
                        'title': title,
                        'context': match.group(0)
                    }
        
        return None
    
    def _is_valid_person_name(self, name: str, company_name: str) -> bool:
        """Strict validation that extracted text is a real person name"""
        if not name or len(name) < 3:
            return False
        
        words = name.split()
        if len(words) < 2:
            return False
        
        # Must be exactly 2 words (First Last)
        if len(words) != 2:
            return False
        
        # Each word must be capitalized and reasonably long
        for word in words:
            if not word[0].isupper() or len(word) < 2:
                return False
        
        # Reject common non-names and business terms
        invalid_words = [
            'treasurer', 'officer', 'president', 'vice', 'company', 'corp', 'inc',
            'director', 'manager', 'assistant', 'senior', 'executive', 'chief',
            'financial', 'investor', 'relations', 'registrant', 'trust', 'fund',
            'senior', 'director', 'investor', 'relations', 'the', 'registrant'
        ]
        
        name_lower = name.lower()
        if any(invalid in name_lower for invalid in invalid_words):
            return False
        
        # Reject if it looks like a title or department
        if any(word.lower() in ['director', 'manager', 'officer', 'president'] for word in words):
            return False
        
        # Must look like a real person name (no numbers, special chars except hyphens/apostrophes)
        if any(char.isdigit() for char in name):
            return False
        
        # Check against company name to avoid extracting company names
        company_words = set(re.findall(r'[A-Za-z]+', company_name.lower()))
        name_words = set(word.lower() for word in words)
        
        # If both words of the extracted name appear in company name, it's likely a company name
        if name_words.issubset(company_words) and len(company_words) > 0:
            return False
        
        return True
    
    def _extract_title_from_context(self, context: str) -> str:
        """Extract the full title from the context"""
        context_lower = context.lower()
        
        if 'vice president and treasurer' in context_lower:
            return "Vice President and Treasurer"
        elif 'assistant treasurer' in context_lower:
            return "Assistant Treasurer"
        else:
            return "Treasurer"

class HybridTreasurerFinder:
    """Hybrid approach combining SEC filings and company websites"""
    
    def __init__(self):
        self.sec_searcher = SECFilingSearcher()
        self.website_searcher = CompanyWebsiteSearcher()
    
    async def find_treasurer(self, company_name: str) -> TreasurerResult:
        """Find treasurer using hybrid approach"""
        print(f"\n🔍 Searching for treasurer at: {company_name}")
        
        all_candidates = []
        
        # Step 1: Search SEC filings (highest priority)
        print("   📋 Step 1: Searching recent SEC filings...")
        sec_candidates = await self.sec_searcher.search_recent_sec_filings(company_name)
        all_candidates.extend(sec_candidates)
        print(f"      Found {len(sec_candidates)} candidates from SEC filings")
        
        # Step 2: Search company website
        print("   🌐 Step 2: Searching company website...")
        website_candidates = await self.website_searcher.search_company_website(company_name)
        all_candidates.extend(website_candidates)
        print(f"      Found {len(website_candidates)} candidates from company website")
        
        # Step 3: Remove duplicates and rank
        unique_candidates = self._remove_duplicates(all_candidates)
        ranked_candidates = self._rank_candidates(unique_candidates)
        
        # Step 4: Determine primary candidate
        primary_candidate = self._select_primary_candidate(ranked_candidates)
        
        # Step 5: Generate recommendation
        recommendation = self._generate_recommendation(ranked_candidates, primary_candidate)
        
        return TreasurerResult(
            candidates=ranked_candidates,
            primary_candidate=primary_candidate,
            recommendation=recommendation,
            needs_verification=len(ranked_candidates) > 1
        )
    
    def _remove_duplicates(self, candidates: List[TreasurerCandidate]) -> List[TreasurerCandidate]:
        """Remove duplicate candidates based on name"""
        seen_names = set()
        unique_candidates = []
        
        for candidate in candidates:
            name_key = candidate.name.lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    def _rank_candidates(self, candidates: List[TreasurerCandidate]) -> List[TreasurerCandidate]:
        """Rank candidates by confidence and source reliability"""
        
        def rank_score(candidate):
            # Base score from confidence
            score = candidate.confidence
            
            # Bonus for SEC filings (most reliable)
            if candidate.source.startswith('sec_'):
                score += 0.1
            
            # Bonus for company website
            if candidate.source == 'company_website':
                score += 0.05
            
            return score
        
        return sorted(candidates, key=rank_score, reverse=True)
    
    def _select_primary_candidate(self, candidates: List[TreasurerCandidate]) -> Optional[TreasurerCandidate]:
        """Select the primary candidate if confident enough"""
        if not candidates:
            return None
        
        top_candidate = candidates[0]
        
        # If we have a high-confidence candidate from SEC filings, use it
        if (top_candidate.confidence >= 0.8 and 
            top_candidate.source.startswith('sec_') and
            len(candidates) == 1):
            return top_candidate
        
        # If we have multiple candidates, don't auto-select
        if len(candidates) > 1:
            return None
        
        # If we have a single candidate with decent confidence, use it
        if top_candidate.confidence >= 0.7:
            return top_candidate
        
        return None
    
    def _generate_recommendation(self, candidates: List[TreasurerCandidate], primary: Optional[TreasurerCandidate]) -> str:
        """Generate recommendation based on results"""
        
        if not candidates:
            return "No treasurer information found. Contact company directly."
        
        if primary:
            return f"Likely current treasurer: {primary.name} ({primary.title}) from {primary.source}"
        
        if len(candidates) == 1:
            return f"Possible treasurer: {candidates[0].name} ({candidates[0].title}) from {candidates[0].source} - verify"
        
        # Multiple candidates
        candidate_names = [f"{c.name} ({c.title})" for c in candidates[:3]]
        return f"Multiple candidates found: {', '.join(candidate_names)} - review and select"

# Main function
async def find_treasurer_hybrid(company_name: str) -> TreasurerResult:
    """Main function to find treasurer using hybrid approach"""
    finder = HybridTreasurerFinder()
    return await finder.find_treasurer(company_name)

# Test function
async def test_hybrid_approach():
    """Test the hybrid approach on problematic companies"""
    
    test_companies = [
        "VF Corp",           # Doug Hassman (Head of Treasury)
        "Hologic Inc",       # Sarah Rana
        "Evolus Inc",        # Michael Suh
        "Nordson Corp",      # Anand Patel
    ]
    
    print("🧪 TESTING HYBRID TREASURER FINDER")
    print("=" * 60)
    
    for company in test_companies:
        print(f"\n🏢 Testing: {company}")
        print("-" * 40)
        
        try:
            result = await find_treasurer_hybrid(company)
            
            print(f"📊 Results:")
            print(f"   Primary: {result.primary_candidate.name if result.primary_candidate else 'None'}")
            print(f"   Recommendation: {result.recommendation}")
            print(f"   Needs verification: {result.needs_verification}")
            
            if result.candidates:
                print(f"   Candidates found:")
                for i, candidate in enumerate(result.candidates, 1):
                    print(f"      {i}. {candidate.name} ({candidate.title}) - {candidate.confidence:.2f} from {candidate.source}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()

if __name__ == "__main__":
    asyncio.run(test_hybrid_approach()) 