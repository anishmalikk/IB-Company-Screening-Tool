import requests
import json
import re
import os
from bs4 import BeautifulSoup
from openai import OpenAI
from sec_api import QueryApi
import pandas as pd
import asyncio
import platform
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERP_API_KEY = os.getenv("SERPAPI_API_KEY")
SEC_API_KEY = os.getenv("SEC_API_KEY")   # For SEC EDGAR
OUTPUT_FILE = "screening_results.xlsx"

# Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
sec_api = QueryApi(api_key=SEC_API_KEY)

def search_web(query):
    """Perform a web search using SerpAPI"""    
    url = f"https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "engine": "google"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get('organic_results', [])
    else:
        print(f"SerpAPI error: {response.status_code} {response.text}")
        return []


def get_company_leadership_url(company_name):
    """Try to find the official leadership or executive team page"""
    print(f"\n=== SEARCHING FOR LEADERSHIP PAGE FOR: {company_name} ===")
    queries = [
        f"{company_name} executive leadership team",
        f"{company_name} corporate leadership team",
        f"{company_name} corporate executive team", 
        f"{company_name} corporate management team",
        f"{company_name} leadership team",
        f"{company_name} executive team",
        f"{company_name} management team",
        f"{company_name} officers",
        f"{company_name} board of directors"
    ]
    keywords = ["leadership", "executive", "management", "team", "board", "officers", "corporate"]
    
    # Sites to exclude (third-party sites that often appear in search results)
    exclude_domains = [
        "wsj.com", "marketwatch.com", "yahoo.com", "finance.yahoo.com", 
        "bloomberg.com", "reuters.com", "cnbc.com", "seekingalpha.com",
        "investing.com", "tradingview.com", "finviz.com", "zacks.com",
        "theorg.com", "comparably.com", "rocketreach.co", "globaldata.com",
        "simplywall.st", "morningstar.com"
    ]
    
    # Additional domains to exclude for casino/gaming companies (property-specific pages)
    casino_exclude_domains = [
        "casinos.", "casino.", "resort.", "property.", "location."
    ]
    
    for i, query in enumerate(queries):
        print(f"\nTrying query {i+1}: '{query}'")
        search_results = search_web(query)
        print(f"Found {len(search_results)} search results")
        
        for j, result in enumerate(search_results):
            title = result.get("title", "").lower()
            link = result.get("link", "").lower()
            print(f"  Result {j+1}: Title='{result.get('title', '')}' | Link='{result.get('link', '')}'")
            
            # Skip excluded domains
            if any(domain in link for domain in exclude_domains):
                print(f"  ✗ Excluded domain: {link}")
                continue
            
            # Skip property-specific pages for casino/gaming companies
            if any(domain in link for domain in casino_exclude_domains):
                print(f"  ✗ Excluded property-specific domain: {link}")
                continue
            
            # Check if it's likely the official company site
            company_words = company_name.lower().split()
            # More strict matching - require company name to be in the domain
            is_official_site = any(word in link.split('/')[2] for word in company_words if len(word) > 2)
            
            # Check if it's likely a corporate page (not property-specific)
            # Prioritize executive/leadership pages over governance pages
            is_executive_page = ("executive" in title or "leadership" in title or 
                               "management" in title or "officers" in title)
            is_corporate_page = ("corporate" in title or "corporate" in link or 
                               "investor" in link or "about" in link or 
                               "executive" in title or "leadership" in title)
            
            # Skip governance pages unless no executive pages are found
            is_governance_page = ("governance" in title or "governance" in link or 
                                "board" in title or "directors" in title)
            
            if any(kw in title for kw in keywords) or any(kw in link for kw in keywords):
                if is_official_site:
                    if is_executive_page:
                        print(f"  ✓ EXECUTIVE SITE MATCH! Returning: {result.get('link', '')}")
                        return result.get("link", "")
                    elif is_corporate_page and not is_governance_page:
                        print(f"  ✓ CORPORATE SITE MATCH! Returning: {result.get('link', '')}")
                        return result.get("link", "")
                    elif is_governance_page:
                        print(f"  ⚠️ Governance page (skipping): {result.get('link', '')}")
                    else:
                        print(f"  ⚠️ Property site match (skipping): {result.get('link', '')}")
                else:
                    print(f"  ⚠️ Non-official site match: {result.get('link', '')}")
            else:
                print(f"  ✗ No keywords match")
    
    print("❌ No leadership page found")
    return None

async def scrape_execs_from_leadership_page(url):
    """Scrape and extract plain text from leadership page"""
    print(f"\n=== SCRAPING LEADERSHIP PAGE: {url} ===")
    try:
        # Try Playwright first for JavaScript-heavy pages
        print("Trying Playwright for JavaScript-rendered content...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            
            print(f"Navigating to: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for dynamic content to load
            print("Waiting for dynamic content...")
            await page.wait_for_timeout(3000)  # Wait 3 seconds for JS to load
            
            # Try to wait for executive content to appear
            try:
                await page.wait_for_selector(".module-committee", timeout=5000)
                print("✓ Found committee module, waiting for data...")
                await page.wait_for_timeout(2000)  # Additional wait for data
            except:
                print("⚠️ Committee module not found, continuing anyway...")
            
            # Get the rendered HTML
            html_content = await page.content()
            await browser.close()
            
            print(f"Playwright rendered content length: {len(html_content)} characters")
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Try to find executive content in specific elements
            executive_text = ""
            
            # Priority 1: Look for main content areas
            main_selectors = [
                "main", "article", ".main-content", "#main-content", 
                ".content", "#content", ".page-content", "#page-content",
                ".executives", "#executives", ".leadership", "#leadership",
                ".management", "#management", ".officers", "#officers",
                ".module-committee", "#module-committee"  # Amazon-specific
            ]
            
            for selector in main_selectors:
                elements = soup.select(selector)
                if elements:
                    print(f"Found content in selector: {selector}")
                    for element in elements:
                        text = element.get_text(separator="\n", strip=True)
                        if len(text.split()) > 50:  # Only if substantial content
                            executive_text += text + "\n\n"
            
            # Priority 2: Look for specific executive-related elements
            exec_selectors = [
                "h1", "h2", "h3", "h4", "h5", "h6",  # Headers often contain names
                ".executive", "#executive", ".officer", "#officer",
                ".ceo", "#ceo", ".cfo", "#cfo", ".treasurer", "#treasurer",
                ".president", "#president", ".director", "#director",
                ".module-committee_name", "#module-committee_name"  # Amazon-specific
            ]
            
            for selector in exec_selectors:
                elements = soup.select(selector)
                if elements:
                    print(f"Found executive content in selector: {selector}")
                    for element in elements:
                        text = element.get_text(separator="\n", strip=True)
                        if len(text.split()) > 10:  # Even smaller chunks for executives
                            executive_text += text + "\n\n"
            
            # Priority 3: Look for paragraphs and divs containing executive keywords
            exec_keywords = ["CEO", "CFO", "Treasurer", "President", "Chief", "Executive", "Officer", "Director"]
            for keyword in exec_keywords:
                # Find elements containing these keywords using string search
                for element in soup.find_all():
                    element_text = element.get_text()
                    if keyword.lower() in element_text.lower():
                        text = element.get_text(separator="\n", strip=True)
                        if len(text.split()) > 5:
                            executive_text += text + "\n\n"
            
            # If we found targeted content, use it; otherwise fall back to full page
            if executive_text.strip():
                print(f"✓ Found targeted executive content: {len(executive_text.split())} words")
                print(f"First 300 chars: {executive_text[:300]}...")
                return executive_text
            else:
                print("⚠️ No targeted content found, using full page text")
                text = soup.get_text(separator="\n", strip=True)
                print(f"Full page text length: {len(text)} characters")
                print(f"First 200 chars: {text[:200]}...")
                return text
                
    except Exception as e:
        print(f"❌ Playwright scraping error: {e}")
        print("Falling back to requests...")
        
        # Fallback to requests if Playwright fails
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            print(f"Making request with headers: {headers}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Response status code: {response.status_code}")
            print(f"Response content length: {len(response.text)} characters")
            
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            print(f"Fallback text length: {len(text)} characters")
            return text
        except Exception as e2:
            print(f"❌ Fallback scraping error: {e2}")
            return "scraping not working"

async def get_executives(company_name):
    """Main function to get CEO, CFO, and Treasurer"""
    print(f"\n=== GETTING EXECUTIVES FOR: {company_name} ===")
    
    url = get_company_leadership_url(company_name)
    if not url:
        print("❌ No leadership URL found")
        return f"Could not find leadership page for {company_name}"

    print(f"✓ Found leadership URL: {url}")
    raw_text = await scrape_execs_from_leadership_page(url)
    
    if not raw_text or len(raw_text.split()) < 100:
        print(f"❌ Raw text not usable - length: {len(raw_text.split()) if raw_text else 0} words")
        return f"Could not extract usable text from: {url}"
    
    print(f"✓ Raw text is usable - {len(raw_text.split())} words")
    
    # Clean up the text to reduce token count
    cleaned_text = clean_executive_text(raw_text)
    print(f"✓ Cleaned text - {len(cleaned_text.split())} words")
    print("=== CLEANED TEXT BEING SENT TO GPT ===")
    print(cleaned_text)
    print("=== END CLEANED TEXT ===")
    
    # Debug: Show first 1000 chars of raw text to see what we're missing
    print("=== DEBUG: FIRST 1000 CHARS OF RAW TEXT ===")
    print(raw_text[:1000])
    print("=== END DEBUG ===")
    
    prompt = f"""
Based on the following leadership page text, extract the executive names in this exact format:
CEO: [full name]
CFO: [full name] 
Treasurer (or closest): [full name]

Instructions:
- Look for "President and Chief Executive Officer" or "Chairman, President & Chief Executive Officer" and find the name that appears BEFORE this title
- Look for "Chief Financial Officer" (with or without "Senior Vice President") and find the name that appears BEFORE this title
- Look for "Treasurer" (with or without "Vice President") and find the name that appears BEFORE this title
- Use the full name (including middle initials if present)
- If a position is not found, write "same"
- Return only the three lines in the exact format above, nothing else

Leadership Page Text:
\"\"\"
{cleaned_text}
\"\"\"
"""

    print("=== SENDING TO GPT ===")
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content
    result = content.strip() if content else ""
    print(f"=== GPT RESPONSE ===")
    print(result)
    print("=== END GPT RESPONSE ===")
    return result

def clean_executive_text(text):
    """Clean up executive text to reduce token count and remove duplicates"""
    lines = text.split('\n')
    cleaned_lines = []
    seen_lines = set()
    
    # Track if we're in an executive section
    in_executive_section = False
    executive_section_keywords = [
        'executive', 'leadership', 'management', 'officers', 'directors', 'team',
        'ceo', 'cfo', 'treasurer', 'president', 'chief', 'officer', 'director',
        'chair', 'chairman', 'chairwoman', 'founder', 'co-founder',
        'general manager', 'senior vice president', 'vice president'
    ]
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Skip navigation, JavaScript, and repetitive content
        skip_patterns = [
            'Skip to main content', 'EN', 'Français', 'Deutsch', 'Italiano', 'Español',
            'Visit a different', 'European Union', 'United States',
            'Site Search', 'Overview', 'About', 'Investor Relations',
            'Annual reports', 'Quarterly results', 'SEC filings', 'Press releases',
            'FAQs', 'Corporate governance', 'Contact us', 'Events',
            'Facebook', 'Instagram', 'LinkedIn', 'Twitter', 'Youtube',
            'Shop', 'Job Creation', 'Working At', 'Our Communities',
            'Sustainability', 'Innovation', 'Our Company', 'Investors', 'Press center',
            'Select awards', 'Conditions of Use', '©', 'Powered By',
            '(opens in new window)', 'Committee Composition',
            '= Committee Chair', '= Member', '= Executive Chair', '= Lead Director',
            '$(\'', 'usePublic:', 'apiKey:', 'committeeTypes:',
            'customRoles:', 'headerTpl:', 'itemTpl:', 'legendTpl:', 'beforeRender:',
            'onComplete:', 'q4App.toggle', 'console.log', '/* beautify preserve:start */',
            '/* beautify preserve:end */', '!function(', '{"@context"', '{"@type"',
            'Executive Leadership Team', 'Board of Directors', 'About Me >'
        ]
        
        if any(pattern in line for pattern in skip_patterns):
            continue
            
        # Remove duplicate lines
        if line in seen_lines:
            continue
            
        # Check if this line indicates we're in an executive section
        if any(keyword in line.lower() for keyword in executive_section_keywords):
            in_executive_section = True
            cleaned_lines.append(line)
            seen_lines.add(line)
            continue
            
        # If we're in an executive section, keep the next few lines (likely names)
        if in_executive_section:
            # Keep lines that look like names (2-3 words, capitalized)
            if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$', line):
                cleaned_lines.append(line)
                seen_lines.add(line)
            # Keep lines that are clearly executive titles
            elif any(keyword in line.lower() for keyword in executive_section_keywords):
                cleaned_lines.append(line)
                seen_lines.add(line)
            # Keep lines that might be names but don't match the strict pattern
            elif len(line.split()) <= 4 and any(word[0].isupper() for word in line.split()):
                cleaned_lines.append(line)
                seen_lines.add(line)
            # Keep lines that look like names with middle initials (e.g., "Kenneth T. Lane")
            elif re.match(r'^[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+$', line):
                cleaned_lines.append(line)
                seen_lines.add(line)
            # If we hit a line that doesn't look like a name or title, stop
            elif len(line.split()) > 5:
                in_executive_section = False
    
    return '\n'.join(cleaned_lines)

def google_search_treasurer(company_name):
    """Search for treasurer using SerpAPI"""
    search_results = search_web(f'{company_name} "treasurer"')
    for result in search_results:
        if 'linkedin' in result.get('link', '').lower():
            response = requests.get(result['link'])
            if company_name.lower() in response.text.lower():
                name_pattern = re.compile(r'[A-Z][a-z]+ [A-Z][a-z]+')
                match = name_pattern.search(response.text)
                return match.group(0) if match else "same"
    return "same"

def get_industry_and_blurb(company_name):
    """Get industry and company blurb"""
    prompt = f"""Give me the industry of {company_name} in under 5 words (in caps for first letters. ex: Media and Entertainment). After that give me a small 3 sentence blurb on what their company does. The blurb should be concise."""
    
    # Search for company info
    search_results = search_web(f"{company_name} about")
    context = "\n".join([result.get('snippet', '') for result in search_results[:3]])
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt + "\nContext: " + context}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""

def get_credit_agreement(company_name):
    """Retrieve and summarize credit agreement"""
    prompt = f"""Pull the latest credit agreement for {company_name}. Summarize it (include lead bank, amount, structure, rate, covenants, other key info) and provide a direct link at the bottom."""
    
    # Search SEC EDGAR for credit agreement
    query = {
        "query": f'"{company_name}" "credit agreement"',
        "formTypes": ["8-K", "10-Q", "10-K"],
        "start": 0,
        "limit": 1
    }
    filings = sec_api.get_filings(query)
    filing_url = None
    if filings and 'filings' in filings and filings['filings']:
        filing_url = filings['filings'][0]['linkToFilingDetails']
    
    # Extract agreement text (simplified)
    agreement_text = "Extracted credit agreement text" if filing_url else ""
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt + "\nContext: " + agreement_text}]
    )
    content = response.choices[0].message.content
    summary = content.strip() if content else ""
    
    if filing_url:
        summary += f"\nDirect Link: {filing_url}"
    return summary

def process_10q_debt(company_name, debt_section):
    """Process 10-Q debt section"""
    prompt = f"""Convert the "Debt" and "Liquidity and Capital Resources" section from {company_name}'s latest 10-Q to layman's terms, focusing on the debt capital stack. Organize from earliest to latest maturity in the format:
facility @ (interest rate) mat. mm/yyyy (Lead Bank)
- Supporting bullet points"""
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt + "\n\n" + debt_section}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""

def get_covenant_analysis(company_name):
    """Analyze covenants"""
    prompt = f"""Give me a covenant analysis for {company_name}. Are they close on any covenants or is there anything else alarming? Provide in bullets."""
    
    search_results = search_web(f"{company_name} covenant breach")
    context = "\n".join([result.get('snippet', '') for result in search_results[:3]])
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt + "\nContext: " + context}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""

def get_refi_credit_analysis(company_name):
    """Analyze refi and credit"""
    prompt = f"""Provide a paragraph of analysis on refi and credit for {company_name}. Focus on debt due by 2027, cash reserves, deleveraging, and risks. Keep it concise."""
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""

# def store_results(company_name, data):
#     """Store results in Excel"""
#     df = pd.DataFrame({
#         'Company': [company_name],
#         'Executives': [data['executives']],
#         'Industry_and_Blurb': [data['industry_blurb']],
#         'Credit_Agreement': [data['credit_agreement']],
#         'Debt_Stack': [data['debt_stack']],
#         'Covenant_Analysis': [data['covenant_analysis']],
#         'Refi_Credit_Analysis': [data['refi_credit_analysis']]
#     })
#     df.to_excel(OUTPUT_FILE, index=False)

async def main():
    company_name = input("Enter company name: ")
    debt_section = "Paste 10-Q Debt and Liquidity section here"
    results = {
        'executives': await get_executives(company_name),
        #'industry_blurb': get_industry_and_blurb(company_name),
        #'credit_agreement': get_credit_agreement(company_name),
       # 'debt_stack': process_10q_debt(company_name, debt_section),
        #'covenant_analysis': get_covenant_analysis(company_name),
       # 'refi_credit_analysis': get_refi_credit_analysis(company_name)
    }
    for key, value in results.items():
        print(f"\n{key.upper()}:\n{value}\n")
    print("Done!")

if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())