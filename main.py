from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db, init_db
from app.models import (
    User, Router, Package, Subscriber, SubscriberDevice,
    Invoice, Payment, VacationHold, AuditLog
)

# Initialize schema and seed data
init_db()

app = FastAPI(title="CyberNet ISP Billing & MikroTik Management")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_customers = db.query(Subscriber).count()
    active_customers = db.query(Subscriber).filter(Subscriber.status == "active").count()
    packages = db.query(Package).all()
    routers = db.query(Router).all()
    devices = db.query(SubscriberDevice).all()
        
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "total_customers": total_customers,
            "active_customers": active_customers,
            "packages": packages,
            "routers": routers,
            "devices": devices
        }
    )

@app.get("/hotspot/login")
def hotspot_login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/hotspot/submit")
def hotspot_submit(phone: str = Form(...), db: Session = Depends(get_db)):
    customer = db.query(Subscriber).filter(Subscriber.phone == phone).first()
    if not customer:
        customer = Subscriber(
            phone=phone,
            username=phone,
            password="pin_" + phone[-4:],
            fullname="Hotspot User",
            type="hotspot",
            status="pending"
        )
        db.add(customer)
        db.commit()
    
    return RedirectResponse(url=f"/hotspot/pending?phone={phone}", status_code=303)

@app.get("/hotspot/pending")
def hotspot_pending(request: Request, phone: str):
    return templates.TemplateResponse(request=request, name="pending.html", context={"phone": phone})
