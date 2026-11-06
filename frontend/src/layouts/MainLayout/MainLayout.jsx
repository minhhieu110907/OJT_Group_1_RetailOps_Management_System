import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import styles from './MainLayout.module.css';

export default function MainLayout() {
  return (
    <div className={styles.layoutContainer}>
      {/* Thanh Sidebar cố định bên trái */}
      <Sidebar />

      {/* Vùng khung bên phải gồm Header (có User Dropdown) và Nội dung trang (<Outlet />) */}
      <div className={styles.mainWrapper}>
        <Header />

        {/* Vùng nội dung chính bên dưới Header */}
        <main className={styles.pageContent}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
