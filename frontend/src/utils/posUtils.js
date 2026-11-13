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
