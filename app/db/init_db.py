"""创建数据表 + 增量迁移"""
from app.db.models import Base, engine
from app.db.migrate import run_migrations


def init_db():
    Base.metadata.create_all(engine)
    run_migrations(engine)
    print("✅ Database initialized")

if __name__ == "__main__":
    init_db()
