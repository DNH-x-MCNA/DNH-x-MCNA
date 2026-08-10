// ============================================================================
// Icon SVG dùng chung cho toàn bộ app (header, sidebar, modal, Admin Panel,
// màn đăng nhập) — tách ra từ page.tsx (05/08/2026) để AdminUsersPanel.tsx và
// AuthScreens.tsx không còn phải dùng emoji làm icon chrome, thống nhất 1 hệ
// hình ảnh duy nhất.
// ============================================================================
export type IconProps = { className?: string };

export const IconChart = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconLogout = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconPlus = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" />
  </svg>
);
export const IconTrash = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6h16Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconSend = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 20 20.5 12 4 4l2.5 7.2L4 20Zm2.5-7.8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconSearch = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
    <path d="m20 20-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
export const IconUsers = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="9" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8" />
    <path d="M2.8 19c.6-3.2 3.2-5 6.2-5s5.6 1.8 6.2 5M16 8.3a3 3 0 1 1 3.6 4.9M19 13.4c2.2.5 3.7 2 4.2 4.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
export const IconCoin = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
    <path d="M12 7v10M9.5 9.3c0-1.1 1.1-2 2.5-2s2.5.7 2.5 1.7c0 2.3-5 1.4-5 3.7 0 1 1.1 1.7 2.5 1.7s2.5-.9 2.5-2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);
export const IconMenu = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
export const IconClose = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
export const IconRefresh = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M20 11A8 8 0 1 0 18.5 16M20 5v6h-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconSquare = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
);

// --- Bo sung 05/08/2026 cho AdminUsersPanel.tsx / AuthScreens.tsx (thay emoji) ---
export const IconKey = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="7" cy="14.5" r="3.2" stroke="currentColor" strokeWidth="1.8" />
    <path d="M9.3 12.3 19 2.6M15.5 6.1l2.4 2.4M18.3 3.3l2.4 2.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
export const IconCheck = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 12.5 9.5 18 20 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconSettings = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
    <path d="M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.5-2-3.4-2.4.7a7.6 7.6 0 0 0-2.6-1.5L14 2h-4l-.4 2.8a7.6 7.6 0 0 0-2.6 1.5l-2.4-.7-2 3.4 2 1.5a7.6 7.6 0 0 0 0 3l-2 1.5 2 3.4 2.4-.7a7.6 7.6 0 0 0 2.6 1.5L10 22h4l.4-2.8a7.6 7.6 0 0 0 2.6-1.5l2.4.7 2-3.4-2-1.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);
export const IconLock = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <rect x="5" y="11" width="14" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
    <path d="M8 11V7.5a4 4 0 0 1 8 0V11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
export const IconUnlock = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <rect x="5" y="11" width="14" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
    <path d="M8 11V7.5a4 4 0 0 1 7.5-1.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);
export const IconShieldLock = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M12 2 4 5.5V11c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5.5L12 2Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    <rect x="9.3" y="11.5" width="5.4" height="4.2" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10.5 11.5V10a1.5 1.5 0 0 1 3 0v1.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);
export const IconClock = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
    <path d="M12 7v5.5l3.8 2.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconShield = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M12 2 4 5.5V11c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5.5L12 2Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
  </svg>
);
export const IconClipboard = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <rect x="6" y="4" width="12" height="17" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
    <path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1M9 10h6M9 14h6M9 18h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);
export const IconMail = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <rect x="3" y="5" width="18" height="14" rx="1.7" stroke="currentColor" strokeWidth="1.7" />
    <path d="m4 6.5 8 6 8-6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconWarning = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M12 3.5 2 20h20L12 3.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    <path d="M12 9.5v4.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="12" cy="17" r="1" fill="currentColor" stroke="none" />
  </svg>
);
export const IconLightbulb = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.4 1 1.1 1 1.9v.2h5v-.2c0-.8.4-1.5 1-1.9A6 6 0 0 0 12 3Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const IconMessage = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path d="M4 4.8h16A1.2 1.2 0 0 1 21.2 6v10a1.2 1.2 0 0 1-1.2 1.2H8l-4.5 3.5a.5.5 0 0 1-.8-.4V6a1.2 1.2 0 0 1 1.2-1.2Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);
