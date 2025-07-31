# ib-company-screener
Automated IB company screening tool using GPT + SEC + other public data

## Executive Scraper Pipeline

The `exec_scraper.py` module provides automated extraction of company leadership information (CEO, CFO, Treasurer) using a multi-source data pipeline.

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
- Uses LLM (configurable via `MODEL_NAME` env var, default: gpt-3.5-turbo)
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
- `MODEL_NAME`: LLM model for data processing (default: gpt-3.5-turbo)

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
- `MODEL_NAME`: LLM model for format inference (default: gpt-3.5-turbo)
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
- Uses configurable model (default: gpt-3.5-turbo)
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
- `MODEL_NAME`: LLM model for analysis (default: gpt-3.5-turbo)

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

## 10-Q Analysis Pipeline

The `promptand10q.py` module provides automated extraction and analysis of debt facilities from SEC 10-Q filings using AI-powered document parsing.

### Pipeline Overview

```
Company Ticker Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    SEC Filing Discovery Phase               │
├─────────────────────────────────────────────────────────────┤
│ 1. Ticker to CIK Mapping                                    │
│ 2. Latest 10-Q Filing Retrieval                             │
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

**`download_and_parse_10q(ticker: str)`**
- Downloads 10-Q HTML content from SEC
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

**LLM Analysis Strategy**
- **Model**: Configurable via `10Q_MODEL_NAME` (default: gpt-4o-mini)
- **Temperature**: 0.1 for consistent extraction
- **Focus**: Active facilities only, comprehensive listing
- **Format**: One facility per line with key details

#### 3. Prompt Generation Functions

**`generate_manual_gpt_prompt(facility_list: str, html_content: str)`**
- Constructs detailed analysis prompt for manual GPT use
- Integrates facility list with full HTML document
- Provides structured format requirements
- Includes maturity ordering and completeness instructions

**Prompt Structure**
- **Input**: Facility list + full HTML document
- **Output Format**: `$[Amount] [Type] @ [Rate] mat. MM/YYYY (Bank)`
- **Requirements**: Full facility amounts, supporting bullets, maturity ordering
- **Validation**: Missing information handling

#### 4. Pipeline Orchestration

**`run_prompt_generation_pipeline(ticker: str, debug=False)`**
- Main orchestration function for complete pipeline
- Coordinates document download, facility extraction, and prompt generation
- Returns both facility list and manual analysis prompt
- Handles error cases and debugging

### Main Entry Points

**`get_latest_10q_link_for_ticker(ticker: str)`**
- Returns direct URL to latest 10-Q filing
- Used by both analysis pipeline and download endpoint

**`run_prompt_generation_pipeline(ticker: str, debug=False)`**
- Complete pipeline for debt facility analysis
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

#### Error Handling
- CIK mapping failures with graceful degradation
- SEC API error handling and retry logic
- Document download failures with appropriate fallbacks
- LLM analysis error handling and debugging support

## FastAPI Server Pipeline

The `main.py` module provides the REST API server that orchestrates all screening components and serves the frontend application.

### Pipeline Overview

```
HTTP Request Input
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Request Processing Phase                 │
├─────────────────────────────────────────────────────────────┤
│ 1. Parameter Validation & Parsing                           │
│ 2. Optional Component Selection                             │
│ 3. Async Pipeline Orchestration                             │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Component Execution Phase                │
├─────────────────────────────────────────────────────────────┤
│ 1. Executive Information (exec_scraper)                     │
│ 2. Email Construction (email_scraper)                       │
│ 3. Industry Classification (get_industry)                   │
│ 4. 10-Q Link Retrieval (promptand10q)                       │
│ 5. Debt Analysis (promptand10q)                             │
└─────────────────────────────────────────────────────────────┘
       ↓
┌─────────────────────────────────────────────────────────────┐
│                    Response Assembly Phase                  │
├─────────────────────────────────────────────────────────────┤
│ 1. Error Handling & Fallbacks                               │
│ 2. Data Formatting & Validation                             │
│ 3. Structured JSON Response                                 │
└─────────────────────────────────────────────────────────────┘
       ↓
Structured Company Screening Response
```

### Key Endpoints & Data Flow

#### 1. Main Screening Endpoint

**`/company_info/{company_name}/{ticker}`**
- **Method**: GET
- **Parameters**: 
  - `company_name`: Company name for search
  - `ticker`: Stock ticker for SEC filings
  - `include_executives`: Boolean flag (default: true)
  - `include_emails`: Boolean flag (default: true)
  - `include_industry`: Boolean flag (default: true)
  - `include_industry_blurb`: Boolean flag (default: true)
  - `include_10q_link`: Boolean flag (default: true)
  - `include_debt_liquidity`: Boolean flag (default: true)

**Response Structure**
```json
{
  "executives": {
    "cfo": "Name",
    "treasurer": "Name", 
    "ceo": "Name"
  },
  "emails": {
    "domain": "@company.com",
    "format": "first.last",
    "cfo_email": "cfo@company.com",
    "treasurer_email": "treasurer@company.com"
  },
  "industry": "Industry Classification",
  "industry_blurb": "3-sentence description",
  "latest_10q_link": "SEC filing URL",
  "debt_liquidity_summary": ["Analysis results"],
  "debt_analysis_prompt": "Manual GPT prompt",
  "facility_list": "Extracted facilities"
}
```

#### 2. File Download Endpoint

**`/download_10q/{ticker}`**
- **Method**: GET
- **Parameters**:
  - `ticker`: Stock ticker for SEC filing
  - `company_name`: Optional company name for filename
- **Response**: HTML file download with proper headers

#### 3. Data Processing Functions

**`parse_execs(exec_str)`**
- Parses executive information from LLM output
- Extracts CFO, Treasurer, and CEO names
- Handles various output formats and edge cases
- Returns structured executive data

**Error Handling Strategy**
- Individual component error isolation
- Graceful degradation for partial failures
- Detailed error messages for debugging
- Fallback strategies for critical components

### Technical Details

#### Environment Variables
- All component-specific environment variables
- CORS configuration for frontend integration
- User agent configuration for SEC compliance

#### Dependencies
- **FastAPI**: Modern web framework for API development
- **CORSMiddleware**: Cross-origin resource sharing
- **asyncio**: Asynchronous execution support
- **All screening components**: Modular integration

#### CORS Configuration
- **allow_origins**: ["*"] for development flexibility
- **allow_credentials**: True for authentication support
- **allow_methods**: ["*"] for full HTTP method support
- **allow_headers**: ["*"] for custom header support

#### Error Handling
- Component-level error isolation
- Structured error responses
- Debug logging for troubleshooting
- Graceful degradation strategies

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
- **Default**: "gpt-3.5-turbo"
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
