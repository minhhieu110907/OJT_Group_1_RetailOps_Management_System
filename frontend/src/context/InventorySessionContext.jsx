import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { areAdjustmentSessionsEqual } from '../pages/Inventory/inventoryAdjustmentController';

const InventorySessionContext = createContext(null);

export function InventorySessionProvider({ children }) {
  const { user } = useAuth();
  const [liftedSession, setLiftedSession] = useState(null);

  // Clear lifted session immediately if user logs out or switches accounts
  useEffect(() => {
    if (!user || user.role !== 'ADMIN') {
      setLiftedSession(null);
    }
  }, [user]);

  const updateLiftedSession = useCallback((newSession) => {
    setLiftedSession((prev) => {
      if (areAdjustmentSessionsEqual(prev, newSession)) {
        return prev;
      }
      return newSession;
    });
  }, []);

  const clearLiftedSession = useCallback(() => {
    setLiftedSession(null);
  }, []);

  return (
    <InventorySessionContext.Provider
      value={{
        liftedSession,
        updateLiftedSession,
        clearLiftedSession,
      }}
    >
      {children}
    </InventorySessionContext.Provider>
  );
}

export function useInventorySession() {
  const ctx = useContext(InventorySessionContext);
  if (!ctx) {
    // If mounted outside provider (e.g. isolated test without wrapper), fail-safe to noop/local
    return {
      liftedSession: null,
      updateLiftedSession: () => {},
      clearLiftedSession: () => {},
    };
  }
  return ctx;
}

