# CyberNet ISP Billing & MikroTik Management System

A Python FastAPI application for ISP customer management, automated billing, and MikroTik Hotspot integration.

## Features
- **FastAPI Framework**: High performance asynchronous web application.
- **SQLAlchemy ORM**: Database modeling for customers and billing records with SQLite.
- **MikroTik Hotspot Portal**:
  - `/hotspot/login`: Captive portal user login screen.
  - `/hotspot/submit`: User self-registration and pending status activation.
  - `/hotspot/pending`: User approval pending status screen.
- **Admin Dashboard**: Live metrics for active, pending, and total subscribers.

## Getting Started

### Prerequisites
- Python 3.10+
- Virtual Environment (`venv`)

### Installation
1. Clone the repository:
   ```bash
   git clone git@github.com:ShajjadKhan/ispbilling.git
   cd ispbilling
   ```

2. Set up virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Run the development server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Access the portal:
   - Dashboard: `http://localhost:8000/`
   - Hotspot Login: `http://localhost:8000/hotspot/login`
   - Interactive API Docs: `http://localhost:8000/docs`
