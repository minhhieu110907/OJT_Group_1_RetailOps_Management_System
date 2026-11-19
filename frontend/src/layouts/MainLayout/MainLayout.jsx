import { useState, useCallback } from 'react';
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
