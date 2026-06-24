# MidProj_SmartPDFAnalyzer

```mermaid
---
title: "Midterm Project: Smart PDF Analyzer Architectural Flow"
---
flowchart TD
    %% Define distinct styles for different roles
    classDef main fill:#546e7a,stroke:#263238,color:#fff
    classDef orch fill:#9b59b6,stroke:#7d3c98,color:#fff
    classDef extract fill:#3498db,stroke:#2980b9,color:#fff
    classDef analytics fill:#2ecc71,stroke:#27ae60,color:#fff,stroke-width:3px
    classDef closer fill:#e67e22,stroke:#d35400,color:#fff
    classDef data fill:#f1c40f,stroke:#f39c12,color:#333
    classDef user fill:#e74c3c,stroke:#c0392b,color:#fff

    %% Components
    Input([PDF File uploaded to pdfs container]):::data
    Trigger[blob_trigger<br/>Client Function]:::main
    Orchestrator[pdf_analyzer_orchestrator<br/>Orchestrator]:::orch

    %% Connection Input -> Orch
    Input --> Trigger
    Trigger -- startsNew --> Orchestrator

    %% Role 2 Extraction Activities
    Orchestrator -- call_activity --> ExtractText[extract_text<br/>Activity 1]:::extract
    Orchestrator -- call_activity --> ExtractMeta[extract_metadata<br/>Activity 2]:::extract

    %% Role 3 Analytics Activities (YOUR ROLE)
    Orchestrator -- call_activity --> AnalyzeStats[analyze_statistics<br/>Activity 3]:::analytics
    Orchestrator -- call_activity --> DetectSensitive[detect_sensitive_data<br/>Activity 4]:::analytics

    %% Re-convergence
    FanIn{{context.task_all<br/>Fan-In point<br/>Wait for ALL Results}}:::orch
    ExtractText & ExtractMeta & AnalyzeStats & DetectSensitive --> FanIn

    %% Role 4 Closing and Chaining
    GenReport[generate_report<br/>Sequential Chain]:::closer
    StoreReport[store_results<br/>Sequential Chain]:::closer
    FanIn --> GenReport
    GenReport --> StoreReport

    %% Data Output
    TableStorage[(PdfAnalysisResults<br/>Azure Table Storage)]:::data
    StoreReport --> TableStorage

    %% Retrieval Loop
    User((Browser/Client)):::user
    HttpApi[get_results<br/>HTTP GET Endpoint]:::closer

    User -- "id: ReportRowKey" --> HttpApi
    HttpApi -. "get_entity" .-> TableStorage
    TableStorage -. returns entity .-> HttpApi
    HttpApi -- "JSON Analysis Report" --> User
