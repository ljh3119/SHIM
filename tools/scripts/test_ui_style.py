from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def require(text: str, expected: str, label: str) -> None:
    assert expected in text, f"{label}: 필수 스타일이 없습니다: {expected}"


def forbid(text: str, forbidden: str, label: str) -> None:
    assert forbidden not in text, f"{label}: 이전 스타일이 남아 있습니다: {forbidden}"


def main() -> int:
    app_css = read("src/static/css/app.css")
    compiled_css = read("src/static/css/tailwind.css")
    base = read("src/templates/base.html")
    dashboard = read("src/templates/admin_dashboard.html")
    admin_calendar = read("src/templates/admin_leaves_calendar.html")
    admin_timeline = read("src/templates/partials/admin_leaves_timeline_partial.html")
    holidays = read("src/templates/admin_holidays.html")
    user_calendar = read("src/templates/user_calendar.html")
    team_calendar = read("src/templates/user_team_calendar.html")
    history = read("src/templates/user_history.html")
    approvals = read("src/templates/user_approvals.html")

    require(
        app_css,
        "--color-dense-grid: rgb(208 213 221 / 0.55);",
        "공통 토큰",
    )
    require(base, "border: 1px solid var(--color-dense-line);", "공통 패널")
    require(compiled_css, ".border-dense-grid", "Tailwind border 유틸리티")
    require(compiled_css, ".divide-dense-grid", "Tailwind divide 유틸리티")

    for label, template in (
        ("관리자 캘린더", admin_calendar),
        ("사용자 캘린더", user_calendar),
        ("팀 캘린더", team_calendar),
    ):
        require(template, "var(--color-dense-grid)", label)
        forbid(template, "#d0d5dd", label)

    require(dashboard, "grid: { color: denseGridColor }", "대시보드 차트")
    assert dashboard.count("grid: { color: denseGridColor }") == 2
    forbid(dashboard, "rgba(208, 213, 221, 0.3)", "대시보드 차트")

    for label, template in (
        ("관리자 캘린더", admin_calendar),
        ("관리자 타임라인", admin_timeline),
        ("개인 캘린더", user_calendar),
        ("팀 일정", team_calendar),
        ("신청 내역", history),
        ("결재 관리", approvals),
    ):
        forbid(template, "rounded-[18px]", label)
        require(
            template,
            "rounded-2xl border border-dense-line bg-dense-surface",
            f"{label} PC 패널",
        )

    require(
        holidays,
        "rounded-2xl border border-dense-line bg-dense-surface",
        "공휴일 주요 패널",
    )
    require(
        holidays,
        "w-24 rounded-xl border border-dense-line",
        "공휴일 연도 선택기",
    )
    require(
        holidays,
        "rounded-xl border border-dense-grid bg-dense-surface-soft",
        "공휴일 내부 행",
    )

    for label, template in (
        ("개인 캘린더", user_calendar),
        ("팀 일정", team_calendar),
        ("신청 내역", history),
        ("결재 관리", approvals),
    ):
        require(
            template,
            "rounded-xl border border-dense-line bg-dense-surface",
            f"{label} 모바일 주요 카드",
        )
        require(template, "border-dense-grid", f"{label} 내부 구분선")

    require(
        team_calendar,
        "border-dense-grid bg-dense-surface-soft p-3",
        "동적 팀 일정 행",
    )
    require(base, "border-t border-dense-grid bg-dense-surface-soft", "공통 모달 푸터")
    require(
        user_calendar,
        "border-t border-dense-grid bg-dense-surface-soft",
        "신청 모달 푸터",
    )
    require(
        team_calendar,
        "border-t border-dense-grid bg-dense-surface-soft",
        "팀 신청 모달 푸터",
    )

    # 의미가 있는 상태·선택·위험 표현은 일반 그리드 토큰으로 덮지 않습니다.
    require(user_calendar, "border-red-100", "선택 불가 날짜")
    require(team_calendar, "border-bottom: 2px solid #175cd3", "팀 일정 선택선")
    require(approvals, "border-dense-amber/20", "결재 선택 상태")
    require(history, "border border-[#abefc6]", "승인 상태")
    require(
        admin_timeline,
        "changeStatus({{ leave.id }}, this, 'CANCELED')",
        "관리자 승인 취소 버튼",
    )
    require(admin_timeline, "min-w-[11rem]", "관리자 타임라인 관리 열")
    require(admin_timeline, "grid-cols-3", "관리자 작업 버튼 고정 열")
    require(admin_timeline, 'aria-hidden="true"', "관리자 취소 버튼 빈 열")
    require(admin_timeline, "취소</button>", "관리자 승인 취소 라벨")
    require(admin_timeline, "삭제</button>", "관리자 삭제 라벨")
    require(
        admin_calendar,
        "previousStatus === 'APPROVED' && newStatus === 'CANCELED'",
        "관리자 승인 취소 확인",
    )


    for label, template in (
        ("관리자 캘린더", admin_calendar),
        ("관리자 타임라인", admin_timeline),
        ("사용자 캘린더", user_calendar),
        ("팀 일정", team_calendar),
        ("신청 내역", history),
        ("결재 관리", approvals),
    ):
        forbid(template, "border-b pb-", label)
        forbid(template, "border-t border-dense-line bg-dense-surface-soft", label)
        forbid(template, "divide-y divide-dense-line", label)

    print("PASS: 관리자·사용자 UI 패널 및 테두리 계층 검증")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
