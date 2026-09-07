from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import Customer

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CyberNet ISP System V2")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_customers = db.query(Customer).count()
    active_customers = db.query(Customer).filter(Customer.status == "active").count()
    pending_customers = db.query(Customer).filter(Customer.status == "pending").all()
        
    return templates.TemplateResponse(
        request, 
        "dashboard.html", 
        {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "pending_customers": pending_customers
        }
    )

@app.get("/hotspot/login")
def hotspot_login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})

@app.post("/hotspot/submit")
def hotspot_submit(phone: str = Form(...), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer:
        customer = Customer(phone=phone, name="Hotspot User", status="pending")
        db.add(customer)
        db.commit()
    
    return RedirectResponse(url=f"/hotspot/pending?phone={phone}", status_code=303)

@app.get("/hotspot/pending")
def hotspot_pending(request: Request, phone: str):
    return templates.TemplateResponse(request, "pending.html", {"phone": phone})
