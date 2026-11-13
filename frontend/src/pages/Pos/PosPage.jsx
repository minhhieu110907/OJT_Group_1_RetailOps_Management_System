import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { productsApi } from '../../api/productsApi';
import { categoriesApi } from '../../api/categoriesApi';
import {
  generateCheckoutIdempotencyKey,
  ordersApi,
} from '../../api/ordersApi';
import {
  DEFAULT_POS_PRODUCT_LIMIT,
  LOW_STOCK_THRESHOLD,
  SEARCH_POS_PRODUCT_LIMIT,
  addProductToCart,
  buildCheckoutPayload,
  calculateCartTotals,
  classifyCheckoutError,
  formatVnd,
  prioritizeCategoriesByLatestProducts,
  updateCartItemQuantity,
} from '../../utils/posUtils';
import styles from './PosPage.module.css';

function ProductThumbnail({ product }) {
  const [hasImageError, setHasImageError] = useState(false);
  const imageUrl = typeof product?.image_url === 'string' ? product.image_url.trim() : '';

  if (imageUrl && !hasImageError) {
    return (
      <img
        src={imageUrl}
        alt={product.name}
        className={styles.productImage}
        loading="lazy"
        onError={() => setHasImageError(true)}
      />
    );
  }

  const words = (product?.name || 'SP').trim().split(/\s+/);
  const monogram =
    words.length >= 2
      ? `${words[0][0] || ''}${words[1][0] || ''}`.toUpperCase()
      : (words[0]?.slice(0, 2) || 'SP').toUpperCase();

  return (
    <div className={styles.imagePlaceholder} aria-hidden="true">
      <span className={styles.placeholderMonogram}>{monogram}</span>
    </div>
  );
}

export default function PosPage() {
  const { isMockMode } = useAuth();
  const toast = useToast();

  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState('');

  const [products, setProducts] = useState([]);
  const [latestProductsSnapshot, setLatestProductsSnapshot] = useState([]);
  const [categories, setCategories] = useState([]);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [cart, setCart] = useState([]);
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [pendingCheckout, setPendingCheckout] = useState(null);
  const isCheckingOutRef = useRef(false);
  const idempotencyKeyRef = useRef(generateCheckoutIdempotencyKey());
  const requestIdRef = useRef(0);

  // Debounce tìm kiếm theo tên sản phẩm hoặc mã SKU
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim());
    }, 280);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Tải danh sách danh mục ACTIVE và 6 sản phẩm mới nhất làm gốc sắp xếp ưu tiên danh mục
  useEffect(() => {
    let cancelled = false;

    async function loadMeta() {
      try {
        const [catRes, latestRes] = await Promise.all([
          categoriesApi.getCategories({ page: 1, pageSize: 100, status: 'ACTIVE' }),
          productsApi.getProducts({
            isMockMode,
            page: 1,
            pageSize: DEFAULT_POS_PRODUCT_LIMIT,
            status: 'ACTIVE',
            sort: 'created_desc',
          }),
        ]);
        if (!cancelled) {
          setCategories(catRes.items || []);
          setLatestProductsSnapshot(latestRes.items || []);
        }
      } catch {
        // Lỗi tải catalog chính sẽ được hiển thị ở effect bên dưới
      }
    }

    loadMeta();
    return () => {
      cancelled = true;
    };
  }, [isMockMode, refreshTrigger]);

  // Tải sản phẩm hiển thị tại POS (mặc định 6 sản phẩm mới nhất; khi tìm kiếm/lọc mở rộng để tra cứu đầy đủ)
  const isFiltering = Boolean(debouncedSearch || selectedCategoryId);

  useEffect(() => {
    const currentRequestId = ++requestIdRef.current;

    async function fetchPosProducts() {
      await Promise.resolve();
      if (currentRequestId !== requestIdRef.current) return;
      setIsLoading(true);
      setLoadError('');

      try {
        const res = await productsApi.getProducts({
          isMockMode,
          page: 1,
          pageSize: isFiltering ? SEARCH_POS_PRODUCT_LIMIT : DEFAULT_POS_PRODUCT_LIMIT,
          keyword: debouncedSearch,
          categoryId: selectedCategoryId,
          status: 'ACTIVE',
          sort: 'created_desc',
        });

        if (currentRequestId === requestIdRef.current) {
          setProducts(res.items || []);
        }
      } catch (err) {
        if (currentRequestId === requestIdRef.current) {
          setLoadError(
            getApiErrorMessage(err, 'Không thể tải danh sách sản phẩm tại quầy.')
          );
        }
      } finally {
        if (currentRequestId === requestIdRef.current) {
          setIsLoading(false);
        }
      }
    }

    fetchPosProducts();
  }, [isMockMode, debouncedSearch, selectedCategoryId, isFiltering, refreshTrigger]);

  const orderedCategories = useMemo(
    () => prioritizeCategoriesByLatestProducts(categories, latestProductsSnapshot),
    [categories, latestProductsSnapshot]
  );

  const cartTotals = useMemo(() => calculateCartTotals(cart), [cart]);
  const hasCartItems = cart.length > 0;
  const isCartLocked = isCheckingOut || Boolean(pendingCheckout);

  const cartQuantityMap = useMemo(() => {
    const map = new Map();
    for (const item of cart) {
      map.set(item.productId, item.quantity);
    }
    return map;
  }, [cart]);

  const handleAddToCart = (product) => {
    if (isCartLocked || isCheckingOutRef.current) return;
    const result = addProductToCart(cart, product);
    if (!result.added) {
      if (result.reason === 'OUT_OF_STOCK') {
        toast.warning(`Sản phẩm "${product.name}" hiện đã hết hàng.`);
      } else if (result.reason === 'EXCEEDS_STOCK') {
        toast.warning(
          `Số lượng "${product.name}" trong giỏ đã đạt mức tồn kho tham khảo (${product.quantity}).`
        );
      }
      return;
    }

    setCart(result.nextCart);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
  };

  const handleUpdateQty = (productId, nextQty) => {
    if (isCartLocked || isCheckingOutRef.current) return;
    setCart((prev) => updateCartItemQuantity(prev, productId, nextQty));
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
  };

  const handleClearCart = () => {
    if (isCartLocked || isCheckingOutRef.current) return;
    setCart([]);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
  };

  const handleAbandonPendingCheckout = () => {
    if (isCheckingOutRef.current) return;
    setPendingCheckout(null);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleConfirmCheckout = async () => {
    if (isCheckingOutRef.current) return;
    const snapshotItems = pendingCheckout
      ? pendingCheckout.itemsSnapshot
      : buildCheckoutPayload(cart);
    const requestKey = pendingCheckout
      ? pendingCheckout.idempotencyKey
      : idempotencyKeyRef.current;

    if (!snapshotItems || snapshotItems.length === 0) return;

    isCheckingOutRef.current = true;
    setIsCheckingOut(true);
    try {
      const order = await ordersApi.checkoutOrder({
        isMockMode,
        items: snapshotItems,
        idempotencyKey: requestKey,
      });

      toast.success(
        `Thanh toán thành công đơn #${order.id} — Tổng ${formatVnd(order.total_vnd)}.`
      );
      setPendingCheckout(null);
      setCart([]);
      idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      const classified = classifyCheckoutError(err);
      if (classified.outcome === 'AMBIGUOUS') {
        setPendingCheckout({
          idempotencyKey: requestKey,
          itemsSnapshot: snapshotItems,
          totalVnd: pendingCheckout ? pendingCheckout.totalVnd : cartTotals.totalVnd,
          lineCount: pendingCheckout ? pendingCheckout.lineCount : cartTotals.lineCount,
          reasonMessage: classified.message,
        });
        toast.warning(classified.message);
      } else if (classified.outcome === 'IDEMPOTENCY_CONFLICT') {
        setPendingCheckout(null);
        idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
        toast.error(classified.message);
      } else {
        setPendingCheckout(null);
        toast.error(classified.message);
        setRefreshTrigger((prev) => prev + 1);
      }
    } finally {
      isCheckingOutRef.current = false;
      setIsCheckingOut(false);
    }
  };

  return (
    <div
      className={`${styles.posLayout} ${
        hasCartItems ? styles.posLayoutWithCart : ''
      }`}
    >
      {/* Khu vực sản phẩm bên trái (tự mở rộng 100% khi giỏ hàng trống) */}
      <section className={styles.catalogSection} aria-label="Danh sách sản phẩm POS">
        <div className={styles.pageHeader}>
          <div className={styles.titleGroup}>
            <h1 className={styles.pageTitle}>Bán hàng tại quầy (POS)</h1>
            <span className={styles.storeBadge}>Cửa hàng RetailOps</span>
          </div>
        </div>

        <div className={styles.toolbar}>
          <div className={styles.searchBox}>
            <svg
              className={styles.searchIcon}
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Tìm kiếm theo tên sản phẩm hoặc mã SKU..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              aria-label="Tìm kiếm theo tên sản phẩm hoặc mã SKU"
            />
            {searchTerm && (
              <button
                type="button"
                className={styles.clearSearchBtn}
                onClick={() => setSearchTerm('')}
                aria-label="Xóa từ khóa tìm kiếm"
              >
                ×
              </button>
            )}
          </div>

          <div className={styles.categoryRow} role="tablist" aria-label="Lọc theo danh mục">
            <button
              type="button"
              role="tab"
              aria-selected={selectedCategoryId === ''}
              className={`${styles.categoryPill} ${
                selectedCategoryId === '' ? styles.categoryPillActive : ''
              }`}
              onClick={() => setSelectedCategoryId('')}
            >
              Tất cả
            </button>

            {orderedCategories.map((cat) => {
              const isSelected = String(selectedCategoryId) === String(cat.id);
              return (
                <button
                  key={cat.id}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  className={`${styles.categoryPill} ${
                    isSelected ? styles.categoryPillActive : ''
                  }`}
                  onClick={() => setSelectedCategoryId(String(cat.id))}
                >
                  {cat.name}
                </button>
              );
            })}
          </div>
        </div>

        {isLoading ? (
          <div className={styles.loadingState}>
            Đang tải sản phẩm sẵn có tại quầy...
          </div>
        ) : loadError ? (
          <div className={styles.errorState} role="alert">
            {loadError}
          </div>
        ) : products.length === 0 ? (
          <div className={styles.emptyState}>
            {isFiltering
              ? 'Không tìm thấy sản phẩm phù hợp với từ khóa hoặc danh mục đã chọn.'
              : 'Chưa có sản phẩm đang hoạt động để bán tại quầy.'}
          </div>
        ) : (
          <div className={styles.productGrid}>
            {products.map((product) => {
              const inCartQty = cartQuantityMap.get(product.id) || 0;
              const isOutOfStock = product.quantity <= 0;
              const isLowStock =
                !isOutOfStock && product.quantity <= LOW_STOCK_THRESHOLD;
              const isAtStockLimit = inCartQty >= product.quantity;

              return (
                <article
                  key={product.id}
                  className={`${styles.productCard} ${
                    isOutOfStock ? styles.productCardOutOfStock : ''
                  }`}
                >
                  <div>
                    <div className={styles.imageFrame}>
                      <ProductThumbnail product={product} />
                      <span className={styles.skuBadge}>{product.sku}</span>
                    </div>

                    <h2 className={styles.productName} title={product.name}>
                      {product.name}
                    </h2>

                    <div className={styles.stockRow}>
                      <span>Tồn kho:</span>
                      {isOutOfStock ? (
                        <span className={styles.outOfStockBadge}>Hết hàng</span>
                      ) : isLowStock ? (
                        <span className={styles.lowStockBadge}>
                          • Còn {product.quantity}
                        </span>
                      ) : (
                        <span className={styles.stockValue}>
                          {product.quantity} sản phẩm
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={styles.cardFooter}>
                    <div>
                      <span className={styles.priceLabel}>Đơn giá</span>
                      <span className={styles.priceValue}>
                        {formatVnd(product.sale_price_vnd)}
                      </span>
                    </div>

                    <button
                      type="button"
                      className={styles.addBtn}
                      onClick={() => handleAddToCart(product)}
                      disabled={isOutOfStock || isAtStockLimit || isCartLocked}
                    >
                      <svg
                        width="15"
                        height="15"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <circle cx="9" cy="21" r="1" />
                        <circle cx="20" cy="21" r="1" />
                        <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
                      </svg>
                      <span>{inCartQty > 0 ? `Thêm (${inCartQty})` : 'Thêm'}</span>
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* Giỏ hàng bên phải — CHỈ hiển thị khi có hàng trong giỏ */}
      {hasCartItems && (
        <aside className={styles.cartPanel} aria-label="Giỏ hàng hiện tại">
          <div className={styles.cartHeader}>
            <h2 className={styles.cartTitle}>
              <svg
                className={styles.cartTitleIcon}
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="9" cy="21" r="1" />
                <circle cx="20" cy="21" r="1" />
                <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
              </svg>
              <span>Giỏ hàng ({cartTotals.lineCount} món)</span>
            </h2>

            <button
              type="button"
              className={styles.clearCartBtn}
              onClick={handleClearCart}
              disabled={isCartLocked}
            >
              Xóa tất cả
            </button>
          </div>

          <div className={styles.cartList}>
            {cart.map((item) => (
              <div key={item.productId} className={styles.cartItem}>
                <div className={styles.cartItemInfo}>
                  <p className={styles.cartItemName} title={item.name}>
                    {item.name}
                  </p>
                  <div className={styles.cartItemMeta}>
                    SKU: {item.sku} • {formatVnd(item.unitPriceVnd)}
                  </div>
                </div>

                <div className={styles.qtyStepper}>
                  <button
                    type="button"
                    className={styles.qtyBtn}
                    onClick={() => handleUpdateQty(item.productId, item.quantity - 1)}
                    disabled={isCartLocked}
                    aria-label={`Giảm số lượng ${item.name}`}
                  >
                    −
                  </button>
                  <span className={styles.qtyValue}>{item.quantity}</span>
                  <button
                    type="button"
                    className={styles.qtyBtn}
                    onClick={() => handleUpdateQty(item.productId, item.quantity + 1)}
                    disabled={
                      isCartLocked ||
                      (typeof item.availableStock === 'number' &&
                        item.quantity >= item.availableStock)
                    }
                    aria-label={`Tăng số lượng ${item.name}`}
                  >
                    +
                  </button>
                </div>

                <div className={styles.cartItemRight}>
                  <span className={styles.lineTotal}>
                    {formatVnd(item.unitPriceVnd * item.quantity)}
                  </span>
                  <button
                    type="button"
                    className={styles.removeItemBtn}
                    onClick={() => handleUpdateQty(item.productId, 0)}
                    disabled={isCartLocked}
                  >
                    Xóa
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.cartFooter}>
            <div className={styles.disclaimerBanner}>
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ flexShrink: 0, marginTop: '1px' }}
                aria-hidden="true"
              >
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <polyline points="9 12 11 14 15 10" />
              </svg>
              <span>
                Giỏ hàng không giữ trước tồn kho. Giá bán và số lượng sẽ được kiểm
                tra khi xác nhận bán.
              </span>
            </div>

            <div className={styles.summaryRow}>
              <span>Tạm tính ({cartTotals.totalUnits} sản phẩm)</span>
              <strong>{formatVnd(cartTotals.totalVnd)}</strong>
            </div>

            <div className={styles.totalRow}>
              <span className={styles.totalLabel}>Tổng tiền thanh toán</span>
              <span className={styles.totalValue}>
                {formatVnd(cartTotals.totalVnd)}
              </span>
            </div>

            {pendingCheckout && (
              <div className={styles.ambiguousBanner} role="alert">
                <strong>Trạng thái đơn hàng chưa xác định</strong>
                <p>{pendingCheckout.reasonMessage}</p>
                <span>
                  Giỏ hàng tạm khóa để tránh tạo đơn trùng. Bấm &quot;Kiểm tra lại kết
                  quả đơn này&quot; để đối chiếu bằng cùng mã giao dịch.
                </span>
                <button
                  type="button"
                  className={styles.abandonPendingBtn}
                  onClick={handleAbandonPendingCheckout}
                  disabled={isCheckingOut}
                >
                  Mở khóa giỏ hàng (bỏ qua đơn chờ)
                </button>
              </div>
            )}

            <button
              type="button"
              className={styles.checkoutBtn}
              onClick={handleConfirmCheckout}
              disabled={isCheckingOut}
            >
              {isCheckingOut
                ? 'Đang xử lý đơn hàng...'
                : pendingCheckout
                ? 'Kiểm tra lại kết quả đơn này'
                : 'Xác nhận bán hàng'}
            </button>
          </div>
        </aside>
      )}
    </div>
  );
}
