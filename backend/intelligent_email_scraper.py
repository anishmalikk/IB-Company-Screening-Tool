"""
Intelligent Email Scraper
========================
Enhanced email extraction that integrates with the intelligent treasurer detection system.
Handles uncertainty transparently by adjusting email extraction strategy based on treasurer confidence.
"""

import re
from serpapi.google_search import GoogleSearch
from nameparser import HumanName
import os
from dotenv import load_dotenv
from llm_client import get_llm_client
import unicodedata
from typing import Dict, Optional, List
import asyncio

# Import the intelligent treasurer system
from intelligent_treasurer_system import get_intelligent_treasurer_info, TreasurerDetectionResult

load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")

# Import existing email utilities
from email_scraper import (
    GENERIC_EMAIL_PREFIXES, is_generic_email, extract_all_non_generic_emails,
    serp_api_search, extract_email_domain, extract_known_emails, detect_email_format,
    normalize_name, construct_email, extract_any_email, infer_format_from_email,
    gpt_infer_format, VALID_EMAIL_FORMATS, FAKE_TEST_NAMES, FAKE_EMAIL_PATTERNS,
    is_fake_or_test_email
)

class IntelligentEmailScraper:
    """
    Enhanced email scraper that handles treasurer uncertainty intelligently.
    Adjusts email extraction strategy based on treasurer detection confidence.
    """
    
    def __init__(self):
        self.client = get_llm_client()
    
    async def scrape_emails_with_intelligence(self, company_name: str, cfo_name: str, ceo_name: str) -> Dict:
        """
        Main email scraping function that uses intelligent treasurer detection.
        Adapts email strategy based on treasurer confidence levels.
        """
        
        print(f"\n📧 Intelligent email scraping for: {company_name}")
        
        # Step 1: Get intelligent treasurer information
        treasurer_info = await get_intelligent_treasurer_info(company_name)
        result = treasurer_info['structured_result']
        email_strategy = treasurer_info['email_guidance']['strategy']
        
        print(f"   📊 Treasurer detection: {result.status}")
        print(f"   📧 Email strategy: {email_strategy}")
        
        # Step 2: Determine treasurer name for email searches
        treasurer_name = self.determine_treasurer_name_for_email(result, email_strategy)
        
        # Step 3: Scrape emails using appropriate strategy
        email_result = await self.scrape_with_strategy(
            company_name, cfo_name, ceo_name, treasurer_name, email_strategy, result
        )
        
        # Step 4: Add intelligence metadata
        email_result['treasurer_detection'] = {
            'status': result.status,
            'confidence_level': result.confidence_level,
            'email_strategy': email_strategy,
            'recommendation': result.recommendation,
            'candidates': [c.name for c in result.candidates] if result.candidates else []
        }
        
        return email_result
    
    def determine_treasurer_name_for_email(self, result: TreasurerDetectionResult, email_strategy: str) -> Optional[str]:
        """Determine which treasurer name to use for email searches based on strategy"""
        
        if email_strategy == "use_treasurer" and result.primary_treasurer:
            return result.primary_treasurer
        elif email_strategy == "use_cfo_only":
            return None  # Don't search for treasurer emails
        else:
            # For "provide_format_only", we might still search to help determine format
            return result.primary_treasurer if result.primary_treasurer else None
    
    async def scrape_with_strategy(self, company_name: str, cfo_name: str, ceo_name: str, 
                                 treasurer_name: Optional[str], email_strategy: str, 
                                 treasurer_result: TreasurerDetectionResult) -> Dict:
        """Scrape emails using the determined strategy"""
        
        # Step 1: Find email domain
        domain = await self.find_email_domain(company_name)
        if not domain:
            return {"error": "Could not find domain"}
        
        # Step 2: Search for known emails with priority order
        known_emails = await self.search_for_known_emails(
            company_name, domain, cfo_name, ceo_name, treasurer_name, email_strategy
        )
        
        if known_emails:
            # Step 3: Detect format and construct emails
            return self.construct_emails_from_known(
                domain, known_emails, cfo_name, ceo_name, treasurer_name, 
                email_strategy, treasurer_result
            )
        else:
            # Step 4: Fallback to format inference
            return await self.fallback_email_construction(
                company_name, domain, cfo_name, ceo_name, treasurer_name, 
                email_strategy, treasurer_result
            )
    
    async def find_email_domain(self, company_name: str) -> Optional[str]:
        """Find the company's email domain"""
        
        query_1 = f"{company_name} email format"
        result_1 = serp_api_search(company_name, query_1, num_results=60)
        domain = extract_email_domain(result_1['snippets'])
        
        if not domain:
            # Fallback: search for investor relations/pr email
            fallback_query = f"{company_name} investor relations pr email"
            result_1b = serp_api_search(company_name, fallback_query, num_results=60)
            domain = extract_email_domain(result_1b['snippets'])
        
        return domain
    
    async def search_for_known_emails(self, company_name: str, domain: str, cfo_name: str, 
                                    ceo_name: str, treasurer_name: Optional[str], 
                                    email_strategy: str) -> List[tuple]:
        """Search for known emails with intelligent prioritization"""
        
        print(f"   🔍 Searching for known emails (strategy: {email_strategy})")
        
        all_snippets = []
        known_emails = []
        
        # Priority 1: CFO (always search)
        if cfo_name:
            print(f"      🔍 Searching CFO: {cfo_name}")
            query_cfo = f'{company_name} "{domain}" {cfo_name} email'
            result_cfo = serp_api_search(company_name, query_cfo, num_results=20)
            known_emails.extend(extract_known_emails(result_cfo['snippets'], domain))
            all_snippets.extend(result_cfo['snippets'])
        
        # Priority 2: CEO (if CFO search didn't work)
        if not known_emails and ceo_name:
            print(f"      🔍 Searching CEO: {ceo_name}")
            query_ceo = f'{company_name} "{domain}" {ceo_name} email'
            result_ceo = serp_api_search(company_name, query_ceo, num_results=20)
            known_emails.extend(extract_known_emails(result_ceo['snippets'], domain))
            all_snippets.extend(result_ceo['snippets'])
        
        # Priority 3: Treasurer (only if strategy allows and we have high confidence)
        if (not known_emails and treasurer_name and 
            email_strategy == "use_treasurer"):
            
            print(f"      🔍 Searching Treasurer: {treasurer_name}")
            query_treasurer = f'{company_name} "{domain}" {treasurer_name} email'
            result_treasurer = serp_api_search(company_name, query_treasurer, num_results=20)
            known_emails.extend(extract_known_emails(result_treasurer['snippets'], domain))
            all_snippets.extend(result_treasurer['snippets'])
        
        # Filter for valid emails with detected formats
        valid_emails = [(n, e) for n, e in known_emails if n and detect_email_format(n, e)]
        
        # Filter out fake/test emails
        actual_names = [name for name in [cfo_name, ceo_name, treasurer_name] 
                       if name and name != "same"]
        filtered_emails = [(n, e) for n, e in valid_emails 
                          if not is_fake_or_test_email(e, actual_names)]
        
        print(f"      ✅ Found {len(filtered_emails)} valid email(s)")
        return filtered_emails
    
    def construct_emails_from_known(self, domain: str, known_emails: List[tuple], 
                                   cfo_name: str, ceo_name: str, treasurer_name: Optional[str],
                                   email_strategy: str, treasurer_result: TreasurerDetectionResult) -> Dict:
        """Construct emails from known email examples"""
        
        name, email = known_emails[0]
        fmt = detect_email_format(name, email)
        
        if not fmt:
            return {"error": "Could not detect email format from known emails"}
        
        # Construct emails based on strategy
        cfo_email = construct_email(cfo_name, domain, fmt) if cfo_name else None
        
        # Treasurer email logic based on strategy
        treasurer_email = None
        treasurer_status = "not_applicable"
        
        if email_strategy == "use_treasurer" and treasurer_name:
            treasurer_email = construct_email(treasurer_name, domain, fmt)
            treasurer_status = "provided"
        elif email_strategy == "use_cfo_only":
            treasurer_email = None
            treasurer_status = "skipped_due_to_uncertainty"
        
        return {
            "domain": domain,
            "format": fmt,
            "cfo_email": cfo_email,
            "treasurer_email": treasurer_email,
            "treasurer_status": treasurer_status,
            "source_name": name,
            "source_email": email,
            "strategy_used": email_strategy,
            "uncertainty_reason": treasurer_result.recommendation if email_strategy != "use_treasurer" else None
        }
    
    async def fallback_email_construction(self, company_name: str, domain: str, 
                                        cfo_name: str, ceo_name: str, treasurer_name: Optional[str],
                                        email_strategy: str, treasurer_result: TreasurerDetectionResult) -> Dict:
        """Fallback email construction when no known emails are found"""
        
        print("   🔄 Using fallback email construction...")
        
        # Get all non-generic emails for format inference
        all_snippets_query = f'{company_name} "{domain}" email'
        all_snippets_result = serp_api_search(company_name, all_snippets_query, num_results=40)
        
        actual_names = [name for name in [cfo_name, ceo_name, treasurer_name] 
                       if name and name != "same"]
        all_emails = extract_all_non_generic_emails(all_snippets_result['snippets'], domain, actual_names)
        
        if not all_emails:
            return {"error": "No emails found for format inference"}
        
        # Check if all emails are generic
        if all(is_generic_email(email) for email in all_emails):
            return {"error": "Only generic emails found (no real person emails available)"}
        
        # Try to infer format
        fmt = None
        source_method = "unknown"
        
        # Try with CFO name first
        if cfo_name:
            fmt = infer_format_from_email(all_emails[0], cfo_name)
            if fmt:
                source_method = "inferred from email with CFO name"
        
        # Try GPT fallback if needed
        if not fmt:
            fmt = gpt_infer_format(cfo_name, all_emails)
            if fmt:
                source_method = "gpt-inferred format"
        
        # Try common formats as last resort
        if not fmt:
            for test_fmt in ["firstlast", "first.last", "first_initiallast", "first"]:
                test_email = construct_email(cfo_name, domain, test_fmt)
                if test_email:
                    fmt = test_fmt
                    source_method = f"fallback format: {test_fmt}"
                    break
        
        if not fmt:
            return {"error": "Could not infer email format"}
        
        # Construct emails based on strategy
        cfo_email = construct_email(cfo_name, domain, fmt) if cfo_name else None
        
        # Treasurer email logic
        treasurer_email = None
        treasurer_status = "not_applicable"
        
        if email_strategy == "use_treasurer" and treasurer_name:
            treasurer_email = construct_email(treasurer_name, domain, fmt)
            treasurer_status = "provided"
        elif email_strategy == "use_cfo_only":
            treasurer_email = None
            treasurer_status = "skipped_due_to_uncertainty"
        
        return {
            "domain": domain,
            "format": fmt,
            "cfo_email": cfo_email,
            "treasurer_email": treasurer_email,
            "treasurer_status": treasurer_status,
            "source_email": all_emails[0] if all_emails else None,
            "source": source_method,
            "strategy_used": email_strategy,
            "uncertainty_reason": treasurer_result.recommendation if email_strategy != "use_treasurer" else None
        }

# Convenience function for backward compatibility
async def intelligent_scrape_emails(company_name: str, cfo_name: str, treasurer_name: str, ceo_name: str) -> Dict:
    """
    Backward-compatible function that handles treasurer uncertainty intelligently.
    
    Note: treasurer_name parameter is ignored - treasurer info is determined by intelligent detection.
    """
    scraper = IntelligentEmailScraper()
    return await scraper.scrape_emails_with_intelligence(company_name, cfo_name, ceo_name)

# Test function
async def test_intelligent_email_scraper():
    """Test the intelligent email scraper"""
    
    test_cases = [
        ("M/I Homes Inc", "Derek Klutts", "Robert Mason"),  # Should find treasurer email
        ("Hologic Inc", "Karleen Oberton", "Stephen MacMillan"),  # Should skip treasurer email
        ("VF Corp", "Matt Puckett", "Bracken Darrell"),  # Should handle uncertainty
    ]
    
    print("🧪 TESTING INTELLIGENT EMAIL SCRAPER")
    print("=" * 70)
    
    for company_name, cfo_name, ceo_name in test_cases:
        print(f"\n🏢 Testing: {company_name}")
        
        result = await intelligent_scrape_emails(company_name, cfo_name, "", ceo_name)
        
        print(f"   CFO email: {result.get('cfo_email', 'Not found')}")
        print(f"   Treasurer status: {result.get('treasurer_status', 'Unknown')}")
        print(f"   Treasurer email: {result.get('treasurer_email', 'Not provided')}")
        print(f"   Strategy: {result.get('strategy_used', 'Unknown')}")
        
        if 'uncertainty_reason' in result and result['uncertainty_reason']:
            print(f"   Reason: {result['uncertainty_reason']}")

if __name__ == "__main__":
    asyncio.run(test_intelligent_email_scraper()) 