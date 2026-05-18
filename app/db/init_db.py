"""创建数据表"""
from app.db.models import Base, engine

def init_db():
    Base.metadata.create_all(engine)
    print(f"✅ Database initialized")

if __name__ == "__main__":
    init_db()
