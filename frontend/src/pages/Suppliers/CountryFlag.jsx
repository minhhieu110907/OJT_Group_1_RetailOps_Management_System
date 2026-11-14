/**
 * Crisp inline SVG flags for priority countries, with clean ISO badge fallback for all 245+ regions.
 * Ensures consistent rendering across Windows/macOS/Linux without relying on emoji flag support or external URLs.
 */
export default function CountryFlag({ isoCode, className = '' }) {
  const code = String(isoCode || 'VN').toUpperCase();

  switch (code) {
    case 'VN':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#DA251D" />
          <polygon
            points="11,3.2 12.18,6.82 15.98,6.82 12.9,9.06 14.08,12.68 11,10.44 7.92,12.68 9.1,9.06 6.02,6.82 9.82,6.82"
            fill="#FFCD00"
          />
        </svg>
      );
    case 'US':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#FFFFFF" />
          <rect y="0" width="22" height="2.28" fill="#B22234" />
          <rect y="4.57" width="22" height="2.28" fill="#B22234" />
          <rect y="9.14" width="22" height="2.28" fill="#B22234" />
          <rect y="13.71" width="22" height="2.29" fill="#B22234" />
          <rect width="10" height="8.5" fill="#3C3B6E" />
          <circle cx="2.5" cy="2.2" r="0.7" fill="#FFFFFF" />
          <circle cx="5" cy="2.2" r="0.7" fill="#FFFFFF" />
          <circle cx="7.5" cy="2.2" r="0.7" fill="#FFFFFF" />
          <circle cx="3.75" cy="4.2" r="0.7" fill="#FFFFFF" />
          <circle cx="6.25" cy="4.2" r="0.7" fill="#FFFFFF" />
          <circle cx="2.5" cy="6.2" r="0.7" fill="#FFFFFF" />
          <circle cx="5" cy="6.2" r="0.7" fill="#FFFFFF" />
          <circle cx="7.5" cy="6.2" r="0.7" fill="#FFFFFF" />
        </svg>
      );
    case 'JP':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="0.8" />
          <circle cx="11" cy="8" r="4.2" fill="#BC002D" />
        </svg>
      );
    case 'KR':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="0.8" />
          <path d="M11 4.2 A3.8 3.8 0 0 1 14.8 8 A1.9 1.9 0 0 1 11 8 A1.9 1.9 0 0 0 7.2 8 A3.8 3.8 0 0 1 11 4.2 Z" fill="#CD2E3A" />
          <path d="M11 11.8 A3.8 3.8 0 0 1 7.2 8 A1.9 1.9 0 0 1 11 8 A1.9 1.9 0 0 0 14.8 8 A3.8 3.8 0 0 1 11 11.8 Z" fill="#0047A0" />
        </svg>
      );
    case 'CN':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#DE2910" />
          <polygon points="5,2.5 5.7,4.6 7.9,4.6 6.1,5.9 6.8,8 5,6.7 3.2,8 3.9,5.9 2.1,4.6 4.3,4.6" fill="#FFDE00" />
          <circle cx="9.2" cy="3" r="0.6" fill="#FFDE00" />
          <circle cx="10.2" cy="4.4" r="0.6" fill="#FFDE00" />
          <circle cx="10.2" cy="6.2" r="0.6" fill="#FFDE00" />
          <circle cx="9.2" cy="7.6" r="0.6" fill="#FFDE00" />
        </svg>
      );
    case 'SG':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="0.8" />
          <path d="M2 0 H20 A2 2 0 0 1 22 2 V8 H0 V2 A2 2 0 0 1 2 0 Z" fill="#EF3340" />
          <circle cx="5.5" cy="4" r="2.2" fill="#FFFFFF" />
          <circle cx="6.4" cy="4" r="2" fill="#EF3340" />
        </svg>
      );
    case 'TH':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#A51931" />
          <rect y="2.6" width="22" height="10.8" fill="#F4F5F8" />
          <rect y="5.2" width="22" height="5.6" fill="#2D2A4A" />
        </svg>
      );
    case 'GB':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#012169" />
          <path d="M0 0 L22 16 M22 0 L0 16" stroke="#FFFFFF" strokeWidth="2.5" />
          <path d="M0 0 L22 16 M22 0 L0 16" stroke="#C8102E" strokeWidth="1.2" />
          <path d="M11 0 V16 M0 8 H22" stroke="#FFFFFF" strokeWidth="4" />
          <path d="M11 0 V16 M0 8 H22" stroke="#C8102E" strokeWidth="2.2" />
        </svg>
      );
    case 'FR':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="7.33" height="16" rx="2" fill="#002395" />
          <rect x="7.33" width="7.34" height="16" fill="#FFFFFF" />
          <rect x="14.67" width="7.33" height="16" rx="2" fill="#ED2939" />
        </svg>
      );
    case 'DE':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#FFCE00" />
          <rect width="22" height="10.67" fill="#DD0000" />
          <rect width="22" height="5.33" fill="#000000" />
        </svg>
      );
    case 'CA':
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="0.8" />
          <rect width="5.5" height="16" fill="#FF0000" />
          <rect x="16.5" width="5.5" height="16" fill="#FF0000" />
          <polygon points="11,4 12.2,7 14,6.5 13,8.5 14,9.5 11.5,9.5 11.5,12 10.5,12 10.5,9.5 8,9.5 9,8.5 8,6.5 9.8,7" fill="#FF0000" />
        </svg>
      );
    default:
      return (
        <svg className={className} width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
          <rect width="22" height="16" rx="2" fill="#F1F5F9" stroke="#CBD5E1" strokeWidth="1" />
          <text
            x="11"
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
}
