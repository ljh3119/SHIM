from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, model_serializer
from src.app.utils import get_timezone_offset_hours

class BaseKSTResponse(BaseModel):
    """모든 datetime 필드를 KST(또는 환경변수 기준) ISO 8601 규격 문자열로 자동 포맷팅하는 래퍼 모델"""
    
    @model_serializer(mode="wrap")
    def serialize_datetime_to_kst_iso(self, handler) -> dict:
        # 1. Pydantic 기본 직렬화 수행
        serialized_data = handler(self)
        
        # 2. 런타임에 오프셋 계산하여 타임존 객체 생성
        offset = get_timezone_offset_hours()
        local_tz = timezone(timedelta(hours=offset))
        
        # 3. 모델 필드를 스캔하여 datetime 필드만 타임존 보정 가공
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, datetime) and field_name in serialized_data:
                # Naive datetime(시간대 정보 없음)은 UTC 기준으로 판단하여 타임존 객체 이식
                if field_value.tzinfo is None:
                    utc_dt = field_value.replace(tzinfo=timezone.utc)
                else:
                    utc_dt = field_value
                
                # UTC 기준 시각을 KST 시각으로 명시 변환
                kst_dt = utc_dt.astimezone(local_tz)
                
                # 초 단위까지 포함하는 ISO 8601 형식 문자열로 직렬화 데이터를 교체
                serialized_data[field_name] = kst_dt.isoformat(timespec="seconds")
                
        return serialized_data
