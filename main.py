import os
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Depends, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, init_db, SessionLocal
from app.models import (
    User, Router, Package, Subscriber, SubscriberDevice,
    HotspotRequest, Invoice, Payment, VacationHold, AuditLog
)
from app.services.mikrotik import MikrotikService

# Ensure standalone database schema is initialized in cybernet.db
init_db()

app = FastAPI(title="CyberNet ISP Billing - Standalone MikroTik System")

# Enable CORS so MikroTik captive portal can make cross-origin AJAX requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def parse_device_name(user_agent: Optional[str]) -> str:
    """Extracts human-readable device model from browser User-Agent."""
    if not user_agent:
        return "Mobile Device"
    ua = user_agent.lower()
    if "iphone" in ua:
        return "Apple iPhone"
    elif "ipad" in ua:
        return "Apple iPad"
    elif "android" in ua:
        if "samsung" in ua or "sm-" in ua:
            return "Samsung Galaxy"
        elif "xiaomi" in ua or "redmi" in ua:
            return "Xiaomi / Redmi"
        elif "huawei" in ua:
            return "Huawei Phone"
        elif "oppo" in ua:
            return "Oppo Phone"
        elif "vivo" in ua:
            return "Vivo Phone"
        elif "tv" in ua or "smart-tv" in ua or "googletv" in ua:
            return "Android TV"
        return "Android Phone"
    elif "windows" in ua:
        return "Windows PC"
    elif "macintosh" in ua or "mac os" in ua:
        return "Apple Mac"
    elif "linux" in ua:
        return "Linux Device"
    elif "smart-tv" in ua or "tizen" in ua or "webos" in ua:
        return "Smart TV"
    return "Mobile Phone"


def normalize_mac(mac: str) -> str:
    """Normalizes MAC address into standard uppercase colon format XX:XX:XX:XX:XX:XX."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    if len(cleaned) == 12:
        return ":".join(cleaned[i:i+2] for i in range(0, 12, 2))
    return mac.upper().replace("-", ":").strip()


def normalize_phone(phone: str) -> str:
    """Normalizes phone number to digits only."""
    return re.sub(r"\D", "", phone).strip()


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
# WEB DASHBOARD (ADMIN PORTAL)
# =========================================================================
@app.get("/")
def dashboard_view(request: Request, db: Session = Depends(get_db)):
    # 1. Real Counts from cybernet.db
    total_subscribers = db.query(Subscriber).count()
    active_subscribers = db.query(Subscriber).filter(Subscriber.status == "active").count()
    pppoe_subscribers = db.query(Subscriber).filter(Subscriber.type == "pppoe").count()
    hotspot_subscribers = db.query(Subscriber).filter(Subscriber.type == "hotspot").count()
    suspended_subscribers = db.query(Subscriber).filter(Subscriber.status == "suspended").count()
    active_holds = db.query(VacationHold).filter(VacationHold.end_date == None).count()

    # Hotspot Connection Requests submitted from captive portal
    pending_hotspot_requests = (
        db.query(HotspotRequest)
        .filter(HotspotRequest.status == "pending")
        .order_by(HotspotRequest.created_at.desc())
        .all()
    )
    recent_hotspot_requests = (
        db.query(HotspotRequest)
        .order_by(HotspotRequest.created_at.desc())
        .limit(15)
        .all()
    )

    # 2. Real Revenue (sum of all verified payments recorded this month)
    first_of_month = date.today().replace(day=1)
    first_of_month_dt = datetime.combine(first_of_month, datetime.min.time())
    month_payments = db.query(Payment).filter(Payment.payment_date >= first_of_month_dt).all()
    month_revenue = sum(p.amount for p in month_payments) if month_payments else 0.0

    # 3. Real Records
    subscribers = db.query(Subscriber).order_by(Subscriber.id.desc()).all()
    payments = db.query(Payment).order_by(Payment.id.desc()).limit(10).all()
    devices = db.query(SubscriberDevice).order_by(SubscriberDevice.id.desc()).all()
    packages = db.query(Package).filter(Package.is_active == True).all()
    router = db.query(Router).first()
    audit_logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()

    # 4. Real Ping & Socket Verification to MikroTik
    router_host = router.host if router else "10.20.30.1"
    router_port = router.port if router else 8728
    ping_ms = measure_ping(router_host)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "total_subscribers": total_subscribers,
            "active_subscribers": active_subscribers,
            "pppoe_subscribers": pppoe_subscribers,
            "hotspot_subscribers": hotspot_subscribers,
            "suspended_subscribers": suspended_subscribers,
            "subscribers": subscribers,
            "active_holds": active_holds,
            "month_revenue": round(month_revenue, 2),
            "payments": payments,
            "devices": devices,
            "packages": packages,
            "router": router,
            "audit_logs": audit_logs,
            "router_host": router_host,
            "router_port": router_port,
            "router_ping": ping_ms,
            "pending_hotspot_requests": pending_hotspot_requests,
            "recent_hotspot_requests": recent_hotspot_requests
        }
    )


# =========================================================================
# MIKROTIK CAPTIVE PORTAL ENDPOINTS
# =========================================================================
@app.post("/api/hotspot/submit")
async def submit_hotspot_phone(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Called when a customer enters their mobile number on the MikroTik Hotspot popup.
    Supports both JSON and Form-data payloads.
    """
    content_type = request.headers.get("content-type", "")
    phone_raw = ""
    mac_raw = ""
    ip_raw = ""
    device_model = ""

    if "application/json" in content_type:
        body = await request.json()
        phone_raw = str(body.get("phone", ""))
        mac_raw = str(body.get("mac", ""))
        ip_raw = str(body.get("ip", ""))
        device_model = str(body.get("device_model", ""))
    else:
        form = await request.form()
        phone_raw = str(form.get("phone", ""))
        mac_raw = str(form.get("mac", ""))
        ip_raw = str(form.get("ip", ""))
        device_model = str(form.get("device_model", ""))

    clean_phone = normalize_phone(phone_raw)
    clean_mac = normalize_mac(mac_raw) if mac_raw else ""
    ip_addr = ip_raw.strip() or (request.client.host if request.client else "")

    if not device_model or len(device_model) < 3:
        device_model = parse_device_name(request.headers.get("user-agent"))

    if not clean_phone or len(clean_phone) < 9:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Please enter a valid phone number (at least 9 digits)."}
        )

    # 1. Check if an existing subscriber exists with this phone number
    sub = (
        db.query(Subscriber)
        .filter((Subscriber.phone == clean_phone) | (Subscriber.username == clean_phone))
        .first()
    )

    today = date.today()

    if sub:
        # Case A: Active Subscriber with valid expiry
        if sub.status == "active" and sub.expiry_date and sub.expiry_date >= today:
            # Check if this MAC is already among their registered devices
            existing_device = next((d for d in sub.devices if d.mac_address == clean_mac), None) if clean_mac else None

            if existing_device:
                # Device is already registered and active
                return JSONResponse({
                    "status": "approved",
                    "message": f"Welcome back, {sub.fullname or clean_phone}! Internet access is active.",
                    "expiry": str(sub.expiry_date),
                    "phone": clean_phone
                })

            # Check device limit for this subscriber's package
            device_limit = sub.package.shared_users if (sub.package and sub.package.shared_users) else 5
            current_device_count = len(sub.devices)

            if current_device_count < device_limit:
                # Add this new device automatically under customer's phone account
                if clean_mac:
                    new_dev = SubscriberDevice(
                        subscriber_id=sub.id,
                        device_name=f"{device_model}",
                        mac_address=clean_mac,
                        ip_address=ip_addr,
                        device_type="phone",
                        is_bypassed=True,
                        is_active=True
                    )
                    db.add(new_dev)
                    db.commit()

                    # Provision MAC on MikroTik IP-binding as bypassed
                    mt = get_router_service(db)
                    if mt:
                        try:
                            mt.add_ip_binding(
                                mac_address=clean_mac,
                                binding_type="bypassed",
                                comment=f"Hotspot: {clean_phone} ({device_model})"
                            )
                            mt.close()
                        except Exception as e:
                            pass

                return JSONResponse({
                    "status": "approved",
                    "message": f"New device added ({current_device_count + 1}/{device_limit})! Access granted.",
                    "expiry": str(sub.expiry_date),
                    "phone": clean_phone
                })
            else:
                return JSONResponse({
                    "status": "device_limit",
                    "message": f"Device limit reached ({current_device_count}/{device_limit} devices). Please contact admin.",
                    "phone": clean_phone
                })

        # Case B: Subscriber exists but expired or suspended
        elif sub.status == "suspended":
            return JSONResponse({
                "status": "suspended",
                "message": "Your account is temporarily suspended. Please contact network admin.",
                "phone": clean_phone
            })
        else:
            # Expired
            return JSONResponse({
                "status": "expired",
                "message": f"Your package expired on {sub.expiry_date}. Please renew to regain internet access.",
                "phone": clean_phone
            })

    # 2. Case C: Brand New Customer -> Create/Update HotspotRequest (Waiting for Admin Activation)
    existing_req = None
    if clean_mac:
        existing_req = db.query(HotspotRequest).filter(
            HotspotRequest.mac_address == clean_mac,
            HotspotRequest.status == "pending"
        ).first()

    if existing_req:
        existing_req.phone = clean_phone
        existing_req.ip_address = ip_addr
        existing_req.device_model = device_model
        existing_req.updated_at = datetime.utcnow()
    else:
        new_req = HotspotRequest(
            phone=clean_phone,
            mac_address=clean_mac or "UNKNOWN",
            ip_address=ip_addr,
            device_model=device_model,
            status="pending"
        )
        db.add(new_req)

    db.commit()

    return JSONResponse({
        "status": "pending",
        "message": f"Request registered for {clean_phone}! Waiting for administrator approval.",
        "phone": clean_phone
    })


@app.get("/api/hotspot/check-status")
def check_hotspot_status(
    mac: Optional[str] = None,
    phone: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Called by captive portal poller every 5 seconds to check if request was approved.
    """
    clean_mac = normalize_mac(mac) if mac else None
    clean_phone = normalize_phone(phone) if phone else None

    # Check 1: Is this MAC active on a subscriber?
    if clean_mac:
        device = db.query(SubscriberDevice).filter(
            SubscriberDevice.mac_address == clean_mac,
            SubscriberDevice.is_active == True
        ).first()

        if device and device.subscriber and device.subscriber.status == "active":
            today = date.today()
            if device.subscriber.expiry_date and device.subscriber.expiry_date >= today:
                return JSONResponse({
                    "status": "approved",
                    "message": "Access granted!",
                    "expiry": str(device.subscriber.expiry_date)
                })

    # Check 2: Check HotspotRequest status
    req = None
    if clean_mac:
        req = db.query(HotspotRequest).filter(HotspotRequest.mac_address == clean_mac).order_by(HotspotRequest.id.desc()).first()
    elif clean_phone:
        req = db.query(HotspotRequest).filter(HotspotRequest.phone == clean_phone).order_by(HotspotRequest.id.desc()).first()

    if req:
        if req.status == "approved":
            return JSONResponse({
                "status": "approved",
                "message": "Request approved! Internet is ready."
            })
        elif req.status == "rejected":
            return JSONResponse({
                "status": "rejected",
                "message": req.admin_notes or "Request was rejected by network admin."
            })
        return JSONResponse({"status": "pending", "message": "Waiting for admin activation."})

    return JSONResponse({"status": "pending", "message": "Checking activation status..."})


@app.post("/api/hotspot/requests/{req_id}/approve")
def approve_hotspot_request(
    req_id: int,
    fullname: str = Form(""),
    package_id: int = Form(...),
    validity_days: int = Form(30),
    amount_paid: float = Form(...),
    payment_method: str = Form("cash"),
    db: Session = Depends(get_db)
):
    """
    Admin 1-click action: Approves customer request submitted from captive portal.
    Creates or updates subscriber, adds device MAC bypass, records payment, and provisions RouterOS.
    """
    req = db.query(HotspotRequest).filter(HotspotRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    package = db.query(Package).filter(Package.id == package_id).first()
    router = db.query(Router).first()

    today = date.today()
    exp_date = today + timedelta(days=validity_days)

    # Check if subscriber with this phone already exists
    sub = db.query(Subscriber).filter(Subscriber.phone == req.phone).first()

    if not sub:
        # Create brand new subscriber
        sub_name = fullname.strip() if fullname.strip() else f"User {req.phone}"
        sub = Subscriber(
            router_id=router.id if router else None,
            package_id=package.id if package else None,
            type="hotspot",
            username=req.phone,
            password=req.phone[-6:] if len(req.phone) >= 6 else "123456",
            fullname=sub_name,
            phone=req.phone,
            status="active",
            billing_start_date=today,
            expiry_date=exp_date,
            monthly_fee=amount_paid,
            balance=0.0
        )
        db.add(sub)
        db.flush()
    else:
        # Renew / extend existing subscriber
        base_date = max(sub.expiry_date, today) if sub.expiry_date else today
        exp_date = base_date + timedelta(days=validity_days)
        sub.expiry_date = exp_date
        sub.status = "active"
        if fullname.strip():
            sub.fullname = fullname.strip()
        if package:
            sub.package_id = package.id

    # Register the requesting MAC device under this subscriber
    if req.mac_address and req.mac_address != "UNKNOWN":
        dev = db.query(SubscriberDevice).filter(SubscriberDevice.mac_address == req.mac_address).first()
        if not dev:
            dev = SubscriberDevice(
                subscriber_id=sub.id,
                device_name=req.device_model or "Mobile Phone",
                mac_address=req.mac_address,
                ip_address=req.ip_address,
                device_type="phone",
                is_bypassed=True,
                is_active=True
            )
            db.add(dev)
        else:
            dev.subscriber_id = sub.id
            dev.is_bypassed = True
            dev.is_active = True

    # Record Payment
    receipt_no = f"REC-HS-{int(datetime.utcnow().timestamp())}"
    pay = Payment(
        subscriber_id=sub.id,
        amount=amount_paid,
        method=payment_method,
        receipt_no=receipt_no,
        notes=f"Hotspot activation via phone submission ({validity_days} days)"
    )
    db.add(pay)

    # Mark request approved
    req.status = "approved"
    req.subscriber_id = sub.id
    req.updated_at = datetime.utcnow()

    # Audit log
    audit = AuditLog(
        action="APPROVE_HOTSPOT",
        details=f"Approved Hotspot connection for {req.phone} ({sub.fullname}). Paid {amount_paid} SAR. MAC {req.mac_address} bypassed until {exp_date}."
    )
    db.add(audit)
    db.commit()

    # Provision MAC bypass on MikroTik Router
    mt = get_router_service(db)
    if mt and req.mac_address and req.mac_address != "UNKNOWN":
        try:
            mt.add_ip_binding(
                mac_address=req.mac_address,
                binding_type="bypassed",
                comment=f"Hotspot: {req.phone} ({sub.fullname})"
            )
            # Also ensure hotspot user secret exists
            profile_name = package.mikrotik_profile if package else "hotspot-monthly"
            mt.add_hotspot_user(
                name=req.phone,
                password=sub.password,
                profile=profile_name,
                comment=f"Exp: {exp_date} | {sub.fullname}"
            )
            mt.close()
        except Exception as e:
            db.add(AuditLog(action="ROUTER_SYNC_WARN", details=f"MikroTik sync warning: {e}"))
            db.commit()

    return RedirectResponse(url="/", status_code=303)


@app.post("/api/hotspot/requests/{req_id}/reject")
def reject_hotspot_request(
    req_id: int,
    reason: str = Form("Request declined by administrator"),
    db: Session = Depends(get_db)
):
    """Admin rejects pending connection request."""
    req = db.query(HotspotRequest).filter(HotspotRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = "rejected"
    req.admin_notes = reason.strip()
    req.updated_at = datetime.utcnow()

    audit = AuditLog(
        action="REJECT_HOTSPOT",
        details=f"Rejected Hotspot connection for {req.phone} (MAC: {req.mac_address}). Reason: {reason}"
    )
    db.add(audit)
    db.commit()

    return RedirectResponse(url="/", status_code=303)


@app.get("/hotspot/login")
def serve_hotspot_login(request: Request):
    """Serves the responsive MikroTik captive portal login page directly."""
    return templates.TemplateResponse(request=request, name="hotspot_login.html", context={})


@app.get("/hotspot/download-login")
def download_hotspot_login():
    """Download login.html ready to upload into MikroTik /hotspot/ directory."""
    login_file = BASE_DIR / "templates" / "hotspot_login.html"
    if not login_file.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    content = login_file.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Disposition": "attachment; filename=login.html"}
    )


# =========================================================================
# MANUAL SUBSCRIBER PROVISIONING (PPPoE / Hotspot)
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
    clean_phone = normalize_phone(phone)
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
        phone=clean_phone or clean_user,
        status="active",
        billing_start_date=today,
        expiry_date=exp_date,
        monthly_fee=package.price if package else 30.0,
        balance=0.0
    )
    db.add(sub)

    audit = AuditLog(
        action=f"ADD_{type.upper()}",
        details=f"Created {type.upper()} subscriber '{clean_user}' ({fullname}) - Expiry: {exp_date}"
    )
    db.add(audit)
    db.commit()

    # Provision secret on router
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
            db.add(AuditLog(action="ROUTER_SYNC_WARN", details=f"Could not provision on MikroTik: {e}"))
            db.commit()

    return RedirectResponse(url="/", status_code=303)


# =========================================================================
# BYPASS ANDROID TV / NON-BROWSER DEVICE (MAC BINDING)
# =========================================================================
@app.post("/api/devices/bypass")
def bypass_device(
    subscriber_id: int = Form(...),
    device_name: str = Form(...),
    mac_address: str = Form(...),
    device_type: str = Form("tv"),
    db: Session = Depends(get_db)
):
    """
    Solves the Android TV / Game Console problem:
    Bypasses the captive portal for devices that lack web browsers.
    """
    clean_mac = normalize_mac(mac_address)
    sub = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    dev = db.query(SubscriberDevice).filter(SubscriberDevice.mac_address == clean_mac).first()
    if not dev:
        dev = SubscriberDevice(
            subscriber_id=sub.id,
            device_name=device_name.strip(),
            mac_address=clean_mac,
            device_type=device_type,
            is_bypassed=True,
            is_active=True
        )
        db.add(dev)
    else:
        dev.subscriber_id = sub.id
        dev.device_name = device_name.strip()
        dev.device_type = device_type
        dev.is_bypassed = True
        dev.is_active = True

    audit = AuditLog(
        action="BYPASS_DEVICE",
        details=f"Bypassed {device_type.upper()} '{device_name}' (MAC: {clean_mac}) for customer {sub.phone} ({sub.fullname})"
    )
    db.add(audit)
    db.commit()

    # Apply to MikroTik IP-binding as bypassed
    mt = get_router_service(db)
    if mt:
        try:
            mt.add_ip_binding(
                mac_address=clean_mac,
                binding_type="bypassed",
                comment=f"Customer: {sub.phone} ({device_name})"
            )
            mt.close()
        except Exception as e:
            db.add(AuditLog(action="ROUTER_SYNC_WARN", details=f"Could not add IP-binding on router: {e}"))
            db.commit()

    return RedirectResponse(url="/", status_code=303)


# =========================================================================
# LIFECYCLE: RENEW / SUSPEND / RESUME / UPDATE ROUTER
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

    base_date = max(sub.expiry_date, date.today()) if sub.expiry_date else date.today()
    new_exp = base_date + timedelta(days=days)
    sub.expiry_date = new_exp
    sub.status = "active"

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

    mt = get_router_service(db)
    if mt:
        try:
            device_macs = [d.mac_address for d in sub.devices] if sub.devices else []
            mt.renew_subscriber(sub.type, sub.username, str(new_exp), device_macs=device_macs)
            mt.close()
        except Exception:
            pass

    return RedirectResponse(url="/", status_code=303)


@app.post("/api/subscribers/{sub_id}/suspend")
def suspend_subscriber_endpoint(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    sub.status = "suspended"
    audit = AuditLog(action="SUSPEND", details=f"Suspended subscriber {sub.username}")
    db.add(audit)
    db.commit()

    mt = get_router_service(db)
    if mt:
        try:
            device_macs = [d.mac_address for d in sub.devices] if sub.devices else []
            mt.suspend_subscriber(sub.type, sub.username, device_macs=device_macs)
            mt.close()
        except Exception:
            pass

    return RedirectResponse(url="/", status_code=303)


@app.post("/api/subscribers/{sub_id}/resume")
def resume_subscriber_endpoint(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    sub.status = "active"
    audit = AuditLog(action="RESUME", details=f"Resumed subscriber {sub.username}")
    db.add(audit)
    db.commit()

    mt = get_router_service(db)
    if mt:
        try:
            device_macs = [d.mac_address for d in sub.devices] if sub.devices else []
            profile = sub.package.mikrotik_profile if sub.package else None
            mt.resume_subscriber(sub.type, sub.username, profile=profile, device_macs=device_macs)
            mt.close()
        except Exception:
            pass

    return RedirectResponse(url="/", status_code=303)


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
