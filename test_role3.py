import re

def local_test_analyze_statistics(raw_text: str, page_count: int):
    print("--- Starting Analytics Scan ---")
    
    # 1. Calculate stats
    words = raw_text.split()
    word_count = len(words)
    
    # Fallback to 1 page if 0 is passed to prevent division by zero errors
    pages = page_count if page_count > 0 else 1
    avg_words_per_page = round(word_count / pages, 2)
    
    # Reading time calculation (Word count / 200 words per minute)
    estimated_reading_time_mins = round(word_count / 200, 2)
    
    return {
        "pageCount": page_count,
        "wordCount": word_count,
        "avgWordsPerPage": avg_words_per_page,
        "estimatedReadingTimeMinutes": estimated_reading_time_mins
    }

def local_test_sensitive_data(raw_text: str):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'
    url_pattern = r'https?://[^\s]+'
    date_pattern = r'\b\d{4}[-/]\d{2}[-/]\d{2}\b|\b\d{2}[-/]\d{2}[-/]\d{4}\b'
    
    emails = list(set(re.findall(email_pattern, raw_text)))
    phones = list(set(re.findall(phone_pattern, raw_text)))
    urls = list(set(re.findall(url_pattern, raw_text)))
    dates = list(set(re.findall(date_pattern, raw_text)))
    
    return {
        "containsSensitiveData": bool(emails or phones or urls),
        "foundEmails": emails,
        "foundPhoneNumbers": phones,
        "foundUrls": urls,
        "foundDates": dates
    }

# ==========================================
# TEST CASE: Mocking a 2-page PDF text extraction
# ==========================================
mock_pdf_text = """
Invoice Number: INV-2026-99
Date of Issue: 2026-06-24
Prepared by: john.doe@company.com or assistance@support.org
If you have questions, call our helpline at 613-555-0123 or 6135559876.
Please review our terms at https://portal.company.com/terms and pay before 07/15/2026.
"""
mock_page_count = 2

# Run both components
stats_results = local_test_analyze_statistics(mock_pdf_text, mock_page_count)
security_results = local_test_sensitive_data(mock_pdf_text)

print("Statistics Results:")
print(stats_results)
print("\nSecurity Results:")
print(security_results)