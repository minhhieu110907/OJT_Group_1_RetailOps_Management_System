import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import styles from './CustomSelect.module.css';

/**
 * Shared accessible & theme-aware CustomSelect component for RetailOps.
 * - Renders a visually-hidden native <select> so <label htmlFor>, getByLabelText,
 *   form required validation, and synthetic onChange({ target: { name, value } })
 *   remain 100% compatible with native HTML forms and automated tests.
 * - Renders a custom portal listbox with rounded corners, emerald checkmark,
 *   full Light/Dark theme support, keyboard navigation, and automatic quick search
 *   when options exceed searchThreshold (default: 6).
 */
export default function CustomSelect({
  id,
  name,
  value = '',
  onChange,
  options = [],
  disabled = false,
  required = false,
  ariaLabel,
  title,
  placeholder,
  searchable,
  searchThreshold = 6,
  searchPlaceholder = 'Tìm nhanh...',
  className = '',
  size = 'md',
  fullWidth = false,
}) {
  const reactId = useId();
  const listboxId = `custom-select-listbox-${reactId}`;
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const [menuPosition, setMenuPosition] = useState(null);

  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const searchInputRef = useRef(null);

  const normalizedValue = value === null || value === undefined ? '' : String(value);

  const normalizedOptions = useMemo(
    () =>
      options.map((opt) => ({
        value: opt.value === null || opt.value === undefined ? '' : String(opt.value),
        label: String(opt.label ?? ''),
        disabled: Boolean(opt.disabled),
      })),
    [options]
  );

  const selectedOption = useMemo(
    () => normalizedOptions.find((opt) => opt.value === normalizedValue) || null,
    [normalizedOptions, normalizedValue]
  );

  const showSearch =
    typeof searchable === 'boolean'
      ? searchable
      : normalizedOptions.length > searchThreshold;

  const filteredOptions = useMemo(() => {
    const trimmed = searchQuery.trim().toLowerCase();
    if (!trimmed) return normalizedOptions;
    return normalizedOptions.filter((opt) =>
      opt.label.toLowerCase().includes(trimmed)
    );
  }, [normalizedOptions, searchQuery]);

  const emitChange = useCallback(
    (nextVal) => {
      if (typeof onChange === 'function') {
        onChange({
          target: {
            id: id || '',
            name: name || '',
            value: nextVal,
          },
        });
      }
    },
    [id, name, onChange]
  );

  const updateMenuPosition = useCallback(() => {
    if (!triggerRef.current || typeof window === 'undefined') return;
    const rect = triggerRef.current.getBoundingClientRect();
    const viewportHeight = window.innerHeight || 800;
    const viewportWidth = window.innerWidth || 1280;
    const estimatedMenuHeight = Math.min(
      300,
      filteredOptions.length * 38 + (showSearch ? 52 : 12)
    );
    const spaceBelow = viewportHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;
    const openUpward =
      spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow;

    const minWidth = Math.max(rect.width, 190);
    const maxLeft = Math.max(8, viewportWidth - minWidth - 8);
    const left = Math.max(8, Math.min(rect.left, maxLeft));

    setMenuPosition({
      top: openUpward ? undefined : rect.bottom + 6,
      bottom: openUpward ? viewportHeight - rect.top + 6 : undefined,
      left,
      minWidth: Math.min(minWidth, viewportWidth - 16),
      maxWidth: Math.min(Math.max(rect.width, 340), viewportWidth - 16),
      maxHeight: Math.max(
        160,
        Math.min(280, openUpward ? spaceAbove - 8 : spaceBelow - 8)
      ),
    });
  }, [filteredOptions.length, showSearch]);

  const closeMenu = useCallback(() => {
    setIsOpen(false);
    setSearchQuery('');
    setActiveIndex(-1);
  }, []);

  const openMenu = useCallback(() => {
    if (disabled) return;
    setSearchQuery('');
    const currentIdx = normalizedOptions.findIndex(
      (opt) => opt.value === normalizedValue
    );
    setActiveIndex(currentIdx >= 0 ? currentIdx : 0);
    setIsOpen(true);
  }, [disabled, normalizedOptions, normalizedValue]);

  useEffect(() => {
    if (!isOpen) return undefined;
    updateMenuPosition();

    if (showSearch && searchInputRef.current) {
      window.requestAnimationFrame(() => {
        searchInputRef.current?.focus();
      });
    }

    const handlePointerDown = (event) => {
      const target = event.target;
      if (
        rootRef.current?.contains(target) ||
        menuRef.current?.contains(target)
      ) {
        return;
      }
      closeMenu();
    };

    const handleScrollOrResize = (event) => {
      if (event?.type === 'scroll' && menuRef.current?.contains(event.target)) {
        return;
      }
      updateMenuPosition();
    };

    const handleGlobalKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeMenu();
        triggerRef.current?.focus();
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('resize', handleScrollOrResize);
    window.addEventListener('scroll', handleScrollOrResize, true);
    document.addEventListener('keydown', handleGlobalKeyDown, true);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('resize', handleScrollOrResize);
      window.removeEventListener('scroll', handleScrollOrResize, true);
      document.removeEventListener('keydown', handleGlobalKeyDown, true);
    };
  }, [closeMenu, isOpen, showSearch, updateMenuPosition]);

  const handleSelectOption = (opt) => {
    if (opt.disabled) return;
    emitChange(opt.value);
    closeMenu();
    triggerRef.current?.focus();
  };

  const handleKeyDown = (event) => {
    if (disabled) return;

    if (!isOpen) {
      if (
        event.key === 'Enter' ||
        event.key === ' ' ||
        event.key === 'ArrowDown' ||
        event.key === 'ArrowUp'
      ) {
        event.preventDefault();
        openMenu();
      }
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (filteredOptions.length > 0) {
        setActiveIndex((prev) => (prev + 1) % filteredOptions.length);
      }
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (filteredOptions.length > 0) {
        setActiveIndex((prev) =>
          prev <= 0 ? filteredOptions.length - 1 : prev - 1
        );
      }
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const targetOpt = filteredOptions[activeIndex];
      if (targetOpt && !targetOpt.disabled) {
        handleSelectOption(targetOpt);
      }
    } else if (event.key === 'Tab') {
      closeMenu();
    }
  };

  const displayLabel =
    selectedOption?.label ??
    placeholder ??
    (normalizedOptions[0]?.label || 'Chọn...');
  const isPlaceholder =
    normalizedValue === '' &&
    Boolean(
      placeholder ||
        (selectedOption && selectedOption.label.startsWith('-- '))
    );

  return (
    <div
      ref={rootRef}
      className={`${styles.customSelectRoot} ${
        fullWidth ? styles.customSelectFullWidth : ''
      } ${className}`}
      title={title}
    >
      {/* Visually hidden native select for form validation, label htmlFor, and test compatibility */}
      <select
        id={id}
        name={name}
        aria-label={ariaLabel}
        value={normalizedValue}
        disabled={disabled}
        required={required}
        tabIndex={-1}
        className={styles.srOnlyNativeSelect}
        onChange={onChange}
      >
        {normalizedOptions.map((opt) => (
          <option
            key={`${opt.value}-${opt.label}`}
            value={opt.value}
            disabled={opt.disabled}
          >
            {opt.label}
          </option>
        ))}
      </select>

      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        className={`${styles.customSelectTrigger} ${
          size === 'sm' ? styles.customSelectTriggerSm : ''
        } ${isOpen ? styles.customSelectTriggerOpen : ''} ${
          isPlaceholder ? styles.customSelectTriggerPlaceholder : ''
        }`}
        onClick={() => (isOpen ? closeMenu() : openMenu())}
        onKeyDown={handleKeyDown}
      >
        <span className={styles.customSelectLabel}>{displayLabel}</span>
        <svg
          className={`${styles.customSelectChevron} ${
            isOpen ? styles.customSelectChevronOpen : ''
          }`}
          width="15"
          height="15"
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
      </button>

      {isOpen &&
        menuPosition &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={menuRef}
            id={listboxId}
            role="listbox"
            className={styles.customSelectMenu}
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
              minWidth: `${menuPosition.minWidth}px`,
              maxWidth: `${menuPosition.maxWidth}px`,
            }}
          >
            {showSearch && (
              <div className={styles.customSelectSearchWrap}>
                <svg
                  className={styles.customSelectSearchIcon}
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
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setActiveIndex(0);
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={searchPlaceholder}
                  className={styles.customSelectSearchInput}
                />
                {searchQuery && (
                  <button
                    type="button"
                    className={styles.customSelectClearBtn}
                    onClick={() => {
                      setSearchQuery('');
                      setActiveIndex(0);
                      searchInputRef.current?.focus();
                    }}
                    aria-label="Xóa tìm kiếm"
                  >
                    ×
                  </button>
                )}
              </div>
            )}

            <div
              className={styles.customSelectOptionsList}
              style={{ maxHeight: `${menuPosition.maxHeight}px` }}
            >
              {filteredOptions.length === 0 ? (
                <div className={styles.customSelectEmpty}>
                  Không tìm thấy kết quả phù hợp
                </div>
              ) : (
                filteredOptions.map((opt, idx) => {
                  const isSelected = opt.value === normalizedValue;
                  const isActive = idx === activeIndex;
                  return (
                    <button
                      key={`${opt.value}-${opt.label}`}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      disabled={opt.disabled}
                      className={`${styles.customSelectOption} ${
                        isSelected ? styles.customSelectOptionSelected : ''
                      } ${isActive ? styles.customSelectOptionActive : ''}`}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => handleSelectOption(opt)}
                    >
                      <span className={styles.customSelectOptionText}>
                        {opt.label}
                      </span>
                      {isSelected && (
                        <svg
                          className={styles.customSelectCheck}
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
