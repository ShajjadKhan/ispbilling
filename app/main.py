from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app.models.customer import Customer

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CyberNet ISP System V2")
templates = Jinja2Templates(directory="app/templates")

@app.get("/")
def read_root(request: Request, db: Session = Depends(get_db)):
    try:
        total_customers = db.query(Customer).count()
        active_customers = db.query(Customer).filter(Customer.status == "active").count()
    except Exception as e:
        total_customers = 0
        active_customers = 0
        
    return templates.TemplateResponse(
        request, 
        "dashboard.html", 
        {
            "title": "Dashboard",
            "total_customers": total_customers,
            "active_customers": active_customers
        }
    )
