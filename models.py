from app.models import (
    Base, User, Router, Package, Subscriber, Invoice, Payment, VacationHold, AuditLog
)

# Backward-compatibility alias
Customer = Subscriber
