import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import styles from './CustomDatePicker.module.css';

const WEEKDAY_LABELS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

function getVietnamTodayIso() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const y = parts.find((p) => p.type === 'year')?.value || '2026';
  const m = parts.find((p) => p.type === 'month')?.value || '01';
  const d = parts.find((p) => p.type === 'day')?.value || '01';
  return `${y}-${m}-${d}`;
}

function parseIsoDate(iso) {
  if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso.trim())) {
    return null;
  }
  const [y, m, d] = iso.trim().split('-').map(Number);
  if (!y || m < 1 || m > 12 || d < 1 || d > 31) return null;
  return { year: y, month: m, day: d };
}

function formatIsoToVN(iso) {
  const parsed = parseIsoDate(iso);
  if (!parsed) return '';
  const dd = String(parsed.day).padStart(2, '0');
  const mm = String(parsed.month).padStart(2, '0');
  return `${dd}/${mm}/${parsed.year}`;
}

function toIsoString(year, month, day) {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function buildCalendarDays(viewYear, viewMonth) {
  const firstDayDate = new Date(Date.UTC(viewYear, viewMonth - 1, 1));
  // Convert Sunday=0..Saturday=6 into Monday=0..Sunday=6
  const startOffset = (firstDayDate.getUTCDay() + 6) % 7;
  const daysInMonth = new Date(Date.UTC(viewYear, viewMonth, 0)).getUTCDate();

  const prevMonthYear = viewMonth === 1 ? viewYear - 1 : viewYear;
  const prevMonth = viewMonth === 1 ? 12 : viewMonth - 1;
  const daysInPrevMonth = new Date(
    Date.UTC(prevMonthYear, prevMonth, 0)
  ).getUTCDate();

  const cells = [];
  for (let i = startOffset - 1; i >= 0; i -= 1) {
    const day = daysInPrevMonth - i;
    cells.push({
      iso: toIsoString(prevMonthYear, prevMonth, day),
      day,
      inCurrentMonth: false,
    });
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push({
      iso: toIsoString(viewYear, viewMonth, day),
      day,
      inCurrentMonth: true,
    });
  }

  const nextMonthYear = viewMonth === 12 ? viewYear + 1 : viewYear;
  const nextMonth = viewMonth === 12 ? 1 : viewMonth + 1;
  let nextDay = 1;
  while (cells.length % 7 !== 0) {
    cells.push({
      iso: toIsoString(nextMonthYear, nextMonth, nextDay),
      day: nextDay,
      inCurrentMonth: false,
    });
    nextDay += 1;
  }

  return cells;
}

/**
 * RetailOps themed CustomDatePicker:
 * - Full-box clickable trigger button (no tiny native calendar icon click target).
 * - Preserves a visually-hidden <input type="date"> for form & test compatibility.
 * - Renders a portal calendar popover synchronized with RetailOps Light & Dark themes.
 */
export default function CustomDatePicker({
  id,
  name,
  value = '',
  onChange,
  prefixLabel = '',
  placeholder = 'Tất cả các ngày',
  badgeText = '',
  ariaLabel = 'Chọn ngày',
  clearable = true,
  disabled = false,
  min = '',
  max = '',
  className = '',
}) {
  const reactId = useId();
  const popoverId = `custom-datepicker-${reactId}`;
  const todayIso = useMemo(() => getVietnamTodayIso(), []);
  const parsedValue = useMemo(() => parseIsoDate(value), [value]);
  const parsedToday = useMemo(
    () => parseIsoDate(todayIso) || { year: 2026, month: 11, day: 25 },
    [todayIso]
  );

  const [isOpen, setIsOpen] = useState(false);
  const [viewYear, setViewYear] = useState(
    parsedValue?.year ?? parsedToday.year
  );
  const [viewMonth, setViewMonth] = useState(
    parsedValue?.month ?? parsedToday.month
  );
  const [menuPosition, setMenuPosition] = useState(null);

  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);

  const emitDateChange = useCallback(
    (nextIso) => {
      if (typeof onChange === 'function') {
        onChange({
          target: {
            id: id || '',
            name: name || '',
            value: nextIso,
          },
        });
      }
    },
    [id, name, onChange]
  );

  const updatePopoverPosition = useCallback(() => {
    if (!triggerRef.current || typeof window === 'undefined') return;
    const rect = triggerRef.current.getBoundingClientRect();
    const viewportHeight = window.innerHeight || 800;
    const viewportWidth = window.innerWidth || 1280;
    const popoverWidth = 292;
    const estimatedHeight = 330;

    const spaceBelow = viewportHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;
    const openUpward = spaceBelow < estimatedHeight && spaceAbove > spaceBelow;

    const maxLeft = Math.max(8, viewportWidth - popoverWidth - 8);
    const left = Math.max(8, Math.min(rect.left, maxLeft));

    setMenuPosition({
      top: openUpward ? undefined : rect.bottom + 6,
      bottom: openUpward ? viewportHeight - rect.top + 6 : undefined,
      left,
    });
  }, []);

  const openPopover = useCallback(() => {
    if (disabled) return;
    const base = parseIsoDate(value) || parsedToday;
    setViewYear(base.year);
    setViewMonth(base.month);
    setIsOpen(true);
  }, [disabled, parsedToday, value]);

  const closePopover = useCallback(() => {
    setIsOpen(false);
  }, []);

  useEffect(() => {
    if (!isOpen) return undefined;
    updatePopoverPosition();

    const handlePointerDown = (event) => {
      const target = event.target;
      if (
        rootRef.current?.contains(target) ||
        popoverRef.current?.contains(target)
      ) {
        return;
      }
      closePopover();
    };

    const handleViewportUpdate = () => {
      updatePopoverPosition();
    };

    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closePopover();
        triggerRef.current?.focus();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('resize', handleViewportUpdate);
    window.addEventListener('scroll', handleViewportUpdate, true);
    document.addEventListener('keydown', handleEscape, true);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('resize', handleViewportUpdate);
      window.removeEventListener('scroll', handleViewportUpdate, true);
      document.removeEventListener('keydown', handleEscape, true);
    };
  }, [closePopover, isOpen, updatePopoverPosition]);

  const handleStepMonth = (delta) => {
    let nextM = viewMonth + delta;
    let nextY = viewYear;
    if (nextM < 1) {
      nextM = 12;
      nextY -= 1;
    } else if (nextM > 12) {
      nextM = 1;
      nextY += 1;
    }
    setViewYear(nextY);
    setViewMonth(nextM);
  };

  const isDateDisabled = useCallback(
    (iso) => {
      if (min && iso < min) return true;
      if (max && iso > max) return true;
      return false;
    },
    [max, min]
  );

  const calendarDays = useMemo(
    () => buildCalendarDays(viewYear, viewMonth),
    [viewMonth, viewYear]
  );

  const displayDateText = value ? formatIsoToVN(value) : placeholder;

  return (
    <div ref={rootRef} className={`${styles.datePickerRoot} ${className}`}>
      <input
        id={id}
        name={name}
        type="date"
        aria-label={ariaLabel}
        value={value || ''}
        min={min || undefined}
        max={max || undefined}
        disabled={disabled}
        tabIndex={-1}
        className={styles.srOnlyNativeDate}
        onChange={onChange}
      />

      <div
        ref={triggerRef}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls={isOpen ? popoverId : undefined}
        aria-disabled={disabled || undefined}
        className={`${styles.dateTrigger} ${
          isOpen ? styles.dateTriggerOpen : ''
        } ${disabled ? styles.dateTriggerDisabled : ''}`}
        onClick={() => (isOpen ? closePopover() : openPopover())}
        onKeyDown={(event) => {
          if (disabled) return;
          if (event.target !== event.currentTarget) return;
          if (
            event.key === 'Enter' ||
            event.key === ' ' ||
            event.key === 'ArrowDown'
          ) {
            event.preventDefault();
            if (isOpen) closePopover();
            else openPopover();
          }
        }}
      >
        <span className={styles.calendarIcon} aria-hidden="true">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        </span>

        {prefixLabel && (
          <span className={styles.prefixLabel}>{prefixLabel}</span>
        )}

        <span
          className={`${styles.dateValueText} ${
            !value ? styles.datePlaceholderText : ''
          }`}
        >
          {displayDateText}
        </span>

        {badgeText && <span className={styles.badgeInline}>{badgeText}</span>}

        {clearable && value && !disabled ? (
          <button
            type="button"
            className={styles.clearDateBtn}
            onClick={(event) => {
              event.stopPropagation();
              emitDateChange('');
              closePopover();
            }}
            aria-label="Xóa ngày đã chọn"
            title="Xóa ngày"
          >
            ×
          </button>
        ) : (
          <svg
            className={`${styles.chevronIcon} ${
              isOpen ? styles.chevronIconOpen : ''
            }`}
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        )}
      </div>

      {isOpen &&
        menuPosition &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={popoverRef}
            id={popoverId}
            role="dialog"
            aria-label="Bảng chọn ngày"
            className={styles.calendarPopover}
            style={{
              top:
                menuPosition.top !== undefined
                  ? `${menuPosition.top}px`
                  : undefined,
              bottom:
                menuPosition.bottom !== undefined
                  ? `${menuPosition.bottom}px`
                  : undefined,
              left: `${menuPosition.left}px`,
            }}
          >
            <div className={styles.calendarHeader}>
              <button
                type="button"
                className={styles.monthNavBtn}
                onClick={() => handleStepMonth(-1)}
                aria-label="Tháng trước"
              >
                ‹
              </button>
              <span className={styles.monthTitle}>
                Tháng {String(viewMonth).padStart(2, '0')}, {viewYear}
              </span>
              <button
                type="button"
                className={styles.monthNavBtn}
                onClick={() => handleStepMonth(1)}
                aria-label="Tháng sau"
              >
                ›
              </button>
            </div>

            <div className={styles.weekdayGrid}>
              {WEEKDAY_LABELS.map((w) => (
                <span key={w} className={styles.weekdayCell}>
                  {w}
                </span>
              ))}
            </div>

            <div className={styles.daysGrid}>
              {calendarDays.map((cell) => {
                const isSelected = cell.iso === value;
                const isToday = cell.iso === todayIso;
                const cellDisabled = isDateDisabled(cell.iso);
                return (
                  <button
                    key={cell.iso}
                    type="button"
                    disabled={cellDisabled}
                    className={`${styles.dayBtn} ${
                      !cell.inCurrentMonth ? styles.dayBtnOutside : ''
                    } ${isToday && !isSelected ? styles.dayBtnToday : ''} ${
                      isSelected ? styles.dayBtnSelected : ''
                    }`}
                    onClick={() => {
                      emitDateChange(cell.iso);
                      closePopover();
                      triggerRef.current?.focus();
                    }}
                  >
                    {cell.day}
                  </button>
                );
              })}
            </div>

            <div className={styles.calendarFooter}>
              <button
                type="button"
                className={styles.footerClearBtn}
                onClick={() => {
                  emitDateChange('');
                  closePopover();
                  triggerRef.current?.focus();
                }}
              >
                Xóa ngày
              </button>
              <button
                type="button"
                className={styles.footerTodayBtn}
                disabled={isDateDisabled(todayIso)}
                onClick={() => {
                  emitDateChange(todayIso);
                  closePopover();
                  triggerRef.current?.focus();
                }}
              >
                Hôm nay
              </button>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
