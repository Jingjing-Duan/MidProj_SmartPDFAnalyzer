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

#Activity placeholders
@myApp.activity_trigger(input_name="input_data")
def extract_text(input_data):
    return "placeholder"


@myApp.activity_trigger(input_name="input_data")
def extract_metadata(input_data):
    return {}


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
