from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import hashlib
from app.core.config import settings
from app.models.models import Base, User, Router, Package

# SQLite connect arguments
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

# Enable WAL mode for SQLite for better concurrency
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """FastAPI dependency to yield database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    """Simple SHA256 password hash for admin users."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    """Initializes tables and seeds initial administrator, packages, and router if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed default master admin if no user exists
        if not db.query(User).first():
            master_user = User(
                username="admin",
                password_hash=hash_password("admin123"),
                fullname="System Administrator",
                role="master",
                phone="0500000000",
                is_active=True
            )
            db.add(master_user)

        # Seed default packages if none exist
        if not db.query(Package).first():
            sample_packages = [
                Package(name="PPPoE Standard 10M", type="pppoe", price=30.0, validity_days=30, mikrotik_profile="10M", rate_limit="10M/10M", description="Standard 10Mbps home connection"),
                Package(name="PPPoE Ultra 20M", type="pppoe", price=50.0, validity_days=30, mikrotik_profile="20M", rate_limit="20M/20M", description="High speed 20Mbps connection"),
                Package(name="Hotspot Monthly 30 Days", type="hotspot", price=30.0, validity_days=30, mikrotik_profile="hotspot-monthly", rate_limit="5M/5M", description="WiFi Hotspot 30 days unlimited"),
                Package(name="Hotspot Weekly 7 Days", type="hotspot", price=10.0, validity_days=7, mikrotik_profile="hotspot-weekly", rate_limit="5M/5M", description="WiFi Hotspot 7 days pass"),
            ]
            db.add_all(sample_packages)

        # Seed default router if none exists
        if not db.query(Router).first():
            default_router = Router(
                name="Main MikroTik Router",
                host=settings.DEFAULT_ROUTER_HOST,
                port=settings.DEFAULT_ROUTER_PORT,
                username="admin",
                password="",
                use_ssl=False,
                is_active=True,
                notes="Default primary gateway MikroTik router"
            )
            db.add(default_router)

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
