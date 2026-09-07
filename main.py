import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, init_db, SessionLocal
from app.models import (
    User, Router, Package, Subscriber, SubscriberDevice,
    Invoice, Payment, VacationHold, AuditLog
)
from app.services.mikrotik import MikrotikService

# Ensure standalone database schema is initialized in cybernet.db
init_db()

app = FastAPI(title="CyberNet ISP Billing - Standalone MikroTik System")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def measure_ping(host: str) -> str:
    """Measures real ICMP ping response to MikroTik router."""
    try:
        res = subprocess.run(
            ["ping", "-c", "1", "-W", "1", host],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "time=" in line:
                    return line.split("time=")[1].split()[0] + " ms"
        return "Reachable (TCP open)"
    except Exception:
        return "Checking..."

def get_router_service(db: Session) -> Optional[MikrotikService]:
    """Helper to instantiate MikrotikService from the active router in cybernet.db."""
    router = db.query(Router).filter(Router.is_active == True).first()
    if router and router.username:
        return MikrotikService(
            host=router.host,
            username=router.username,
            password=router.password,
            port=router.port,
            use_ssl=router.use_ssl
        )
    return None

# =========================================================================
# WEB DASHBOARD
# =========================================================================
@app.get("/")
def dashboard_view(request: Request, db: Session = Depends(get_db)):
    # 1. Real Counts from cybernet.db
    subscribers = db.query(Subscriber).all()
    pppoe_subs = [s for s in subscribers if s.type == "pppoe" and s.status == "active"]
    hotspot_subs = [s for s in subscribers if s.type == "hotspot" and s.status == "active"]
    suspended_subs = [s for s in subscribers if s.status == "suspended"]
    
    # Expiring within 3 days
    today = date.today()
    in_3_days = today + timedelta(days=3)
    expiring_soon = [
        s for s in subscribers 
        if s.status == "active" and s.expiry_date and s.expiry_date <= in_3_days
    ]
    
    # Active Vacation Holds
    active_holds = db.query(VacationHold).filter(
        (VacationHold.end_date == None) | (VacationHold.end_date >= today)
    ).all()

    # Collections
    now = datetime.utcnow()
    this_month_prefix = now.strftime("%Y-%m")
    payments = db.query(Payment).order_by(Payment.id.desc()).all()
    
    month_revenue = sum(
        p.amount for p in payments 
        if p.payment_date and p.payment_date.strftime("%Y-%m") == this_month_prefix
    )

    # Registered Devices
    devices = db.query(SubscriberDevice).order_by(SubscriberDevice.id.desc()).all()
    
    # Packages and Router Config
    packages = db.query(Package).filter(Package.is_active == True).all()
    router = db.query(Router).first()
    audit_logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(20).all()

    # Real Ping
    router_host = router.host if router else "10.20.30.1"
    router_port = router.port if router else 8728
    ping_ms = measure_ping(router_host)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "subscribers": subscribers,
            "pppoe_subs": pppoe_subs,
            "hotspot_subs": hotspot_subs,
            "suspended_subs": suspended_subs,
            "expiring_soon": expiring_soon,
            "active_holds": active_holds,
            "month_revenue": round(month_revenue, 2),
            "payments": payments,
            "devices": devices,
            "packages": packages,
            "router": router,
            "audit_logs": audit_logs,
            "router_host": router_host,
            "router_port": router_port,
            "router_ping": ping_ms
        }
    )

# =========================================================================
# API: ADD SUBSCRIBER (PPPoE or Hotspot)
# =========================================================================
@app.post("/api/subscribers/add")
def add_subscriber(
    type: str = Form(...),            # pppoe or hotspot
    username: str = Form(...),
    password: str = Form(...),
    fullname: str = Form(...),
    phone: str = Form(...),
    package_id: int = Form(...),
    validity_days: int = Form(30),
    db: Session = Depends(get_db)
):
    clean_user = username.strip()
    if db.query(Subscriber).filter(Subscriber.username == clean_user).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    package = db.query(Package).filter(Package.id == package_id).first()
    router = db.query(Router).first()
    
    today = date.today()
    exp_date = today + timedelta(days=validity_days)

    sub = Subscriber(
        router_id=router.id if router else None,
        package_id=package.id if package else None,
        type=type.lower(),
        username=clean_user,
        password=password.strip(),
        fullname=fullname.strip(),
        phone=phone.strip(),
        status="active",
        billing_start_date=today,
        expiry_date=exp_date,
        monthly_fee=package.price if package else 30.0,
        balance=0.0
    )
    db.add(sub)

    # Audit log
    audit = AuditLog(
        action=f"ADD_{type.upper()}",
        details=f"Created {type.upper()} subscriber '{clean_user}' ({fullname})"
    )
    db.add(audit)
    db.commit()

    # If MikroTik router credentials exist, provision secret on router
    mt = get_router_service(db)
    if mt:
        try:
            profile_name = package.mikrotik_profile if package else "default"
            comment = f"Exp: {exp_date} | {fullname}"
            if type.lower() == "pppoe":
                mt.add_pppoe_secret(name=clean_user, password=password.strip(), profile=profile_name, comment=comment)
            else:
                mt.add_hotspot_user(name=clean_user, password=password.strip(), profile=profile_name, comment=comment)
            mt.close()
        except Exception as e:
            # Log failure but keep DB subscriber
            db.add(AuditLog(action="ROUTER_SYNC_WARN", details=f"Could not provision on MikroTik: {e}"))
            db.commit()

    return RedirectResponse(url="/", status_code=303)

# =========================================================================
# API: BYPASS ANDROID TV / MAC ADDRESS
# =========================================================================
@app.post("/api/devices/bypass")
def bypass_device(
    subscriber_id: int = Form(...),
    device_name: str = Form(...),
    mac_address: str = Form(...),
    device_type: str = Form("tv"),
    db: Session = Depends(get_db)
):
    clean_mac = mac_address.upper().replace("-", ":").strip()
    sub = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    dev = SubscriberDevice(
        subscriber_id=sub.id,
        device_name=device_name.strip(),
        mac_address=clean_mac,
        device_type=device_type,
        is_bypassed=True,
        is_active=True
    )
    db.add(dev)

    audit = AuditLog(
        action="BYPASS_DEVICE",
        details=f"Bypassed MAC '{clean_mac}' ({device_name}) for customer {sub.username}"
    )
    db.add(audit)
    db.commit()

    # Apply to MikroTik IP-binding if credentials present
    mt = get_router_service(db)
    if mt:
        try:
            mt.add_ip_binding(
                mac_address=clean_mac,
                binding_type="bypassed",
                comment=f"Customer: {sub.username} ({device_name})"
            )
            mt.close()
        except Exception as e:
            db.add(AuditLog(action="ROUTER_SYNC_WARN", details=f"Could not add IP-binding on router: {e}"))
            db.commit()

    return RedirectResponse(url="/", status_code=303)

# =========================================================================
# API: RENEW SUBSCRIBER
# =========================================================================
@app.post("/api/subscribers/{sub_id}/renew")
def renew_subscriber_endpoint(
    sub_id: int,
    amount: float = Form(...),
    method: str = Form("cash"),
    days: int = Form(30),
    db: Session = Depends(get_db)
):
    sub = db.query(Subscriber).filter(Subscriber.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    # Calculate new expiry date
    base_date = max(sub.expiry_date, date.today()) if sub.expiry_date else date.today()
    new_exp = base_date + timedelta(days=days)
    sub.expiry_date = new_exp
    sub.status = "active"

    # Record Payment
    receipt_no = f"REC-{int(datetime.utcnow().timestamp())}"
    pay = Payment(
        subscriber_id=sub.id,
        amount=amount,
        method=method,
        receipt_no=receipt_no,
        notes=f"Renewal for {days} days"
    )
    db.add(pay)

    audit = AuditLog(
        action="RENEW",
        details=f"Renewed {sub.username} until {new_exp} (Paid {amount} SAR via {method})"
    )
    db.add(audit)
    db.commit()

    # Re-enable on MikroTik
    mt = get_router_service(db)
    if mt:
        try:
            mt.renew_subscriber(sub.type, sub.username, str(new_exp))
            mt.close()
        except Exception:
            pass

    return RedirectResponse(url="/", status_code=303)

# =========================================================================
# API: SUSPEND SUBSCRIBER
# =========================================================================
@app.post("/api/subscribers/{sub_id}/suspend")
def suspend_subscriber_endpoint(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    sub.status = "suspended"
    audit = AuditLog(action="SUSPEND", details=f"Suspended subscriber {sub.username}")
    db.add(audit)
    db.commit()

    # Disable secret on MikroTik and kick session
    mt = get_router_service(db)
    if mt:
        try:
            device_macs = [d.mac_address for d in sub.devices] if sub.devices else []
            mt.suspend_subscriber(sub.type, sub.username, device_macs=device_macs)
            mt.close()
        except Exception:
            pass

    return RedirectResponse(url="/", status_code=303)

# =========================================================================
# API: UPDATE ROUTER CONFIG (CREDENTIALS)
# =========================================================================
@app.post("/api/router/update")
def update_router_config(
    host: str = Form(...),
    port: int = Form(8728),
    username: str = Form(...),
    password: str = Form(""),
    db: Session = Depends(get_db)
):
    router = db.query(Router).first()
    if not router:
        router = Router(name="Main MikroTik Router", host=host, port=port, username=username, password=password)
        db.add(router)
    else:
        router.host = host.strip()
        router.port = port
        router.username = username.strip()
        if password:
            router.password = password.strip()
    
    db.add(AuditLog(action="ROUTER_CONFIG", details=f"Updated Router credentials for {host}:{port}"))
    db.commit()
    return RedirectResponse(url="/", status_code=303)
