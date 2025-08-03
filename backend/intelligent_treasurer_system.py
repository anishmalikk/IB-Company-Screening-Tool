"""
Intelligent Treasurer Detection System
====================================
Handles uncertainty transparently by returning multiple candidates with confidence levels.
Addresses LinkedIn snippet limitations and provides honest uncertainty handling.
"""

import asyncio
import os
import re
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from llm_client import get_llm_client
from serpapi.google_search import GoogleSearch
import requests
from bs4 import BeautifulSoup

# Import existing components
from exec_scraper import SimplifiedTreasurerDetector, fetch_serp_results, fetch_leadership_page_url, get_leadership_page_text

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")

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

class IntelligentTreasurerSystem:
    """
    Advanced treasurer detection that handles uncertainty transparently.
    Returns structured data instead of forcing potentially incorrect answers.
    """
    
    def __init__(self):
        self.client = get_llm_client()
        self.basic_detector = SimplifiedTreasurerDetector()
        
        # Confidence thresholds (adjusted for better treasurer detection)
        self.HIGH_CONFIDENCE_THRESHOLD = 0.80
        self.MEDIUM_CONFIDENCE_THRESHOLD = 0.55
        self.USABLE_CONFIDENCE_THRESHOLD = 0.45
    
    async def detect_treasurer_candidates(self, company_name: str) -> TreasurerDetectionResult:
        """
        Main detection method that returns structured candidate data
        """
        print(f"\n🔍 Intelligent treasurer detection for: {company_name}")
        
        # Step 1: Get data from multiple sources
        sources = await self.gather_treasurer_data(company_name)
        
        # Step 2: Extract and analyze candidates
        candidates = self.extract_candidates_from_sources(sources, company_name)
        
        # Step 3: Determine overall result structure
        result = self.build_detection_result(candidates, company_name)
        
        self.log_detection_result(result)
        return result
    
    async def gather_treasurer_data(self, company_name: str) -> Dict[str, str]:
        """Gather data from multiple sources"""
        
        print("   📊 Gathering data from multiple sources...")
        
        sources = {}
        
        # Source 1: Leadership page (most reliable when available)
        try:
            leadership_url = fetch_leadership_page_url(company_name)
            if leadership_url:
                sources['leadership_page'] = await get_leadership_page_text(leadership_url)
                print(f"      ✅ Leadership page: {len(sources['leadership_page'])} chars")
            else:
                sources['leadership_page'] = ""
                print("      ⚪ Leadership page: not found")
        except Exception as e:
            sources['leadership_page'] = ""
            print(f"      ❌ Leadership page error: {e}")
        
        # Source 2: General CEO/CFO search (may include treasurer info)
        try:
            sources['general_exec_search'] = fetch_serp_results(company_name, "CEO CFO treasurer executives")
            print(f"      ✅ General exec search: {len(sources['general_exec_search'])} chars")
        except Exception as e:
            sources['general_exec_search'] = ""
            print(f"      ❌ General exec search error: {e}")
        
        # Source 3: Targeted treasurer search (includes LinkedIn snippets)
        try:
            sources['treasurer_search'] = fetch_serp_results(company_name, '"treasurer"', 15)
            print(f"      ✅ Treasurer search: {len(sources['treasurer_search'])} chars")
        except Exception as e:
            sources['treasurer_search'] = ""
            print(f"      ❌ Treasurer search error: {e}")
        
        # Source 4: Company-specific treasury search
        try:
            sources['company_treasury_search'] = fetch_serp_results(company_name, "treasury department finance", 10)
            print(f"      ✅ Treasury dept search: {len(sources['company_treasury_search'])} chars")
        except Exception as e:
            sources['company_treasury_search'] = ""
            print(f"      ❌ Treasury dept search error: {e}")
        
        return sources
    
    def extract_candidates_from_sources(self, sources: Dict[str, str], company_name: str) -> List[TreasurerCandidate]:
        """Extract potential treasurer candidates from all sources"""
        
        print("   🔍 Analyzing sources for candidates...")
        
        candidates = []
        seen_names = set()  # Avoid duplicates
        
        # Analyze each source
        for source_name, content in sources.items():
            if not content:
                continue
                
            print(f"      📋 Analyzing {source_name}...")
            
            source_candidates = self.analyze_source_for_candidates(content, company_name, source_name)
            
            for candidate in source_candidates:
                # Avoid duplicate names (case-insensitive)
                name_key = candidate.name.lower().strip()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    candidates.append(candidate)
                    print(f"         🎯 Found: {candidate.name} (confidence: {candidate.confidence:.2f})")
                else:
                    # Update existing candidate with additional evidence
                    existing = next(c for c in candidates if c.name.lower().strip() == name_key)
                    existing.evidence += f" | Additional from {source_name}: {candidate.evidence[:100]}..."
                    existing.confidence = max(existing.confidence, candidate.confidence)  # Take higher confidence
        
        # Sort by confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        
        return candidates
    
    def analyze_source_for_candidates(self, content: str, company_name: str, source_name: str) -> List[TreasurerCandidate]:
        """Analyze a single source for treasurer candidates"""
        
        candidates = []
        
        # Check for CFO+Treasurer combination first
        if self.basic_detector.is_cfo_treasurer_combo(content):
            print(f"         💼 CFO+Treasurer combo detected in {source_name}")
            return []  # No separate treasurer
        
        # Use regex-based extraction for potential names
        potential_names = self.extract_potential_treasurer_names(content, company_name)
        
        for name in potential_names:
            # Analyze this specific mention
            candidate = self.analyze_treasurer_mention(name, content, company_name, source_name)
            if candidate:
                candidates.append(candidate)
        
        return candidates
    
    def extract_potential_treasurer_names(self, content: str, company_name: str) -> List[str]:
        """Extract potential treasurer names using enhanced regex patterns"""
        
        # Use existing regex patterns but collect all matches
        potential_names = []
        
        for pattern in self.basic_detector.treasurer_name_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                
                # Extract name from groups (same logic as basic detector)
                name = None
                if len(groups) == 1:
                    name = groups[0].strip()
                elif len(groups) == 2:
                    first_name = groups[0].strip()
                    last_name = groups[1].strip()
                    name = f"{first_name} {last_name}"
                elif len(groups) >= 3:
                    for group in groups:
                        candidate = group.strip()
                        if (candidate and 
                            len(candidate.split()) == 2 and 
                            all(word[0].isupper() and word[1:].islower() for word in candidate.split() if len(word) > 1)):
                            name = candidate
                            break
                
                if name and self.basic_detector.is_valid_person_name(name, company_name):
                    potential_names.append(name)
        
        # Remove duplicates
        return list(set(potential_names))
    
    def analyze_treasurer_mention(self, name: str, content: str, company_name: str, source_name: str) -> Optional[TreasurerCandidate]:
        """Analyze a specific treasurer mention to determine confidence"""
        
        # Find the context around this name mention
        context = self.extract_context_around_name(name, content)
        
        # Determine confidence based on multiple factors
        confidence, issues = self.assess_candidate_confidence(name, context, source_name)
        
        if confidence < 0.3:  # Too low confidence to consider
            return None
        
        return TreasurerCandidate(
            name=name,
            confidence=confidence,
            source=source_name,
            evidence=context[:200] + "..." if len(context) > 200 else context,
            potential_issues=issues
        )
    
    def extract_context_around_name(self, name: str, content: str) -> str:
        """Extract context around a name mention"""
        
        # Find the name in content (case insensitive)
        name_pattern = re.escape(name)
        match = re.search(name_pattern, content, re.IGNORECASE)
        
        if not match:
            return ""
        
        start = max(0, match.start() - 100)
        end = min(len(content), match.end() + 100)
        
        return content[start:end].strip()
    
    def assess_candidate_confidence(self, name: str, context: str, source_name: str) -> tuple[float, List[str]]:
        """Assess confidence level for a treasurer candidate"""
        
        confidence = 0.5  # Base confidence
        issues = []
        
        # Source reliability factor
        source_factors = {
            'leadership_page': 0.3,      # Most reliable
            'general_exec_search': 0.2,  # Good
            'treasurer_search': 0.15,    # Moderate (may include LinkedIn snippets)
            'company_treasury_search': 0.1  # Supporting info
        }
        confidence += source_factors.get(source_name, 0.1)
        
        context_lower = context.lower()
        
        # Positive indicators
        if "current" in context_lower or "serves as" in context_lower:
            confidence += 0.2
        if "assistant treasurer" in context_lower:
            confidence += 0.15
        if any(word in context_lower for word in ["executive", "officer", "management"]):
            confidence += 0.1
        if source_name == "leadership_page":
            confidence += 0.15  # Leadership pages are more current
        
        # Negative indicators
        if self.basic_detector.is_outdated_info(context):
            confidence -= 0.3
            issues.append("potentially_outdated")
        
        if "linkedin" in context_lower:
            confidence -= 0.05  # Reduced penalty - LinkedIn snippets may be stale but still useful
            issues.append("linkedin_snippet")
        
        if any(word in context_lower for word in ["former", "past", "previous", "until"]):
            confidence -= 0.4
            issues.append("past_role_indicator")
        
        if "cfo" in context_lower and "treasurer" in context_lower:
            confidence -= 0.3  # Dual role, less clear
            issues.append("dual_role_mention")
        
        # Timeline concerns for LinkedIn/search results
        if source_name in ["treasurer_search", "company_treasury_search"]:
            confidence -= 0.05  # Reduced penalty for search results
            issues.append("search_result_uncertainty")
        
        return max(0.0, min(1.0, confidence)), issues
    
    def build_detection_result(self, candidates: List[TreasurerCandidate], company_name: str) -> TreasurerDetectionResult:
        """Build the final detection result based on candidates"""
        
        if not candidates:
            return TreasurerDetectionResult(
                status="none_found",
                primary_treasurer=None,
                candidates=[],
                confidence_level="low",
                recommendation="Contact company directly for treasurer information",
                email_strategy="use_cfo_only"
            )
        
        # Check for CFO+Treasurer combination across all sources
        has_cfo_combo = any("dual_role_mention" in c.potential_issues for c in candidates)
        if has_cfo_combo:
            return TreasurerDetectionResult(
                status="cfo_treasurer_combo",
                primary_treasurer="same",
                candidates=candidates,
                confidence_level="high",
                recommendation="CFO handles treasurer duties",
                email_strategy="use_cfo_only"
            )
        
        top_candidate = candidates[0]
        
        # Single high-confidence candidate
        if (top_candidate.confidence >= self.HIGH_CONFIDENCE_THRESHOLD and 
            (len(candidates) == 1 or candidates[1].confidence < self.MEDIUM_CONFIDENCE_THRESHOLD)):
            
            return TreasurerDetectionResult(
                status="single_confident",
                primary_treasurer=top_candidate.name,
                candidates=candidates,
                confidence_level="high",
                recommendation=f"High confidence: {top_candidate.name} is the treasurer",
                email_strategy="use_treasurer"
            )
        
        # Multiple viable candidates
        viable_candidates = [c for c in candidates if c.confidence >= self.USABLE_CONFIDENCE_THRESHOLD]
        if len(viable_candidates) > 1:
            return TreasurerDetectionResult(
                status="multiple_candidates",
                primary_treasurer=None,
                candidates=candidates,
                confidence_level="medium",
                recommendation=f"Multiple possible treasurers found: {', '.join(c.name for c in viable_candidates[:3])}",
                email_strategy="use_cfo_only"
            )
        
        # Single medium confidence
        if top_candidate.confidence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            # Use treasurer email if confidence is reasonably high and no major red flags
            has_major_issues = any(issue in ["past_role_indicator", "potentially_outdated"] 
                                 for issue in top_candidate.potential_issues)
            email_strategy = "use_cfo_only" if has_major_issues else "use_treasurer"
            
            return TreasurerDetectionResult(
                status="uncertain",
                primary_treasurer=top_candidate.name,
                candidates=candidates,
                confidence_level="medium",
                recommendation=f"Likely treasurer: {top_candidate.name} (verify with company)",
                email_strategy=email_strategy
            )
        
        # Low confidence
        return TreasurerDetectionResult(
            status="uncertain",
            primary_treasurer=None,
            candidates=candidates,
            confidence_level="low",
            recommendation="Treasurer information unclear - contact company for confirmation",
            email_strategy="use_cfo_only"
        )
    
    def log_detection_result(self, result: TreasurerDetectionResult):
        """Log the detection result for debugging"""
        
        print(f"\n📊 TREASURER DETECTION RESULT")
        print(f"   Status: {result.status}")
        print(f"   Confidence: {result.confidence_level}")
        print(f"   Primary: {result.primary_treasurer}")
        print(f"   Email strategy: {result.email_strategy}")
        print(f"   Recommendation: {result.recommendation}")
        
        if result.candidates:
            print(f"   Candidates ({len(result.candidates)}):")
            for i, candidate in enumerate(result.candidates[:3]):  # Show top 3
                issues_str = f" (issues: {', '.join(candidate.potential_issues)})" if candidate.potential_issues else ""
                print(f"      {i+1}. {candidate.name} - {candidate.confidence:.2f} from {candidate.source}{issues_str}")
    
    def format_for_legacy_system(self, result: TreasurerDetectionResult) -> str:
        """Format result for compatibility with existing system"""
        
        if result.status == "single_confident":
            return result.primary_treasurer
        elif result.status == "cfo_treasurer_combo":
            return "same"
        elif result.status == "multiple_candidates":
            # List top candidates for user awareness
            candidate_names = [c.name for c in result.candidates[:2]]
            return f"Multiple possible: {', '.join(candidate_names)}"
        elif result.primary_treasurer:
            return f"{result.primary_treasurer} (verify)"
        else:
            return "same"

# Integration function for existing system
async def get_intelligent_treasurer_info(company_name: str) -> Dict:
    """
    Main entry point that returns both structured data and legacy format
    """
    system = IntelligentTreasurerSystem()
    result = await system.detect_treasurer_candidates(company_name)
    
    return {
        'structured_result': result,
        'legacy_format': system.format_for_legacy_system(result),
        'email_guidance': {
            'strategy': result.email_strategy,
            'treasurer_name': result.primary_treasurer if result.email_strategy == "use_treasurer" else None,
            'fallback_reason': result.recommendation
        }
    }

# Test function
async def test_intelligent_system():
    """Test the intelligent system on various company types"""
    
    test_companies = [
        "M/I Homes Inc",      # Known working case
        "Hologic Inc",        # Known "same" case  
        "VF Corp",            # Known difficult case
        "Sonos Inc",          # Known unclear case
    ]
    
    print("🧪 TESTING INTELLIGENT TREASURER SYSTEM")
    print("=" * 70)
    
    for company in test_companies:
        result = await get_intelligent_treasurer_info(company)
        
        print(f"\n🏢 {company}")
        print(f"   Legacy format: {result['legacy_format']}")
        print(f"   Email strategy: {result['email_guidance']['strategy']}")
        print(f"   Status: {result['structured_result'].status}")
        
        if result['structured_result'].candidates:
            print(f"   Top candidate: {result['structured_result'].candidates[0].name} "
                  f"(confidence: {result['structured_result'].candidates[0].confidence:.2f})")

if __name__ == "__main__":
    asyncio.run(test_intelligent_system()) 