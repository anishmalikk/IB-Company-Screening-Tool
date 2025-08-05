#!/usr/bin/env python3
"""
Email System Test
================
Simple test to verify the email system works for Celanese and Nordson.
"""

import json
from dotenv import load_dotenv
from email_scraper import scrape_emails

# Load environment variables
load_dotenv()

def test_email_system():
    """Test the email system with Celanese and Nordson"""
    
    companies = [
        {
            "name": "Celanese Corporation",
            "ceo": "Scott Richardson", 
            "cfo": "Chuck Kyrish",
            "treasurer": "same"
        },
        {
            "name": "Nordson Corporation", 
            "ceo": "Sundaram Nagarajan",
            "cfo": "Daniel Hopgood",
            "treasurer": "same"
        }
    ]
    
    print("🧪 EMAIL SYSTEM TEST")
    print("=" * 50)
    
    for company in companies:
        print(f"\n🏢 Testing: {company['name']}")
        print("-" * 30)
        
        try:
            result = scrape_emails(
                company_name=company['name'],
                cfo_name=company['cfo'],
                treasurer_name=company['treasurer'],
                ceo_name=company['ceo']
            )
            
            # Display key results
            if "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Domain: {result.get('domain', 'Not found')}")
                print(f"✅ Format: {result.get('format', 'Not detected')}")
                print(f"✅ CFO Email: {result.get('cfo_email', 'Not constructed')}")
                print(f"✅ Source Email: {result.get('source_email', 'Not found')}")
                print(f"✅ Website Source: {result.get('website_source', 'Unknown')}")
                print(f"✅ Source Quality: {result.get('source_quality', 'Unknown')}")
                
                # Add debugging info
                if 'debug_emails' in result:
                    print(f"\n🔍 DEBUG - All emails found:")
                    for email_info in result['debug_emails']:
                        print(f"  📧 {email_info['email']} (Quality: {email_info['quality']}, Source: {email_info['source']})")
            
            # Full JSON for reference
            print(f"\n📋 Full Result:")
            print(json.dumps(result, indent=2))
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*50)

if __name__ == "__main__":
    test_email_system()
    print("\n🎯 Test Complete!")
    print("Check that:")
    print("  ✅ Real emails are found (not fake ones)")
    print("  ✅ Website sources show actual domains")
    print("  ✅ Email formats are detected correctly") 