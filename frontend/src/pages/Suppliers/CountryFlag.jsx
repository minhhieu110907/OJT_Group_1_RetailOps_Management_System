import { useState } from 'react';

/**
 * Special ISO-to-flagcdn code mappings for telecom-specific island territories:
 * - TA (Tristan da Cunha) -> 'sh-ta' (official Tristan da Cunha flag)
 * - AC (Ascension Island) -> 'sh-ac' (official Ascension Island flag)
 */
const FLAGCDN_CODE_MAP = {
  TA: 'sh-ta',
  AC: 'sh-ac',
};

/**
 * Codes that must always render the custom legal/neutral inline SVG instead of external CDN.
 */
const CUSTOM_INLINE_ONLY_CODES = new Set(['TW']);

/**
 * Offline fallback inline SVGs and custom legal SVG for TW (Chinese Taipei).
 */
function renderInlineSvgFlag(code, className) {
  switch (code) {
    case 'VN':
      return (
        <svg className={className} width="24" height="16" viewBox="0 0 24 16" aria-hidden="true">
          <rect width="24" height="16" rx="2" fill="#DA251D" />
          <polygon
            points="12,3.2 13.18,6.82 16.98,6.82 13.9,9.06 15.08,12.68 12,10.44 8.92,12.68 10.1,9.06 7.02,6.82 10.82,6.82"
            fill="#FFCD00"
          />
        </svg>
      );
    case 'TW':
      // Neutral Chinese Taipei (Đài Bắc Trung Hoa) plum-blossom emblem flag
      return (
        <svg className={className} width="24" height="16" viewBox="0 0 24 16" aria-hidden="true">
          <rect width="24" height="16" rx="2" fill="#FFFFFF" stroke="#CBD5E1" strokeWidth="0.9" />
          {/* Outer 5-petal plum blossom */}
          <path
            d="M12,2.3 C13.5,2.3 14.5,3.5 14.1,4.9 C15.5,4.9 16.7,6.1 16.2,7.5 C17.2,8.5 16.8,10.3 15.4,10.9 C15.4,12.3 13.9,13.5 12.5,12.8 L12,12.5 L11.5,12.8 C10.1,13.5 8.6,12.3 8.6,10.9 C7.2,10.3 6.8,8.5 7.8,7.5 C7.3,6.1 8.5,4.9 9.9,4.9 C9.5,3.5 10.5,2.3 12,2.3 Z"
            fill="#FFFFFF"
            stroke="#00529B"
            strokeWidth="0.85"
          />
          <path
            d="M12,3.1 C13.1,3.1 13.8,4.0 13.5,5.1 C14.6,5.1 15.5,6.0 15.1,7.1 C15.9,7.9 15.6,9.3 14.5,9.8 C14.5,10.9 13.4,11.8 12.3,11.2 L12,11.0 L11.7,11.2 C10.6,11.8 9.5,10.9 9.5,9.8 C8.4,9.3 8.1,7.9 8.9,7.1 C8.5,6.0 9.4,5.1 10.5,5.1 C10.2,4.0 10.9,3.1 12,3.1 Z"
            fill="none"
            stroke="#DE2910"
            strokeWidth="0.65"
          />
          {/* Inner circle emblem */}
          <circle cx="12" cy="7.2" r="2.0" fill="#00529B" />
          <circle cx="12" cy="7.2" r="1.15" fill="#FFFFFF" />
          {/* Olympic-style interlocking rings motif at base of blossom */}
          <circle cx="10.7" cy="10.1" r="0.75" fill="none" stroke="#0081C8" strokeWidth="0.45" />
          <circle cx="12" cy="10.1" r="0.75" fill="none" stroke="#222222" strokeWidth="0.45" />
          <circle cx="13.3" cy="10.1" r="0.75" fill="none" stroke="#EE334E" strokeWidth="0.45" />
        </svg>
      );
    case 'KR':
      return (
        <svg className={className} width="24" height="16" viewBox="0 0 24 16" aria-hidden="true">
          <rect width="24" height="16" rx="2" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="0.8" />
          <g transform="rotate(-33.69 12 8)">
            <path d="M8.6 8 A3.4 3.4 0 0 1 15.4 8 Z" fill="#CD2E3A" />
            <path d="M8.6 8 A3.4 3.4 0 0 0 15.4 8 Z" fill="#0047A0" />
            <circle cx="10.3" cy="8" r="1.7" fill="#CD2E3A" />
            <circle cx="13.7" cy="8" r="1.7" fill="#0047A0" />
          </g>
          <g stroke="#000000" strokeWidth="0.65" strokeLinecap="butt">
            <g transform="translate(6.0, 4.1) rotate(-56.3)">
              <line x1="-1.5" y1="-0.8" x2="1.5" y2="-0.8" />
              <line x1="-1.5" y1="0" x2="1.5" y2="0" />
              <line x1="-1.5" y1="0.8" x2="1.5" y2="0.8" />
            </g>
            <g transform="translate(18.0, 4.1) rotate(56.3)">
              <line x1="-1.5" y1="-0.8" x2="-0.2" y2="-0.8" />
              <line x1="0.2" y1="-0.8" x2="1.5" y2="-0.8" />
              <line x1="-1.5" y1="0" x2="1.5" y2="0" />
              <line x1="-1.5" y1="0.8" x2="-0.2" y2="0.8" />
              <line x1="0.2" y1="0.8" x2="1.5" y2="0.8" />
            </g>
            <g transform="translate(6.0, 11.9) rotate(56.3)">
              <line x1="-1.5" y1="-0.8" x2="1.5" y2="-0.8" />
              <line x1="-1.5" y1="0" x2="-0.2" y2="0" />
              <line x1="0.2" y1="0" x2="1.5" y2="0" />
              <line x1="-1.5" y1="0.8" x2="1.5" y2="0.8" />
            </g>
            <g transform="translate(18.0, 11.9) rotate(-56.3)">
              <line x1="-1.5" y1="-0.8" x2="-0.2" y2="-0.8" />
              <line x1="0.2" y1="-0.8" x2="1.5" y2="-0.8" />
              <line x1="-1.5" y1="0" x2="-0.2" y2="0" />
              <line x1="0.2" y1="0" x2="1.5" y2="0" />
              <line x1="-1.5" y1="0.8" x2="-0.2" y2="0.8" />
              <line x1="0.2" y1="0.8" x2="1.5" y2="0.8" />
            </g>
          </g>
        </svg>
      );
    case 'TA':
    case 'AC':
      return (
        <svg className={className} width="24" height="16" viewBox="0 0 24 16" aria-hidden="true">
          <rect width="24" height="16" rx="2" fill="#012169" />
          <path d="M0 0 L11 7.5 M11 0 L0 7.5" stroke="#FFFFFF" strokeWidth="1.6" />
          <path d="M5.5 0 V7.5 M0 3.75 H11" stroke="#FFFFFF" strokeWidth="2.4" />
          <path d="M5.5 0 V7.5 M0 3.75 H11" stroke="#C8102E" strokeWidth="1.3" />
          <path
            d="M15.2 5.0 H19.4 V8.6 C19.4 10.6 17.3 11.9 17.3 11.9 C17.3 11.9 15.2 10.6 15.2 8.6 Z"
            fill="#FFFFFF"
            stroke="#F59E0B"
            strokeWidth="0.7"
          />
          <path d="M15.6 8.2 H19.0" stroke="#0284C7" strokeWidth="1.1" />
          <polygon points="17.3,5.7 18.4,7.5 16.2,7.5" fill="#0284C7" />
        </svg>
      );
    default:
      return null;
  }
}

export default function CountryFlag({ isoCode, className = '' }) {
  const code = String(isoCode || 'VN').toUpperCase();
  const [failedCode, setFailedCode] = useState(null);

  if (CUSTOM_INLINE_ONLY_CODES.has(code)) {
    const customSvg = renderInlineSvgFlag(code, className);
    if (customSvg) return customSvg;
  }

  const cdnCode = FLAGCDN_CODE_MAP[code] || code.toLowerCase();

  if (failedCode !== code && /^[a-z]{2}(-[a-z]{2})?$/.test(cdnCode)) {
    return (
      <img
        src={`https://flagcdn.com/${cdnCode}.svg`}
        alt=""
        width="24"
        height="16"
        loading="lazy"
        aria-hidden="true"
        className={className}
        style={{
          width: '24px',
          height: '16px',
          objectFit: 'fill',
          borderRadius: '2px',
          border: '1px solid #e2e8f0',
          display: 'inline-block',
          flexShrink: 0,
        }}
        onError={() => setFailedCode(code)}
      />
    );
  }

  const inlineSvg = renderInlineSvgFlag(code, className);
  if (inlineSvg) {
    return inlineSvg;
  }

  return (
    <svg className={className} width="24" height="16" viewBox="0 0 24 16" aria-hidden="true">
      <rect width="24" height="16" rx="2" fill="#F1F5F9" stroke="#CBD5E1" strokeWidth="1" />
      <text
        x="12"
        y="11"
        textAnchor="middle"
        fontSize="7.5"
        fontWeight="700"
        fontFamily="system-ui, -apple-system, sans-serif"
        fill="#475569"
      >
        {code}
      </text>
    </svg>
  );
}
