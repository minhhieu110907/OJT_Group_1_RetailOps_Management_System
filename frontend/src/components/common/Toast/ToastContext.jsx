import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { ToastViewport } from './Toast';

// 1. Tạo Context cho hệ thống thông báo Toast
const ToastContext = createContext(null);

// 2. Tạo Provider bọc ngoài ứng dụng
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  // Hàm xóa 1 thông báo theo ID
  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  // Hàm thêm 1 thông báo mới và tự động ẩn sau 3000ms (3 giây)
  const addToast = useCallback(
    (type, message, duration = 3000) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

      setToasts((prev) => [...prev, { id, type, message }]);

      setTimeout(() => {
        removeToast(id);
      }, duration);
    },
    [removeToast]
  );

  // Bộ hàm gọi nhanh: toast.success(...), toast.error(...), toast.warning(...), toast.info(...)
  const toast = useMemo(() => {
    const api = {
      success: (message) => addToast('success', message),
      error: (message) => addToast('error', message),
      warning: (message) => addToast('warning', message),
      info: (message) => addToast('info', message),
    };
    // Hỗ trợ cả 2 cách viết: `const toast = useToast()` hoặc `const { toast } = useToast()`
    api.toast = api;
    return api;
  }, [addToast]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {/* Hiển thị danh sách thông báo nổi ở góc trên bên phải */}
      <ToastViewport toasts={toasts} onClose={removeToast} />
    </ToastContext.Provider>
  );
}

// 3. Custom Hook để gọi thông báo ở bất kỳ component nào
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast phải được sử dụng bên trong <ToastProvider>');
  }
  return context;
}

