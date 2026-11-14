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

    # 1. C Baseline 공통 토큰 검증
    require(
        app_css,
        "--color-dense-grid: oklch(85.5% 0.011 88);",
        "공통 토큰",
    )
    require(app_css, "border: 1px solid var(--color-rule);", "공통 패널")
    require(compiled_css, ".border-dense-line", "Tailwind border 유틸리티")

    require(admin_calendar, "var(--color-dense-line)", "관리자 캘린더")
    require(user_calendar, "var(--color-rule)", "사용자 캘린더")
    require(team_calendar, "var(--color-rule)", "팀 캘린더")
    forbid(admin_calendar, "#d0d5dd", "관리자 캘린더")
    forbid(user_calendar, "#d0d5dd", "사용자 캘린더")
    forbid(team_calendar, "#d0d5dd", "팀 캘린더")

    # 2. 대시보드 차트 그리드 색상
    require(dashboard, "grid: { color: denseGridColor }", "대시보드 차트")
    assert dashboard.count("grid: { color: denseGridColor }") == 2
    forbid(dashboard, "rgba(208, 213, 221, 0.3)", "대시보드 차트")

    # 3. C Baseline 모서리 반경 검증 (PC 메인 패널: rounded-[6px])
    for label, template in (
        ("관리자 캘린더", admin_calendar),
        ("관리자 타임라인", admin_timeline),
        ("개인 캘린더", user_calendar),
        ("팀 일정", team_calendar),
        ("신청 내역", history),
        ("결재 관리", approvals),
    ):
        forbid(template, "rounded-[18px]", label)
        forbid(template, "rounded-2xl", label)
        require(
            template,
            "rounded-[6px] border border-dense-line bg-dense-surface",
            f"{label} PC 패널",
        )

    # 4. 공휴일 패널 모서리 (6px / 4px / 4px)
    require(
        holidays,
        "rounded-[6px] border border-dense-line bg-dense-surface",
        "공휴일 주요 패널",
    )
    require(
        holidays,
        "w-24 rounded-[4px] border border-field-edge",
        "공휴일 연도 선택기",
    )
    require(
        holidays,
        "rounded-[4px] border border-dense-line bg-dense-surface",
        "공휴일 내부 행",
    )

    # 5. 모바일 주요 카드 (C Baseline: rounded-[4px])
    for label, template in (
        ("개인 캘린더", user_calendar),
        ("팀 일정", team_calendar),
        ("신청 내역", history),
        ("결재 관리", approvals),
    ):
        require(
            template,
            "rounded-[4px] border border-dense-line bg-dense-surface",
            f"{label} 모바일 주요 카드",
        )
        require(template, "border-dense-line", f"{label} 내부 구분선")

    # 6. 모달 푸터 및 일정 구분선
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

    # 7. 상태 및 선택 표기 검증 (행위 보존)
    require(user_calendar, "border-red-100", "선택 불가 날짜")
    require(team_calendar, "border-bottom: 2px solid var(--color-accent)", "팀 일정 선택선")
    require(approvals, "border-dense-amber/20", "결재 선택 상태")
    require(history, "border-dense-green/20", "승인 상태")
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
        forbid(template, "rounded-2xl", label)
        forbid(template, "rounded-[18px]", label)

    print("PASS: 관리자·사용자 UI 패널 및 테두리 계층 검증 (C BASELINE 기준)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
