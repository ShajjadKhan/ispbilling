from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    """Staff, Admin, and Collector user accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    fullname = Column(String(128), nullable=False)
    role = Column(String(32), default="admin")  # master, admin, collector, tech
    phone = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    payments = relationship("Payment", back_populates="collector")
    audit_logs = relationship("AuditLog", back_populates="user")


class Router(Base):
    """MikroTik RouterOS devices."""
    __tablename__ = "routers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    host = Column(String(100), nullable=False)  # IP or domain
    port = Column(Integer, default=8728)        # 8728 (API) or 8729 (SSL)
    username = Column(String(64), nullable=False)
    password = Column(String(128), nullable=False)
    use_ssl = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    identity = Column(String(100), nullable=True)
    ros_version = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    last_seen = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subscribers = relationship("Subscriber", back_populates="router")


class Package(Base):
    """Internet service packages / bandwidth plans."""
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(32), default="pppoe")  # pppoe, hotspot
    price = Column(Float, nullable=False, default=0.0)
    validity_days = Column(Integer, default=30)
    mikrotik_profile = Column(String(100), nullable=False)  # Profile name on RouterOS
    rate_limit = Column(String(50), nullable=True)          # e.g., '10M/20M'
    shared_users = Column(Integer, default=1)               # Max concurrent devices allowed on Hotspot
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subscribers = relationship("Subscriber", back_populates="package")


class Subscriber(Base):
    """ISP Customers (PPPoE and Hotspot users)."""
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    router_id = Column(Integer, ForeignKey("routers.id"), nullable=True)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=True)
    
    # Subscriber type and credentials
    type = Column(String(32), default="pppoe")  # pppoe, hotspot
    username = Column(String(64), unique=True, index=True, nullable=False)
    password = Column(String(64), nullable=False)
    
    # Personal Info
    fullname = Column(String(128), nullable=False)
    phone = Column(String(32), index=True, nullable=False)
    national_id = Column(String(64), nullable=True)
    address = Column(String(255), nullable=True)
    mac_address = Column(String(32), nullable=True)
    
    # Status & Lifecycle
    # active, suspended, hold, expired, pending
    status = Column(String(32), default="active", index=True)
    billing_start_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)
    monthly_fee = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)  # Positive = due/debt, Negative = credit
    
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    router = relationship("Router", back_populates="subscribers")
    package = relationship("Package", back_populates="subscribers")
    invoices = relationship("Invoice", back_populates="subscriber", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="subscriber", cascade="all, delete-orphan")
    vacation_holds = relationship("VacationHold", back_populates="subscriber", cascade="all, delete-orphan")
    devices = relationship("SubscriberDevice", back_populates="subscriber", cascade="all, delete-orphan")


class SubscriberDevice(Base):
    """Connected devices for a subscriber (e.g. Android TV, Gaming Console, Phones).
    Supports MAC address bypass (ip-binding) in MikroTik Hotspot.
    """
    __tablename__ = "subscriber_devices"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=False)
    device_name = Column(String(100), nullable=False)  # e.g., "Living Room Android TV"
    mac_address = Column(String(32), index=True, nullable=False)  # e.g., "AA:BB:CC:DD:EE:FF"
    device_type = Column(String(32), default="tv")  # tv, phone, pc, console, other
    ip_address = Column(String(45), nullable=True)
    is_bypassed = Column(Boolean, default=True)  # True = bypass captive portal via ip-binding
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subscriber = relationship("Subscriber", back_populates="devices")


class Invoice(Base):
    """Monthly or renewal invoices."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=False)
    invoice_no = Column(String(64), unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0.0)
    status = Column(String(32), default="unpaid")  # unpaid, partial, paid, cancelled
    due_date = Column(Date, nullable=False)
    billing_month = Column(String(20), nullable=True)  # e.g., "2026-09"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subscriber = relationship("Subscriber", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")


class Payment(Base):
    """Payment transactions and collection receipts."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(32), default="cash")  # cash, transfer, card, online
    receipt_no = Column(String(64), unique=True, index=True, nullable=False)
    collected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    # Relationships
    subscriber = relationship("Subscriber", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")
    collector = relationship("User", back_populates="payments")


class VacationHold(Base):
    """Vacation holds to pause billing and suspend service temporarily."""
    __tablename__ = "vacation_holds"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # NULL means indefinite until resumed
    held_days = Column(Integer, default=0)
    reason = Column(String(255), default="Vacation")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    subscriber = relationship("Subscriber", back_populates="vacation_holds")


class AuditLog(Base):
    """Audit trail of all administrative and billing actions."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(64), nullable=False)  # RENEW, SUSPEND, HOLD, RESUME, PAYMENT, etc.
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="audit_logs")
