import re
import logging
import azure.functions as func
import azure.durable_functions as df

myApp = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ==========================================
# 1. BLOB TRIGGER
# ==========================================
@myApp.blob_trigger(
    arg_name="myblob",
    path="pdfs/{name}",
    connection="PdfStorageConnection"
)
@myApp.durable_client_input(client_name="client")
async def blob_trigger(myblob: func.InputStream, client):
    blob_name = myblob.name
    blob_bytes = myblob.read()

    input_data = {
        "blob_name": blob_name,
        "blob_bytes": list(blob_bytes),
        "blob_size_kb": round(len(blob_bytes) / 1024, 2)
    }

    instance_id = await client.start_new(
        "pdf_analyzer_orchestrator",
        client_input=input_data
    )

    logging.info(f"Started orchestration {instance_id} for {blob_name}")
    

# ==========================================
# 2. ORCHESTRATOR
# ==========================================
@myApp.orchestration_trigger(context_name="context")
def pdf_analyzer_orchestrator(context):
    input_data = context.get_input()

    tasks = [
        context.call_activity("extract_text", input_data),
        context.call_activity("extract_metadata", input_data),
        context.call_activity("analyze_statistics", input_data),
        context.call_activity("detect_sensitive_data", input_data)
    ]

    results = yield context.task_all(tasks)

    report_input = {
        "blob_name": input_data["blob_name"],
        "blob_size_kb": input_data["blob_size_kb"],
        "text": results[0],
        "metadata": results[1],
        "statistics": results[2],
        "sensitive_data": results[3]
    }

    report = yield context.call_activity("generate_report", report_input)
    stored = yield context.call_activity("store_results", report)

    return stored

@myApp.activity_trigger(input_name="input_data")
def extract_text(input_data):
    import io
    import pypdf
    import logging
    
    logging.info("Activity 'extract_text' started processing PDF...")
    try:
        pdf_bytes = bytes(input_data["blob_bytes"])
        pdf_file = io.BytesIO(pdf_bytes)
        
        reader = pypdf.PdfReader(pdf_file)
        page_count = len(reader.pages)
        
        extracted_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        
        logging.info(f"Successfully extracted {len(extracted_text)} characters from {page_count} pages.")
        
        return {
            "raw_text": extracted_text,
            "page_count": page_count
        }
        
    except Exception as e:
        logging.error(f"Error in extract_text activity: {str(e)}")
        return {
            "raw_text": "",
            "page_count": 0,
            "error": str(e)
        }

#Extract Metadata
@myApp.activity_trigger(input_name="input_data")
def extract_metadata(input_data):
    import io
    import pypdf
    import logging
    
    logging.info("Activity 'extract_metadata' started processing PDF...")
    try:
        pdf_bytes = bytes(input_data["blob_bytes"])
        pdf_file = io.BytesIO(pdf_bytes)
        
        reader = pypdf.PdfReader(pdf_file)
        meta = reader.metadata
        
        pdf_metadata = {
            "title": meta.title if meta and meta.title else "Unknown",
            "author": meta.author if meta and meta.author else "Unknown",
            "subject": meta.subject if meta and meta.subject else "Unknown",
            "creator": meta.creator if meta and meta.creator else "Unknown",
            "producer": meta.producer if meta and meta.producer else "Unknown",
            "creation_date": str(meta.creation_date) if meta and meta.creation_date else "Unknown"
        }
        
        logging.info(f"Successfully extracted metadata: Title={pdf_metadata['title']}")
        return pdf_metadata
        
    except Exception as e:
        logging.error(f"Error in extract_metadata activity: {str(e)}")
        return {
            "title": "Unknown",
            "author": "Unknown",
            "error": str(e)
        }


@myApp.activity_trigger(input_name="input_data")
def analyze_statistics(input_data: dict):
    logging.info("Role 3: Running text statistics analysis activity...")
    try:
        raw_text = ""
        page_count = 1

        # Fallback handling to extract text from dictionary or sequence structures
        if isinstance(input_data, dict):
            raw_text = input_data.get("text", input_data.get("raw_text", input_data.get("extracted_text", "")))
            page_count = input_data.get("page_count", 1)
        elif isinstance(input_data, (list, tuple)):
            for item in input_data:
                if isinstance(item, dict):
                    if "text" in item or "raw_text" in item or "extracted_text" in item:
                        raw_text = item.get("text", item.get("raw_text", item.get("extracted_text", "")))
                    if "page_count" in item or "pageCount" in item:
                        page_count = item.get("page_count", item.get("pageCount", 1))

        words = raw_text.split()
        word_count = len(words)
        
        pages = page_count if page_count > 0 else 1
        avg_words_per_page = round(word_count / pages, 2)
        estimated_reading_time_mins = round(word_count / 200, 2)
        
        return {
            "pageCount": pages,
            "wordCount": word_count,
            "avgWordsPerPage": avg_words_per_page,
            "estimatedReadingTimeMinutes": estimated_reading_time_mins
        }
    except Exception as e:
        logging.error(f"Role 3 Statistics analysis failed: {str(e)}")
        return {"error": str(e)}


@myApp.activity_trigger(input_name="input_data")
def detect_sensitive_data(input_data: dict):
    logging.info("Role 3: Scanning text for sensitive PII data...")
    try:
        raw_text = ""
        page_count = 1

        # Fallback handling to extract text from dictionary or sequence structures
        if isinstance(input_data, dict):
            raw_text = input_data.get("text", input_data.get("raw_text", input_data.get("extracted_text", "")))
            page_count = input_data.get("page_count", 1)
        elif isinstance(input_data, (list, tuple)):
            for item in input_data:
                if isinstance(item, dict):
                    if "text" in item or "raw_text" in item or "extracted_text" in item:
                        raw_text = item.get("text", item.get("raw_text", item.get("extracted_text", "")))
                    if "page_count" in item or "pageCount" in item:
                        page_count = item.get("page_count", item.get("pageCount", 1))
        
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
    except Exception as e:
        logging.error(f"Role 3 Sensitive data scan failed: {str(e)}")
        return {"error": str(e)}


@myApp.activity_trigger(input_name="input_data")
def generate_report(input_data):
    return input_data


@myApp.activity_trigger(input_name="input_data")
def store_results(input_data):
    return {
        "status": "success"
    }