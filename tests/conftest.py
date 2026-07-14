import os
import shutil

# app 모듈 import 전에 테스트 환경 강제 (settings는 import 시점에 로드됨)
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["REDIS_URL"] = ""  # 인메모리 토큰 저장소
os.environ["UPLOAD_DIR"] = "./test_uploads"
os.environ["MAX_FILE_SIZE"] = "1024"  # 413 테스트를 위해 1KB로 축소

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest.fixture(scope="session")
def client():
    if os.path.exists("./test.db"):
        os.remove("./test.db")
    shutil.rmtree("./test_uploads", ignore_errors=True)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    engine.dispose()
    if os.path.exists("./test.db"):
        os.remove("./test.db")
    shutil.rmtree("./test_uploads", ignore_errors=True)
