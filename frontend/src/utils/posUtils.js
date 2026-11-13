export const DEFAULT_POS_PRODUCT_LIMIT = 6;
export const SEARCH_POS_PRODUCT_LIMIT = 24;
export const LOW_STOCK_THRESHOLD = 10;

/**
 * Format integer VND amount into readable Vietnamese currency string.
 */
export function formatVnd(amount) {
  const safeValue = Number.isFinite(amount) ? Math.round(amount) : 0;
  return `${new Intl.NumberFormat('vi-VN').format(safeValue)} ₫`;
}

/**
 * Prioritize ACTIVE categories that have newly added products (ordered by latestProducts),
 * followed by remaining ACTIVE categories.
 */
export function prioritizeCategoriesByLatestProducts(categories = [], latestProducts = []) {
  const activeCategories = Array.isArray(categories)
    ? categories.filter((cat) => cat && cat.status === 'ACTIVE')
    : [];

  if (activeCategories.length === 0) {
    return [];
  }

  const categoryMap = new Map(activeCategories.map((cat) => [cat.id, cat]));
  const prioritized = [];
  const seenIds = new Set();

  if (Array.isArray(latestProducts)) {
    for (const product of latestProducts) {
      if (!product || product.status !== 'ACTIVE') continue;
      const catId = product.category_id;
      if (categoryMap.has(catId) && !seenIds.has(catId)) {
        seenIds.add(catId);
        prioritized.push(categoryMap.get(catId));
      }
    }
  }

  for (const cat of activeCategories) {
    if (!seenIds.has(cat.id)) {
      seenIds.add(cat.id);
      prioritized.push(cat);
    }
  }

  return prioritized;
}

/**
 * Add 1 unit of a product to cart while respecting reference stock quantity.
 */
export function addProductToCart(cart = [], product) {
  if (!product || typeof product.id !== 'number') {
    return { nextCart: cart, added: false, reason: 'INVALID_PRODUCT' };
  }
  if ((product.quantity ?? 0) <= 0) {
    return { nextCart: cart, added: false, reason: 'OUT_OF_STOCK' };
  }

  const existingIndex = cart.findIndex((item) => item.productId === product.id);
  if (existingIndex === -1) {
    return {
      nextCart: [
        ...cart,
        {
          productId: product.id,
          sku: product.sku,
          name: product.name,
          unitPriceVnd: product.sale_price_vnd,
          quantity: 1,
          availableStock: product.quantity,
        },
      ],
      added: true,
      reason: null,
    };
  }

  const existing = cart[existingIndex];
  const maxStock = product.quantity;
  if (existing.quantity >= maxStock) {
    return { nextCart: cart, added: false, reason: 'EXCEEDS_STOCK' };
  }

  const nextCart = cart.map((item, idx) =>
    idx === existingIndex
      ? {
          ...item,
          name: product.name,
          unitPriceVnd: product.sale_price_vnd,
          availableStock: maxStock,
          quantity: item.quantity + 1,
        }
      : item
  );

  return { nextCart, added: true, reason: null };
}

/**
 * Update quantity of an item in cart; removes item if nextQuantity <= 0.
 */
export function updateCartItemQuantity(cart = [], productId, nextQuantity) {
  if (nextQuantity <= 0) {
    return cart.filter((item) => item.productId !== productId);
  }

  return cart.map((item) => {
    if (item.productId !== productId) return item;
    const clamped =
      typeof item.availableStock === 'number' && item.availableStock > 0
        ? Math.min(nextQuantity, item.availableStock)
        : nextQuantity;
    return { ...item, quantity: clamped };
  });
}

/**
 * Calculate summary totals for the POS cart.
 */
export function calculateCartTotals(cart = []) {
  let totalUnits = 0;
  let totalVnd = 0;

  for (const item of cart) {
    totalUnits += item.quantity;
    totalVnd += item.unitPriceVnd * item.quantity;
  }

  return {
    lineCount: cart.length,
    totalUnits,
    totalVnd,
  };
}

/**
 * Map cart items to strict CheckoutLine payload expected by POST /orders/checkout.
 */
export function buildCheckoutPayload(cart = []) {
  return cart.map((item) => ({
    product_id: item.productId,
    quantity: item.quantity,
    viewed_unit_price_vnd: item.unitPriceVnd,
  }));
}

/**
 * Classify POS checkout errors into definite failure, idempotency conflict,
 * or ambiguous outcome (where backend may have already committed the order).
 */
export function classifyCheckoutError(error) {
  if (!error) {
    return {
      outcome: 'DEFINITE_FAILURE',
      message: 'Không thể xác nhận bán hàng. Vui lòng thử lại.',
    };
  }

  if (
    error.isClientValidation ||
    error.code === 'ERR_MOCK_NOT_SUPPORTED' ||
    error.isReplayBlocked ||
    error.code === 'ERR_UNSAFE_MUTATION_REPLAY'
  ) {
    return {
      outcome: 'DEFINITE_FAILURE',
      message:
        error.isReplayBlocked || error.code === 'ERR_UNSAFE_MUTATION_REPLAY'
          ? 'Phiên đăng nhập vừa hết hạn nên hệ thống không tự động gửi lại đơn. Vui lòng bấm xác nhận lại.'
          : error.message || 'Dữ liệu đơn hàng không hợp lệ.',
    };
  }

  const status = error.response?.status;
  const apiCode = error.response?.data?.code;
  const apiMessage = error.response?.data?.message;

  if (apiCode === 'IDEMPOTENCY_KEY_REUSED') {
    return {
      outcome: 'IDEMPOTENCY_CONFLICT',
      message:
        apiMessage ||
        'Mã giao dịch đã được sử dụng cho nội dung khác. Vui lòng kiểm tra lại giỏ hàng.',
    };
  }

  if (apiCode === 'REQUEST_IN_PROGRESS') {
    return {
      outcome: 'AMBIGUOUS',
      message:
        apiMessage ||
        'Đơn hàng trước vẫn đang được máy chủ xử lý. Vui lòng kiểm tra lại kết quả trước khi tạo đơn mới.',
    };
  }

  if (
    !error.response ||
    error.code === 'ECONNABORTED' ||
    error.code === 'ETIMEDOUT' ||
    error.code === 'ERR_NETWORK' ||
    (typeof status === 'number' && status >= 500)
  ) {
    return {
      outcome: 'AMBIGUOUS',
      message:
        'Chưa xác định được kết quả đơn hàng do mất kết nối hoặc quá thời gian chờ. Đơn hàng có thể đã được ghi nhận trên máy chủ.',
    };
  }

  return {
    outcome: 'DEFINITE_FAILURE',
    message:
      apiMessage ||
      error.message ||
      'Không thể xác nhận bán hàng. Vui lòng kiểm tra lại tồn kho và đơn giá.',
  };
}

export const PENDING_CHECKOUT_STORAGE_KEY = 'retailops_pos_pending_checkout_v1';
export const PENDING_CHECKOUT_TTL_MS = 24 * 60 * 60 * 1000;

/**
 * Build a non-sensitive owner scope for pending POS checkout without storing
 * JWT, refresh token, CSRF token, or PII in browser storage.
 */
export function buildPendingCheckoutOwnerScope(user, isMockMode = false) {
  if (isMockMode) {
    return user?.id != null ? `mock:${String(user.id)}` : 'mock:demo';
  }
  if (user?.id == null) {
    return null;
  }
  return `api:${String(user.id)}`;
}

/**
 * Persist unresolved/in-flight POS checkout snapshot and idempotency key
 * BEFORE sending the request so crash/reload cannot silently unlock the cart.
 */
export function savePendingCheckout(storage, pendingCheckout, ownerScopeArg) {
  const ownerScope = ownerScopeArg || pendingCheckout?.ownerScope;
  if (
    !storage ||
    typeof storage.setItem !== 'function' ||
    typeof ownerScope !== 'string' ||
    !ownerScope.trim() ||
    !pendingCheckout ||
    typeof pendingCheckout.idempotencyKey !== 'string' ||
    !pendingCheckout.idempotencyKey.trim() ||
    !Array.isArray(pendingCheckout.itemsSnapshot) ||
    pendingCheckout.itemsSnapshot.length === 0
  ) {
    return false;
  }

  try {
    const createdAt = pendingCheckout.createdAt || new Date().toISOString();
    const createdMs = Date.parse(createdAt);
    const expiresAt =
      pendingCheckout.expiresAt ||
      new Date(
        (Number.isFinite(createdMs) ? createdMs : Date.now()) +
          PENDING_CHECKOUT_TTL_MS
      ).toISOString();

    const payload = {
      ownerScope,
      idempotencyKey: pendingCheckout.idempotencyKey,
      itemsSnapshot: pendingCheckout.itemsSnapshot,
      cartSnapshot: Array.isArray(pendingCheckout.cartSnapshot)
        ? pendingCheckout.cartSnapshot
        : [],
      totalVnd: Number.isFinite(pendingCheckout.totalVnd)
        ? pendingCheckout.totalVnd
        : 0,
      lineCount: Number.isFinite(pendingCheckout.lineCount)
        ? pendingCheckout.lineCount
        : pendingCheckout.itemsSnapshot.length,
      reasonMessage:
        typeof pendingCheckout.reasonMessage === 'string'
          ? pendingCheckout.reasonMessage
          : '',
      status:
        pendingCheckout.status === 'IN_FLIGHT' ? 'IN_FLIGHT' : 'AMBIGUOUS',
      createdAt,
      expiresAt,
    };
    storage.setItem(PENDING_CHECKOUT_STORAGE_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

/**
 * Restore unresolved POS checkout from session storage only when ownerScope matches
 * the active user/session, and annotate whether Backend's 24h TTL has expired.
 */
export function loadPendingCheckout(storage, ownerScope, nowMs = Date.now()) {
  if (
    !storage ||
    typeof storage.getItem !== 'function' ||
    typeof ownerScope !== 'string' ||
    !ownerScope.trim()
  ) {
    return null;
  }

  try {
    const raw = storage.getItem(PENDING_CHECKOUT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      !parsed ||
      parsed.ownerScope !== ownerScope ||
      typeof parsed.idempotencyKey !== 'string' ||
      !parsed.idempotencyKey.trim() ||
      !Array.isArray(parsed.itemsSnapshot) ||
      parsed.itemsSnapshot.length === 0
    ) {
      return null;
    }

    const createdMs = Date.parse(parsed.createdAt || '');
    const expiresMs = Date.parse(parsed.expiresAt || '');
    const effectiveExpiresMs = Number.isFinite(expiresMs)
      ? expiresMs
      : Number.isFinite(createdMs)
      ? createdMs + PENDING_CHECKOUT_TTL_MS
      : 0;
    const isExpired = !effectiveExpiresMs || nowMs >= effectiveExpiresMs;

    return {
      ownerScope: parsed.ownerScope,
      idempotencyKey: parsed.idempotencyKey,
      itemsSnapshot: parsed.itemsSnapshot,
      cartSnapshot: Array.isArray(parsed.cartSnapshot) ? parsed.cartSnapshot : [],
      totalVnd: Number.isFinite(parsed.totalVnd) ? parsed.totalVnd : 0,
      lineCount: Number.isFinite(parsed.lineCount)
        ? parsed.lineCount
        : parsed.itemsSnapshot.length,
      reasonMessage:
        typeof parsed.reasonMessage === 'string' && parsed.reasonMessage
          ? parsed.reasonMessage
          : 'Phát hiện giao dịch chưa hoàn tất trước khi tải lại trang. Vui lòng kiểm tra lại kết quả đơn hàng.',
      status: parsed.status === 'IN_FLIGHT' ? 'IN_FLIGHT' : 'AMBIGUOUS',
      createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : '',
      expiresAt: typeof parsed.expiresAt === 'string' ? parsed.expiresAt : '',
      isExpired,
    };
  } catch {
    return null;
  }
}

/**
 * Remove persisted unresolved POS checkout only if it belongs to ownerScope (or no scope filter).
 */
export function clearPendingCheckout(storage, ownerScope) {
  if (!storage || typeof storage.removeItem !== 'function') {
    return;
  }
  try {
    if (ownerScope && typeof storage.getItem === 'function') {
      const raw = storage.getItem(PENDING_CHECKOUT_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.ownerScope && parsed.ownerScope !== ownerScope) {
          return;
        }
      }
    }
    storage.removeItem(PENDING_CHECKOUT_STORAGE_KEY);
  } catch {
    // Ignore storage removal errors
  }
}

/**
 * Enforce unresolved checkout guard:
 * - RETRY always reuses exact itemsSnapshot + idempotencyKey unless 24h TTL expired.
 * - ABANDON / NEW_CHECKOUT is blocked unless manualReconciliationConfirmed === true.
 */
export function resolvePendingCheckoutAction({
  action,
  pendingCheckout,
  manualReconciliationConfirmed = false,
  nowMs = Date.now(),
}) {
  if (!pendingCheckout) {
    if (action === 'RETRY') {
      return {
        allowed: false,
        nextPendingCheckout: null,
        rotateKey: false,
        reason: 'NO_PENDING_CHECKOUT',
      };
    }
    return {
      allowed: true,
      nextPendingCheckout: null,
      rotateKey: true,
      reason: null,
    };
  }

  if (action === 'RETRY') {
    const expiresMs = Date.parse(pendingCheckout.expiresAt || '');
    const isExpired =
      Boolean(pendingCheckout.isExpired) ||
      (Number.isFinite(expiresMs) && nowMs >= expiresMs);

    if (isExpired) {
      return {
        allowed: false,
        nextPendingCheckout: pendingCheckout,
        rotateKey: false,
        reason: 'IDEMPOTENCY_EXPIRED',
        message:
          'Mã giao dịch đã quá thời hạn 24 giờ của máy chủ nên không thể tự kiểm tra lại bằng khóa cũ. Vui lòng đối soát thủ công với Quản trị viên trước khi mở khóa.',
      };
    }

    return {
      allowed: true,
      itemsSnapshot: pendingCheckout.itemsSnapshot,
      idempotencyKey: pendingCheckout.idempotencyKey,
      nextPendingCheckout: pendingCheckout,
      rotateKey: false,
      reason: null,
    };
  }

  if (action === 'ABANDON' || action === 'NEW_CHECKOUT') {
    if (manualReconciliationConfirmed !== true) {
      return {
        allowed: false,
        nextPendingCheckout: pendingCheckout,
        rotateKey: false,
        reason: 'MANUAL_RECONCILIATION_REQUIRED',
        message:
          'Không thể mở khóa giỏ hàng hoặc tạo đơn mới khi chưa xác nhận đã đối soát thủ công kết quả đơn chờ.',
      };
    }

    return {
      allowed: true,
      nextPendingCheckout: null,
      rotateKey: true,
      reason: 'MANUALLY_RECONCILED',
    };
  }

  return {
    allowed: false,
    nextPendingCheckout: pendingCheckout,
    rotateKey: false,
    reason: 'UNKNOWN_ACTION',
  };
}

/**
 * Crash-safe POS checkout executor:
 * 1. Validates ownerScope & checks 24h TTL on retries.
 * 2. Persists snapshot + Idempotency-Key BEFORE calling checkoutOrderFn.
 * 3. Aborts checkout if persistence fails (never sends unprotected mutation).
 * 4. Clears pending state on success / definite failure / conflict; preserves on ambiguous.
 */
export async function executeSafePosCheckout({
  storage,
  ownerScope,
  isMockMode,
  itemsSnapshot,
  cartSnapshot = [],
  totalVnd = 0,
  lineCount = 0,
  idempotencyKey,
  pendingCheckout = null,
  checkoutOrderFn,
  nowMs = Date.now(),
}) {
  if (typeof ownerScope !== 'string' || !ownerScope.trim()) {
    return {
      ok: false,
      outcome: 'DEFINITE_FAILURE',
      pendingCheckout,
      rotateKey: false,
      message: 'Phiên đăng nhập chưa hợp lệ để thực hiện thanh toán.',
    };
  }

  let effectiveItems = itemsSnapshot;
  let effectiveKey = idempotencyKey;

  if (pendingCheckout) {
    const retryResolution = resolvePendingCheckoutAction({
      action: 'RETRY',
      pendingCheckout,
      nowMs,
    });
    if (!retryResolution.allowed) {
      return {
        ok: false,
        outcome: retryResolution.reason,
        pendingCheckout,
        rotateKey: false,
        message: retryResolution.message,
      };
    }
    effectiveItems = retryResolution.itemsSnapshot;
    effectiveKey = retryResolution.idempotencyKey;
  }

  if (!Array.isArray(effectiveItems) || effectiveItems.length === 0) {
    return {
      ok: false,
      outcome: 'DEFINITE_FAILURE',
      pendingCheckout,
      rotateKey: false,
      message: 'Giỏ hàng trống, không thể thanh toán.',
    };
  }

  const createdAt = pendingCheckout?.createdAt || new Date(nowMs).toISOString();
  const createdMs = Date.parse(createdAt);
  const expiresAt =
    pendingCheckout?.expiresAt ||
    new Date(
      (Number.isFinite(createdMs) ? createdMs : nowMs) +
        PENDING_CHECKOUT_TTL_MS
    ).toISOString();

  const inFlightPending = {
    ownerScope,
    idempotencyKey: effectiveKey,
    itemsSnapshot: effectiveItems,
    cartSnapshot:
      pendingCheckout?.cartSnapshot?.length > 0
        ? pendingCheckout.cartSnapshot
        : cartSnapshot,
    totalVnd: pendingCheckout ? pendingCheckout.totalVnd : totalVnd,
    lineCount: pendingCheckout ? pendingCheckout.lineCount : lineCount,
    reasonMessage:
      pendingCheckout?.reasonMessage ||
      'Giao dịch đang được gửi hoặc bị gián đoạn trước khi nhận phản hồi từ máy chủ.',
    status: 'IN_FLIGHT',
    createdAt,
    expiresAt,
  };

  const persisted = savePendingCheckout(storage, inFlightPending, ownerScope);
  if (!persisted) {
    return {
      ok: false,
      outcome: 'PERSIST_FAILED',
      pendingCheckout,
      rotateKey: false,
      message:
        'Không thể lưu trạng thái an toàn trước khi thanh toán. Hệ thống đã chặn gửi đơn để tránh rủi ro tạo đơn trùng.',
    };
  }

  try {
    const order = await checkoutOrderFn({
      isMockMode,
      items: effectiveItems,
      idempotencyKey: effectiveKey,
    });
    clearPendingCheckout(storage, ownerScope);
    return {
      ok: true,
      outcome: 'SUCCESS',
      order,
      pendingCheckout: null,
      rotateKey: true,
    };
  } catch (err) {
    const classified = classifyCheckoutError(err);
    if (classified.outcome === 'AMBIGUOUS') {
      const nextPending = {
        ...inFlightPending,
        status: 'AMBIGUOUS',
        reasonMessage: classified.message,
      };
      savePendingCheckout(storage, nextPending, ownerScope);
      return {
        ok: false,
        outcome: 'AMBIGUOUS',
        pendingCheckout: nextPending,
        rotateKey: false,
        message: classified.message,
      };
    }

    clearPendingCheckout(storage, ownerScope);
    return {
      ok: false,
      outcome: classified.outcome,
      pendingCheckout: null,
      rotateKey: classified.outcome === 'IDEMPOTENCY_CONFLICT',
      message: classified.message,
    };
  }
}
