export const VN_TIMEZONE = 'Asia/Ho_Chi_Minh';

export const DASHBOARD_PRESETS = Object.freeze({
  TODAY: 'today',
  LAST_7_DAYS: 'last7Days',
  LAST_30_DAYS: 'last30Days',
  THIS_MONTH: 'thisMonth',
  CUSTOM: 'custom',
});

const vnDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: VN_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const vnDisplayDateFormatter = new Intl.DateTimeFormat('vi-VN', {
  timeZone: VN_TIMEZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const vnDisplayDateTimeFormatter = new Intl.DateTimeFormat('vi-VN', {
  timeZone: VN_TIMEZONE,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const VI_WEEKDAYS = [
  'Chủ Nhật',
  'Thứ Hai',
  'Thứ Ba',
  'Thứ Tư',
  'Thứ Năm',
  'Thứ Sáu',
  'Thứ Bảy',
];

/**
 * Returns today's calendar date (YYYY-MM-DD) in Asia/Ho_Chi_Minh.
 */
export function getVietnamTodayIsoDate(now = new Date()) {
  return vnDateFormatter.format(now);
}

/**
 * Shifts a YYYY-MM-DD calendar date by deltaDays without local-timezone drift.
 */
export function shiftIsoDate(isoDate, deltaDays) {
  const [y, m, d] = String(isoDate).split('-').map(Number);
  const utc = Date.UTC(y, m - 1, d + deltaDays);
  const dt = new Date(utc);
  const year = dt.getUTCFullYear();
  const month = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const day = String(dt.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Formats YYYY-MM-DD as DD/MM/YYYY.
 */
export function formatIsoDateShortVN(isoDate, includeYear = true) {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(String(isoDate))) return '—';
  const [y, m, d] = String(isoDate).split('-');
  return includeYear ? `${d}/${m}/${y}` : `${d}/${m}`;
}

/**
 * Formats YYYY-MM-DD with Vietnamese weekday label, e.g. "04/11/2026 (Thứ Tư - Hôm nay)".
 */
export function formatIsoDateWithWeekdayVN(isoDate, todayIso) {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(String(isoDate))) return '—';
  const [y, m, d] = String(isoDate).split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const weekday = VI_WEEKDAYS[dt.getUTCDay()];
  const base = formatIsoDateShortVN(isoDate, true);
  if (todayIso && isoDate === todayIso) {
    return `${base} (${weekday} - Hôm nay)`;
  }
  return `${base} (${weekday})`;
}

/**
 * Resolves { from, to, label } YYYY-MM-DD bounds for a preset or custom date range.
 */
export function resolveDashboardDateRange(preset, customRange = {}, now = new Date()) {
  const today = getVietnamTodayIsoDate(now);

  if (preset === DASHBOARD_PRESETS.TODAY) {
    return {
      from: today,
      to: today,
      badgeLabel: 'Hôm nay',
      periodLabel: `Hôm nay (${formatIsoDateShortVN(today)})`,
      error: '',
    };
  }
  if (preset === DASHBOARD_PRESETS.LAST_7_DAYS) {
    const from = shiftIsoDate(today, -6);
    return {
      from,
      to: today,
      badgeLabel: 'Kỳ 7 ngày',
      periodLabel: `7 ngày gần nhất (${formatIsoDateShortVN(from)} - ${formatIsoDateShortVN(today)})`,
      error: '',
    };
  }
  if (preset === DASHBOARD_PRESETS.LAST_30_DAYS) {
    const from = shiftIsoDate(today, -29);
    return {
      from,
      to: today,
      badgeLabel: 'Kỳ 30 ngày',
      periodLabel: `Kỳ 30 ngày qua (${formatIsoDateShortVN(from)} - ${formatIsoDateShortVN(today)})`,
      error: '',
    };
  }
  if (preset === DASHBOARD_PRESETS.THIS_MONTH) {
    const from = `${today.slice(0, 7)}-01`;
    return {
      from,
      to: today,
      badgeLabel: 'Tháng này',
      periodLabel: `Tháng này (${formatIsoDateShortVN(from)} - ${formatIsoDateShortVN(today)})`,
      error: '',
    };
  }
  if (preset === DASHBOARD_PRESETS.CUSTOM) {
    const from = String(customRange.from || '').trim();
    const to = String(customRange.to || '').trim();
    if (!from || !to) {
      return {
        from,
        to,
        badgeLabel: 'Tùy chọn',
        periodLabel: '',
        error: 'Vui lòng chọn đầy đủ ngày bắt đầu và ngày kết thúc.',
      };
    }
    if (from > to) {
      return {
        from,
        to,
        badgeLabel: 'Tùy chọn',
        periodLabel: '',
        error: 'Ngày bắt đầu không được lớn hơn ngày kết thúc.',
      };
    }
    return {
      from,
      to,
      badgeLabel: 'Tùy chọn',
      periodLabel: `${formatIsoDateShortVN(from)} - ${formatIsoDateShortVN(to)}`,
      error: '',
    };
  }

  return {
    from: today,
    to: today,
    badgeLabel: 'Hôm nay',
    periodLabel: `Hôm nay (${formatIsoDateShortVN(today)})`,
    error: '',
  };
}

/**
 * Returns { from, to } YYYY-MM-DD bounds for the full previous calendar month in Asia/Ho_Chi_Minh.
 */
export function getPreviousMonthDateRange(now = new Date()) {
  const today = getVietnamTodayIsoDate(now);
  const [y, m] = today.split('-').map(Number);
  const firstOfCurrentMonthUtc = Date.UTC(y, m - 1, 1);
  const lastOfPrevMonth = new Date(firstOfCurrentMonthUtc - 86400000);
  const prevYear = lastOfPrevMonth.getUTCFullYear();
  const prevMonth = String(lastOfPrevMonth.getUTCMonth() + 1).padStart(2, '0');
  const prevLastDay = String(lastOfPrevMonth.getUTCDate()).padStart(2, '0');
  return {
    from: `${prevYear}-${prevMonth}-01`,
    to: `${prevYear}-${prevMonth}-${prevLastDay}`,
  };
}

/**
 * Computes month-over-month percentage change between current and previous month values.
 */
export function computeMonthOverMonthDelta(currentVal = 0, prevVal = 0) {
  const curr = typeof currentVal === 'number' && Number.isFinite(currentVal) ? currentVal : 0;
  const prev = typeof prevVal === 'number' && Number.isFinite(prevVal) ? prevVal : 0;

  if (prev === 0 && curr === 0) {
    return {
      diffPct: 0,
      direction: 'neutral',
      text: '0% so với tháng trước',
    };
  }
  if (prev === 0 && curr > 0) {
    return {
      diffPct: 100,
      direction: 'up',
      text: '+100% so với tháng trước',
    };
  }
  const rawPct = ((curr - prev) / prev) * 100;
  const rounded = Math.round(rawPct * 10) / 10;
  const sign = rounded > 0 ? '+' : '';
  const direction = rounded > 0 ? 'up' : rounded < 0 ? 'down' : 'neutral';
  const formatted = String(rounded).replace('.', ',');
  return {
    diffPct: rounded,
    direction,
    text: `${sign}${formatted}% so với tháng trước`,
  };
}

/**
 * Builds chronological buckets for the trend chart and breakdown table:
 * - TODAY / LAST_7_DAYS: 7 daily buckets (today - 6 .. today)
 * - LAST_30_DAYS: 5 non-overlapping weekly/segment buckets covering (today - 29 .. today)
 * - THIS_MONTH: 1..5 weekly buckets from day 01 of current month up to today
 */
export function buildDashboardSeriesBuckets(preset, now = new Date()) {
  const today = getVietnamTodayIsoDate(now);

  if (preset === DASHBOARD_PRESETS.TODAY || preset === DASHBOARD_PRESETS.LAST_7_DAYS) {
    const buckets = [];
    for (let offset = -6; offset <= 0; offset += 1) {
      const iso = shiftIsoDate(today, offset);
      buckets.push({
        key: iso,
        from: iso,
        to: iso,
        isToday: offset === 0,
        chartLabel: formatIsoDateShortVN(iso, false),
        tableLabel: formatIsoDateWithWeekdayVN(iso, today),
      });
    }
    return buckets;
  }

  if (preset === DASHBOARD_PRESETS.LAST_30_DAYS) {
    const segments = [
      { startOffset: -29, endOffset: -28, prefix: 'Đầu kỳ' },
      { startOffset: -27, endOffset: -21, prefix: 'Tuần 2' },
      { startOffset: -20, endOffset: -14, prefix: 'Tuần 3' },
      { startOffset: -13, endOffset: -7, prefix: 'Tuần 4' },
      { startOffset: -6, endOffset: 0, prefix: 'Tuần 5' },
    ];
    return segments.map((seg, idx) => {
      const from = shiftIsoDate(today, seg.startOffset);
      const to = shiftIsoDate(today, seg.endOffset);
      const shortRange = `${formatIsoDateShortVN(from, false)}-${formatIsoDateShortVN(to, false)}`;
      const fullRange = `${formatIsoDateShortVN(from, false)} - ${formatIsoDateShortVN(to, true)}`;
      return {
        key: `30d-${idx + 1}-${from}`,
        from,
        to,
        isToday: seg.endOffset === 0,
        chartLabel: shortRange,
        tableLabel: `${seg.prefix}: ${fullRange}`,
      };
    });
  }

  if (preset === DASHBOARD_PRESETS.THIS_MONTH) {
    const yearMonth = today.slice(0, 7);
    const currentDay = Number(today.slice(8, 10));
    const weekRanges = [
      [1, 7],
      [8, 14],
      [15, 21],
      [22, 28],
      [29, 31],
    ];
    const buckets = [];
    weekRanges.forEach(([startDay, endDay], idx) => {
      if (startDay > currentDay) return;
      const clampedEnd = Math.min(endDay, currentDay);
      const from = `${yearMonth}-${String(startDay).padStart(2, '0')}`;
      const to = `${yearMonth}-${String(clampedEnd).padStart(2, '0')}`;
      const shortRange =
        from === to
          ? formatIsoDateShortVN(from, false)
          : `${formatIsoDateShortVN(from, false)}-${formatIsoDateShortVN(to, false)}`;
      const fullRange =
        from === to
          ? formatIsoDateShortVN(from, true)
          : `${formatIsoDateShortVN(from, false)} - ${formatIsoDateShortVN(to, true)}`;
      buckets.push({
        key: `month-w${idx + 1}-${from}`,
        from,
        to,
        isToday: clampedEnd === currentDay,
        chartLabel: shortRange,
        tableLabel: `Tuần ${idx + 1}: ${fullRange}`,
      });
    });
    return buckets;
  }

  return [];
}

/**
 * Computes completion & cancellation percentages for the Order Breakdown Donut card.
 */
export function computeOrderStructureMetrics(completedOrders = 0, cancelledOrders = 0) {
  const completed = Number.isInteger(completedOrders) && completedOrders > 0 ? completedOrders : 0;
  const cancelled = Number.isInteger(cancelledOrders) && cancelledOrders > 0 ? cancelledOrders : 0;
  const total = completed + cancelled;
  if (total === 0) {
    return {
      total: 0,
      completed: 0,
      cancelled: 0,
      completedPct: 0,
      cancelledPct: 0,
      completedPctLabel: '0%',
      cancelledPctLabel: '0%',
    };
  }
  const completedPctRaw = (completed / total) * 100;
  const cancelledPctRaw = 100 - completedPctRaw;
  const formatPct = (val) => {
    const rounded = Math.round(val * 10) / 10;
    return `${String(rounded).replace('.', ',')}%`;
  };
  return {
    total,
    completed,
    cancelled,
    completedPct: completedPctRaw,
    cancelledPct: cancelledPctRaw,
    completedPctLabel: formatPct(completedPctRaw),
    cancelledPctLabel: formatPct(cancelledPctRaw),
  };
}

/**
 * Formats an exclusive [period_start, period_end_exclusive) range in Asia/Ho_Chi_Minh.
 */
export function formatVietnamPeriodRange(periodStartIso, periodEndExclusiveIso) {
  if (!periodStartIso || !periodEndExclusiveIso) return '—';
  const startMs = Date.parse(periodStartIso);
  const endExclusiveMs = Date.parse(periodEndExclusiveIso);
  if (Number.isNaN(startMs) || Number.isNaN(endExclusiveMs)) return '—';

  const startLabel = vnDisplayDateFormatter.format(new Date(startMs));
  const inclusiveEndMs = endExclusiveMs > startMs ? endExclusiveMs - 1 : endExclusiveMs;
  const endLabel = vnDisplayDateFormatter.format(new Date(inclusiveEndMs));

  return startLabel === endLabel ? startLabel : `${startLabel} – ${endLabel}`;
}

/**
 * Formats an ISO timestamp into DD/MM/YYYY HH:mm in Asia/Ho_Chi_Minh.
 */
export function formatVietnamDateTime(isoTimestamp) {
  if (!isoTimestamp) return '—';
  const ms = Date.parse(isoTimestamp);
  if (Number.isNaN(ms)) return '—';
  return vnDisplayDateTimeFormatter.format(new Date(ms));
}

/**
 * Computes bar width percentage (0..100) for horizontal comparison bars.
 */
export function computeProductBarPercent(value, maxValue) {
  if (typeof value !== 'number' || typeof maxValue !== 'number' || maxValue <= 0 || value <= 0) {
    return 0;
  }
  const pct = Math.round((value / maxValue) * 100);
  return Math.max(0, Math.min(100, pct));
}

/**
 * Stale-response & unmount guard for async Dashboard fetches.
 */
export async function executeGuardedDashboardFetch({
  seqRef,
  isMountedRef,
  fetcher,
  onSuccess,
  onError,
  onFinally,
}) {
  const reqId = ++seqRef.current;
  const isStale = () => (isMountedRef && !isMountedRef.current) || seqRef.current !== reqId;

  try {
    const result = await fetcher();
    if (isStale()) return { status: 'stale', reqId };
    onSuccess?.(result);
    return { status: 'applied', reqId, result };
  } catch (error) {
    if (isStale()) return { status: 'stale', reqId };
    onError?.(error);
    return { status: 'error', reqId, error };
  } finally {
    if (!isStale()) {
      onFinally?.();
    }
  }
}
