(function (root) {
    function parseInstant(value) {
        return value ? new Date(value) : null;
    }

    function parseDateOnly(value) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
        const [year, month, day] = value.split('-').map(Number);
        const date = new Date(year, month - 1, day);
        return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
    }

    root.shimTime = Object.freeze({ parseInstant, parseDateOnly });
    root.parseLocalDate = parseDateOnly;
})(typeof window === 'undefined' ? globalThis : window);