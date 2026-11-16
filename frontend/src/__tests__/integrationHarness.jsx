import React from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import InventoryList from '../pages/Inventory/InventoryList.jsx';
import InventoryAdjustModal from '../pages/Inventory/InventoryAdjustModal.jsx';
import { InventorySessionProvider, useInventorySession } from '../context/InventorySessionContext.jsx';
import { AuthContext } from '../context/AuthContext.jsx';
import { ToastProvider } from '../components/common/Toast/ToastContext.jsx';
import axiosClient from '../api/axiosClient.js';
import { inventoryApi } from '../api/inventoryApi.js';

export {
  InventoryList,
  InventoryAdjustModal,
  InventorySessionProvider,
  useInventorySession,
  AuthContext,
  ToastProvider,
  axiosClient,
  inventoryApi,
};

/**
 * Test router component providing programmatic navigation hook ref
 */
export function TestAppRouter({ navigateRef }) {
  const navigate = useNavigate();
  React.useEffect(() => {
    if (navigateRef) {
      navigateRef.current = navigate;
    }
  }, [navigate, navigateRef]);
  return (
    <Routes>
      <Route path="/inventory" element={<InventoryList />} />
      <Route
        path="/orders"
        element={<div data-testid="orders-page">Trang danh sách đơn hàng (Placeholder)</div>}
      />
    </Routes>
  );
}
