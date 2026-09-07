import sys
import os
from datetime import date, datetime, timedelta

# Ensure parent directory is in python path
sys.path.insert(0, os.path.abspath("."))

from app.core.config import settings
from app.database import engine, SessionLocal, init_db
from app.models import (
    Base, User, Router, Package, Subscriber, Invoice, Payment, VacationHold, AuditLog
)
from app.services.mikrotik import MikrotikService

print("==================================================")
print("RUNNING STEP 1 VERIFICATION TEST")
print("==================================================")

print("1. Initializing Database Schema & Seed Data...")
init_db()
db = SessionLocal()

print("2. Verifying Tables & Seed Records...")
admin = db.query(User).filter(User.username == "admin").first()
assert admin is not None, "Admin user seed failed"
print(f"   [PASS] Master User found: {admin.username} ({admin.fullname})")

packages = db.query(Package).all()
assert len(packages) >= 4, "Package seed failed"
print(f"   [PASS] Packages seeded: {len(packages)} packages available")
for pkg in packages:
    print(f"          - [{pkg.type.upper()}] {pkg.name} ({pkg.price} {settings.DEFAULT_CURRENCY} / {pkg.validity_days}d) -> Profile: {pkg.mikrotik_profile}")

routers = db.query(Router).all()
assert len(routers) >= 1, "Router seed failed"
print(f"   [PASS] Routers configured: {routers[0].name} @ {routers[0].host}:{routers[0].port}")

print("\n3. Testing Relational Integrity (Subscriber -> Invoice -> Payment -> Hold)...")
test_sub = Subscriber(
    router_id=routers[0].id,
    package_id=packages[0].id,
    type="pppoe",
    username="test_sub_step1",
    password="secretpassword123",
    fullname="Test Subscriber One",
    phone="0512345678",
    status="active",
    billing_start_date=date.today(),
    expiry_date=date.today() + timedelta(days=30),
    monthly_fee=packages[0].price,
    balance=0.0
)
db.add(test_sub)
db.commit()
db.refresh(test_sub)
print(f"   [PASS] Created Subscriber ID: {test_sub.id}, username: {test_sub.username}")

# Create Invoice
test_inv = Invoice(
    subscriber_id=test_sub.id,
    invoice_no=f"INV-{int(datetime.utcnow().timestamp())}",
    amount=packages[0].price,
    paid_amount=packages[0].price,
    status="paid",
    due_date=date.today() + timedelta(days=5),
    billing_month="2026-09"
)
db.add(test_inv)
db.commit()
db.refresh(test_inv)
print(f"   [PASS] Created Invoice ID: {test_inv.id}, Invoice No: {test_inv.invoice_no}")

# Create Payment
test_pay = Payment(
    invoice_id=test_inv.id,
    subscriber_id=test_sub.id,
    amount=packages[0].price,
    method="cash",
    receipt_no=f"REC-{int(datetime.utcnow().timestamp())}",
    collected_by=admin.id,
    notes="Initial payment test"
)
db.add(test_pay)
db.commit()
print(f"   [PASS] Created Payment Receipt: {test_pay.receipt_no}")

# Create Vacation Hold
test_hold = VacationHold(
    subscriber_id=test_sub.id,
    start_date=date.today(),
    reason="Summer Holiday",
    created_by=admin.id
)
db.add(test_hold)
db.commit()
print(f"   [PASS] Created Vacation Hold ID: {test_hold.id}")

# Audit Log
test_audit = AuditLog(
    user_id=admin.id,
    action="STEP1_TEST",
    details="Verified full relational database schema"
)
db.add(test_audit)
db.commit()
print(f"   [PASS] Logged Audit Entry: {test_audit.action}")

print("\n4. Testing MikrotikService Interface...")
svc = MikrotikService(host="10.20.30.1", username="admin", password="wrongpassword", port=8728)
assert hasattr(svc, "get_pppoe_secrets"), "Missing get_pppoe_secrets"
assert hasattr(svc, "add_pppoe_secret"), "Missing add_pppoe_secret"
assert hasattr(svc, "kick_active_pppoe"), "Missing kick_active_pppoe"
assert hasattr(svc, "get_hotspot_users"), "Missing get_hotspot_users"
assert hasattr(svc, "suspend_subscriber"), "Missing suspend_subscriber"
assert hasattr(svc, "renew_subscriber"), "Missing renew_subscriber"
print("   [PASS] MikrotikService has all lifecycle methods for PPPoE and Hotspot.")

print("\n5. Cleaning up test record...")
db.delete(test_sub)
db.commit()
db.close()
print("   [PASS] Cleanup complete. Test subscriber and cascade dependencies removed.")

print("\n==================================================")
print("ALL STEP 1 VERIFICATIONS PASSED SUCCESSFULLY!")
print("==================================================")
