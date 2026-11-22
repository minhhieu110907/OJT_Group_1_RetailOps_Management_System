import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import styles from './SupplierCategorySelect.module.css';

const MAX_VISIBLE_TAGS = 3;

function normalizeSearchText(text) {
  return String(text || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'd')
    .toLowerCase()
    .trim();
}

export default function SupplierCategorySelect({
  categories = [],
  selectedIds = [],
  disabled = false,
  error = '',
  onChange,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [dropdownStyle, setDropdownStyle] = useState(null);

  const triggerRef = useRef(null);
  const dropdownRef = useRef(null);
  const searchInputRef = useRef(null);

  const visibleCategories = useMemo(
    () =>
      (Array.isArray(categories) ? categories : []).filter(
        (cat) => cat.status === 'ACTIVE' || selectedIds.includes(cat.id)
      ),
    [categories, selectedIds]
  );

  const selectedCategories = useMemo(() => {
    const map = new Map(visibleCategories.map((c) => [c.id, c]));
    return selectedIds
      .map((id) => map.get(id))
      .filter(Boolean);
  }, [visibleCategories, selectedIds]);

  const filteredCategories = useMemo(() => {
    const q = normalizeSearchText(searchQuery);
    if (!q) return visibleCategories;
    return visibleCategories.filter((cat) =>
      normalizeSearchText(cat.name).includes(q)
    );
  }, [visibleCategories, searchQuery]);

  const updateDropdownPosition = useCallback(() => {
    const triggerEl = triggerRef.current;
    if (!triggerEl) return;

    const rect = triggerEl.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;
    const panelWidth = Math.min(Math.max(rect.width, 240), viewportWidth - 24);
    const left = Math.max(12, Math.min(rect.left, viewportWidth - panelWidth - 12));

    const spaceBelow = viewportHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;

    if (spaceBelow < 230 && spaceAbove > spaceBelow) {
      setDropdownStyle({
        left: `${left}px`,
        bottom: `${viewportHeight - rect.top + 6}px`,
        width: `${panelWidth}px`,
        maxHeight: `${Math.min(320, Math.max(180, spaceAbove - 8))}px`,
      });
    } else {
      setDropdownStyle({
        left: `${left}px`,
        top: `${rect.bottom + 6}px`,
        width: `${panelWidth}px`,
        maxHeight: `${Math.min(320, Math.max(180, spaceBelow - 8))}px`,
      });
    }
  }, []);

  const closeDropdown = useCallback(() => {
    setIsOpen(false);
    setSearchQuery('');
  }, []);

  const handleToggle = () => {
    if (disabled) return;
    if (isOpen) {
      closeDropdown();
    } else {
      updateDropdownPosition();
      setIsOpen(true);
    }
  };

  useEffect(() => {
    if (!isOpen) return undefined;

    const timer = setTimeout(() => {
      searchInputRef.current?.focus();
    }, 0);

    const handleClickOutside = (event) => {
      if (
        triggerRef.current?.contains(event.target) ||
        dropdownRef.current?.contains(event.target)
      ) {
        return;
      }
      closeDropdown();
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeDropdown();
      }
    };

    const handleReposition = () => {
      updateDropdownPosition();
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown, true);
    window.addEventListener('resize', handleReposition);
    window.addEventListener('scroll', handleReposition, true);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown, true);
      window.removeEventListener('resize', handleReposition);
      window.removeEventListener('scroll', handleReposition, true);
    };
  }, [isOpen, closeDropdown, updateDropdownPosition]);

  const handleToggleCategory = (cat) => {
    if (disabled) return;
    const isSelected = selectedIds.includes(cat.id);
    if (cat.status !== 'ACTIVE' && !isSelected) return;
    const next = isSelected
      ? selectedIds.filter((id) => id !== cat.id)
      : [...selectedIds, cat.id];
    onChange?.(next);
  };

  const handleClearAll = (event) => {
    event.stopPropagation();
    if (disabled) return;
    onChange?.([]);
  };

  if (error) {
    return (
      <div className={styles.errorBox} role="alert">
        {error}
      </div>
    );
  }

  const displayedTags = selectedCategories.slice(0, MAX_VISIBLE_TAGS);
  const overflowCount = Math.max(0, selectedCategories.length - MAX_VISIBLE_TAGS);

  return (
    <div className={styles.wrapper}>
      <div
        ref={triggerRef}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-disabled={disabled}
        className={`${styles.trigger} ${isOpen ? styles.triggerOpen : ''} ${
          disabled ? styles.triggerDisabled : ''
        }`}
        onClick={handleToggle}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            handleToggle();
          }
        }}
      >
        <div className={styles.tagsArea}>
          {selectedCategories.length === 0 ? (
            <span className={styles.placeholder}>
              {visibleCategories.length === 0
                ? 'Chưa có danh mục nào'
                : 'Chọn danh mục cung cấp...'}
            </span>
          ) : (
            <>
              {displayedTags.map((cat) => (
                <span key={cat.id} className={styles.selectedTag}>
                  <span className={styles.selectedTagText}>{cat.name}</span>
                  {!disabled && (
                    <button
                      type="button"
                      className={styles.tagRemoveBtn}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleToggleCategory(cat);
                      }}
                      aria-label={`Bỏ chọn ${cat.name}`}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
              {overflowCount > 0 && (
                <span className={styles.overflowTag}>+{overflowCount} khác</span>
              )}
            </>
          )}
        </div>

        <div className={styles.triggerRight}>
          {selectedCategories.length > 0 && !disabled && (
            <button
              type="button"
              className={styles.clearAllIconBtn}
              onClick={handleClearAll}
              title="Bỏ chọn tất cả danh mục"
              aria-label="Bỏ chọn tất cả danh mục"
            >
              ×
            </button>
          )}
          <svg
            className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`}
            width="16"
            height="16"
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
        </div>
      </div>

      {isOpen &&
        dropdownStyle &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={dropdownRef}
            className={styles.dropdownPanel}
            style={dropdownStyle}
            role="listbox"
            aria-multiselectable="true"
          >
            <div className={styles.searchHeader}>
              <svg
                className={styles.searchIcon}
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
                className={styles.searchInput}
                placeholder="Tìm nhanh danh mục..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <div className={styles.optionsList}>
              {filteredCategories.length === 0 ? (
                <div className={styles.emptyState}>
                  {visibleCategories.length === 0
                    ? 'Chưa có danh mục nào.'
                    : 'Không tìm thấy danh mục phù hợp.'}
                </div>
              ) : (
                filteredCategories.map((cat) => {
                  const isSelected = selectedIds.includes(cat.id);
                  const isInactive = cat.status !== 'ACTIVE';
                  const isItemDisabled = disabled || (isInactive && !isSelected);
                  return (
                    <button
                      key={cat.id}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      disabled={isItemDisabled}
                      className={`${styles.optionRow} ${
                        isSelected ? styles.optionRowSelected : ''
                      }`}
                      onClick={() => handleToggleCategory(cat)}
                    >
                      <span
                        className={`${styles.checkboxBox} ${
                          isSelected ? styles.checkboxBoxChecked : ''
                        }`}
                        aria-hidden="true"
                      >
                        {isSelected && (
                          <svg
                            width="11"
                            height="11"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="3.2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                      </span>
                      <span className={styles.optionLabel}>{cat.name}</span>
                      {isInactive && (
                        <span className={styles.inactiveBadge}>Ngừng HĐ</span>
                      )}
                    </button>
                  );
                })
              )}
            </div>

            <div className={styles.dropdownFooter}>
              <span className={styles.selectedCountText}>
                Đã chọn: <strong>{selectedCategories.length}</strong>
              </span>
              <div className={styles.footerActions}>
                {selectedCategories.length > 0 && (
                  <button
                    type="button"
                    className={styles.footerClearBtn}
                    onClick={handleClearAll}
                  >
                    Bỏ chọn hết
                  </button>
                )}
                <button
                  type="button"
                  className={styles.footerDoneBtn}
                  onClick={closeDropdown}
                >
                  Xong
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
