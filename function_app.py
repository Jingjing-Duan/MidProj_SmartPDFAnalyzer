import re
import logging
import azure.functions as func
import azure.durable_functions as df
from datetime import datetime, timezone
import json
import os
import uuid
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError

# CREATE THE DURABLE FUNCTION APP
myApp = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# TABLE STORAGE HELPER
TABLE_NAME = os.environ.get("PDF_REPORT_TABLE_NAME", "PdfAnalysisReports")

def get_table_client():
    """
    Get a TableClient for storing/retrieving PDF analysis reports.
    The table is created automatically if it does not already exist.
    """
    connection_string = os.environ.get(
        "PdfStorageConnection",
        os.environ["AzureWebJobsStorage"]
    )

    table_service_client = TableServiceClient.from_connection_string(
        conn_str=connection_string
    )

    table_client = table_service_client.create_table_if_not_exists(
        table_name=TABLE_NAME
    )

    return table_client

# Return a JSON HTTP response.
def json_response(data, status_code=200):
    return func.HttpResponse(
        json.dumps(data, indent=2),
        status_code=status_code,
        mimetype="application/json"
    )

# ==========================================
# 1. BLOB TRIGGER (Role 1)
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
# 2. ORCHESTRATOR (FIXED SEQUENTIAL FLOW)
# ==========================================
@myApp.orchestration_trigger(context_name="context")
def pdf_analyzer_orchestrator(context):
    input_data = context.get_input()

    # STEP 1: Extract the text from the PDF first
    extraction_tasks = [
        context.call_activity("extract_text", input_data),
        context.call_activity("extract_metadata", input_data)
    ]
    extraction_results = yield context.task_all(extraction_tasks)
    
    extracted_text_string = extraction_results[0]
    extracted_metadata_dict = extraction_results[1]

    # Create the package containing the text data for your analytics activities
    analysis_input = {
        "text": extracted_text_string,
        "page_count": extracted_metadata_dict.get("page_count", 1) if isinstance(extracted_metadata_dict, dict) else 1
    }

    # STEP 2: Run your analysis activities in parallel with the real text!
    analysis_tasks = [
        context.call_activity("analyze_statistics", analysis_input),
        context.call_activity("detect_sensitive_data", analysis_input)
    ]
    analysis_results = yield context.task_all(analysis_tasks)

    # STEP 3: Assemble the final combined JSON report
    report_input = {
        "blob_name": input_data["blob_name"],
        "blob_size_kb": input_data["blob_size_kb"],
        "text": extracted_text_string,
        "metadata": extracted_metadata_dict,
        "statistics": analysis_results[0],
        "sensitive_data": analysis_results[1]
    }

    report = yield context.call_activity("generate_report", report_input)
    stored = yield context.call_activity("store_results", report)

    return stored


# ==========================================
# 3. ACTIVITY FUNCTIONS (Role 2 & Role 3 & Role 4)
# ==========================================

# [REAL IMPLEMENTATION] ACTIVITY 1: Extract Text (Role 2)
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
        
        extracted_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        
        logging.info(f"Successfully extracted {len(extracted_text)} characters.")
        return extracted_text
        
    except Exception as e:
        logging.error(f"Error in extract_text activity: {str(e)}")
        return ""


# [REAL IMPLEMENTATION] ACTIVITY 2: Extract Metadata (Role 2)
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
            "creation_date": str(meta.creation_date) if meta and meta.creation_date else "Unknown",
            "page_count": len(reader.pages)
        }
        
        logging.info(f"Successfully extracted metadata and page count: {len(reader.pages)}")
        return pdf_metadata
        
    except Exception as e:
        logging.error(f"Error in extract_metadata activity: {str(e)}")
        return {
            "title": "Unknown",
            "author": "Unknown",
            "page_count": 1
        }


# [REAL IMPLEMENTATION] ACTIVITY 3: Analyze Statistics (Role 3)
@myApp.activity_trigger(input_name="input_data")
def analyze_statistics(input_data: dict):
    logging.info("Role 3: Running text statistics analysis activity...")
    try:
        raw_text = ""
        page_count = 1

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


# [REAL IMPLEMENTATION] ACTIVITY 4: Detect Sensitive Data (Role 3)
@myApp.activity_trigger(input_name="input_data")
def detect_sensitive_data(input_data: dict):
    logging.info("Role 3: Scanning text for sensitive PII data...")
    try:
        raw_text = ""
        page_count = 1

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


# [REAL IMPLEMENTATION] ACTIVITY 5: Generate Report (Role 4)
@myApp.activity_trigger(input_name="input_data")
def generate_report(input_data):
    logging.info("Generating final PDF analysis report.")

    blob_name = input_data.get("blob_name", "unknown.pdf")
    file_name = blob_name.split("/")[-1]

    report = {
        "report_id": str(uuid.uuid4()),
        "file_name": file_name,
        "blob_name": blob_name,
        "blob_size_kb": input_data.get("blob_size_kb", 0),
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "analysis_results": {
            "text": input_data.get("text", {}),
            "metadata": input_data.get("metadata", {}),
            "statistics": input_data.get("statistics", {}),
            "sensitive_data": input_data.get("sensitive_data", {})
        }
    }
    return report


# [REAL IMPLEMENTATION] ACTIVITY 6: Store Results (Role 4)
@myApp.activity_trigger(input_name="input_data")
def store_results(input_data):
    logging.info("Storing PDF analysis report in Azure Table Storage.")

    table_client = get_table_client()
    report_id = input_data.get("report_id")

    entity = {
        "PartitionKey": "PDF_REPORT",
        "RowKey": report_id,
        "report_id": report_id,
        "file_name": input_data.get("file_name", ""),
        "blob_name": input_data.get("blob_name", ""),
        "blob_size_kb": input_data.get("blob_size_kb", 0),
        "processed_at_utc": input_data.get("processed_at_utc", ""),
        "status": "completed",
        "report_json": json.dumps(input_data)
    }

    table_client.upsert_entity(entity=entity)
    logging.info("Report stored successfully with report ID: %s", report_id)

    return {
        "status": "stored",
        "report_id": report_id,
        "table_name": TABLE_NAME,
        "message": "Report stored successfully in Azure Table Storage."
    }


# ==========================================
# 4. HTTP GET ENDPOINT (Role 4)
# ==========================================
@myApp.route(route="reports/{report_id?}", methods=["GET"])
def get_report(req: func.HttpRequest) -> func.HttpResponse:
    report_id = req.route_params.get("report_id")

    try:
        table_client = get_table_client()

        if report_id:
            entity = table_client.get_entity(
                partition_key="PDF_REPORT",
                row_key=report_id
            )
            report = json.loads(entity["report_json"])
            return json_response({
                "mode": "single_report",
                "report_id": report_id,
                "report": report
            })

        limit_param = req.params.get("limit", "10")
        try:
            limit = int(limit_param)
        except ValueError:
            return json_response({
                "error": "Invalid limit value. Limit must be a number."
            }, status_code=400)

        if limit <= 0:
            return json_response({
                "error": "Limit must be greater than 0."
            }, status_code=400)

        entities = table_client.query_entities(
            query_filter="PartitionKey eq 'PDF_REPORT'"
        )

        reports = []
        for entity in entities:
            reports.append({
                "report_id": entity.get("RowKey"),
                "file_name": entity.get("file_name"),
                "blob_name": entity.get("blob_name"),
                "processed_at_utc": entity.get("processed_at_utc"),
                "status": entity.get("status")
            })

        reports.sort(
            key=lambda item: item.get("processed_at_utc") or "",
            reverse=True
        )

        limited_reports = reports[:limit]

        return json_response({
            "mode": "report_list",
            "count": len(limited_reports),
            "limit": limit,
            "reports": limited_reports
        })

    except ResourceNotFoundError:
        return json_response({
            "error": "Report not found",
            "report_id": report_id
        }, status_code=404)

    except Exception as error:
        logging.error("Error in get_report endpoint: %s", error)
        return json_response({
            "error": "Internal server error while retrieving report data.",
            "details": str(error)
        }, status_code=500)