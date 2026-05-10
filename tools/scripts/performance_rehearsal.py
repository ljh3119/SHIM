from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import httpx


DEFAULT_ENDPOINTS = (
    ("admin_dashboard", "/admin/dashboard"),
    ("admin_timeline_all", "/admin/leave/timeline"),
    ("admin_calendar_month", "/admin/leave/calendar?view=month"),
    ("admin_calendar_year", "/admin/leave/calendar?view=year"),
)


@dataclass
class EndpointResult:
    name: str
    path: str
    status_code: int | None
    timings_ms: list[float]
    error: str = ""

    @property
    def avg_ms(self) -> float:
        return statistics.fmean(self.timings_ms) if self.timings_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.timings_ms) if self.timings_ms else 0.0


def parse_endpoint(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        name = raw.strip("/").replace("/", "_").replace("?", "_") or "root"
        return name, raw
    name, path = raw.split("=", 1)
    return name.strip(), path.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure authenticated admin page response times for SHIM operational rehearsal.",
    )
    parser.add_argument("--base-url", default=os.getenv("SHIM_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--admin-id", default=os.getenv("SHIM_ADMIN_ID", "admin"))
    parser.add_argument("--password", default=os.getenv("SHIM_ADMIN_PASSWORD", "0000"))
    parser.add_argument("--repeat", type=int, default=int(os.getenv("SHIM_PERF_REPEAT", "5")))
    parser.add_argument("--warmup", type=int, default=int(os.getenv("SHIM_PERF_WARMUP", "1")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("SHIM_PERF_TIMEOUT", "10")))
    parser.add_argument("--threshold-sec", type=float, default=float(os.getenv("SHIM_PERF_THRESHOLD_SEC", "3")))
    parser.add_argument(
        "--endpoint",
        action="append",
        default=[],
        help="Additional or replacement endpoint in name=/path format. If provided, defaults are not used.",
    )
    return parser


def login(client: httpx.Client, admin_id: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"user_id": admin_id, "password": password},
        follow_redirects=False,
    )
    if response.status_code not in (302, 303):
        raise RuntimeError(f"login failed: status={response.status_code}")
    if "access_token" not in client.cookies:
        raise RuntimeError("login failed: access_token cookie was not set")


def measure_endpoint(
    client: httpx.Client,
    name: str,
    path: str,
    repeat: int,
    warmup: int,
) -> EndpointResult:
    status_code: int | None = None
    timings_ms: list[float] = []

    try:
        for _ in range(warmup):
            response = client.get(path, follow_redirects=False)
            status_code = response.status_code
            if response.status_code != 200:
                return EndpointResult(name, path, status_code, timings_ms, f"warmup returned {response.status_code}")

        for _ in range(repeat):
            started = time.perf_counter()
            response = client.get(path, follow_redirects=False)
            elapsed_ms = (time.perf_counter() - started) * 1000
            status_code = response.status_code
            if response.status_code != 200:
                return EndpointResult(name, path, status_code, timings_ms, f"request returned {response.status_code}")
            timings_ms.append(elapsed_ms)
    except httpx.HTTPError as exc:
        return EndpointResult(name, path, status_code, timings_ms, str(exc))

    return EndpointResult(name, path, status_code, timings_ms)


def print_results(results: list[EndpointResult], threshold_sec: float, repeat: int) -> bool:
    threshold_ms = threshold_sec * 1000
    all_passed = True

    print("SHIM performance rehearsal")
    print(f"timestamp={datetime.now().isoformat(timespec='seconds')}")
    print(f"repeat={repeat} threshold_ms={threshold_ms:.0f}")
    print("")
    print("| endpoint | status | avg_ms | max_ms | result |")
    print("|---|---:|---:|---:|---|")

    for result in results:
        if result.error:
            all_passed = False
            outcome = f"FAIL ({result.error})"
        elif result.max_ms > threshold_ms:
            all_passed = False
            outcome = "FAIL (threshold)"
        else:
            outcome = "PASS"
        status = result.status_code if result.status_code is not None else "-"
        print(f"| {result.name} | {status} | {result.avg_ms:.1f} | {result.max_ms:.1f} | {outcome} |")

    print("")
    return all_passed


def main() -> int:
    args = build_parser().parse_args()

    if args.repeat <= 0:
        print("--repeat must be greater than 0", file=sys.stderr)
        return 2
    if args.warmup < 0:
        print("--warmup must be 0 or greater", file=sys.stderr)
        return 2

    endpoints = [parse_endpoint(item) for item in args.endpoint] if args.endpoint else list(DEFAULT_ENDPOINTS)
    base_url = args.base_url.rstrip("/") + "/"

    try:
        with httpx.Client(base_url=base_url, timeout=args.timeout) as client:
            login(client, args.admin_id, args.password)
            results = [
                measure_endpoint(client, name, urljoin("/", path.lstrip("/")), args.repeat, args.warmup)
                for name, path in endpoints
            ]
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"performance rehearsal failed: {exc}", file=sys.stderr)
        return 1

    return 0 if print_results(results, args.threshold_sec, args.repeat) else 1


if __name__ == "__main__":
    raise SystemExit(main())
