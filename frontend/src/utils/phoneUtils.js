import {
  getCountries,
  getCountryCallingCode,
  parsePhoneNumberFromString,
} from 'libphonenumber-js';

const PRIORITY_COUNTRIES = [
  'VN',
  'US',
  'JP',
  'KR',
  'CN',
  'SG',
  'TH',
  'GB',
  'AU',
  'FR',
  'DE',
  'CA',
  'TW',
  'MY',
  'ID',
  'PH',
];

const COUNTRY_NAME_OVERRIDES_VI = {
  VN: 'Việt Nam',
  US: 'Hoa Kỳ (Mỹ)',
  JP: 'Nhật Bản',
  KR: 'Hàn Quốc',
  CN: 'Trung Quốc',
  SG: 'Singapore',
  TH: 'Thái Lan',
  GB: 'Vương quốc Anh',
  AU: 'Úc',
  FR: 'Pháp',
  DE: 'Đức',
  CA: 'Canada',
  TW: 'Đài Loan',
};

const PHONE_PLACEHOLDERS = {
  VN: '912 345 678',
  US: '202 555 0123',
  CA: '416 555 0123',
  JP: '90 1234 5678',
  KR: '10 1234 5678',
  CN: '138 0013 8000',
  SG: '8123 4567',
  TH: '81 234 5678',
  GB: '7400 123456',
  AU: '412 345 678',
  FR: '6 12 34 56 78',
  DE: '151 23456789',
  MY: '12 345 6789',
  ID: '812 3456 7890',
  PH: '917 123 4567',
  TW: '912 345 678',
};

function stripAccents(str) {
  return String(str || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase();
}

let cachedCountryOptions = null;

/**
 * Build full country list from libphonenumber-js metadata with localized Vietnamese & English names.
 */
export function getAllCountryOptions() {
  if (cachedCountryOptions) return cachedCountryOptions;

  let viDisplay = null;
  let enDisplay = null;
  try {
    viDisplay = new Intl.DisplayNames(['vi'], { type: 'region' });
    enDisplay = new Intl.DisplayNames(['en'], { type: 'region' });
  } catch {
    viDisplay = null;
    enDisplay = null;
  }

  const priorityRank = new Map(PRIORITY_COUNTRIES.map((code, idx) => [code, idx]));

  const options = getCountries().map((isoCode) => {
    const callingCode = getCountryCallingCode(isoCode);
    const viName =
      COUNTRY_NAME_OVERRIDES_VI[isoCode] ||
      (viDisplay ? viDisplay.of(isoCode) : null) ||
      isoCode;
    const enName = (enDisplay ? enDisplay.of(isoCode) : null) || isoCode;

    return {
      isoCode,
      callingCode,
      dialCode: `+${callingCode}`,
      name: viName,
      englishName: enName,
      searchText: `${stripAccents(viName)} ${stripAccents(enName)} ${isoCode.toLowerCase()} +${callingCode} ${callingCode}`,
    };
  });

  options.sort((a, b) => {
    const rankA = priorityRank.has(a.isoCode) ? priorityRank.get(a.isoCode) : Infinity;
    const rankB = priorityRank.has(b.isoCode) ? priorityRank.get(b.isoCode) : Infinity;
    if (rankA !== rankB) return rankA - rankB;
    return a.name.localeCompare(b.name, 'vi');
  });

  cachedCountryOptions = options;
  return cachedCountryOptions;
}

export function getCountryOptionByIso(isoCode) {
  const options = getAllCountryOptions();
  return options.find((c) => c.isoCode === isoCode) || options.find((c) => c.isoCode === 'VN');
}

export function filterCountryOptions(options, query) {
  const trimmed = typeof query === 'string' ? query.trim() : '';
  if (!trimmed) return options;

  const normalizedQuery = stripAccents(trimmed);
  const numericQuery = trimmed.replace(/^\+/, '');

  return options.filter((item) => {
    if (item.searchText.includes(normalizedQuery)) return true;
    if (numericQuery && item.callingCode.startsWith(numericQuery)) return true;
    return false;
  });
}

export function getPhonePlaceholder(isoCode) {
  return PHONE_PLACEHOLDERS[isoCode] || 'Nhập số điện thoại...';
}

const ALLOWED_PHONE_CHARS_REGEX = /^[0-9+\-\s().]+$/;

/**
 * Validate and normalize phone input to E.164 using libphonenumber-js metadata.
 */
export function parseAndValidateSupplierPhone(rawInput, selectedCountryIso = 'VN') {
  const raw = typeof rawInput === 'string' ? rawInput : '';
  const trimmed = raw.trim();

  // Optional field: empty or whitespace-only is valid and maps to null
  if (!trimmed) {
    return {
      isValid: true,
      e164: null,
      error: '',
      detectedCountry: selectedCountryIso,
    };
  }

  if (!ALLOWED_PHONE_CHARS_REGEX.test(trimmed)) {
    return {
      isValid: false,
      e164: null,
      error: 'Số điện thoại chỉ được chứa chữ số, khoảng trắng và dấu gạch ngang.',
      detectedCountry: selectedCountryIso,
    };
  }

  const isInternational = trimmed.startsWith('+');
  const parsed = isInternational
    ? parsePhoneNumberFromString(trimmed)
    : parsePhoneNumberFromString(trimmed, selectedCountryIso);

  if (!parsed || !parsed.isValid()) {
    return {
      isValid: false,
      e164: null,
      error: isInternational
        ? 'Số điện thoại quốc tế không hợp lệ.'
        : 'Số điện thoại không hợp lệ theo mã quốc gia đã chọn.',
      detectedCountry: selectedCountryIso,
    };
  }

  const e164 = parsed.number;
  if (e164.length > 32) {
    return {
      isValid: false,
      e164: null,
      error: 'Số điện thoại không được vượt quá 32 ký tự.',
      detectedCountry: selectedCountryIso,
    };
  }

  return {
    isValid: true,
    e164,
    error: '',
    detectedCountry: parsed.country || selectedCountryIso,
  };
}

/**
 * Hydrate countryIso + national display input when opening Edit modal with stored E.164 or legacy phone.
 */
export function hydrateSupplierPhoneField(storedPhone) {
  const raw = typeof storedPhone === 'string' ? storedPhone.trim() : '';
  if (!raw) {
    return {
      countryIso: 'VN',
      nationalInput: '',
    };
  }

  if (raw.startsWith('+')) {
    const parsed = parsePhoneNumberFromString(raw);
    if (parsed && parsed.isValid()) {
      const countryIso = parsed.country || 'VN';
      return {
        countryIso,
        nationalInput: parsed.formatNational(),
      };
    }
  }

  // Fallback for legacy non-E.164 stored values: try parsing with VN first
  const vnParsed = parsePhoneNumberFromString(raw, 'VN');
  if (vnParsed && vnParsed.isValid()) {
    return {
      countryIso: vnParsed.country || 'VN',
      nationalInput: vnParsed.formatNational(),
    };
  }

  // Preserve raw string if unparseable so existing data is never silently dropped
  return {
    countryIso: 'VN',
    nationalInput: raw,
  };
}

/**
 * Handle pasted text that may be a full E.164 international number.
 * Returns updated { countryIso, nationalInput } if international country is detected, or null otherwise.
 */
export function parsePastedInternationalPhone(pastedText) {
  const trimmed = typeof pastedText === 'string' ? pastedText.trim() : '';
  if (!trimmed.startsWith('+')) return null;

  const parsed = parsePhoneNumberFromString(trimmed);
  if (parsed && parsed.isValid() && parsed.country) {
    return {
      countryIso: parsed.country,
      nationalInput: parsed.formatNational(),
      e164: parsed.number,
    };
  }
  return null;
}
