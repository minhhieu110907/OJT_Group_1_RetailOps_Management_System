import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import CountryFlag from './CountryFlag';
import {
  filterCountryOptions,
  getAllCountryOptions,
  getCountryOptionByIso,
  getPhonePlaceholder,
  parsePastedInternationalPhone,
} from '../../utils/phoneUtils';
import styles from './SupplierPhoneInput.module.css';

export default function SupplierPhoneInput({
  countryIso = 'VN',
  value = '',
  error = '',
  disabled = false,
  onChange,
  onCountryChange,
  onBlur,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [dropdownStyle, setDropdownStyle] = useState(null);

  const triggerRef = useRef(null);
  const dropdownRef = useRef(null);
  const searchInputRef = useRef(null);
  const phoneInputRef = useRef(null);
  const listRef = useRef(null);

  const listboxId = useId();
  const inputId = useId();

  const allCountries = useMemo(() => getAllCountryOptions(), []);
  const selectedCountry = useMemo(
    () => getCountryOptionByIso(countryIso),
    [countryIso]
  );
  const filteredCountries = useMemo(
    () => filterCountryOptions(allCountries, searchQuery),
    [allCountries, searchQuery]
  );
  const placeholder = useMemo(
    () => getPhonePlaceholder(selectedCountry.isoCode),
    [selectedCountry.isoCode]
  );

  const updateDropdownPosition = useCallback(() => {
    const triggerEl = triggerRef.current;
    if (!triggerEl) return;

    const rect = triggerEl.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;
    const panelWidth = Math.min(320, viewportWidth - 24);
    const left = Math.max(12, Math.min(rect.left, viewportWidth - panelWidth - 12));

    const spaceBelow = viewportHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;

    if (spaceBelow < 200 && spaceAbove > spaceBelow) {
      setDropdownStyle({
        left: `${left}px`,
        bottom: `${viewportHeight - rect.top + 6}px`,
        width: `${panelWidth}px`,
      });
    } else {
      setDropdownStyle({
        left: `${left}px`,
        top: `${rect.bottom + 6}px`,
        width: `${panelWidth}px`,
      });
    }
  }, []);

  const closeDropdown = useCallback(() => {
    setIsOpen(false);
    setSearchQuery('');
  }, []);

  const openDropdown = useCallback(() => {
    if (disabled) return;
    updateDropdownPosition();
    const currentIdx = allCountries.findIndex(
      (c) => c.isoCode === selectedCountry.isoCode
    );
    setActiveIndex(currentIdx >= 0 ? currentIdx : 0);
    setSearchQuery('');
    setIsOpen(true);
  }, [allCountries, disabled, selectedCountry.isoCode, updateDropdownPosition]);

  const handleToggleDropdown = () => {
    if (isOpen) {
      closeDropdown();
    } else {
      openDropdown();
    }
  };

  const handleSelectCountry = useCallback(
    (option) => {
      closeDropdown();
      if (onCountryChange) {
        onCountryChange(option.isoCode);
      }
      setTimeout(() => {
        phoneInputRef.current?.focus();
      }, 0);
    },
    [closeDropdown, onCountryChange]
  );

  // Focus search input when dropdown opens
  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => {
      searchInputRef.current?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [isOpen]);

  // Reposition on window resize/scroll and handle outside click + Escape
  useEffect(() => {
    if (!isOpen) return undefined;

    const handleReposition = () => updateDropdownPosition();

    const handleMouseDownOutside = (event) => {
      if (
        triggerRef.current?.contains(event.target) ||
        dropdownRef.current?.contains(event.target)
      ) {
        return;
      }
      closeDropdown();
    };

    const handleEscapeCapture = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeDropdown();
        triggerRef.current?.focus();
      }
    };

    window.addEventListener('resize', handleReposition);
    window.addEventListener('scroll', handleReposition, true);
    document.addEventListener('mousedown', handleMouseDownOutside);
    window.addEventListener('keydown', handleEscapeCapture, true);

    return () => {
      window.removeEventListener('resize', handleReposition);
      window.removeEventListener('scroll', handleReposition, true);
      document.removeEventListener('mousedown', handleMouseDownOutside);
      window.removeEventListener('keydown', handleEscapeCapture, true);
    };
  }, [closeDropdown, isOpen, updateDropdownPosition]);

  const safeActiveIndex =
    activeIndex >= filteredCountries.length ? 0 : activeIndex;

  // Scroll active option into view when navigating with keyboard
  useEffect(() => {
    if (!isOpen) return;
    const listEl = listRef.current;
    const activeEl = listEl?.children?.[safeActiveIndex];
    if (activeEl && typeof activeEl.scrollIntoView === 'function') {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  }, [isOpen, safeActiveIndex]);

  const handleSearchKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (filteredCountries.length > 0) {
        setActiveIndex((prev) => (prev + 1) % filteredCountries.length);
      }
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (filteredCountries.length > 0) {
        setActiveIndex((prev) =>
          prev - 1 < 0 ? filteredCountries.length - 1 : prev - 1
        );
      }
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const target = filteredCountries[safeActiveIndex];
      if (target) {
        handleSelectCountry(target);
      }
    }
  };

  const handlePaste = (event) => {
    const pasted = event.clipboardData?.getData('text');
    if (!pasted) return;
    const parsed = parsePastedInternationalPhone(pasted);
    if (parsed) {
      event.preventDefault();
      if (onCountryChange && parsed.countryIso !== selectedCountry.isoCode) {
        onCountryChange(parsed.countryIso, parsed.nationalInput);
      } else if (onChange) {
        onChange(parsed.nationalInput);
      }
    }
  };

  return (
    <div>
      <div className={styles.phoneFieldRow}>
        {/* Left: Country Calling Code Selector */}
        <button
          ref={triggerRef}
          type="button"
          className={`${styles.countryTrigger} ${
            isOpen ? styles.countryTriggerOpen : ''
          }`}
          onClick={handleToggleDropdown}
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={isOpen ? listboxId : undefined}
          aria-label={`Chọn mã quốc gia, hiện tại ${selectedCountry.name} (${selectedCountry.dialCode})`}
        >
          <CountryFlag isoCode={selectedCountry.isoCode} className={styles.flagIcon} />
          <span className={styles.dialCodeText}>{selectedCountry.dialCode}</span>
          <svg
            className={`${styles.chevronIcon} ${isOpen ? styles.chevronOpen : ''}`}
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
        </button>

        {/* Right: Phone Input */}
        <input
          ref={phoneInputRef}
          id={inputId}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          className={`${styles.phoneInput} ${error ? styles.phoneInputError : ''}`}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange && onChange(e.target.value)}
          onPaste={handlePaste}
          onBlur={onBlur}
          maxLength={32}
          disabled={disabled}
          aria-invalid={Boolean(error)}
        />
      </div>

      {error ? (
        <p className={styles.errorText} role="alert">
          {error}
        </p>
      ) : (
        <p className={styles.helperText}>
          Nhập số điện thoại, không cần nhập mã quốc gia.
        </p>
      )}

      {/* Searchable Country Dropdown rendered via Portal so Modal overflow never clips it */}
      {isOpen &&
        dropdownStyle &&
        createPortal(
          <div
            ref={dropdownRef}
            className={styles.dropdownPanel}
            style={dropdownStyle}
          >
            <div className={styles.searchWrapper}>
              <div className={styles.searchInputBox}>
                <svg
                  className={styles.searchIcon}
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
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
                  placeholder="Tìm tên quốc gia hoặc mã vùng..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setActiveIndex(0);
                  }}
                  onKeyDown={handleSearchKeyDown}
                  aria-label="Tìm kiếm quốc gia"
                />
              </div>
            </div>

            {filteredCountries.length === 0 ? (
              <div className={styles.emptyState}>
                Không tìm thấy quốc gia phù hợp
              </div>
            ) : (
              <ul
                ref={listRef}
                id={listboxId}
                role="listbox"
                aria-label="Danh sách mã quốc gia"
                className={styles.countryList}
              >
                {filteredCountries.map((option, idx) => {
                  const isSelected = option.isoCode === selectedCountry.isoCode;
                  const isActive = idx === safeActiveIndex;
                  return (
                    <li
                      key={option.isoCode}
                      role="option"
                      aria-selected={isSelected}
                      className={`${styles.countryOption} ${
                        isSelected ? styles.countryOptionSelected : ''
                      } ${isActive ? styles.countryOptionActive : ''}`}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => handleSelectCountry(option)}
                    >
                      <span className={styles.optionLeft}>
                        <CountryFlag
                          isoCode={option.isoCode}
                          className={styles.flagIcon}
                        />
                        <span className={styles.optionName}>{option.name}</span>
                      </span>
                      <span className={styles.optionRight}>
                        <span className={styles.optionDialCode}>
                          {option.dialCode}
                        </span>
                        {isSelected && (
                          <svg
                            className={styles.checkIcon}
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
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>,
          document.body
        )}
    </div>
  );
}
