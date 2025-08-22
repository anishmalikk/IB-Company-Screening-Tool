# ib-company-screener
A comprehensive automated investment banking company screening platform that leverages advanced AI, SEC filings, and public data sources to provide detailed financial and executive intelligence.

## Frontend Interface
<img width="2000" height="1085" alt="screenerUI" src="https://github.com/user-attachments/assets/d23ad4a1-7821-4258-8c61-77f71b837626" />
▶️ [Watch the demo on YouTube](https://youtu.be/tQ7nEyVsclU)
<br><br>
The platform provides a modern web interface (`frontend.html`) with the following features:

### Search Interface
- **Company Name Input**: Full company name (e.g., "Apple Inc.", "Microsoft Corporation")
- **Ticker Symbol Input**: Stock ticker (e.g., "AAPL", "MSFT")
- **Configurable Functions**: Checkbox selection for different data components

### Available Data Components
1. **Executive Information**: CEO, CFO, and Treasurer details
2. **Email Information**: Constructed executive email addresses with domain and format detection
3. **S&P Credit Rating**: Latest credit rating from S&P
4. **Industry Information**: Industry classification and business description
5. **SEC Filing Links**: Latest 10-Q and 10-K filing URLs
6. **Debt and Liquidity Analysis**: Downloadable SEC filings and analysis prompts

### Results Display
- **Company Overview**: Basic company information with credit rating and industry
- **Executive Details**: CEO, CFO, and Treasurer information with LinkedIn links for treasurer candidates
- **Email Information**: Constructed emails with quality scoring and source information
- **SEC Filings**: Downloadable 10-Q and 10-K files with custom naming
- **Analysis Prompts**: Copyable GPT prompts for debt analysis and summary generation

## Backend API Architecture

The FastAPI server (`main.py`) provides a comprehensive REST API that orchestrates all screening components.

### Main Endpoint: `/company_info/{company_name}/{ticker}`

**Query Parameters:**
- `include_executives` (bool): Executive information (default: true)
- `include_emails` (bool): Email construction (default: true)
- `include_credit_rating` (bool): S&P credit rating (default: true)
- `include_industry` (bool): Industry classification (default: true)
- `include_industry_blurb` (bool): Business description (default: true)
- `include_10q_link` (bool): Latest 10-Q filing URL (default: true)
- `include_10k_link` (bool): Latest 10-K filing URL (default: false)
- `include_debt_liquidity` (bool): Debt analysis and prompts (default: true)

**Response Structure:**
```json
{
  "executives": {
    "cfo": "Name",
    "treasurer": "Name", 
    "ceo": "Name",
    "treasurer_metadata": {
      "candidates": [
        {
          "name": "Candidate Name",
          "linkedin_url": "LinkedIn URL",
          "score": 0.95
        }
      ]
    }
  },
  "emails": {
    "domain": "@company.com",
    "format": "first.last",
    "cfo_email": "cfo@company.com",
    "treasurer_email": "treasurer@company.com",
    "all_discovered_emails": [
      {
        "email": "email@company.com",
        "quality": "high",
        "score": 0.95,
        "source": "website"
      }
    ]
  },
  "credit_rating": "BBB+",
  "industry": "Technology",
  "industry_blurb": "3-sentence description",
  "latest_10q_link": "SEC filing URL",
  "latest_10k_link": "SEC filing URL",
  "debt_liquidity_summary": ["Analysis results"],
  "debt_analysis_prompt": "Manual GPT prompt",
  "debt_summary_prompt": "Summary generation prompt"
}
```

### File Download Endpoints

**`/download_10q/{ticker}`**
- Downloads 10-Q filing as HTML file
- Optional `company_name` parameter for custom filename
- Returns file with proper headers for browser download

**`/download_10k/{ticker}`**
- Downloads 10-K filing as HTML file
- Optional `company_name` parameter for custom filename
- Returns file with proper headers for browser download

## Executive Scraper Pipeline

The `exec_scraper.py` module provides automated extraction of company leadership information using a multi-source data pipeline.

### Pipeline Overview

```
Company Name Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Data Collection Phase                    │
├─────────────────────────────────────────────────────────────┤
│ 1. CEO/CFO Search Results (SerpAPI)                         │
│ 2. Leadership Page URL Discovery                            │
│ 3. Leadership Page Full Text Scraping (Playwright)          │
│ 4. Treasurer-Specific Search Results                        │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Data Processing Phase                    │
├─────────────────────────────────────────────────────────────┤
│ LLM Analysis & Formatting                                   │
│ - Validates current vs former executives                    │
│ - Cross-references multiple sources                         │
│ - Formats output in standardized format                     │
└─────────────────────────────────────────────────────────────┘
       ↓
Formatted Executive Information Output
```

### Key Functions & Data Flow

#### 1. Data Collection Functions

**`fetch_serp_results(company_name, query, num_results=20)`**
- Uses SerpAPI to search Google for company-specific queries
- Returns concatenated snippets from organic search results
- Configurable result count (default: 20 results)

**`fetch_leadership_page_url(company_name)`**
- Searches for company leadership pages using keywords: "leadership", "executive", "management", "officers", "team", "board", "directors"
- Implements smart URL selection:
  1. **Best match**: Leadership keyword + company domain
  2. **Fallback**: Any URL with leadership keyword
  3. **Final fallback**: First search result

**`get_leadership_page_text(url)`**
- **Primary**: Uses Playwright for JavaScript-rendered content
- **Fallback**: Requests + BeautifulSoup for static content
- Extracts full page text with proper formatting
- Handles timeouts and user-agent spoofing

#### 2. Specialized Search Functions

**`fetch_leadership_page_snippets(company_name)`**
- Searches: `"{company_name} leadership site"`
- Returns leadership-related search snippets

**`fetch_treasurer_search_snippets(company_name)`**
- Searches: `"{company_name} "treasurer""` (exact match)
- Focuses specifically on treasurer information

#### 3. Data Processing & Output

**`format_exec_info(ceo_cfo_snippets, leadership_snippets, treasurer_snippets, company_name)`**
- Combines all collected data sources
- Uses LLM (configurable via `MODEL_NAME` env var, default: gpt-4.1-nano)
- Validates current vs former executives
- Cross-references multiple sources for accuracy
- Outputs standardized format:
  ```
  CFO: [Name]
  Treasurer (or closest): [Name or "same"]
  CEO: [Name]
  ```

### Main Entry Points

**`get_execs_via_serp(company_name)`** (async)
- Primary async function orchestrating the entire pipeline
- Returns formatted executive information

**`get_execs_via_serp_sync(company_name)`** (sync)
- Synchronous wrapper for backward compatibility
- Uses `asyncio.run()` to execute async pipeline

### Technical Details

#### Environment Variables
- `SERPAPI_API_KEY`: Required for Google search functionality
- `MODEL_NAME`: LLM model for data processing (default: gpt-4.1-nano)

#### Dependencies
- **SerpAPI**: Google search results
- **Playwright**: JavaScript rendering for dynamic content
- **Requests + BeautifulSoup**: Fallback web scraping
- **LLM Client**: AI-powered data analysis

#### Error Handling
- Graceful fallbacks from Playwright to requests
- Timeout handling (30s for Playwright, 10s for requests)
- Empty result handling with appropriate defaults

#### Data Quality Features
- Multi-source validation to ensure current executives
- Cross-referencing between search results and company websites
- Latest news consideration for recent leadership changes
- LinkedIn and other credible source integration for treasurer information

## Intelligent Treasurer System

The `intelligent_treasurer_system.py` module provides advanced treasurer detection with uncertainty handling and multiple candidate ranking.

### Key Features

**Multi-Candidate Detection**
- Returns multiple treasurer candidates with confidence scores
- LinkedIn URL extraction for each candidate
- Source quality assessment and ranking

**Uncertainty Handling**
- Transparent confidence levels (high, medium, low)
- Fallback strategies for unclear results
- Honest reporting of detection limitations

**Enhanced Name Validation**
- spaCy NER for name entity recognition
- NLTK name database validation
- Navigation term filtering
- Company name similarity detection

### Data Structures

**`TreasurerCandidate`**
```python
@dataclass
class TreasurerCandidate:
    name: str
    confidence: float  # 0.0 to 1.0
    source: str  # e.g., "leadership_page", "search_results"
    evidence: str  # Supporting evidence text
    potential_issues: List[str]  # e.g., ["outdated_info"]
    linkedin_url: Optional[str] = None
```

**`TreasurerDetectionResult`**
```python
@dataclass
class TreasurerDetectionResult:
    status: str  # "single_confident", "multiple_candidates", "uncertain"
    primary_treasurer: Optional[str]
    candidates: List[TreasurerCandidate]
    confidence_level: str  # "high", "medium", "low"
    recommendation: str
    email_strategy: str  # "use_treasurer", "use_cfo_only"
```

### Detection Strategies

**Source Integration**
- Leadership page text analysis
- Google search result parsing
- LinkedIn snippet extraction
- Cross-source validation

**Confidence Assessment**
- Context quality analysis
- Recency validation
- Role clarity assessment
- Source credibility scoring

## Email Scraper Pipeline

The `email_scraper.py` module provides automated extraction and construction of executive email addresses using intelligent pattern recognition and multi-source validation.

### Pipeline Overview

```
Company Name + Executive Names Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Domain Discovery Phase                   │
├─────────────────────────────────────────────────────────────┤
│ 1. Email Format Search (SerpAPI)                            │
│ 2. Domain Extraction from Search Results                    │
│ 3. Fallback: Investor Relations/PR Email Search             │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Email Discovery Phase                    │
├─────────────────────────────────────────────────────────────┤
│ 1. CFO Email Search (Primary)                               │
│ 2. CEO Email Search (Fallback)                              │
│ 3. Treasurer Email Search (Secondary Fallback)              │
│ 4. Name-Email Pair Extraction                               │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Format Detection Phase                   │
├─────────────────────────────────────────────────────────────┤
│ 1. Pattern Analysis (first.last, firstlast, etc.)           │
│ 2. GPT Format Inference (Fallback)                          │
│ 3. Common Format Testing (Last Resort)                      │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Email Construction Phase                 │
├─────────────────────────────────────────────────────────────┤
│ 1. Name Normalization & Parsing                             │
│ 2. Email Format Application                                 │
│ 3. Fake/Test Email Filtering                                │
│ 4. Generic Email Detection                                  │
└─────────────────────────────────────────────────────────────┘
       ↓
Constructed Executive Email Addresses
```

### Key Functions & Data Flow

#### 1. Domain Discovery Functions

**`serp_api_search(company_name, query, num_results=20, start=0)`**
- Core search function using SerpAPI
- Configurable result count and pagination
- Returns structured snippets from organic results

**`extract_email_domain(snippets)`**
- Extracts first valid email domain from search snippets
- Uses regex pattern: `([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)`
- Returns domain portion for email construction

#### 2. Email Discovery Functions

**`extract_known_emails(snippets, domain)`**
- Extracts (name, email) pairs from snippets for given domain
- Uses improved regex for names with middle initials, periods, hyphens
- Pattern: `([A-Z][a-zA-Z.\'\-]+(?: [A-Z][a-zA-Z.\'\-]+)+)[^\n]{0,100}` + email
- Fallback: extracts all emails with domain if no name matches

**`extract_all_non_generic_emails(snippets, domain, actual_names)`**
- Filters out generic emails (info@, pr@, contact@, etc.)
- Filters out fake/test emails using `is_fake_or_test_email()`
- Returns list of valid person emails for format inference

#### 3. Email Format Detection Functions

**`detect_email_format(name, email)`**
- Analyzes name-email pair to determine format pattern
- Supports formats: first.last, firstlast, f.last, first, last
- Uses HumanName parser for robust name handling

**`infer_format_from_email(email, name=None)`**
- Attempts to infer format from email structure alone
- Compares against common patterns when name is available
- Fallback pattern analysis for unknown names

**`gpt_infer_format(name, emails)`**
- Uses LLM to analyze email patterns when traditional methods fail
- Provides structured prompt for format detection
- Returns standardized format strings or "NO_VALID_FORMAT"

#### 4. Email Construction Functions

**`construct_email(name, domain, fmt)`**
- Builds email address from name, domain, and format
- Handles name normalization and parsing
- Supports 8+ email formats with defensive programming

**`normalize_name(name)`**
- Handles Unicode normalization and non-breaking spaces
- Ensures consistent name formatting across sources

#### 5. Email Validation Functions

**`is_generic_email(email)`**
- Detects generic/department emails using predefined prefixes
- Filters: pr, info, investor, contact, support, admin, etc.
- Handles dot-separated local parts robustly

**`is_fake_or_test_email(email, actual_names=None)`**
- Comprehensive fake email detection using multiple strategies:
  - Random patterns (abcdef, qwerty, test123)
  - Length validation (too short/long)
  - Vowel absence detection
  - Common fake name patterns
  - Actual name cross-referencing

### Main Entry Point

**`scrape_emails(company_name, cfo_name, treasurer_name, ceo_name)`**
- Orchestrates entire email discovery and construction pipeline
- Implements multi-level fallback strategy
- Returns structured result with domain, format, and constructed emails

### Technical Details

#### Environment Variables
- `SERPAPI_API_KEY`: Required for Google search functionality
- `MODEL_NAME`: LLM model for format inference (default: gpt-4.1-nano)
- `OPENAI_API_KEY`: Required for GPT fallback functionality

#### Dependencies
- **SerpAPI**: Google search results
- **nameparser**: Robust name parsing and normalization
- **OpenAI/LLM Client**: AI-powered format inference
- **re**: Advanced regex pattern matching
- **unicodedata**: Unicode normalization

#### Email Format Support
- `first.last`: john.smith@company.com
- `firstlast`: johnsmith@company.com
- `first_initiallast`: jsmith@company.com
- `first_initial.last`: j.smith@company.com
- `first`: john@company.com
- `last`: smith@company.com
- `first.last_initial`: john.s@company.com
- `first_initiallast_initial`: js@company.com

#### Data Quality Features
- Multi-source validation with actual names
- Comprehensive fake email filtering
- Generic email detection and filtering
- Fallback strategies for format detection
- Unicode normalization for international names
- Defensive programming for edge cases

#### Error Handling
- Graceful fallbacks from specific to general searches
- Multiple format detection strategies
- Empty result handling with appropriate error messages
- Timeout and API error handling

## Credit Rating Pipeline

The `getcreditrating.py` module provides automated extraction of S&P credit ratings using web search and AI-powered analysis.

### Pipeline Overview

```
Company Name Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Web Search Phase                         │
├─────────────────────────────────────────────────────────────┤
│ 1. S&P Credit Rating Search (SerpAPI)                       │
│ 2. Snippet Collection from Organic Results                  │
│ 3. Context Aggregation (10 results)                         │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    AI Analysis Phase                        │
├─────────────────────────────────────────────────────────────┤
│ 1. Structured Prompt Construction                           │
│ 2. LLM Credit Rating Extraction                             │
│ 3. Format Validation & Output                               │
└─────────────────────────────────────────────────────────────┘
       ↓
Latest S&P Credit Rating
```

### Key Functions & Data Flow

#### 1. Web Search Functions

**`search_company_credit_rating(company_name: str)`**
- Direct SerpAPI integration using GoogleSearch
- Configurable result count (default: 10 results)
- Error handling for API failures
- Returns organic search results with snippets

**Search Query Strategy**
- Primary query: `"{company_name} S&P credit rating"`
- Focuses on official S&P ratings
- Optimized for credit rating context

#### 2. Data Processing Functions

**`extract_credit_rating_from_snippets(company_name: str, snippets: List[Dict])`**
- Uses LLM to analyze search snippets
- Extracts latest S&P credit rating
- Handles multiple rating formats and sources
- Returns standardized rating format

**`get_company_credit_rating(company_name: str)`**
- Main orchestration function combining search and AI analysis
- Constructs comprehensive prompt with search context
- Handles LLM response processing and formatting
- Returns structured credit rating output

#### 3. AI Analysis Functions

**Prompt Construction Strategy**
- **Focus**: Latest S&P credit rating extraction
- **Format**: Standard rating format (e.g., "BBB+", "AA-")
- **Context Integration**: Uses aggregated search snippets
- **Validation**: Official S&P ratings only

**LLM Processing**
- Uses configurable model (default: gpt-4.1-nano)
- Structured output format with clear examples
- Error handling for empty or malformed responses

### Main Entry Point

**`get_company_credit_rating(company_name: str)`**
- Single entry point for credit rating extraction
- Returns latest S&P credit rating or "N/A"
- Handles complete pipeline from search to AI analysis

### Technical Details

#### Environment Variables
- `SERPAPI_API_KEY`: Required for web search functionality
- `OPENAI_API_KEY`: Required for LLM analysis
- `MODEL_NAME`: LLM model for analysis (default: gpt-4.1-nano)

#### Dependencies
- **serpapi**: Google search results
- **OpenAI**: LLM client for AI-powered analysis
- **os**: Environment variable management

#### Output Format
- **Credit Rating**: Standard S&P format (e.g., "BBB+", "AA-", "N/A")
- **Error Handling**: Returns "N/A" for unavailable ratings
- **Validation**: Focuses on official S&P ratings only

#### Data Quality Features
- Multi-source context aggregation from search results
- Structured prompt with clear examples
- Format validation for credit rating classification
- Latest rating prioritization

#### Error Handling
- SerpAPI error handling with status code checking
- Empty result handling with appropriate fallbacks
- LLM response validation and formatting
- Graceful degradation for API failures

## Industry & Company Blurb Pipeline

The `get_industry.py` module provides automated extraction of company industry classification and business description using web search and AI-powered analysis.

### Pipeline Overview

```
Company Name Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Web Search Phase                         │
├─────────────────────────────────────────────────────────────┤
│ 1. Company "About" Search (SerpAPI)                         │
│ 2. Snippet Collection from Organic Results                  │
│ 3. Context Aggregation (15 results)                         │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    AI Analysis Phase                        │
├─────────────────────────────────────────────────────────────┤
│ 1. Structured Prompt Construction                           │
│ 2. LLM Industry Classification                              │
│ 3. Business Description Generation                          │
│ 4. Format Validation & Output                               │
└─────────────────────────────────────────────────────────────┘
       ↓
Industry Classification + 3-Sentence Company Blurb
```

### Key Functions & Data Flow

#### 1. Web Search Functions

**`search_web(query, num_results=15)`**
- Direct SerpAPI integration using requests
- Configurable result count (default: 15 results)
- Error handling for API failures
- Returns organic search results with snippets

**Search Query Strategy**
- Primary query: `"{company_name} about"`
- Focuses on company description and business information
- Optimized for industry classification context

#### 2. Data Processing Functions

**`get_industry_and_blurb(company_name)`**
- Main orchestration function combining search and AI analysis
- Constructs comprehensive prompt with search context
- Handles LLM response processing and formatting
- Returns structured industry + blurb output

#### 3. AI Analysis Functions

**Prompt Construction Strategy**
- **Industry Classification**: Under 5 words, capitalized format
- **Example Format**: "Semiconductors and Consumer Electronics"
- **Business Description**: Concise 3-sentence blurb
- **Context Integration**: Uses aggregated search snippets

**LLM Processing**
- Uses configurable model (default: gpt-4.1-nano)
- Structured output format with clear examples
- Error handling for empty or malformed responses

### Main Entry Point

**`get_industry_and_blurb(company_name)`**
- Single entry point for industry and blurb extraction
- Returns combined industry classification and business description
- Handles complete pipeline from search to AI analysis

### Technical Details

#### Environment Variables
- `SERPAPI_API_KEY`: Required for web search functionality
- `OPENAI_API_KEY`: Required for LLM analysis
- `MODEL_NAME`: LLM model for analysis (default: gpt-4.1-nano)

#### Dependencies
- **requests**: HTTP client for SerpAPI integration
- **OpenAI**: LLM client for AI-powered analysis
- **os**: Environment variable management

#### Output Format
- **Industry**: Capitalized format, under 5 words
  - Example: "Media And Entertainment", "Semiconductors and Consumer Electronics"
- **Business Blurb**: 3-sentence concise description
  - Focuses on products, services, customers, and market position

#### Data Quality Features
- Multi-source context aggregation from search results
- Structured prompt with clear examples
- Format validation for industry classification
- Concise but comprehensive business descriptions

#### Error Handling
- SerpAPI error handling with status code checking
- Empty result handling with appropriate fallbacks
- LLM response validation and formatting
- Graceful degradation for API failures

## 10-Q & 10-K Analysis Pipeline

The `promptand10q.py` module provides automated extraction and analysis of debt facilities from SEC 10-Q and 10-K filings using AI-powered document parsing.

### Pipeline Overview

```
Company Ticker Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    SEC Filing Discovery Phase               │
├─────────────────────────────────────────────────────────────┤
│ 1. Ticker to CIK Mapping                                    │
│ 2. Latest 10-Q/10-K Filing Retrieval                        │
│ 3. Document Download & Parsing                              │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Facility Extraction Phase                │
├─────────────────────────────────────────────────────────────┤
│ 1. First Pass: LLM Facility Identification                  │
│ 2. Facility List Generation                                 │
│ 3. Format Validation & Structuring                          │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Prompt Generation Phase                  │
├─────────────────────────────────────────────────────────────┤
│ 1. Manual GPT Prompt Construction                           │
│ 2. Full HTML Document Integration                           │
│ 3. Structured Analysis Instructions                         │
└─────────────────────────────────────────────────────────────┘
       ↓
Facility List + Manual Analysis Prompt
```

### Key Functions & Data Flow

#### 1. SEC Filing Functions

**`get_latest_10q_link_for_ticker(ticker: str)`**
- Maps ticker to CIK using `ticker_utils.py`
- Retrieves latest 10-Q filing from SEC EDGAR
- Returns direct URL to filing document
- Handles CIK formatting and accession number processing

**`get_latest_10k_link_for_ticker(ticker: str)`**
- Maps ticker to CIK using `ticker_utils.py`
- Retrieves latest 10-K filing from SEC EDGAR
- Returns direct URL to filing document
- Handles CIK formatting and accession number processing

**`download_and_parse_10q(ticker: str)`**
- Downloads 10-Q HTML content from SEC
- Parses document using BeautifulSoup
- Extracts both HTML and text content
- Returns structured document data

**`download_and_parse_10k(ticker: str)`**
- Downloads 10-K HTML content from SEC
- Parses document using BeautifulSoup
- Extracts both HTML and text content
- Returns structured document data

#### 2. Facility Extraction Functions

**`extract_facility_names_from_10q(soup, text_content, debug=False)`**
- First pass LLM analysis of 10-Q document
- Identifies all currently active debt facilities
- Extracts facility names, currencies, maturities, types
- Uses specialized prompt for comprehensive extraction
- Returns structured facility list

**`extract_facility_names_from_10k(soup, text_content, debug=False)`**
- First pass LLM analysis of 10-K document
- Identifies all currently active debt facilities
- Extracts facility names, currencies, maturities, types
- Uses specialized prompt for comprehensive extraction
- Returns structured facility list

**LLM Analysis Strategy**
- **Model**: Configurable via `10Q_MODEL_NAME` (default: gpt-4o-mini)
- **Temperature**: 0.1 for consistent extraction
- **Focus**: Active facilities only, comprehensive listing
- **Format**: One facility per line with key details

#### 3. Prompt Generation Functions

**`generate_manual_gpt_prompt(facility_list_10q: str, facility_list_10k: str, html_content: str)`**
- Constructs detailed analysis prompt for manual GPT use
- Integrates facility list with full HTML document
- Provides structured format requirements
- Includes maturity ordering and completeness instructions

**`generate_debt_summary_prompt()`**
- Creates prompt for converting debt analysis into concise summaries
- Focuses on one-line facility summaries
- Provides structured format for consistent output

**Prompt Structure**
- **Input**: Facility list + full HTML document
- **Output Format**: `$[Amount] [Type] @ [Rate] mat. MM/YYYY (Bank)`
- **Requirements**: Full facility amounts, supporting bullets, maturity ordering
- **Validation**: Missing information handling

#### 4. Pipeline Orchestration

**`run_prompt_generation_pipeline(ticker: str, debug=False)`**
- Main orchestration function for complete 10-Q pipeline
- Coordinates document download, facility extraction, and prompt generation
- Returns both facility list and manual analysis prompt
- Handles error cases and debugging

**`run_10k_prompt_generation_pipeline(ticker: str, debug=False)`**
- Main orchestration function for complete 10-K pipeline
- Coordinates document download, facility extraction, and prompt generation
- Returns both facility list and manual analysis prompt
- Handles error cases and debugging

### Main Entry Points

**`get_latest_10q_link_for_ticker(ticker: str)`**
- Returns direct URL to latest 10-Q filing
- Used by both analysis pipeline and download endpoint

**`get_latest_10k_link_for_ticker(ticker: str)`**
- Returns direct URL to latest 10-K filing
- Used by both analysis pipeline and download endpoint

**`run_prompt_generation_pipeline(ticker: str, debug=False)`**
- Complete pipeline for 10-Q debt facility analysis
- Returns structured data for manual GPT analysis

**`run_10k_prompt_generation_pipeline(ticker: str, debug=False)`**
- Complete pipeline for 10-K debt facility analysis
- Returns structured data for manual GPT analysis

### Technical Details

#### Environment Variables
- `OPENAI_API_KEY`: Required for LLM analysis
- `10Q_MODEL_NAME`: LLM model for facility extraction (default: gpt-4o-mini)

#### Dependencies
- **sec_edgar_api**: SEC EDGAR client for filing access
- **requests**: HTTP client for document download
- **BeautifulSoup**: HTML parsing and text extraction
- **OpenAI**: LLM client for AI-powered analysis
- **ticker_utils**: CIK mapping functionality

#### Data Quality Features
- Comprehensive facility identification from full document
- Active facility filtering (excludes outdated facilities)
- Structured output format with key details
- Maturity-based ordering for analysis
- Missing information handling and reporting
- Deduplication of facility listings

#### Error Handling
- CIK mapping failures with graceful degradation
- SEC API error handling and retry logic
- Document download failures with appropriate fallbacks
- LLM analysis error handling and debugging support

## LLM Client Pipeline

The `llm_client.py` module provides unified LLM client configuration supporting both OpenAI and OpenRouter APIs.

### Pipeline Overview

```
Environment Configuration
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Client Selection Phase                   │
├─────────────────────────────────────────────────────────────┤
│ 1. USE_OPENROUTER Environment Check                         │
│ 2. API Key Validation                                       │
│ 3. Client Configuration                                     │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Client Initialization Phase              │
├─────────────────────────────────────────────────────────────┤
│ 1. OpenAI Client (Default)                                  │
│ 2. OpenRouter Client (Alternative)                          │
│ 3. Base URL Configuration                                   │
└─────────────────────────────────────────────────────────────┘
       ↓
Configured LLM Client Instance
```

### Key Functions & Data Flow

#### 1. Client Configuration Functions

**`get_llm_client() -> OpenAI`**
- **Primary**: OpenAI client with standard configuration
- **Alternative**: OpenRouter client with custom base URL
- **Validation**: API key presence and format checking
- **Error Handling**: Runtime errors for missing configuration

**Client Selection Logic**
- **Default**: OpenAI client with `OPENAI_API_KEY`
- **Alternative**: OpenRouter client with `OPENROUTER_API_KEY`
- **Configuration**: `USE_OPENROUTER` environment variable
- **Base URL**: OpenRouter uses `https://openrouter.ai/api/v1`

#### 2. Model Configuration Functions

**`get_model_name() -> str`**
- Returns configured model name for LLM calls
- **Default**: "gpt-4.1-nano"
- **Configuration**: `MODEL_NAME` environment variable
- **Usage**: Consistent model selection across components

### Technical Details

#### Environment Variables
- `USE_OPENROUTER`: Boolean flag for client selection
- `OPENAI_API_KEY`: Required for OpenAI client
- `OPENROUTER_API_KEY`: Required for OpenRouter client
- `MODEL_NAME`: Configurable model selection

#### Dependencies
- **OpenAI**: Official OpenAI Python client
- **os**: Environment variable access
- **dotenv**: Environment file loading

#### Error Handling
- Missing API key validation
- Runtime error handling for configuration issues
- Clear error messages for debugging

## Ticker Utilities Pipeline

The `ticker_utils.py` module provides ticker-to-CIK mapping functionality for SEC filing access.

### Pipeline Overview

```
Ticker Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    CIK Mapping Phase                        │
├─────────────────────────────────────────────────────────────┤
│ 1. JSON Database Loading                                    │
│ 2. Case-Insensitive Ticker Matching                         │
│ 3. CIK String Extraction                                    │
└─────────────────────────────────────────────────────────────┘
       ↓
CIK String Output
```

### Key Functions & Data Flow

#### 1. Mapping Functions

**`get_cik_for_ticker(ticker: str) -> str`**
- Loads company ticker database from JSON file
- Performs case-insensitive ticker matching
- Returns CIK string for SEC filing access
- Handles missing tickers with empty string return

**Database Structure**
- **File**: `company_tickers.json`
- **Format**: Nested JSON with ticker and CIK mapping
- **Size**: ~748KB with comprehensive company coverage
- **Access**: Local file system for fast lookups

### Technical Details

#### Dependencies
- **json**: JSON file parsing
- **os**: File path management

#### Data Quality Features
- Comprehensive company coverage
- Case-insensitive matching
- Fast local database access
- Graceful handling of missing tickers

#### Error Handling
- File loading error handling
- Missing ticker graceful degradation
- Empty string returns for failed lookups

## Setup and Installation

### Prerequisites
- **Python 3.8+** (required for backend)
- **Git** (for cloning the repository)
- **Required API keys** (see Environment Variables section below)

### Environment Variables
```bash
# Required API Keys
SERPAPI_API_KEY=your_serpapi_key
OPENAI_API_KEY=your_openai_key
SEC_API_KEY=your_sec_api_key
OPENROUTER_API_KEY=your_openrouter_key  # Optional
OPENFIGI_API_KEY=your_openfigi_key  # Optional

# Model Configuration
MODEL_NAME=gpt-4.1-nano
10Q_MODEL_NAME=gpt-4.1-nano  # Change to gpt-4-turbo for most accuracy, but more expensive
SECONDPASS_MODEL=gpt-4.1-nano

# Client Selection
USE_OPENROUTER=false  # Set to true for OpenRouter

# Model Choices (for reference):
# gpt-4.1-nano (cheap)
# gpt-4o-mini (cheap)
# gpt-4o (moderate)
# gpt-4-turbo (expensive but better accuracy)
# Pricing: https://platform.openai.com/docs/models/compare
```

### Quick Setup (Recommended)

#### 🍎 macOS / Linux
```bash
# 1. Clone the repository
git clone <repository-url>
cd ib-company-screener

# 2. Run the automated setup script
chmod +x setup.sh
./setup.sh

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your API keys using your preferred editor
nano .env  # or: code .env, vim .env, etc.

# 4. Start the application
chmod +x start.sh
./start.sh
```

#### 🪟 Windows
```bash
# 1. Clone the repository
git clone <repository-url>
cd ib-company-screener

# 2. Run the automated setup script
# Open PowerShell as Administrator and run:
powershell -ExecutionPolicy Bypass -File setup.ps1

# 3. Configure environment variables
copy .env.example .env
# Edit .env with your API keys using your preferred editor
notepad .env  # or: code .env, etc.

# 4. Start the application
powershell -ExecutionPolicy Bypass -File start.ps1
```

### Manual Setup (Alternative)

#### 🍎 macOS / Linux
```bash
# 1. Clone the repository
git clone <repository-url>
cd ib-company-screener

# 2. Create and activate virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install

# 5. Configure environment variables
cd ..
cp .env.example .env
# Edit .env with your API keys

# 6. Start backend server
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 7. Start frontend server (in new terminal)
cd ..
python -m http.server 8080
```

#### 🪟 Windows
```bash
# 1. Clone the repository
git clone <repository-url>
cd ib-company-screener

# 2. Create and activate virtual environment
cd backend
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install

# 5. Configure environment variables
cd ..
copy .env.example .env
# Edit .env with your API keys

# 6. Start backend server
cd backend
venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 7. Start frontend server (in new terminal)
cd ..
python -m http.server 8080
```

### Accessing the Application

After successful setup, you can access:

- **🌐 Frontend Interface**: http://localhost:8080/frontend.html
- **🔧 Backend API**: http://localhost:8000
- **📚 API Documentation**: http://localhost:8000/docs

### Troubleshooting

#### Common Issues

**Port Already in Use**
```bash
# Kill processes using ports 8000 and 8080
lsof -ti:8000 | xargs kill -9  # macOS/Linux
lsof -ti:8080 | xargs kill -9  # macOS/Linux

# Windows (PowerShell)
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Python Not Found**
```bash
# Ensure Python 3.8+ is installed
python3 --version  # macOS/Linux
python --version   # Windows
```

**Virtual Environment Issues**
```bash
# Recreate virtual environment
rm -rf backend/venv  # macOS/Linux
rmdir /s backend\venv  # Windows
# Then run setup script again
```

**API Key Issues**
- Ensure all required API keys are set in `.env`
- Verify API keys are valid and have sufficient credits
- Check API service status for external services

#### Getting Help

1. **Check the logs** in your terminal for error messages
2. **Verify API keys** are correctly set in `.env`
3. **Test with known companies** like "Apple Inc." (AAPL) or "Microsoft Corporation" (MSFT)
4. **Check network connectivity** for external API calls

### Usage

1. **Enter company information**
   - Company name (e.g., "Apple Inc.")
   - Ticker symbol (e.g., "AAPL")

2. **Select desired functions**
   - Check/uncheck the functions you want to run
   - All functions are enabled by default

3. **Submit and wait for results**
   - Results will be displayed in organized sections
   - Download links for SEC filings
   - Copyable prompts for debt analysis

### File Structure
```
ib-company-screener/
├── frontend.html          # Main web interface
├── script.js             # Frontend JavaScript logic
├── styles.css            # Frontend styling
├── backend/
│   ├── main.py           # FastAPI server
│   ├── exec_scraper.py   # Executive extraction
│   ├── email_scraper.py  # Email construction
│   ├── get_industry.py   # Industry classification
│   ├── getcreditrating.py # Credit rating extraction
│   ├── promptand10q.py   # SEC filing analysis
│   ├── intelligent_treasurer_system.py # Advanced treasurer detection
│   ├── llm_client.py     # LLM client configuration
│   ├── ticker_utils.py   # Ticker-CIK mapping
│   └── requirements.txt   # Python dependencies
├── start.sh              # Startup script
├── setup.sh              # Setup script
└── README.md             # This file
```

## Technical Architecture

### Frontend-Backend Communication
- **Protocol**: HTTP REST API
- **CORS**: Enabled for cross-origin requests
- **Data Format**: JSON
- **Error Handling**: Structured error responses

### Data Flow
1. **User Input** → Frontend form submission
2. **API Request** → Backend endpoint processing
3. **Component Execution** → Parallel async processing
4. **Data Aggregation** → Structured JSON response
5. **Result Display** → Frontend rendering

### Error Handling Strategy
- **Component Isolation**: Individual component failures don't affect others
- **Graceful Degradation**: Partial results when some components fail
- **User Feedback**: Clear error messages and status indicators
- **Fallback Strategies**: Multiple approaches for critical data

### Performance Optimizations
- **Async Processing**: Parallel execution of independent components
- **Caching**: Local ticker database for fast lookups
- **Timeout Handling**: Configurable timeouts for external APIs
- **Resource Management**: Efficient memory usage and cleanup

## Contributing

### Development Guidelines
- Follow existing code structure and patterns
- Add comprehensive error handling
- Include appropriate logging and debugging
- Test with multiple company types and scenarios
- Update documentation for new features

### Testing Strategy
- Test with various company sizes and industries
- Verify API key configurations
- Test error scenarios and edge cases
- Validate frontend-backend integration
- Check SEC filing accessibility

### Deployment Considerations
- Environment variable management
- API key security
- CORS configuration for production
- Error monitoring and logging
- Performance optimization for high usage
