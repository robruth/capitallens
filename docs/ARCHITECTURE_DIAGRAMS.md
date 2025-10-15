# FastAPI Migration - Architecture Diagrams

This document provides visual representations of the new architecture using Mermaid diagrams.

---

## System Overview

```mermaid
graph TB
    subgraph "Client Layer"
        CLI[CLI Tool]
        Browser[Web Browser]
        API_Client[External API Client]
    end
    
    subgraph "API Layer"
        FastAPI[FastAPI Application]
        WS[WebSocket Handler]
        Router_Import[Import Router]
        Router_Models[Models Router]
        Router_Validation[Validation Router]
    end
    
    subgraph "Task Queue Layer"
        Redis[(Redis)]
        Celery_Worker[Celery Worker]
    end
    
    subgraph "Service Layer"
        ExcelService[Excel Import Service]
        ValidationService[Validation Service]
        FormulaService[Formula Service]
    end
    
    subgraph "Storage Layer"
        PostgreSQL[(PostgreSQL)]
        FileSystem[File System - models/]
    end
    
    CLI -->|HTTP/WS| FastAPI
    Browser -->|HTTP/WS| FastAPI
    API_Client -->|HTTP| FastAPI
    
    FastAPI --> Router_Import
    FastAPI --> Router_Models
    FastAPI --> Router_Validation
    FastAPI --> WS
    
    Router_Import -->|Enqueue Job| Redis
    Router_Validation -->|Enqueue Job| Redis
    
    Redis -->|Consume Task| Celery_Worker
    
    Celery_Worker --> ExcelService
    Celery_Worker --> ValidationService
    
    ExcelService --> FormulaService
    ExcelService --> PostgreSQL
    ExcelService --> FileSystem
    
    ValidationService --> PostgreSQL
    
    WS -.->|Read Progress| Redis
    Router_Import --> PostgreSQL
    Router_Models --> PostgreSQL
```

---

## Import Workflow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Redis
    participant Worker as Celery Worker
    participant Service as Excel Import Service
    participant WS as WebSocket
    
    Client->>API: POST /api/import/upload (file)
    API->>DB: Create JobRun record
    API->>Redis: Enqueue import task
    API-->>Client: 202 Accepted (job_id)
    
    Client->>WS: Connect /ws/import/{job_id}
    WS-->>Client: Connection established
    
    Worker->>Redis: Consume task
    Worker->>DB: Update status: PROCESSING
    Worker->>Service: import_file(path, name)
    
    Service->>Redis: Progress: hashing (5%)
    Redis->>WS: Push update
    WS-->>Client: Progress update
    
    Service->>Service: Parse workbook
    Service->>Redis: Progress: parsing (30%)
    Redis->>WS: Push update
    WS-->>Client: Progress update
    
    Service->>Service: Build dependency graph
    Service->>Redis: Progress: dependencies (40%)
    Redis->>WS: Push update
    WS-->>Client: Progress update
    
    Service->>Service: Evaluate formulas
    Service->>Redis: Progress: evaluation (70%)
    Redis->>WS: Push update
    WS-->>Client: Progress update
    
    Service->>DB: Bulk insert cells
    Service->>Redis: Progress: insertion (90%)
    Redis->>WS: Push update
    WS-->>Client: Progress update
    
    Service-->>Worker: Return result
    Worker->>DB: Update status: SUCCESS
    Worker->>Redis: Progress: complete (100%)
    Redis->>WS: Push final status
    WS-->>Client: Job complete
    WS->>Client: Close connection
```

---

## Service Layer Architecture

```mermaid
graph LR
    subgraph "Framework-Agnostic Services"
        ExcelImportService[Excel Import Service]
        ValidationService[Validation Service]
        FormulaService[Formula Service]
        StorageService[Storage Service]
    end
    
    subgraph "Business Logic Components"
        FormulaParser[Formula Parser]
        CircularDetector[Circular Reference Detector]
        CircularSolver[Circular Solver]
        HyperFormulaEval[HyperFormula Evaluator]
    end
    
    subgraph "Data Access"
        SQLAlchemy[SQLAlchemy ORM]
        FileIO[File I/O]
    end
    
    ExcelImportService --> FormulaParser
    ExcelImportService --> CircularDetector
    ExcelImportService --> CircularSolver
    ExcelImportService --> HyperFormulaEval
    
    ValidationService --> FormulaService
    
    ExcelImportService --> SQLAlchemy
    ExcelImportService --> FileIO
    StorageService --> FileIO
    
    ValidationService --> SQLAlchemy
```

---

## Database Schema

```mermaid
erDiagram
    MODELS ||--o{ CELL : contains
    MODELS ||--o{ JOB_RUNS : has
    JOB_RUNS ||--o{ JOB_PROGRESS : tracks
    
    MODELS {
        int id PK
        string name
        string file_hash UK
        string file_path
        timestamp uploaded_at
        jsonb workbook_metadata
        jsonb import_summary
    }
    
    CELL {
        int model_id PK,FK
        string sheet_name PK
        int row_num PK
        string col_letter PK
        string cell_type
        numeric raw_value
        text raw_text
        text formula
        numeric calculated_value
        text calculated_text
        boolean is_circular
        boolean has_mismatch
    }
    
    JOB_RUNS {
        string job_id PK
        string job_type
        string status
        timestamp created_at
        timestamp started_at
        timestamp completed_at
        jsonb params
        jsonb result
        jsonb error
        int model_id FK
    }
    
    JOB_PROGRESS {
        int id PK
        string job_id FK
        string stage
        numeric percent
        text message
        timestamp timestamp
    }
```

---

## Celery Task Flow

```mermaid
stateDiagram-v2
    [*] --> Pending: Task enqueued
    Pending --> Processing: Worker picks up task
    
    Processing --> Hashing: Compute file hash
    Hashing --> Parsing: Load workbook
    Parsing --> Dependencies: Build graph
    Dependencies --> Evaluation: Evaluate formulas
    Evaluation --> Insertion: Insert to DB
    Insertion --> Complete: Success
    
    Processing --> Failed: Error occurred
    Hashing --> Failed: File error
    Parsing --> Failed: Parse error
    Dependencies --> Failed: Graph error
    Evaluation --> Failed: Eval error
    Insertion --> Failed: DB error
    
    Complete --> [*]
    Failed --> [*]
    
    note right of Processing
        Update progress in Redis
        Send WebSocket updates
    end note
```

---

## Progress Stages

```mermaid
gantt
    title Import Job Progress Stages
    dateFormat X
    axisFormat %s
    
    section File Processing
    Hashing           :0, 5
    Parsing           :5, 25
    
    section Analysis
    Dependencies      :25, 15
    
    section Evaluation
    Formula Eval      :40, 40
    
    section Database
    Insertion         :80, 15
    Validation        :95, 5
```

---

## API Request/Response Flow

```mermaid
graph TD
    A[Client Request] --> B{Endpoint Type}
    
    B -->|Upload| C[Import Router]
    B -->|Query| D[Models Router]
    B -->|Validate| E[Validation Router]
    
    C --> F[Validate Request]
    F --> G[Save Temp File]
    G --> H[Create Job Record]
    H --> I[Enqueue Celery Task]
    I --> J[Return Job ID]
    
    D --> K[Query Database]
    K --> L[Apply Filters]
    L --> M[Paginate Results]
    M --> N[Format Response]
    
    E --> O[Check Model Exists]
    O --> P[Create Validation Job]
    P --> Q[Enqueue Task]
    Q --> R[Return Job ID]
```

---

## Deployment Architecture

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Nginx/Traefik]
    end
    
    subgraph "API Services"
        API1[FastAPI Instance 1]
        API2[FastAPI Instance 2]
        API3[FastAPI Instance N]
    end
    
    subgraph "Worker Pool"
        W1[Celery Worker 1]
        W2[Celery Worker 2]
        W3[Celery Worker N]
    end
    
    subgraph "Data Layer"
        PG[(PostgreSQL Primary)]
        PG_Replica[(PostgreSQL Replica)]
        Redis_Cluster[(Redis Cluster)]
    end
    
    subgraph "Storage"
        NFS[Shared Storage - models/]
    end
    
    LB --> API1
    LB --> API2
    LB --> API3
    
    API1 --> Redis_Cluster
    API2 --> Redis_Cluster
    API3 --> Redis_Cluster
    
    Redis_Cluster --> W1
    Redis_Cluster --> W2
    Redis_Cluster --> W3
    
    API1 --> PG
    API2 --> PG
    API3 --> PG
    
    W1 --> PG
    W2 --> PG
    W3 --> PG
    
    W1 --> NFS
    W2 --> NFS
    W3 --> NFS
    
    PG -.->|Replication| PG_Replica
```

---

## Error Handling Flow

```mermaid
flowchart TD
    Start[Task Execution] --> Try{Try Block}
    
    Try -->|Success| UpdateSuccess[Update Job: SUCCESS]
    Try -->|Exception| Catch[Catch Exception]
    
    Catch --> LogError[Log Error Details]
    LogError --> UpdateFailed[Update Job: FAILED]
    UpdateFailed --> StoreError[Store Error in DB]
    
    StoreError --> CheckRetry{Retryable?}
    CheckRetry -->|Yes| Retry[Schedule Retry]
    CheckRetry -->|No| NotifyUser[Notify User]
    
    Retry --> End[End]
    NotifyUser --> End
    UpdateSuccess --> CleanupTemp[Cleanup Temp Files]
    CleanupTemp --> NotifySuccess[Notify Success]
    NotifySuccess --> End
```

---

## CLI Dual-Mode Operation

```mermaid
graph LR
    CLI[CLI Invocation] --> Check{--api-url provided?}
    
    Check -->|No| Direct[Direct Mode]
    Check -->|Yes| API_Mode[API Mode]
    
    Direct --> ImportService[Use Excel Import Service]
    ImportService --> DB[(PostgreSQL)]
    
    API_Mode --> Upload[HTTP Upload]
    Upload --> FastAPI[FastAPI Backend]
    FastAPI --> JobQueue[Celery Queue]
    JobQueue --> Worker[Celery Worker]
    Worker --> ImportService2[Excel Import Service]
    ImportService2 --> DB2[(PostgreSQL)]
    
    API_Mode --> WebSocket[WebSocket Connection]
    WebSocket --> ProgressUpdates[Real-time Progress]
```

---

**Version:** 1.0  
**Last Updated:** 2025-10-15