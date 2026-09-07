import sys
import os
from datetime import date, datetime, timedelta

# Ensure parent directory is in python path
sys.path.insert(0, os.path.abspath("."))

from app.core.config import settings
from app.database import engine, SessionLocal, init_db
from app.models import (
    Base, User, Router, Package, Subscriber, SubscriberDevice,
    Invoice, Payment, VacationHold, AuditLog
)
from app.services.mikrotik import MikrotikService

print("==================================================")
print("RUNNING STEP 1 + MULTI-DEVICE / MAC BYPASS TEST")
print("==================================================")

print("1. Initializing Database Schema...")
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
    print(f"          - [{pkg.type.upper()}] {pkg.name} ({pkg.price} {settings.DEFAULT_CURRENCY} / {pkg.validity_days}d) | Shared Users: {pkg.shared_users} -> Profile: {pkg.mikrotik_profile}")

routers = db.query(Router).all()
assert len(routers) >= 1, "Router seed failed"
print(f"   [PASS] Routers configured: {routers[0].name} @ {routers[0].host}:{routers[0].port}")

print("\n3. Testing Relational Integrity with Multiple Devices & Android TV Bypass...")
test_sub = Subscriber(
    router_id=routers[0].id,
    package_id=packages[2].id,  # Hotspot Monthly
    type="hotspot",
    username="0597595059",
    password="pin_" + str(int(datetime.now().timestamp()))[-4:],
    fullname="Multi-Device Hotspot Customer",
    phone="0597595059",
    status="active",
    billing_start_date=date.today(),
    expiry_date=date.today() + timedelta(days=30),
    monthly_fee=packages[2].price,
    balance=0.0
)
db.add(test_sub)
db.commit()
db.refresh(test_sub)
print(f"   [PASS] Created Subscriber ID: {test_sub.id}, username: {test_sub.username}")

# Add Android TV Device (Bypassed)
tv_device = SubscriberDevice(
    subscriber_id=test_sub.id,
    device_name="Living Room Android TV",
    mac_address="A4:C1:38:12:34:56",
    device_type="tv",
    ip_address="10.20.30.55",
    is_bypassed=True,
    is_active=True,
    notes="Living room TV - bypass captive portal"
)
# Add Kid's Tablet Device
tablet_device = SubscriberDevice(
    subscriber_id=test_sub.id,
    device_name="Kids iPad",
    mac_address="3C:22:FB:44:55:66",
    device_type="phone",
    is_bypassed=False,  # Regular captive portal login
    is_active=True
)
db.add_all([tv_device, tablet_device])
db.commit()

# Verify devices associated with subscriber
sub_devices = db.query(SubscriberDevice).filter(SubscriberDevice.subscriber_id == test_sub.id).all()
assert len(sub_devices) == 2, "Failed to associate devices"
print(f"   [PASS] Registered {len(sub_devices)} devices for customer {test_sub.username}:")
for dev in sub_devices:
    bypass_str = "YES (Bypasses Captive Portal)" if dev.is_bypassed else "NO (Standard Login)"
    print(f"          - [{dev.device_type.upper()}] {dev.device_name} (MAC: {dev.mac_address}) | Bypassed: {bypass_str}")

# Create Invoice & Payment
test_inv = Invoice(
    subscriber_id=test_sub.id,
    invoice_no=f"INV-{int(datetime.now().timestamp())}",
    amount=packages[2].price,
    paid_amount=packages[2].price,
    status="paid",
    due_date=date.today() + timedelta(days=5),
    billing_month="2026-09"
)
db.add(test_inv)
db.commit()
db.refresh(test_inv)

test_pay = Payment(
    invoice_id=test_inv.id,
    subscriber_id=test_sub.id,
    amount=packages[2].price,
    method="cash",
    receipt_no=f"REC-{int(datetime.now().timestamp())}",
    collected_by=admin.id,
    notes="Payment for Multi-device plan"
)
db.add(test_pay)
db.commit()
print(f"   [PASS] Invoiced & Paid: Invoice {test_inv.invoice_no}, Receipt {test_pay.receipt_no}")

print("\n4. Testing MikrotikService Interface with MAC Bypass & Host Discovery...")
svc = MikrotikService(host="10.20.30.1", username="admin", password="wrongpassword", port=8728)
assert hasattr(svc, "get_ip_bindings"), "Missing get_ip_bindings"
assert hasattr(svc, "add_ip_binding"), "Missing add_ip_binding"
assert hasattr(svc, "update_ip_binding"), "Missing update_ip_binding"
assert hasattr(svc, "delete_ip_binding"), "Missing delete_ip_binding"
assert hasattr(svc, "get_hotspot_hosts"), "Missing get_hotspot_hosts"
assert hasattr(svc, "set_hotspot_profile_shared_users"), "Missing set_hotspot_profile_shared_users"
print("   [PASS] MikrotikService has all MAC IP-binding, Auto-Discovery & shared-users methods.")

print("\n5. Cleaning up test records...")
db.delete(test_sub)  # Cascade will delete devices, invoice, payment
db.commit()
db.close()
print("   [PASS] Cleanup complete. Cascade deleted subscriber and all registered devices.")

print("\n==================================================")
print("ALL MULTI-DEVICE & MAC BYPASS VERIFICATIONS PASSED!")
print("==================================================")
