
# CarbonLens
CarbonLens — Enterprise Carbon Footprint Tracker & AI Assistant (FH Dortmund Capstone)

## 📖 Project Description
CarbonLens is a full-stack Python web platform that helps companies track their greenhouse gas emissions. Companies can record their operational activity (like electricity usage, flights, or vehicle fuel), and the system automatically converts this data into exact CO2e emissions using international standards (the GHG Protocol). It then visualizes the data on a dashboard and uses an AI Coach to suggest tailored ways to reduce their carbon footprint.

**Technology Stack:** FastAPI (Backend) · Streamlit (Frontend) · PostgreSQL 16 (Database) · Docker (Deployment) · OpenAI API (AI Coach).

## 👥 Team Overview & Roles
Each team member owns one subsystem end-to-end, including the database models, API routes, UI pages, and unit tests for their respective sections.

| Member | Name | Role | Subsystem | Key Responsibilities |
| :--- | :--- | :--- | :--- | :--- |
| **Member 1** | **Saba Brahmani** | Data & Database Engineer | **S1: Data & Identity** | Database schema, Alembic migrations, Authentication (JWT), Activity records, CSV imports, Tenant isolation, Assets & Meter Readings. |
| **Member 2** | **Tuba Jabeen** | Carbon Engine & DevOps | **S2: Emission Engine** | Emission factor database, unit conversions, Scope 1/2/3 classification, calculation core, what-if simulations, and Docker setup. |
| **Member 3** | **Sameer Ghaffar** | Analytics & Frontend Lead | **S3: Analytics & Reporting** | Streamlit website shell, main dashboard, sustainability score, tracking reduction targets, live monitoring, and PDF/CSV reports. |
| **Member 4** | **Mustafa Mulla Khil** | AI Engineer & Integration | **S4: AI Coach** | OpenAI integration, grounded chat (using company data), personalized recommendations, intelligent free-text identification, and the learning hub. |

## 🏗️ System Architecture
The project runs in three Docker containers (Database, API, UI). 
Data flows from **S1 (Data Entry)** ➔ **S2 (Calculation)** ➔ **S3 (Dashboard/Reports)** ➔ **S4 (AI Advice)**.

---
## Documentation
- [S1 Data & Identity (how it works, API, how to run)](docs/S1_Data_and_Identity.md)
- [S2 Emission Engine (how it works, API, how to run)](docs/S2_Emission_Engine.md)
- [S4 AI Sustainability Coach (how it works, API, requirements, how to run)](docs/S4_AI_Coach.md)
  

## System Design (UML Diagrams)

### S1 – Data & Identity (Saba Brahmani)
![S1 UML Diagram](https://github.com/user-attachments/assets/16dcaa2a-2eee-4e72-ac93-88626b30f673)



### S2 – Emission Engine (Tuba Jabeen)
![S2 UML diagram](docs/S2_UML.png)

### S4 – AI Sustainability Coach (Mustafa Mulla Khil)
![S4 UML diagram](docs/S4_UML.png)
