import re
import ipaddress
from urllib.parse import urlparse
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class ClosedNetworkCORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, origins_raw: str):
        super().__init__(app)
        self.allowed_patterns = []
        self.allowed_subnets = []
        
        # 쉼표 구분자로 IP 및 와일드카드 도메인 파싱
        for origin in (origins_raw or "").split(","):
            origin = origin.strip()
            if not origin:
                continue
                
            parsed = urlparse(origin)
            netloc_host = parsed.netloc.split(":")[0]  # 포트 정보 제외 호스트 추출
            path = parsed.path
            
            # 만약 path가 /CIDR 형태(예: /24)라면 netloc_host 뒤에 붙여서 서브넷 구성
            full_host = netloc_host
            if path and re.match(r"^/\d+$", path):
                full_host = f"{netloc_host}{path}"
            
            # 1. IP 대역 서브넷 분석 시도 (예: 192.168.10.0/24)
            try:
                subnet = ipaddress.ip_network(full_host, strict=False)
                self.allowed_subnets.append((parsed.scheme, subnet))
            except ValueError:
                # 2. 정규식 변환 처리 (예: http://*.local -> ^http://.*\.local$)
                regex_str = "^" + re.escape(origin).replace(r"\*", ".*") + "$"
                self.allowed_patterns.append(re.compile(regex_str))

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if not origin:
            return await call_next(request)
            
        allowed = False
        parsed_origin = urlparse(origin)
        origin_ip = parsed_origin.netloc.split(":")[0]
        
        # 패턴 1: 정규식/와일드카드 대조
        for pattern in self.allowed_patterns:
            if pattern.match(origin):
                allowed = True
                break
                
        # 패턴 2: CIDR 서브넷 대조
        if not allowed:
            for scheme, subnet in self.allowed_subnets:
                if parsed_origin.scheme == scheme:
                    try:
                        ip_addr = ipaddress.ip_address(origin_ip)
                        if ip_addr in subnet:
                            allowed = True
                            break
                    except ValueError:
                        pass

        if allowed:
            # 브라우저 Preflight OPTIONS 요청 즉시 대응
            if request.method == "OPTIONS":
                response = Response(status_code=204)
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Cookie"
                response.headers["Access-Control-Max-Age"] = "86400"
                return response
                
            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
            
        return await call_next(request)
