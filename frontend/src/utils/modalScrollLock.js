/**
 * Reference-counted background scroll & wheel/touchpad lock for open modals.
 * Ensures that while any modal is open, background containers (html, body, main)
 * cannot be scrolled via mouse wheel, touchpad, or touch gestures, while still
 * allowing scrolling inside the modal box and clicking the backdrop to close.
 */

let activeModalLocks = 0;
let prevBodyOverflow = '';
let prevHtmlOverflow = '';

function blockBackdropScroll(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;

  const modalSurface = target.closest(
    '[role="dialog"], [aria-modal="true"], [role="listbox"]'
  );
  // Chặn cuộn nếu con trỏ nằm ngoài modal hoặc đang đặt trực tiếp trên lớp nền mờ (backdrop)
  if (!modalSurface || target === modalSurface) {
    if (event.cancelable) {
      event.preventDefault();
    }
  }
}

export function acquireModalScrollLock() {
  if (typeof document === 'undefined') {
    return () => {};
  }

  if (activeModalLocks === 0) {
    prevBodyOverflow = document.body.style.overflow;
    prevHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    document.documentElement.setAttribute('data-modal-open', 'true');
    document.addEventListener('wheel', blockBackdropScroll, { passive: false });
    document.addEventListener('touchmove', blockBackdropScroll, { passive: false });
  }
  activeModalLocks += 1;

  let released = false;
  return () => {
    if (released) return;
    released = true;
    activeModalLocks = Math.max(0, activeModalLocks - 1);
    if (activeModalLocks === 0) {
      document.removeEventListener('wheel', blockBackdropScroll);
      document.removeEventListener('touchmove', blockBackdropScroll);
      document.documentElement.removeAttribute('data-modal-open');
      document.body.style.overflow = prevBodyOverflow;
      document.documentElement.style.overflow = prevHtmlOverflow;
    }
  };
}
