# LOKVAANI AI — Product Requirements Document

## 1. Product Overview

**LOKVAANI AI** is an AI-powered indigenous knowledge preservation and discovery platform, initially focused on Uttarakhand.

The platform helps communities, knowledge holders, students, researchers, NGOs, and government organizations document, discover, understand, verify, and preserve traditional knowledge that may otherwise disappear.

LOKVAANI AI uses AI to reduce the manual effort required for documentation while keeping communities in control of their knowledge, ownership, access, and publication.

**Tagline:**
Preserve the Past. Understand It. Build the Future.

---

## 2. Problem Statement

India has a large amount of indigenous and traditional knowledge related to:

* Traditional agriculture
* Local food and preservation
* Medicinal and plant knowledge
* Handicrafts
* Traditional architecture
* Water management
* Folk culture
* Traditional tools
* Oral histories
* Local festivals and practices
* Traditional skills

Much of this knowledge exists primarily through oral transmission and individual knowledge holders.

As practitioners age and younger generations move away from traditional practices, valuable knowledge can disappear without being documented.

Existing digital platforms generally focus on storing cultural content rather than creating an intelligent system that can:

* Automatically document knowledge
* Understand regional languages
* Connect related knowledge
* Identify knowledge at risk of disappearing
* Enable intelligent discovery
* Connect traditional knowledge with scientific research
* Respect community ownership and access restrictions

LOKVAANI AI aims to solve this problem.

---

## 3. Product Goal

Build an AI-powered platform that can:

1. Digitally preserve indigenous knowledge.
2. Automatically process audio, video, images, and documents.
3. Support regional Indian languages.
4. Make traditional knowledge searchable using natural language.
5. Identify knowledge that is at risk of disappearing.
6. Connect traditional knowledge with relevant scientific information.
7. Give communities control over access and ownership.
8. Provide visibility to knowledge holders and traditional products.
9. Encourage younger generations to learn traditional knowledge.

---

# 4. Initial Geographic Scope

The first version will focus on **Uttarakhand**.

The platform will organize knowledge using the state's 13 districts:

* Almora
* Bageshwar
* Chamoli
* Champawat
* Dehradun
* Haridwar
* Nainital
* Pauri Garhwal
* Pithoragarh
* Rudraprayag
* Tehri Garhwal
* Udham Singh Nagar
* Uttarkashi

The architecture should allow additional Indian states to be added later.

---

# 5. Target Users

## 5.1 Knowledge Holders

People who possess traditional skills or knowledge.

Examples:

* Farmers
* Artisans
* Craftspeople
* Traditional practitioners
* Elder community members
* Food producers
* Local experts

They can document and share their knowledge while controlling access.

---

## 5.2 Communities

Communities can:

* Contribute knowledge
* Verify information
* Control access
* Protect sensitive knowledge
* Decide whether information can be publicly displayed

---

## 5.3 Students

Students can:

* Explore local culture
* Learn traditional practices
* Discover knowledge holders
* Ask AI questions
* Follow personalized learning paths

---

## 5.4 Researchers

Researchers can:

* Search structured knowledge
* Find related practices
* Study regional traditions
* Compare traditional and scientific knowledge
* Request access to restricted knowledge

---

## 5.5 NGOs and Organizations

Organizations can:

* Identify endangered knowledge
* Find communities
* Support preservation programs
* Discover local practitioners
* Monitor preservation activities

---

## 5.6 Government Organizations

Government organizations can use LOKVAANI AI to:

* Identify disappearing cultural practices
* Prioritize preservation programs
* Discover regional knowledge
* Support artisans and communities
* Analyze preservation trends

---

# 6. Core Product Features

## 6.1 Uttarakhand Knowledge Explorer

Users can browse:

```text
Uttarakhand
    ↓
District
    ↓
Region / Community
    ↓
Knowledge Category
    ↓
Tradition / Practice
    ↓
Knowledge Holder
    ↓
Documentation
```

Example:

```text
Tehri Garhwal
    ↓
Traditional Agriculture
    ↓
Traditional Seed Preservation
    ↓
Knowledge Holder
    ↓
Video + Transcript + Documentation
```

---

# 7. Knowledge Categories

The platform should initially support:

* Traditional Agriculture
* Food Heritage
* Plant Knowledge
* Traditional Crafts
* Handicrafts
* Folk Culture
* Traditional Architecture
* Water Management
* Environmental Practices
* Traditional Tools
* Oral Histories
* Festivals and Traditions
* Local Products
* Vanishing Skills

The category system should be extensible.

---

# 8. AI Knowledge Capture

Knowledge holders should be able to upload:

* Video
* Audio
* Images
* PDF
* Text documents

The AI pipeline automatically processes the content.

```text
Video / Audio / Image / Document
                ↓
           AI Processing
                ↓
      ┌─────────┼─────────┐
      ↓         ↓         ↓
 Speech      OCR       Vision
      ↓
 Translation
      ↓
 Knowledge Extraction
      ↓
 Metadata Generation
      ↓
 Community Verification
      ↓
 Access Control
      ↓
 ROOTS Knowledge Base
```

The goal is to minimize manual data entry.

---

# 9. AI Models

## 9.1 Speech-to-Text

**Model:** Whisper

Purpose:

* Convert uploaded audio/video into text.
* Support multilingual recordings.
* Create searchable transcripts.

Example:

```text
Traditional Knowledge Video
          ↓
        Whisper
          ↓
       Transcript
```

---

## 9.2 Indian Language Translation

**Model:** AI4Bharat IndicTrans2

Purpose:

* Translate Indian languages.
* Support Hindi and English.
* Preserve the original language alongside translations.

Example:

```text
Garhwali
    ↓
IndicTrans2
    ↓
Hindi
    ↓
English
```

The original recording and transcript should always be preserved where permitted.

---

## 9.3 Knowledge Extraction

**Model:** Llama 3.1 / Mistral

The LLM extracts structured information from transcripts.

Example:

```text
Input:
Traditional farming interview

Output:

Practice:
Traditional Mountain Farming

District:
Tehri Garhwal

Category:
Agriculture

Materials:
...

Process:
...

Cultural Importance:
...

Environmental Benefits:
...

Keywords:
...
```

The extracted information must be reviewed before being treated as verified knowledge.

---

## 9.4 Semantic Search

**Embedding Model:** BGE-M3

Purpose:

Convert knowledge documents and user queries into vector representations.

Example:

```text
"What traditional farming methods
are used in Tehri?"

        ↓

      BGE-M3

        ↓

Vector Search

        ↓

Relevant Knowledge
```

---

## 9.5 Vector Database

**Initial option:** FAISS

Purpose:

* Store embeddings.
* Find semantically similar knowledge.
* Enable intelligent search.

For large-scale deployment, Qdrant or another dedicated vector database can be introduced.

---

## 9.6 RAG Question Answering

**Technology:** LangChain + LLM + BGE-M3 + FAISS

Users can ask:

> What traditional water conservation methods are found in Tehri?

ROOTS AI will:

```text
Question
   ↓
Embedding
   ↓
Vector Search
   ↓
ROOTS Knowledge
   ↓
LLM
   ↓
Answer + Sources
```

The system should answer from the ROOTS knowledge base rather than relying solely on the general knowledge of the LLM.

---

## 9.7 OCR

**Model:** PaddleOCR

Purpose:

Extract information from:

* Old documents
* Scanned pages
* Historical records
* Images containing text
* Traditional manuscripts where appropriate

---

## 9.8 Computer Vision

**Model:** YOLO or suitable vision model

Possible uses:

* Identify traditional tools
* Identify craft objects
* Identify agricultural equipment
* Classify uploaded images
* Generate image metadata

Vision predictions should be treated as AI-generated suggestions until verified.

---

# 10. Knowledge Preservation Risk Detector

One of the major AI features of ROOTS AI is the **Knowledge Preservation Risk Score**.

The system estimates whether a traditional practice is at risk of disappearing.

Potential factors:

* Number of known practitioners
* Practitioner age distribution
* Number of younger practitioners
* Documentation availability
* Frequency of practice
* Geographic concentration
* Transmission to younger generations
* Recent contribution activity

Example:

```text
Traditional Wool Weaving

Practitioners: 8
Young Practitioners: 1
Documentation: Low
Practice Frequency: Declining

Risk Score: 89 / 100

Status: HIGH RISK
```

The score is an indicator, not an absolute scientific measurement.

Organizations can use it to prioritize preservation efforts.

---

# 11. Community Ownership and Access

ROOTS AI must not assume that every traditional practice should be publicly available.

Each knowledge record should contain:

* Knowledge ID
* Contributor
* Community
* Region
* Ownership information
* Access level
* Verification status
* Attribution requirements
* Commercial-use permission
* Publication status

Example Knowledge ID:

```text
UK-TEHRI-AGRI-00421
```

---

## 11.1 Access Levels

The system should support:

### Public

Anyone can view the information.

### Registered Users

Only authenticated users can access it.

### Community Only

Only authorized community members can access it.

### Research Access

Researchers can request access.

### Restricted

The content is stored but not publicly accessible.

---

# 12. Verification System

Knowledge should have verification levels.

```text
Level 1 → AI Extracted
Level 2 → Community Verified
Level 3 → Expert Verified
Level 4 → Research Supported
```

AI-generated information must not automatically become verified information.

Sensitive knowledge should require human/community approval before publication.

---

# 13. Traditional Knowledge + Scientific Knowledge

ROOTS AI should allow traditional knowledge to be connected with relevant scientific research.

Example:

```text
Traditional Water Management
            ↓
      ROOTS Knowledge
            ↓
      Related Concepts
            ↓
Hydrology
Watershed Management
Soil Conservation
Environmental Science
```

The platform must clearly distinguish:

```text
Traditional Knowledge
        ≠
Scientific Evidence
```

A traditional claim should not automatically be presented as scientifically proven.

---

# 14. Plant Knowledge

Plant-related knowledge can contain:

* Local name
* Scientific name
* Region
* Traditional use
* Preparation/practice
* Community source
* Historical context
* Related research
* Evidence level

The platform should not provide unsupported medical diagnoses or treatment recommendations.

---

# 15. Knowledge Holder Profiles

With consent, knowledge holders can have profiles containing:

* Name
* Region
* Skills
* Biography/story
* Knowledge contributions
* Videos
* Images
* Products
* Workshops
* Contact or official channel

Sensitive personal information should not be exposed without permission.

---

# 16. Traditional Product Discovery

ROOTS AI can provide visibility for disappearing traditional products.

Examples:

* Handicrafts
* Traditional textiles
* Handmade tools
* Local food products
* Traditional art

Each product can contain:

```text
Product
    ↓
Story
    ↓
Cultural Significance
    ↓
Knowledge Holder
    ↓
Region
    ↓
Manufacturing Process
    ↓
Availability
```

The initial MVP should focus on discovery and visibility rather than building a complete e-commerce system.

---

# 17. Learn Your Roots

ROOTS AI can create personalized learning paths.

Example:

User:

> I want to learn traditional farming in Uttarakhand.

AI generates:

```text
1. History
2. Traditional Seeds
3. Farming Methods
4. Traditional Tools
5. Irrigation
6. Environmental Practices
7. Local Knowledge Holders
8. Scientific Comparison
9. Videos
10. Further Reading
```

This feature is designed to make indigenous knowledge more accessible to younger generations.

---

# 18. Main User Journey

## Knowledge Holder

```text
Login
 ↓
Upload Video
 ↓
AI Transcription
 ↓
AI Translation
 ↓
AI Knowledge Extraction
 ↓
AI Metadata Generation
 ↓
Community Review
 ↓
Set Access Level
 ↓
Publish
```

---

## Student

```text
Open ROOTS AI
 ↓
Select Uttarakhand
 ↓
Select District
 ↓
Explore Knowledge
 ↓
Ask ROOTS AI
 ↓
Read / Watch
 ↓
Learn
```

---

## Researcher

```text
Search Knowledge
 ↓
Find Relevant Records
 ↓
Read Available Information
 ↓
Request Restricted Access
 ↓
Research
```

---

# 19. Technical Architecture

```text
                         ROOTS AI
                            |
             ┌──────────────┴──────────────┐
             |                             |
          FRONTEND                      BACKEND
             |                             |
      HTML + CSS + JS                    Flask
             |                             |
             └──────────────┬──────────────┘
                            |
                       PostgreSQL
                            |
                ┌───────────┴───────────┐
                |                       |
           AI PIPELINE              VECTOR SEARCH
                |                       |
       ┌────────┼────────┐             FAISS
       |        |        |
    Whisper  IndicTrans2  LLM
       |        |        |
       └────────┼────────┘
                |
        Knowledge Extraction
                |
          Metadata Generation
                |
          Knowledge Database
                |
        Community Verification
                |
          Access Control
```

---

# 20. Technology Stack

## Frontend

* HTML5
* CSS3
* JavaScript
* Bootstrap

The frontend should remain lightweight and responsive.

---

## Backend

* Python
* Flask
* Flask RESTful APIs
* Flask-Login

Flask will handle:

* Routing
* Authentication
* API endpoints
* File uploads
* Database operations
* AI pipeline integration
* Access control

---

## Database

### MVP

SQLite can be used during initial development.

### Production

PostgreSQL should be used for:

* Users
* Communities
* Districts
* Knowledge records
* Knowledge holders
* Permissions
* Verification
* Products
* Research requests

---

## AI/ML

* Whisper — Speech-to-text
* IndicTrans2 — Indian language translation
* Llama 3.1 / Mistral — Knowledge extraction and RAG responses
* BGE-M3 — Embeddings
* FAISS — Vector search
* PaddleOCR — OCR
* YOLO / Vision model — Image analysis
* LangChain — RAG orchestration

---

## Storage

* Local storage during development
* AWS S3 / Cloudinary for production media storage

---

## Development Tools

* Git
* GitHub
* VS Code
* Python virtual environment
* Postman

---

# 21. Flask Application Structure

```text
roots-ai/
│
├── app.py
├── config.py
├── requirements.txt
│
├── models/
│   ├── user.py
│   ├── knowledge.py
│   ├── community.py
│   └── product.py
│
├── routes/
│   ├── auth.py
│   ├── dashboard.py
│   ├── knowledge.py
│   ├── upload.py
│   └── search.py
│
├── ai/
│   ├── speech.py
│   ├── translation.py
│   ├── extraction.py
│   ├── embeddings.py
│   ├── rag.py
│   ├── risk_detector.py
│   ├── ocr.py
│   └── vision.py
│
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── dashboard.html
│   ├── districts.html
│   ├── district.html
│   ├── knowledge.html
│   ├── knowledge_detail.html
│   ├── upload.html
│   ├── search.html
│   └── profile.html
│
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── app.js
│   └── images/
│
├── uploads/
│
└── database/
```

---

# 22. AI Processing Pipeline

```text
                UPLOAD
                  |
                  ↓
          Video / Audio / Image
                  |
                  ↓
             AI Processing
                  |
       ┌──────────┼──────────┐
       ↓          ↓          ↓
    Whisper      OCR       Vision
       |
       ↓
   Transcript
       |
       ↓
 IndicTrans2
       |
       ↓
 Translation
       |
       ↓
   Llama / Mistral
       |
       ↓
Knowledge Extraction
       |
       ↓
 Metadata Generation
       |
       ↓
     BGE-M3
       |
       ↓
     FAISS
       |
       ↓
 Knowledge Database
       |
       ↓
Community Verification
       |
       ↓
 Access Control
       |
       ↓
     ROOTS AI
```

---

# 23. MVP Scope

The first working version should contain:

1. ROOTS AI homepage
2. Uttarakhand district explorer
3. District-wise knowledge categories
4. User authentication
5. Knowledge-holder profiles
6. Video/audio upload
7. Whisper transcription
8. IndicTrans2 translation
9. LLM knowledge extraction
10. Knowledge record generation
11. PostgreSQL/SQLite database
12. AI semantic search
13. RAG-based "Ask ROOTS AI"
14. Access-control system
15. Community verification
16. Basic knowledge-risk score
17. Traditional/scientific knowledge linking
18. Basic product discovery

---

# 24. Future Features

Future versions can include:

* Advanced knowledge graph
* Mobile application
* Offline knowledge collection
* Community reward system
* Research portal
* Government dashboard
* NGO collaboration portal
* Workshops and learning programs
* Traditional product marketplace
* Advanced provenance system
* Blockchain-based provenance if technically justified
* Expansion from Uttarakhand to other Indian states

---

# 25. Privacy and Ethics

ROOTS AI must follow these principles:

### Community Consent

Knowledge should not be published without appropriate consent.

### Ownership

Communities should retain control over how their knowledge is shared.

### Attribution

Knowledge contributors should receive appropriate attribution.

### Access Control

Sensitive information should support restricted access.

### Human Verification

AI-generated information should be reviewed before being considered verified.

### Cultural Sensitivity

The system must respect culturally sensitive knowledge.

### Scientific Accuracy

Traditional claims must not automatically be represented as scientifically proven.

### Medical Safety

Plant and traditional health knowledge should be presented for educational/documentation purposes and should not become unsupported medical advice.

---

# 26. Success Metrics

The platform can measure:

* Number of documented traditions
* Number of knowledge holders
* Number of participating communities
* Number of districts covered
* Number of AI-processed recordings
* Number of verified knowledge records
* Number of endangered practices identified
* Search success rate
* Number of students using learning content
* Number of researchers using the platform
* Number of traditional products receiving visibility

---

# 27. Unique Selling Proposition

ROOTS AI is not simply a digital archive.

It combines:

```text
Indigenous Knowledge
        +
Artificial Intelligence
        +
Community Ownership
        +
Semantic Search
        +
Scientific Research
        +
Preservation Risk Detection
        +
Knowledge Discovery
        +
Economic Visibility
```

The platform moves from:

**Documentation → Discovery → Understanding → Research → Learning → Preservation → Revival**

---

# 28. Core Product Principle

ROOTS AI should follow one fundamental principle:

> AI handles repetitive documentation and discovery work; communities retain cultural authority and control over their knowledge.

The objective is not to replace traditional knowledge holders with AI.

The objective is to ensure that their knowledge can survive, remain discoverable, and reach future generations.

---

# 29. Long-Term Vision

ROOTS AI starts with Uttarakhand but is designed to become a national indigenous knowledge infrastructure.

```text
Uttarakhand
     ↓
Northern India
     ↓
All Indian States
     ↓
National Indigenous Knowledge Network
```

The long-term vision is to build a platform where India's traditional knowledge can be:

* Preserved
* Protected
* Discovered
* Studied
* Learned
* Verified
* Respected
* Revived


