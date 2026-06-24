import logging
import azure.functions as func
import azure.durable_functions as df

myApp = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

#Blob Trigger
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

    logging.info(
        f"Started orchestration {instance_id} for {blob_name}"
    )
    
#Orchestrator
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

    report = yield context.call_activity(
        "generate_report",
        report_input
    )

    stored = yield context.call_activity(
        "store_results",
        report
    )

    return stored

#Extract Text
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
def analyze_statistics(input_data):
    return {}


@myApp.activity_trigger(input_name="input_data")
def detect_sensitive_data(input_data):
    return {}


@myApp.activity_trigger(input_name="input_data")
def generate_report(input_data):
    return input_data


@myApp.activity_trigger(input_name="input_data")
def store_results(input_data):
    return {
        "status": "success"
    }
