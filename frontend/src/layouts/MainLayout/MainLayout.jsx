import { useState, useCallback, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import styles from './MainLayout.module.css';

export default function MainLayout() {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  const handleToggleMobileNav = useCallback(() => {
    setIsMobileNavOpen((prev) => !prev);
  }, []);

  const handleCloseMobileNav = useCallback(() => {
    setIsMobileNavOpen(false);
  }, []);

  // P2: Đồng bộ trạng thái khi viewport resize vượt breakpoint desktop (>= 1024px)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;

    const mql = window.matchMedia('(min-width: 1024px)');

    const handleBreakpointChange = (e) => {
      // Khi chuyển sang desktop, đóng mobile drawer
      if (e.matches) {
        setIsMobileNavOpen(false);
      }
    };

    if (mql.matches) {
      setIsMobileNavOpen(false);
    }

    if (mql.addEventListener) {
      mql.addEventListener('change', handleBreakpointChange);
    } else if (mql.addListener) {
      mql.addListener(handleBreakpointChange);
    }

    return () => {
      if (mql.removeEventListener) {
        mql.removeEventListener('change', handleBreakpointChange);
      } else if (mql.removeListener) {
        mql.removeListener(handleBreakpointChange);
      }
    };
  }, []);

  return (
    <div className={styles.layoutContainer}>
      {/* Thanh Sidebar bên trái (cố định trên Desktop, trượt Drawer trên Tablet & Mobile) */}
      <Sidebar
        isOpen={isMobileNavOpen}
        onClose={handleCloseMobileNav}
      />

      {/* Vùng khung bên phải gồm Header (có User Dropdown) và Nội dung trang (<Outlet />) */}
      <div className={styles.mainWrapper}>
        <Header
          isMobileNavOpen={isMobileNavOpen}
          onToggleMobileNav={handleToggleMobileNav}
        />

        {/* Vùng nội dung chính bên dưới Header */}
        <main className={styles.pageContent}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
