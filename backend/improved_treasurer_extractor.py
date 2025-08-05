"""
Improved Treasurer Extractor
==========================
Efficient and accurate approach:
1. Check official leadership page first
2. Single comprehensive search with 30 results
3. Use GPT to extract actual human names (not regex)
4. Single verification search per promising candidate
5. Confidence scoring with 80%+ threshold
"""

import os
import asyncio
from typing import Dict, List, Optional, Tuple
from llm_client import get_llm_client
from serpapi.google_search import GoogleSearch

# Import existing functions we'll reuse
from ceo_cfo_extractor import fetch_leadership_page_url, get_leadership_page_text

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")

class LinkedInTreasurerCandidateFinder:
    """
    Finds potential treasurer candidates with LinkedIn URLs for human selection.
    Much more reliable than trying to automatically verify roles.
    """
    
    def __init__(self):
        self.client = get_llm_client()
        self.api_calls_used = 0
    
    async def get_treasurer_candidates(self, company_name: str) -> Dict[str, any]:
        """
        Main function: Find LinkedIn candidates for human selection.
        Returns a list of potential treasurers with LinkedIn URLs when possible.
        """
        print(f"\n🔍 Finding treasurer candidates for: {company_name}")
        self.api_calls_used = 0
        
        # Step 1: Check official leadership page first
        print("   📋 Step 1: Checking official leadership page...")
        official_treasurer = await self.check_official_leadership_page(company_name)
        
        if official_treasurer and official_treasurer != "not_found":
            print(f"      ✅ Found on official page: {official_treasurer}")
            return {
                "treasurer": official_treasurer,
                "candidates": [],
                "selection_needed": False,
                "source": "official_page",
                "api_calls_used": self.api_calls_used
            }
        
        print("      ⚪ Not found on official page, searching for candidates...")
        
        # Step 2: Search for LinkedIn candidates
        print("   🔍 Step 2: Searching for LinkedIn candidates...")
        search_results = await self.comprehensive_linkedin_search(company_name)
        
        if not search_results:
            print("      ❌ No search results found")
            return self._return_no_candidates("No search results found")
        
        # Step 3: Extract LinkedIn candidates with GPT
        print("   🤖 Step 3: Extracting LinkedIn candidates...")
        candidates = await self.extract_linkedin_candidates(company_name, search_results)
        
        if not candidates:
            print("      ❌ No candidates found by GPT")
            return self._return_no_candidates("No candidates found by GPT")
        
        print(f"      ✅ Found {len(candidates)} candidate(s)")
        for i, candidate in enumerate(candidates, 1):
            url_display = candidate['url'] if candidate['url'] != 'NO_URL_FOUND' else 'No LinkedIn URL'
            score_display = f" (Score: {candidate.get('score', '?')})" if 'score' in candidate else ""
            print(f"         {i}. {candidate['name']}{score_display} - {url_display}")
        
        print(f"      📊 Total API calls used: {self.api_calls_used}")
        
        return {
            "treasurer": None,  # No automatic selection
            "candidates": candidates,
            "selection_needed": True,
            "source": "linkedin_search",
            "api_calls_used": self.api_calls_used,
            "instruction": "Please select the correct treasurer from the candidates list (ranked by likelihood), or choose 'same' if CFO handles treasury"
        }
    
    async def check_official_leadership_page(self, company_name: str) -> Optional[str]:
        """Check official leadership page for explicit treasurer mention."""
        try:
            leadership_url = fetch_leadership_page_url(company_name)
            if not leadership_url:
                return "not_found"
            
            print(f"      ✅ Found leadership page: {leadership_url}")
            self.api_calls_used += 1
            
            leadership_text = await get_leadership_page_text(leadership_url)
            if not leadership_text:
                return "not_found"
            
            print(f"      ✅ Scraped {len(leadership_text)} characters from leadership page")
            
            # Simple check for explicit treasurer mentions
            text_lower = leadership_text.lower()
            if "treasurer" in text_lower:
                # Try to extract the name using basic patterns
                import re
                patterns = [
                    r'([A-Z][a-z]+\s+[A-Z][a-z]+)[^.]{0,50}treasurer',
                    r'treasurer[^.]{0,50}([A-Z][a-z]+\s+[A-Z][a-z]+)',
                ]
                
                for pattern in patterns:
                    matches = re.finditer(pattern, leadership_text, re.IGNORECASE)
                    for match in matches:
                        name = match.group(1).strip()
                        if self.is_valid_person_name(name, company_name):
                            return name
            
            return "not_found"
            
        except Exception as e:
            print(f"      ❌ Error checking leadership page: {e}")
            return "not_found"
    
    async def comprehensive_linkedin_search(self, company_name: str) -> str:
        """Search for LinkedIn profiles and treasury-related information."""
        try:
            # Enhanced search queries to catch more treasurer variations
            search_queries = [
                f'site:linkedin.com "{company_name}" treasurer',
                f'site:linkedin.com "{company_name}" "assistant treasurer"',
                f'site:linkedin.com "{company_name}" "head of treasury"',
                f'site:linkedin.com "{company_name}" "corporate finance" treasury',
                f'site:linkedin.com "{company_name}" "investor relations" treasury',
                f'site:linkedin.com "{company_name}" "head of corporate finance"',
                f'site:linkedin.com "{company_name}" "corporate finance" "treasury"',
                f'site:linkedin.com "{company_name}" "finance" "treasury"', 
                f'"{company_name}" treasurer linkedin profile',
                f'"{company_name}" treasury department staff linkedin',
                f'"{company_name}" "corporate finance" linkedin',
                f'"{company_name}" "treasury management" linkedin',
                f'site:linkedin.com "{company_name}" "head of" finance',
                f'site:linkedin.com "{company_name}" "director" finance',
                f'site:linkedin.com "{company_name}" "VP" finance'
            ]
            
            all_results_text = []
            seen_urls = set()
            
            for query in search_queries:
                try:
                    search = GoogleSearch({
                        "q": query,
                        "api_key": SERPAPI_API_KEY,
                        "num": 10
                    })
                    results = search.get_dict()
                    self.api_calls_used += 1
                    
                    for result in results.get("organic_results", []):
                        title = result.get("title", "")
                        snippet = result.get("snippet", "")
                        link = result.get("link", "")
                        
                        # Skip duplicates based on URL
                        if link and link in seen_urls:
                            continue
                        if link:
                            seen_urls.add(link)
                        
                        if title or snippet:
                            result_text = f"Query: {query}\nTitle: {title}\nSnippet: {snippet}\nURL: {link}"
                            all_results_text.append(result_text)
                    
                except Exception as e:
                    print(f"         ❌ Search error for '{query}': {e}")
                    continue
            
            combined_text = "\n\n---\n\n".join(all_results_text)
            print(f"      ✅ LinkedIn search completed: {len(all_results_text)} total results")
            return combined_text
            
        except Exception as e:
            print(f"      ❌ Search error: {e}")
            return ""
    
    async def extract_linkedin_candidates(self, company_name: str, search_results: str) -> List[Dict[str, str]]:
        """Use GPT to extract LinkedIn candidates from search results."""
        try:
            prompt = f"""You are identifying possible current Treasurers or treasury-related executives at {company_name}. Below are search results from Google and LinkedIn.

Your task:
- Extract people who are MOST LIKELY to be involved in treasury functions
- Prioritize roles like: "Treasurer", "Assistant Treasurer", "Head of Treasury", "Corporate Finance" (when combined with treasury context), "VP Treasury", "Treasury Manager"
- Include "Head of Corporate Finance" or "Corporate Finance" roles only if they mention treasury, investor relations, or similar financial management responsibilities
- Extract the **person's name and their LinkedIn profile URL** if available
- If URL is not a proper LinkedIn profile URL, use "NO_URL_FOUND"
- EXCLUDE people who are clearly in unrelated roles (HR, Sales, Marketing, IT, Operations)
- Focus on people with recent/current roles (2023, 2024, present)

IMPORTANT: Only include people who have some connection to treasury, finance, or investor relations roles.

Output format (exactly as shown):
Name: [Full Name] | URL: [LinkedIn URL or NO_URL_FOUND]

Examples:
Name: James Baglanis | URL: https://www.linkedin.com/in/jamesbaglanis  
Name: Mark Kirkendall | URL: https://www.linkedin.com/in/markkirkendall
Name: Sarah Johnson | URL: NO_URL_FOUND

Only return the most relevant candidates (maximum 15). If no relevant people found, return: NO CANDIDATES FOUND

Here are the search results:
{search_results}"""

            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )
            self.api_calls_used += 1
            
            content = response.choices[0].message.content.strip()
            
            if not content or content == "NO CANDIDATES FOUND":
                return []
            
            # Parse the response and eliminate duplicates
            candidates = []
            seen_names = set()  # Track names to avoid duplicates
            
            for line in content.split('\n'):
                line = line.strip()
                # Handle both formats: "- Name: ..." and "Name: ..."
                if ('Name:' in line and '| URL:' in line) or ('Name:' in line and 'URL:' in line):
                    try:
                        # Handle different separators
                        if ' | URL: ' in line:
                            parts = line.split(' | URL: ')
                        elif ' URL: ' in line:
                            parts = line.split(' URL: ')
                        else:
                            continue
                        
                        # Extract name (remove "Name:" prefix and any leading dash)
                        name_part = parts[0].strip()
                        if name_part.startswith('- Name:'):
                            name = name_part.replace('- Name:', '').strip()
                        elif name_part.startswith('Name:'):
                            name = name_part.replace('Name:', '').strip()
                        else:
                            continue
                        
                        url = parts[1].strip()
                        
                        # Skip duplicates and validate
                        name_key = name.lower().strip()
                        if name_key in seen_names:
                            continue
                        
                        if name and self.is_valid_person_name(name, company_name):
                            seen_names.add(name_key)
                            candidates.append({
                                'name': name,
                                'url': url
                            })
                    except Exception as e:
                        print(f"      ⚠️ Parse error for line: {line}")
                        continue
            
            # Score and rank candidates if we found any
            if candidates:
                print(f"      🎯 Scoring and ranking {len(candidates)} candidates...")
                candidates = await self.score_and_rank_candidates(company_name, candidates, search_results)
            
            return candidates
            
        except Exception as e:
            print(f"      ❌ GPT extraction error: {e}")
            return []
    
    async def score_and_rank_candidates(self, company_name: str, candidates: List[Dict[str, str]], search_results: str) -> List[Dict[str, str]]:
        """Score and rank candidates by likelihood of being the treasurer."""
        try:
            # Prepare candidate list for scoring
            candidate_list = []
            for i, candidate in enumerate(candidates):
                url_info = f" (LinkedIn: {candidate['url']})" if candidate['url'] != 'NO_URL_FOUND' else ""
                candidate_list.append(f"{i+1}. {candidate['name']}{url_info}")
            
            candidates_text = "\n".join(candidate_list)
            
            prompt = f"""You are ranking potential Treasurer candidates for {company_name} by likelihood. 

Here are the candidates found:
{candidates_text}

Based on the original search results below, score each candidate from 1-100 based on how likely they are to be the current Treasurer or handle treasury functions:

SCORING CRITERIA (in order of importance):
- 100-90: Explicit "Treasurer" or "Assistant Treasurer" title
- 89-80: "Head of Treasury", "VP Treasury", "Treasury Manager" 
- 79-70: "Corporate Finance" roles with treasury/cash management context
- 69-60: "Finance" roles with investor relations or corporate development
- 59-50: General finance roles at the company
- Below 50: Unlikely to be treasurer

Consider:
- Current vs past roles (current roles score higher)
- Specific treasury keywords in job descriptions
- Company name matches
- Role seniority and relevance

Output format (exactly as shown):
Candidate 1: [Score]
Candidate 2: [Score]
...

Only provide scores, no explanations.

Original search results:
{search_results}"""

            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )
            self.api_calls_used += 1
            
            content = response.choices[0].message.content.strip()
            
            # Parse scores
            scores = {}
            for line in content.split('\n'):
                line = line.strip()
                if 'Candidate' in line and ':' in line:
                    try:
                        parts = line.split(':')
                        candidate_num = int(parts[0].replace('Candidate', '').strip())
                        score = int(parts[1].strip())
                        scores[candidate_num - 1] = score  # Convert to 0-based index
                    except (ValueError, IndexError):
                        continue
            
            # Add scores to candidates and sort by score (highest first)
            for i, candidate in enumerate(candidates):
                candidate['score'] = scores.get(i, 50)  # Default score if not found
            
            # Sort by score (highest first)
            candidates.sort(key=lambda x: x['score'], reverse=True)
            
            print(f"      ✅ Ranked candidates by likelihood:")
            for i, candidate in enumerate(candidates[:5]):  # Show top 5
                url_display = candidate['url'] if candidate['url'] != 'NO_URL_FOUND' else 'No URL'
                print(f"         {i+1}. {candidate['name']} (Score: {candidate['score']}) - {url_display}")
            
            return candidates
            
        except Exception as e:
            print(f"      ❌ Scoring error: {e}")
            # Return original candidates if scoring fails
            return candidates
    
    def is_valid_person_name(self, name: str, company_name: str) -> bool:
        """Basic validation for person names."""
        if not name or len(name) < 3:
            return False
        
        words = name.split()
        if len(words) < 2:
            return False
        
        # Check if each word looks like a name (starts with capital)
        for word in words:
            if not word[0].isupper() or len(word) < 2:
                return False
        
        # Only exclude very obvious non-names (be less restrictive)
        invalid_words = [
            'treasurer', 'officer', 'company', 'corp', 'inc', 'department'
        ]
        
        # Only reject if the name contains these obvious business terms
        name_lower = name.lower()
        if any(invalid in name_lower for invalid in invalid_words):
            return False
        
        # Don't reject common titles like "chief", "financial", "president", "vice" 
        # as they might be part of someone's actual name
        
        return True
    
    def _return_no_candidates(self, reason: str) -> Dict[str, any]:
        """Return structure when no candidates found."""
        return {
            "treasurer": "same",
            "candidates": [],
            "selection_needed": False,
            "source": "fallback",
            "reason": reason,
            "api_calls_used": self.api_calls_used,
            "recommendation": "CFO likely handles treasury duties"
        }

# Main integration function
async def get_improved_treasurer_info(company_name: str) -> Dict[str, any]:
    """
    Main entry point for the improved treasurer detection system.
    Returns candidates for human selection when needed.
    """
    finder = LinkedInTreasurerCandidateFinder()
    return await finder.get_treasurer_candidates(company_name)

# Interactive selection function for CLI usage
def select_treasurer_from_candidates(result: Dict[str, any]) -> str:
    """
    Interactive function to let user select treasurer from candidates.
    For CLI usage - can be adapted for web UI.
    """
    if not result.get('selection_needed', False):
        return result.get('treasurer', 'same')
    
    candidates = result.get('candidates', [])
    if not candidates:
        return 'same'
    
    print(f"\n📋 Please select the correct Treasurer (ranked by likelihood):")
    print(f"   [0] CFO handles treasury (use 'same')")
    
    for i, candidate in enumerate(candidates, 1):
        url_display = f" - {candidate['url']}" if candidate['url'] != 'NO_URL_FOUND' else ""
        score_display = f" (Score: {candidate.get('score', '?')})" if 'score' in candidate else ""
        print(f"   [{i}] {candidate['name']}{score_display}{url_display}")
    
    while True:
        try:
            choice = input(f"\nEnter your choice (0-{len(candidates)}): ").strip()
            choice_num = int(choice)
            
            if choice_num == 0:
                return 'same'
            elif 1 <= choice_num <= len(candidates):
                selected = candidates[choice_num - 1]
                print(f"✅ Selected: {selected['name']}")
                return selected['name']
            else:
                print(f"❌ Please enter a number between 0 and {len(candidates)}")
        except ValueError:
            print("❌ Please enter a valid number")

# Test function
async def test_linkedin_candidate_finder():
    """Test the LinkedIn candidate finder system."""
    
    test_companies = [
        "M/I Homes Inc",
        "Hologic Inc", 
        "VF Corp",
        "Sonos Inc"
    ]
    
    print("🧪 TESTING LINKEDIN CANDIDATE FINDER")
    print("=" * 70)
    
    total_api_calls = 0
    
    for company in test_companies:
        print(f"\n🏢 Testing: {company}")
        
        result = await get_improved_treasurer_info(company)
        total_api_calls += result.get('api_calls_used', 0)
        
        if result.get('selection_needed', False):
            # In real usage, you'd call select_treasurer_from_candidates(result)
            # For testing, just show what was found
            candidates = result.get('candidates', [])
            print(f"   📋 Found {len(candidates)} candidates for selection:")
            for i, candidate in enumerate(candidates, 1):
                url_display = candidate['url'] if candidate['url'] != 'NO_URL_FOUND' else 'No URL'
                score_display = f" (Score: {candidate.get('score', '?')})" if 'score' in candidate else ""
                print(f"      {i}. {candidate['name']}{score_display} - {url_display}")
        else:
            print(f"   ✅ Auto-result: {result.get('treasurer', 'same')}")
            print(f"   📍 Source: {result.get('source', 'unknown')}")
    
    print(f"\n📊 TOTAL API CALLS USED: {total_api_calls}")
    print(f"📊 AVERAGE API CALLS PER COMPANY: {total_api_calls / len(test_companies):.1f}")

if __name__ == "__main__":
    asyncio.run(test_linkedin_candidate_finder()) 