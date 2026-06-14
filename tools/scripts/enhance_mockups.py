import re
import os

def enhance_admin_mockup():
    file_path = 'design/ui-mockup/admin_mockup.html'
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    with open(file_path, 'r', encoding='utf-8') as f:
        html = f.read()
        
    # 1. Add Toast CSS to style block
    toast_css = """
        /* Toast Container */
        .toast-container { position: fixed; top: 1rem; right: 1rem; z-index: 9999; display: flex; flex-direction: column; gap: 0.5rem; pointer-events: none; }
        .shim-toast { display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 0.9rem; background-color: #fff; border: 1px solid #e2e8f0; border-radius: 0.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); font-size: 0.7rem; font-weight: 700; color: #1e293b; transform: translateX(120%); transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease; opacity: 0; pointer-events: auto; }
        .shim-toast.show { transform: translateX(0); opacity: 1; }
        .shim-toast-success { border-left: 4px solid #16a34a; }
        .shim-toast-info { border-left: 4px solid #2563eb; }
        .shim-toast-warning { border-left: 4px solid #ea580c; }
        .shim-toast-error { border-left: 4px solid #dc2626; }
"""
    if '.toast-container' not in html:
        html = html.replace('</style>', toast_css + '\n    </style>')
        
    # 2. Add JS helpers showToast and simulateButtonLoading
    js_helpers = """
    window.showToast = function(message, type = 'success') {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = `shim-toast shim-toast-${type}`;
        
        let icon = 'ℹ️';
        if (type === 'success') icon = '✅';
        if (type === 'warning') icon = '⚠️';
        if (type === 'error') icon = '❌';
        
        toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    };

    window.simulateButtonLoading = function(btn, callback, duration = 600) {
        if (!btn || btn.disabled) return;
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.innerHTML = `<span class="inline-block animate-spin mr-1">🔄</span> 처리 중...`;
        
        setTimeout(() => {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = originalHTML;
            if (callback) callback();
        }, duration);
    };
"""
    if 'window.showToast =' not in html:
        # Insert before the script DOMContentLoaded or window.onload
        html = html.replace('window.onload = function() {', js_helpers + '\n    window.onload = function() {')
        
    # 3. Replace alert(...) in script with showToast
    # Ignore commented lines and alert strings inside templates
    def repl_alert(match):
        content = match.group(1)
        type_str = 'success'
        if any(w in content for w in ['실패', '오류', '입력해야', '필수', '입력해 주세요']):
            type_str = 'error'
        elif any(w in content for w in ['경고', '주의', '기입 가능', '이미 다른', '지나간', '없습니다']):
            type_str = 'warning'
        elif any(w in content for w in ['이동', '진행', '내보내기']):
            type_str = 'info'
        return f"showToast({content}, '{type_str}')"
        
    html = re.sub(r'(?<!\/\/ )alert\((["`\'].*?["`\']|[^)]+?)\)', repl_alert, html)
    
    # 4. Wrap onclick handlers with simulateButtonLoading
    html = html.replace('onclick="addHolidaySetting()"', 'onclick="simulateButtonLoading(this, () => addHolidaySetting())"')
    html = html.replace('onclick="saveCalendarScope()"', 'onclick="simulateButtonLoading(this, () => saveCalendarScope())"')
    html = html.replace('onclick="saveBranding()"', 'onclick="simulateButtonLoading(this, () => saveBranding())"')
    html = html.replace('onclick="saveTimePolicy()"', 'onclick="simulateButtonLoading(this, () => saveTimePolicy())"')
    html = html.replace('onsubmit="submitBulkLeave(); return false;"', 'onsubmit="simulateButtonLoading(this.querySelector(\'button[type=submit]\'), () => submitBulkLeave()); return false;"')
    
    # Replace approvals table action buttons
    html = html.replace('onclick="adminApproveG(${leave.id})"', 'onclick="simulateButtonLoading(this, () => adminApproveG(${leave.id}))"')
    html = html.replace('onclick="adminRejectG(${leave.id})"', 'onclick="simulateButtonLoading(this, () => adminRejectG(${leave.id}))"')
    html = html.replace('onclick="adminCancelG(${leave.id})"', 'onclick="simulateButtonLoading(this, () => adminCancelG(${leave.id}))"')
    
    # 5. Make layout container flex-col lg:flex-row to support pivot monitors (narrow widths)
    html = html.replace('class="mx-auto flex w-full max-w-[92rem] flex-1 gap-4 px-4 py-6 sm:px-6 lg:gap-6 lg:px-8"', 'class="mx-auto flex flex-col lg:flex-row w-full max-w-[92rem] flex-1 gap-4 px-4 py-6 sm:px-6 lg:gap-6 lg:px-8"')
    html = html.replace('class="w-[240px] shrink-0 space-y-2 hidden md:block"', 'class="w-full lg:w-[240px] shrink-0 space-y-2 hidden md:block"')
    
    # 6. Add empty state visuals in rendering functions
    # User CRUD table
    html = html.replace('tbody.innerHTML = html;', '''
        if (!html) {
            html = `
                <tr>
                    <td colspan="7" class="px-4 py-12 text-center text-dense-muted font-semibold">
                        <div class="flex flex-col items-center justify-center gap-2">
                            <span class="text-3xl">👥</span>
                            <p class="text-xs font-bold text-dense-text">일치하는 사용자 정보가 존재하지 않습니다.</p>
                            <p class="text-[10px] text-dense-muted">검색어나 소속 필터 조건을 다시 확인해 주시기 바랍니다.</p>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;''')
        
    # Holiday list
    html = html.replace('container.innerHTML = html;', '''
        if (!html) {
            html = `
                <div class="flex flex-col items-center justify-center py-12 text-center gap-2">
                    <span class="text-3xl">📅</span>
                    <p class="text-xs font-bold text-dense-text">등록된 공휴일이 없습니다.</p>
                    <p class="text-[10px] text-dense-muted">새로운 공휴일을 등록하여 연차 신청 제한 일정을 관리해 보세요.</p>
                </div>
            `;
        }
        container.innerHTML = html;''')

    # Audit logs
    html = html.replace('tbody.innerHTML = html;\n    };', '''
        if (!html) {
            html = `
                <tr>
                    <td colspan="6" class="px-4 py-12 text-center text-dense-muted font-semibold">
                        <div class="flex flex-col items-center justify-center gap-2">
                            <span class="text-3xl">🔍</span>
                            <p class="text-xs font-bold text-dense-text">부합하는 감사 로그가 없습니다.</p>
                            <p class="text-[10px] text-dense-muted">수행자, 액션명 또는 기간 필터를 변경해 보세요.</p>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    };''')
    
    # Replace inline password reset / delete buttons inside user table render
    html = html.replace("onclick=\"updateUserAllocatedDays('${user.username}')\"", "onclick=\"simulateButtonLoading(this, () => updateUserAllocatedDays('${user.username}'))\"")
    html = html.replace("onclick=\"resetUserPassword('${user.username}')\"", "onclick=\"simulateButtonLoading(this, () => resetUserPassword('${user.username}'))\"")
    html = html.replace("onclick=\"toggleUserActive('${user.username}')\"", "onclick=\"simulateButtonLoading(this, () => toggleUserActive('${user.username}'))\"")
    html = html.replace("onclick=\"hardDeleteUser('${user.username}')\"", "onclick=\"simulateButtonLoading(this, () => hardDeleteUser('${user.username}'))\"")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("admin_mockup.html enhanced successfully.")


def enhance_option_g():
    file_path = 'design/ui-mockup/option_g.html'
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    with open(file_path, 'r', encoding='utf-8') as f:
        html = f.read()
        
    # 1. Add Toast CSS
    toast_css = """
        /* Toast Container */
        .toast-container { position: fixed; top: 1rem; right: 1rem; z-index: 9999; display: flex; flex-direction: column; gap: 0.5rem; pointer-events: none; }
        .shim-toast { display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 0.9rem; background-color: #fff; border: 1px solid #e2e8f0; border-radius: 0.5rem; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); font-size: 0.7rem; font-weight: 700; color: #1e293b; transform: translateX(120%); transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease; opacity: 0; pointer-events: auto; }
        .shim-toast.show { transform: translateX(0); opacity: 1; }
        .shim-toast-success { border-left: 4px solid #16a34a; }
        .shim-toast-info { border-left: 4px solid #2563eb; }
        .shim-toast-warning { border-left: 4px solid #ea580c; }
        .shim-toast-error { border-left: 4px solid #dc2626; }
"""
    if '.toast-container' not in html:
        html = html.replace('</style>', toast_css + '\n    </style>')
        
    # 2. Add JS helpers
    js_helpers = """
    window.showToast = function(message, type = 'success') {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = `shim-toast shim-toast-${type}`;
        
        let icon = 'ℹ️';
        if (type === 'success') icon = '✅';
        if (type === 'warning') icon = '⚠️';
        if (type === 'error') icon = '❌';
        
        toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    };

    window.simulateButtonLoading = function(btn, callback, duration = 600) {
        if (!btn || btn.disabled) return;
        const originalHTML = btn.innerHTML;
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.innerHTML = `<span class="inline-block animate-spin mr-1">🔄</span> 처리 중...`;
        
        setTimeout(() => {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = originalHTML;
            if (callback) callback();
        }, duration);
    };
"""
    if 'window.showToast =' not in html:
        html = html.replace("document.addEventListener('DOMContentLoaded', () => {", js_helpers + "\n    document.addEventListener('DOMContentLoaded', () => {")

    # 3. Replace alert(...) in script with showToast
    def repl_alert(match):
        content = match.group(1)
        type_str = 'success'
        if any(w in content for w in ['실패', '오류', '입력해야', '필수', '입력해 주세요', '없습니다']):
            type_str = 'error'
        elif any(w in content for w in ['경고', '주의', '기입 가능', '이미 다른', '지나간', '없습니다', '주말 및 공휴일']):
            type_str = 'warning'
        elif any(w in content for w in ['이동', '진행', '내보내기']):
            type_str = 'info'
        return f"showToast({content}, '{type_str}')"
        
    html = re.sub(r'(?<!\/\/ )alert\((["`\'].*?["`\']|[^)]+?)\)', repl_alert, html)

    # 4. Wrap onclick handlers with simulateButtonLoading
    html = html.replace('onclick="window.executeBulkApplyG()"', 'onclick="simulateButtonLoading(this, () => window.executeBulkApplyG())"')
    html = html.replace('onclick="applyLeaveG_Modal()"', 'onclick="simulateButtonLoading(this, () => applyLeaveG_Modal())"')
    html = html.replace('onclick="executeDirectApplyG(\'desktop\')"', 'onclick="simulateButtonLoading(this, () => executeDirectApplyG(\'desktop\'))"')
    html = html.replace('onclick="executeDirectApplyG(\'mobile\')"', 'onclick="simulateButtonLoading(this, () => executeDirectApplyG(\'mobile\'))"')
    
    # 5. Make layout container flex-col lg:flex-row to support pivot monitors (narrow widths)
    html = html.replace('class="hidden md:flex gap-5 fade-in"', 'class="hidden md:flex flex-col lg:flex-row gap-5 fade-in"')
    html = html.replace('class="w-[280px] shrink-0 space-y-4"', 'class="w-full lg:w-[280px] shrink-0 space-y-4"')
    
    # 6. Add empty states inside table renderers
    # My requests detailed view table empty check:
    html = html.replace('tbody.innerHTML = html;\n    }', '''
        if (!html) {
            html = `
                <tr>
                    <td colspan="6" class="px-4 py-12 text-center text-dense-muted font-semibold">
                        <div class="flex flex-col items-center justify-center gap-2">
                            <span class="text-3xl">📋</span>
                            <p class="text-xs font-bold text-dense-text">연차 신청 내역이 없습니다.</p>
                            <p class="text-[10px] text-dense-muted">캘린더에서 날짜를 긁거나(Drag) 개별 선택하여 연차를 등록해 보세요.</p>
                        </div>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    }''')
    
    # Wrap inline cancel action with loading state in option_g renderers
    html = html.replace("onclick=\"cancelLeaveG(${leave.id})\"", "onclick=\"simulateButtonLoading(this, () => cancelLeaveG(${leave.id}))\"")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("option_g.html enhanced successfully.")

if __name__ == '__main__':
    enhance_admin_mockup()
    enhance_option_g()
