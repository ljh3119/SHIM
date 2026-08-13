FROM python:3.12-slim

# 타임존 설정 (기본값: UTC) 및 런타임 캐시·출력 정책
ENV TZ=UTC \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 폐쇄망 배포 시, 로컬 디렉토리(wheels/)를 만들어 미리 다운받은 pip 파일들을 복사한 뒤 --no-index 옵션으로 설치 할 수 있습니다. 
# 본 데모에서는 표준 설치를 사용합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 실행에 필요한 애플리케이션과 DB 초기화 코드만 포함
COPY src ./src
COPY tools/scripts/db_init.py ./tools/scripts/db_init.py
COPY LICENSE ./LICENSE

# Tailwind CSS 로컬 빌드 결과물이나 SQLite는 빌드나 런타임에 맞춰 자동 동기화
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).close()"]

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
