import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Pagination, useToast } from '../../components/common';
import PrintableReceipt from '../../components/pos/PrintableReceipt';
import { getApiErrorMessage } from '../../api/axiosClient';
import { acquireModalScrollLock } from '../../utils/modalScrollLock';
import { productsApi } from '../../api/productsApi';
import { categoriesApi } from '../../api/categoriesApi';
import {
  generateCheckoutIdempotencyKey,
  ordersApi,
} from '../../api/ordersApi';
import {
  DEFAULT_POS_PRODUCT_LIMIT,
  LOW_STOCK_THRESHOLD,
  addProductToCart,
  applyInsufficientStockResolution,
  applyPriceChangedAcceptance,
  buildCheckoutPayload,
  buildInsufficientStockViewModel,
  buildPendingCheckoutOwnerScope,
  buildPriceChangedViewModel,
  calculateCartTotals,
  clampMobileSheetMaxHeight,
  clearPendingCheckout,
  computeMobileSheetDragState,
  evaluatePosCashInput,
  executeSafePosCheckout,
  formatVnd,
  loadPendingCheckout,
  loadPosCart,
  prioritizeCategoriesByLatestProducts,
  resolveMobileSheetSwipeEnd,
  resolvePendingCheckoutAction,
  savePosCart,
  shouldCloseMobileCartOnEscape,
  updateCartItemQuantity,
} from '../../utils/posUtils';
import styles from './PosPage.module.css';

function ProductThumbnail({ product }) {
  const [failedImageUrl, setFailedImageUrl] = useState('');
  const imageUrl = typeof product?.image_url === 'string' ? product.image_url.trim() : '';
  const isValidHttpsImage = /^https:\/\/\S+$/i.test(imageUrl);
  const hasImageError = isValidHttpsImage && failedImageUrl === imageUrl;

  if (isValidHttpsImage && !hasImageError) {
    return (
      <img
        key={imageUrl}
        src={imageUrl}
        alt={product.name}
        className={styles.productImage}
        loading="lazy"
        onError={() => setFailedImageUrl(imageUrl)}
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
  const { user, isMockMode } = useAuth();
  const toast = useToast();
  const ownerScope = buildPendingCheckoutOwnerScope(user, isMockMode);

  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState('');

  const [products, setProducts] = useState([]);
  const [totalProducts, setTotalProducts] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [latestProductsSnapshot, setLatestProductsSnapshot] = useState([]);
  const [categories, setCategories] = useState([]);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [trackedOwnerScope, setTrackedOwnerScope] = useState(ownerScope);
  const [pendingCheckout, setPendingCheckout] = useState(() =>
    typeof window !== 'undefined'
      ? loadPendingCheckout(window.sessionStorage, ownerScope)
      : null
  );
  const [cart, setCart] = useState(() =>
    typeof window !== 'undefined'
      ? loadPendingCheckout(window.sessionStorage, ownerScope)?.cartSnapshot ||
        loadPosCart(window.localStorage, ownerScope)
      : []
  );
  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [manualReconciliationConfirmed, setManualReconciliationConfirmed] =
    useState(false);
  const [completedOrder, setCompletedOrder] = useState(null);
  const [cashReceivedInput, setCashReceivedInput] = useState('');
  const [cashHistory, setCashHistory] = useState([]);
  const [completedPaymentMeta, setCompletedPaymentMeta] = useState(null);
  const [stockConflictDetails, setStockConflictDetails] = useState(null);
  const [priceConflictDetails, setPriceConflictDetails] = useState(null);
  const [isMobileCartExpanded, setIsMobileCartExpanded] = useState(false);
  const [mobileDragHeight, setMobileDragHeight] = useState(null);
  const [mobileDragProgress, setMobileDragProgress] = useState(0);
  const isCheckingOutRef = useRef(false);
  const searchInputRef = useRef(null);
  const idempotencyKeyRef = useRef(
    pendingCheckout?.idempotencyKey || generateCheckoutIdempotencyKey()
  );
  const requestIdRef = useRef(0);
  const hasLoadedProductsRef = useRef(false);
  const mobileSwipeStartYRef = useRef(null);
  const mobileSwipeStartTimeRef = useRef(0);
  const mobileSwipeHandledRef = useRef(false);
  const mobileTouchInCartListRef = useRef(false);
  const mobileCartPanelRef = useRef(null);
  const mobileCartListRef = useRef(null);
  const mobileSheetInnerRef = useRef(null);
  const mobileSheetMaxHeightRef = useRef(260);

  // Đồng bộ lại pendingCheckout/cart nếu đổi tài khoản hoặc đổi chế độ trên cùng trình duyệt
  if (trackedOwnerScope !== ownerScope) {
    setTrackedOwnerScope(ownerScope);
    const restored =
      typeof window !== 'undefined'
        ? loadPendingCheckout(window.sessionStorage, ownerScope)
        : null;
    setPendingCheckout(restored);
    setCart(
      restored?.cartSnapshot ||
        (typeof window !== 'undefined' ? loadPosCart(window.localStorage, ownerScope) : [])
    );
    setManualReconciliationConfirmed(false);
    setCompletedOrder(null);
    setStockConflictDetails(null);
    setPriceConflictDetails(null);
  }

  useEffect(() => {
    idempotencyKeyRef.current =
      pendingCheckout?.idempotencyKey || generateCheckoutIdempotencyKey();
  }, [ownerScope, pendingCheckout?.idempotencyKey]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      savePosCart(window.localStorage, ownerScope, cart);
    }
  }, [ownerScope, cart]);

  // Cảnh báo nếu người dùng reload hoặc rời trang khi có giao dịch đang xử lý / chưa xác định
  useEffect(() => {
    if (typeof window === 'undefined' || (!isCheckingOut && !pendingCheckout)) {
      return undefined;
    }

    const handleBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isCheckingOut, pendingCheckout]);

  // Khóa cuộn trang nền và hỗ trợ phím Escape khi đang mở sheet danh sách giỏ hàng trên mobile
  useEffect(() => {
    const hasCart = cart.length > 0 || Boolean(pendingCheckout);
    if (
      typeof document === 'undefined' ||
      typeof window === 'undefined' ||
      !isMobileCartExpanded ||
      !hasCart
    ) {
      return undefined;
    }
    const prevBodyOverflow = document.body.style.overflow;
    const prevHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';

    const handleKeyDown = (event) => {
      if (
        shouldCloseMobileCartOnEscape({
          key: event.key,
          stockConflictDetails,
          priceConflictDetails,
          completedOrder,
        })
      ) {
        setIsMobileCartExpanded(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = prevBodyOverflow;
      document.documentElement.style.overflow = prevHtmlOverflow;
    };
  }, [
    isMobileCartExpanded,
    cart.length,
    pendingCheckout,
    stockConflictDetails,
    priceConflictDetails,
    completedOrder,
  ]);

  // Phím tắt thao tác nhanh tại quầy POS: F2 (tìm SP), F9 / Ctrl+Enter (thanh toán), Esc (đóng modal)
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const handlePosShortcut = (event) => {
      if (event.key === 'F2') {
        event.preventDefault();
        if (searchInputRef.current) {
          searchInputRef.current.focus();
          if (typeof searchInputRef.current.select === 'function') {
            searchInputRef.current.select();
          }
        }
        return;
      }

      if (event.key === 'Escape') {
        if (completedOrder) {
          setCompletedOrder(null);
          return;
        }
        if (stockConflictDetails) {
          setStockConflictDetails(null);
          return;
        }
        if (priceConflictDetails) {
          setPriceConflictDetails(null);
          return;
        }
        return;
      }

      const isCheckoutShortcut =
        event.key === 'F9' || ((event.ctrlKey || event.metaKey) && event.key === 'Enter');

      if (
        isCheckoutShortcut &&
        cart.length > 0 &&
        !isCheckingOutRef.current &&
        !completedOrder &&
        !stockConflictDetails &&
        !priceConflictDetails &&
        !pendingCheckout?.isExpired
      ) {
        event.preventDefault();
        handleConfirmCheckout();
      }
    };

    window.addEventListener('keydown', handlePosShortcut);
    return () => window.removeEventListener('keydown', handlePosShortcut);
  });

  // Khóa cuộn trang nền khi mở bất kỳ modal kết quả / xung đột thanh toán nào tại POS
  useEffect(() => {
    const hasOpenPosModal = Boolean(
      stockConflictDetails || priceConflictDetails || completedOrder
    );
    if (!hasOpenPosModal) return undefined;
    return acquireModalScrollLock();
  }, [stockConflictDetails, priceConflictDetails, completedOrder]);

  // Chặn cuộn trang nền / pull-to-refresh trên Safari iOS & Chrome Android khi kéo giỏ hàng
  useEffect(() => {
    const panelEl = mobileCartPanelRef.current;
    const hasCart = cart.length > 0 || Boolean(pendingCheckout);
    if (!panelEl || !hasCart) return undefined;

    const handleNativeTouchMove = (event) => {
      if (
        typeof window !== 'undefined' &&
        window.innerWidth > 768
      ) {
        return;
      }
      if (mobileSwipeStartYRef.current === null || !event.touches?.length) return;
      const deltaY = event.touches[0].clientY - mobileSwipeStartYRef.current;

      // Cho phép cuộn tự nhiên bên trong danh sách sản phẩm khi đang mở và không kéo đóng ở đầu danh sách
      if (mobileTouchInCartListRef.current && isMobileCartExpanded) {
        if (deltaY <= 0 || (mobileCartListRef.current?.scrollTop || 0) > 0) {
          return;
        }
      }

      if (event.cancelable) {
        event.preventDefault();
      }
    };

    panelEl.addEventListener('touchmove', handleNativeTouchMove, { passive: false });
    return () => {
      panelEl.removeEventListener('touchmove', handleNativeTouchMove);
    };
  }, [cart.length, pendingCheckout, isMobileCartExpanded]);

  // Debounce tìm kiếm theo tên sản phẩm hoặc mã SKU
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim());
      setCurrentPage(1);
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

  const hasCartItems = cart.length > 0 || Boolean(pendingCheckout);
  const posPageSize = hasCartItems ? 10 : 12;

  // Tải danh sách sản phẩm hiển thị tại POS:
  // - Chưa có sản phẩm trong giỏ: 12 sản phẩm/trang (2 dòng x 6 cột)
  // - Có ít nhất 1 sản phẩm trong giỏ: 10 sản phẩm/trang (2 dòng x 5 cột)
  const isFiltering = Boolean(debouncedSearch || selectedCategoryId);

  useEffect(() => {
    const currentRequestId = ++requestIdRef.current;

    async function fetchPosProducts() {
      await Promise.resolve();
      if (currentRequestId !== requestIdRef.current) return;
      if (!hasLoadedProductsRef.current) {
        setIsLoading(true);
      }
      setLoadError('');

      try {
        const res = await productsApi.getProducts({
          isMockMode,
          page: currentPage,
          pageSize: posPageSize,
          keyword: debouncedSearch,
          categoryId: selectedCategoryId,
          status: 'ACTIVE',
          sort: 'created_desc',
        });

        if (currentRequestId === requestIdRef.current) {
          const nextTotal = res.total || 0;
          const nextTotalPages = Math.max(1, Math.ceil(nextTotal / posPageSize));
          if (currentPage > nextTotalPages) {
            setCurrentPage(nextTotalPages);
            return;
          }
          hasLoadedProductsRef.current = true;
          setProducts(res.items || []);
          setTotalProducts(nextTotal);
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
  }, [
    isMockMode,
    currentPage,
    posPageSize,
    debouncedSearch,
    selectedCategoryId,
    refreshTrigger,
  ]);

  const orderedCategories = useMemo(
    () => prioritizeCategoriesByLatestProducts(categories, latestProductsSnapshot),
    [categories, latestProductsSnapshot]
  );

  const cartTotals = useMemo(() => {
    if (cart.length > 0) {
      return calculateCartTotals(cart);
    }
    if (pendingCheckout) {
      const totalUnits = pendingCheckout.itemsSnapshot.reduce(
        (sum, item) => sum + (item.quantity || 0),
        0
      );
      return {
        lineCount: pendingCheckout.lineCount || pendingCheckout.itemsSnapshot.length,
        totalUnits,
        totalVnd: pendingCheckout.totalVnd || 0,
      };
    }
    return calculateCartTotals(cart);
  }, [cart, pendingCheckout]);
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
    const nextCart = updateCartItemQuantity(cart, productId, nextQty);
    setCart(nextCart);
    if (nextCart.length === 0) {
      setIsMobileCartExpanded(false);
    }
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
  };

  const handleClearCart = () => {
    if (isCartLocked || isCheckingOutRef.current) return;
    setCart([]);
    setIsMobileCartExpanded(false);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
  };

  const handleMobileCartTouchStart = (event) => {
    if (
      !event.touches ||
      event.touches.length === 0 ||
      (typeof window !== 'undefined' && window.innerWidth > 768)
    ) {
      return;
    }
    if (
      event.target instanceof Element &&
      event.target.closest('button, input, label, a') &&
      !event.target.closest(`.${styles.mobileCartToggle}`)
    ) {
      mobileSwipeStartYRef.current = null;
      return;
    }
    const inCartList = Boolean(
      mobileCartListRef.current && mobileCartListRef.current.contains(event.target)
    );
    if (inCartList && mobileCartListRef.current.scrollTop > 0) {
      mobileSwipeStartYRef.current = null;
      return;
    }
    mobileTouchInCartListRef.current = inCartList;
    mobileSwipeStartYRef.current = event.touches[0].clientY;
    mobileSwipeStartTimeRef.current = Date.now();
    mobileSwipeHandledRef.current = false;
    const measuredHeight = mobileSheetInnerRef.current?.scrollHeight || 0;
    const viewportHeight =
      typeof window !== 'undefined' ? window.innerHeight : null;
    mobileSheetMaxHeightRef.current = clampMobileSheetMaxHeight(
      measuredHeight,
      viewportHeight
    );
  };

  const handleMobileCartTouchMove = (event) => {
    if (mobileSwipeStartYRef.current === null || !event.touches?.length) return;
    const currentY = event.touches[0].clientY;
    const deltaY = currentY - mobileSwipeStartYRef.current;

    // Khi vuốt trong danh sách sản phẩm đang mở: ưu tiên cuộn danh sách lên, chỉ kéo đóng khi kéo xuống ở đầu danh sách
    if (mobileTouchInCartListRef.current && isMobileCartExpanded) {
      if (deltaY <= 0 || (mobileCartListRef.current?.scrollTop || 0) > 0) {
        return;
      }
    }

    if (mobileDragHeight === null && Math.abs(deltaY) < 4) return;

    const { height, progress } = computeMobileSheetDragState({
      isExpanded: isMobileCartExpanded,
      deltaY,
      maxHeight: mobileSheetMaxHeightRef.current || 260,
    });

    setMobileDragHeight(height);
    setMobileDragProgress(progress);
  };

  const handleMobileCartTouchEnd = (event) => {
    if (mobileSwipeStartYRef.current === null) return;
    const endY = event.changedTouches?.[0]?.clientY;
    const startY = mobileSwipeStartYRef.current;
    const wasDragging = mobileDragHeight !== null;
    const elapsedMs = Math.max(1, Date.now() - mobileSwipeStartTimeRef.current);
    const maxH = mobileSheetMaxHeightRef.current || 260;
    mobileSwipeStartYRef.current = null;
    mobileTouchInCartListRef.current = false;
    setMobileDragHeight(null);
    setMobileDragProgress(0);
    if (typeof endY !== 'number' || !wasDragging) return;

    const { nextExpanded, handled } = resolveMobileSheetSwipeEnd({
      isExpanded: isMobileCartExpanded,
      deltaY: endY - startY,
      elapsedMs,
      maxHeight: maxH,
    });
    if (handled) {
      mobileSwipeHandledRef.current = true;
      setIsMobileCartExpanded(nextExpanded);
    }
  };

  const handleMobileCartToggleClick = () => {
    if (mobileSwipeHandledRef.current) {
      mobileSwipeHandledRef.current = false;
      return;
    }
    setIsMobileCartExpanded((prev) => !prev);
  };

  const handleAbandonPendingCheckout = () => {
    if (isCheckingOutRef.current) return;
    const resolution = resolvePendingCheckoutAction({
      action: 'ABANDON',
      pendingCheckout,
      manualReconciliationConfirmed,
    });
    if (!resolution.allowed) {
      toast.warning(resolution.message);
      return;
    }

    if (typeof window !== 'undefined') {
      clearPendingCheckout(window.sessionStorage, ownerScope);
    }
    setPendingCheckout(null);
    setManualReconciliationConfirmed(false);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleConfirmCheckout = async () => {
    if (isCheckingOutRef.current) return;
    const cashCheck = evaluatePosCashInput(cashReceivedInput, cartTotals.totalVnd);
    if (!pendingCheckout && !cashCheck.canCheckout) {
      toast.warning(cashCheck.errorMessage || 'Tiền khách đưa chưa đủ để thanh toán.');
      return;
    }
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
      const result = await executeSafePosCheckout({
        storage: typeof window !== 'undefined' ? window.sessionStorage : null,
        ownerScope,
        isMockMode,
        itemsSnapshot: snapshotItems,
        cartSnapshot: cart,
        totalVnd: cartTotals.totalVnd,
        lineCount: cartTotals.lineCount,
        idempotencyKey: requestKey,
        pendingCheckout,
        checkoutOrderFn: ordersApi.checkoutOrder,
      });

      if (result.ok) {
        const postCheck = evaluatePosCashInput(
          cashReceivedInput,
          result.order?.total_vnd ?? 0
        );
        setCompletedPaymentMeta(
          postCheck.hasInput && postCheck.isValid && postCheck.canCheckout
            ? {
                cashReceivedVnd: postCheck.cashReceivedVnd,
                changeDueVnd: postCheck.changeDueVnd,
              }
            : null
        );
        setCompletedOrder(result.order);
        setCashReceivedInput('');
        setCashHistory([]);
        setStockConflictDetails(null);
        setPriceConflictDetails(null);
        toast.success(
          `Thanh toán thành công đơn #${result.order.id} — Tổng ${formatVnd(result.order.total_vnd)}.`
        );
        setPendingCheckout(null);
        setManualReconciliationConfirmed(false);
        setCart([]);
        setIsMobileCartExpanded(false);
        idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
        setRefreshTrigger((prev) => prev + 1);
        return;
      }

      if (result.outcome === 'AMBIGUOUS' || result.outcome === 'IDEMPOTENCY_EXPIRED') {
        setPendingCheckout(result.pendingCheckout);
        setManualReconciliationConfirmed(false);
        toast.warning(result.message);
      } else if (result.outcome === 'PERSIST_FAILED') {
        toast.error(result.message);
      } else if (result.apiCode === 'INSUFFICIENT_STOCK') {
        setPendingCheckout(null);
        setManualReconciliationConfirmed(false);
        idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
        setStockConflictDetails(result.details || {});
        setRefreshTrigger((prev) => prev + 1);
      } else if (result.apiCode === 'PRICE_CHANGED') {
        setPendingCheckout(null);
        setManualReconciliationConfirmed(false);
        idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
        setPriceConflictDetails(result.details || {});
        setRefreshTrigger((prev) => prev + 1);
      } else if (result.outcome === 'IDEMPOTENCY_CONFLICT') {
        setPendingCheckout(null);
        setManualReconciliationConfirmed(false);
        idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
        toast.error(result.message);
      } else {
        setPendingCheckout(null);
        setManualReconciliationConfirmed(false);
        if (result.rotateKey) {
          idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
        }
        toast.error(result.message);
        setRefreshTrigger((prev) => prev + 1);
      }
    } finally {
      isCheckingOutRef.current = false;
      setIsCheckingOut(false);
    }
  };

  const stockConflictVm = useMemo(
    () =>
      stockConflictDetails
        ? buildInsufficientStockViewModel(cart, stockConflictDetails)
        : null,
    [cart, stockConflictDetails]
  );

  const priceConflictVm = useMemo(
    () =>
      priceConflictDetails
        ? buildPriceChangedViewModel(cart, priceConflictDetails)
        : null,
    [cart, priceConflictDetails]
  );

  const handleRemoveInsufficientItems = () => {
    const nextCart = applyInsufficientStockResolution(
      cart,
      stockConflictDetails,
      'REMOVE_INSUFFICIENT'
    );
    setCart(nextCart);
    setStockConflictDetails(null);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
    toast.info('Đã xóa sản phẩm vượt tồn kho khỏi giỏ hàng.');
  };

  const handleAdjustStockToMax = () => {
    const nextCart = applyInsufficientStockResolution(
      cart,
      stockConflictDetails,
      'ADJUST_TO_MAX'
    );
    setCart(nextCart);
    setStockConflictDetails(null);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
    toast.info('Đã điều chỉnh số lượng sản phẩm về mức tồn kho khả dụng tối đa.');
  };

  const handleCancelPriceChanged = () => {
    setPriceConflictDetails(null);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
  };

  const handleAcceptNewPrices = () => {
    const nextCart = applyPriceChangedAcceptance(cart, priceConflictDetails);
    setCart(nextCart);
    setPriceConflictDetails(null);
    idempotencyKeyRef.current = generateCheckoutIdempotencyKey();
    toast.success(
      'Đã cập nhật giá bán mới từ máy chủ. Vui lòng kiểm tra lại giỏ hàng và xác nhận bán.'
    );
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
            <h1 className={styles.pageTitle}>Bán hàng tại quầy</h1>
          </div>
          <div className={styles.shortcutHintBar} aria-label="Phím tắt quầy thu ngân">
            <span className={styles.shortcutChip}>
              <kbd>F2</kbd> Tìm SP
            </span>
            <span className={styles.shortcutChip}>
              <kbd>F9</kbd> / <kbd>Ctrl+Enter</kbd> Thanh toán
            </span>
            <span className={styles.shortcutChip}>
              <kbd>Esc</kbd> Đóng
            </span>
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
              ref={searchInputRef}
              type="text"
              className={styles.searchInput}
              placeholder="Tìm kiếm theo tên sản phẩm hoặc mã SKU (F2)..."
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

          <div className={styles.categorySelectWrap}>
            <select
              className={styles.categorySelectMobile}
              value={selectedCategoryId}
              onChange={(e) => {
                setSelectedCategoryId(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Lọc theo danh mục"
            >
              <option value="">Tất cả danh mục</option>
              {orderedCategories.map((cat) => (
                <option key={cat.id} value={String(cat.id)}>
                  {cat.name}
                </option>
              ))}
            </select>
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
          <>
            <div
              className={`${styles.productGrid} ${
                hasCartItems ? styles.productGridWithCart : ''
              }`}
            >
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
                      <span>Thêm</span>
                    </button>
                  </div>
                </article>
              );
            })}
            </div>

            {Math.ceil(totalProducts / posPageSize) > 1 && (
              <div className={styles.paginationRow}>
                <span className={styles.paginationInfo}>
                  Hiển thị {products.length} / {totalProducts} sản phẩm ({posPageSize} sản phẩm/trang)
                </span>
                <Pagination
                  currentPage={currentPage}
                  totalPages={Math.max(1, Math.ceil(totalProducts / posPageSize))}
                  onPageChange={setCurrentPage}
                />
              </div>
            )}
          </>
        )}
      </section>

      {/* Giỏ hàng bên phải — CHỈ hiển thị khi có hàng trong giỏ */}
      {hasCartItems && (
        <>
          <div
            className={`${styles.mobileCartBackdrop} ${
              isMobileCartExpanded ? styles.mobileCartBackdropVisible : ''
            }`}
            style={
              mobileDragHeight !== null
                ? {
                    opacity: mobileDragProgress,
                    transition: 'none',
                    pointerEvents: mobileDragProgress > 0.02 ? 'auto' : 'none',
                  }
                : undefined
            }
            onClick={() => setIsMobileCartExpanded(false)}
            aria-hidden="true"
          />
          <aside
            ref={mobileCartPanelRef}
            className={`${styles.cartPanel} ${
              isMobileCartExpanded ? styles.cartPanelMobileExpanded : ''
            }`}
            onTouchStart={handleMobileCartTouchStart}
            onTouchMove={handleMobileCartTouchMove}
            onTouchEnd={handleMobileCartTouchEnd}
            onTouchCancel={handleMobileCartTouchEnd}
            aria-label="Giỏ hàng hiện tại"
          >
            <button
              type="button"
              className={styles.mobileCartToggle}
              onClick={handleMobileCartToggleClick}
              aria-expanded={isMobileCartExpanded}
              aria-label={
                isMobileCartExpanded
                  ? 'Thu gọn danh sách giỏ hàng'
                  : 'Mở danh sách sản phẩm đã chọn'
              }
            >
              <span className={styles.mobileCartHandle} aria-hidden="true" />
              <div className={styles.mobileCartToggleRow}>
                <span className={styles.mobileCartToggleTitle}>
                  Giỏ hàng ({cartTotals.lineCount} món · {cartTotals.totalUnits} SP)
                </span>
                <span className={styles.mobileCartToggleAction}>
                  {isMobileCartExpanded ? 'Thu gọn ▼' : 'Xem chi tiết ▲'}
                </span>
              </div>
            </button>

            <div
              className={`${styles.mobileCartSheetBody} ${
                mobileDragHeight !== null ? styles.mobileCartSheetBodyDragging : ''
              }`}
              style={
                mobileDragHeight !== null
                  ? {
                      maxHeight: `${mobileDragHeight}px`,
                      opacity: Math.max(0.15, mobileDragProgress),
                    }
                  : undefined
              }
            >
              <div ref={mobileSheetInnerRef} className={styles.mobileCartSheetInner}>
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

          <div ref={mobileCartListRef} className={styles.cartList}>
            {cart.map((item) => (
              <div key={item.productId} className={styles.cartItem}>
                <div className={styles.cartItemInfo}>
                  <p className={styles.cartItemName} title={item.name}>
                    {item.name}
                  </p>
                  <span className={styles.cartItemMeta}>
                    Đơn giá: {formatVnd(item.unitPriceVnd)}
                  </span>
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
              </div>
            </div>

          <div className={styles.cartFooter}>
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

            {!isCartLocked && cartTotals.totalVnd > 0 && (() => {
              const cashEval = evaluatePosCashInput(cashReceivedInput, cartTotals.totalVnd);
              const cashDigits = cashEval.isValid && cashEval.hasInput ? cashEval.cashReceivedVnd : 0;
              const hasCashInput = cashEval.hasInput;
              const formattedCashDisplay =
                hasCashInput && cashEval.isValid
                  ? cashDigits.toLocaleString('vi-VN')
                  : cashReceivedInput;

              const applyCashChange = (nextVal) => {
                setCashHistory((prev) => [...prev.slice(-19), cashReceivedInput]);
                setCashReceivedInput(nextVal);
              };

              const handleUndoCash = () => {
                if (cashHistory.length === 0) return;
                const previous = cashHistory[cashHistory.length - 1];
                setCashHistory((prev) => prev.slice(0, -1));
                setCashReceivedInput(previous);
              };

              return (
                <div className={styles.cashCalcBox} data-testid="pos-cash-calculator">
                  <div className={styles.cashCalcHeader}>
                    <label htmlFor="pos-cash-received-input" className={styles.cashCalcLabel}>
                      Tiền khách đưa (VNĐ)
                    </label>
                    <div className={styles.cashHeaderActions}>
                      <button
                        type="button"
                        className={styles.cashUndoBtn}
                        onClick={handleUndoCash}
                        disabled={cashHistory.length === 0}
                        title="Quay lại số tiền trước đó"
                        data-testid="pos-cash-undo-btn"
                      >
                        ↩ Hoàn tác
                      </button>
                      {hasCashInput && (
                        <button
                          type="button"
                          className={styles.cashClearBtn}
                          onClick={() => applyCashChange('')}
                          title="Xóa số tiền đã nhập"
                        >
                          Xóa
                        </button>
                      )}
                    </div>
                  </div>

                  <div className={styles.cashInputWrap}>
                    <input
                      id="pos-cash-received-input"
                      type="text"
                      inputMode="numeric"
                      className={styles.cashCalcInput}
                      placeholder="Nhập số tiền"
                      value={formattedCashDisplay}
                      onChange={(e) => {
                        const raw = e.target.value.replace(/\D/g, '');
                        applyCashChange(raw);
                      }}
                    />
                    <span className={styles.cashCurrencySuffix} aria-hidden="true">
                      ₫
                    </span>
                  </div>

                  <div className={styles.cashChipGrid}>
                    <button
                      type="button"
                      className={`${styles.cashChipBtn} ${styles.cashExactBtn}`}
                      onClick={() => applyCashChange(String(cartTotals.totalVnd))}
                    >
                      Đủ
                    </button>
                    {[
                      { label: '+50k', value: 50000 },
                      { label: '+100k', value: 100000 },
                      { label: '+200k', value: 200000 },
                      { label: '+500k', value: 500000 },
                    ].map((preset) => (
                      <button
                        key={preset.label}
                        type="button"
                        className={styles.cashChipBtn}
                        onClick={() => applyCashChange(String(cashDigits + preset.value))}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>

                  {hasCashInput && (
                    <div
                      className={
                        cashEval.canCheckout
                          ? styles.cashChangeRow
                          : `${styles.cashChangeRow} ${styles.cashShortRow}`
                      }
                    >
                      <span>
                        {!cashEval.isValid
                          ? cashEval.errorMessage
                          : cashEval.canCheckout
                          ? 'Tiền trả lại'
                          : 'Còn thiếu'}
                      </span>
                      <strong>
                        {cashEval.isValid
                          ? formatVnd(
                              cashEval.canCheckout
                                ? cashEval.changeDueVnd
                                : cashEval.shortAmountVnd
                            )
                          : '—'}
                      </strong>
                    </div>
                  )}
                </div>
              );
            })()}

            {pendingCheckout && (
              <div className={styles.ambiguousBanner} role="alert">
                <strong>Trạng thái đơn hàng chưa xác định</strong>
                <p>{pendingCheckout.reasonMessage}</p>
                <span>
                  {pendingCheckout.isExpired
                    ? 'Mã giao dịch đã quá thời hạn 24 giờ của máy chủ nên không thể tự kiểm tra lại. Vui lòng đối soát thủ công với Quản trị viên / hóa đơn trước khi mở khóa.'
                    : 'Giỏ hàng đang bị khóa để tránh tạo đơn trùng. Hãy bấm "Kiểm tra lại kết quả đơn này" để gửi lại cùng mã giao dịch. Không tạo đơn mới nếu chưa đối soát thủ công với Quản trị viên / hóa đơn rằng đơn này chưa được ghi nhận.'}
                </span>
                <label className={styles.reconcileAckLabel}>
                  <input
                    type="checkbox"
                    checked={manualReconciliationConfirmed}
                    onChange={(e) =>
                      setManualReconciliationConfirmed(e.target.checked)
                    }
                    disabled={isCheckingOut}
                  />
                  <span>
                    Tôi xác nhận đã đối soát thủ công và đơn này chưa được ghi
                    nhận trên hệ thống
                  </span>
                </label>
                <button
                  type="button"
                  className={styles.abandonPendingBtn}
                  onClick={handleAbandonPendingCheckout}
                  disabled={isCheckingOut || !manualReconciliationConfirmed}
                >
                  Mở khóa giỏ hàng (sau khi đã đối soát)
                </button>
              </div>
            )}

            <button
              type="button"
              className={styles.checkoutBtn}
              onClick={handleConfirmCheckout}
              disabled={
                isCheckingOut ||
                Boolean(pendingCheckout?.isExpired) ||
                (!pendingCheckout &&
                  !evaluatePosCashInput(cashReceivedInput, cartTotals.totalVnd).canCheckout)
              }
            >
              {isCheckingOut
                ? 'Đang xử lý đơn hàng...'
                : pendingCheckout
                ? 'Kiểm tra lại kết quả đơn này'
                : 'Xác nhận bán hàng'}
            </button>
          </div>
        </aside>
        </>
      )}

      {/* Modal 1: Lỗi tồn kho không đủ (HTTP 409 INSUFFICIENT_STOCK) — dữ liệu thật từ Backend */}
      {stockConflictVm && (
        <div
          className={styles.posModalOverlay}
          role="dialog"
          aria-modal="true"
          aria-labelledby="pos-stock-conflict-title"
        >
          <div className={styles.posModalCard}>
            <div className={styles.posModalHeader}>
              <div className={styles.posModalTitleRow}>
                <span className={styles.posModalIconAmber} aria-hidden="true">
                  ⚠
                </span>
                <h2 id="pos-stock-conflict-title" className={styles.posModalTitle}>
                  Tồn kho không đủ (Insufficient Stock)
                </h2>
              </div>
              <button
                type="button"
                className={styles.posModalCloseBtn}
                onClick={() => setStockConflictDetails(null)}
                aria-label="Đóng thông báo tồn kho"
              >
                ✕
              </button>
            </div>

            <div className={styles.posModalBody}>
              <div className={styles.alertBoxAmber}>
                <strong>Phát hiện sản phẩm vượt tồn kho khả dụng!</strong>
                <p>
                  {stockConflictVm.primaryConflict ? (
                    <>
                      Sản phẩm <strong>{stockConflictVm.primaryConflict.name}</strong>{' '}
                      khách yêu cầu{' '}
                      <strong>{stockConflictVm.primaryConflict.requestedQty}</strong>,
                      tuy nhiên máy chủ xác nhận kho hiện tại chỉ còn{' '}
                      <strong>{stockConflictVm.primaryConflict.availableQty}</strong>.
                    </>
                  ) : (
                    'Số lượng yêu cầu vượt quá tồn kho thực tế trên máy chủ.'
                  )}
                </p>
              </div>

              <div className={styles.conflictTableWrap}>
                <table className={styles.conflictTable}>
                  <thead>
                    <tr>
                      <th>Tên sản phẩm</th>
                      <th className={styles.alignCenter}>Yêu cầu</th>
                      <th className={styles.alignCenter}>Tồn khả dụng</th>
                      <th className={styles.alignRight}>Đơn giá</th>
                      <th className={styles.alignRight}>Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stockConflictVm.rows.map((row) => (
                      <tr key={row.productId}>
                        <td className={styles.conflictProductName}>{row.name}</td>
                        <td
                          className={`${styles.alignCenter} ${
                            row.isInsufficient ? styles.qtyDanger : ''
                          }`}
                        >
                          {row.requestedQty}
                        </td>
                        <td
                          className={`${styles.alignCenter} ${
                            row.isInsufficient ? styles.qtySafe : ''
                          }`}
                        >
                          {row.availableQty}
                        </td>
                        <td className={styles.alignRight}>
                          {formatVnd(row.unitPriceVnd)}
                        </td>
                        <td className={styles.alignRight}>
                          {row.isInsufficient ? (
                            <span className={styles.statusPillDanger}>
                              Thiếu {row.shortageQty}
                            </span>
                          ) : (
                            <span className={styles.statusPillSuccess}>Hợp lệ</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className={styles.conflictHelperNote}>
                Hệ thống bảo lưu nguyên vẹn các mặt hàng hợp lệ khác trong giỏ. Vui
                lòng chọn hành động xử lý:
              </p>
            </div>

            <div className={styles.posModalFooterRight}>
              <button
                type="button"
                className={styles.compactSecondaryBtn}
                onClick={handleRemoveInsufficientItems}
              >
                <span>Xóa sản phẩm khỏi giỏ</span>
              </button>
              <button
                type="button"
                className={styles.compactPrimaryBtn}
                onClick={handleAdjustStockToMax}
              >
                <span>
                  {stockConflictVm.singleAdjustableQty != null
                    ? `Điều chỉnh về số lượng tối đa (${stockConflictVm.singleAdjustableQty})`
                    : 'Điều chỉnh về số lượng tối đa'}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 2: Xung đột giá bán (HTTP 409 PRICE_CHANGED) — dữ liệu thật từ Backend */}
      {priceConflictVm && (
        <div
          className={styles.posModalOverlay}
          role="dialog"
          aria-modal="true"
          aria-labelledby="pos-price-conflict-title"
        >
          <div className={styles.posModalCard}>
            <div className={styles.posModalHeader}>
              <div className={styles.posModalTitleRow}>
                <span className={styles.posModalIconRose} aria-hidden="true">
                  🏷
                </span>
                <h2 id="pos-price-conflict-title" className={styles.posModalTitle}>
                  Xung đột giá bán (HTTP 409)
                </h2>
              </div>
              <button
                type="button"
                className={styles.posModalCloseBtn}
                onClick={handleCancelPriceChanged}
                aria-label="Đóng thông báo xung đột giá"
              >
                ✕
              </button>
            </div>

            <div className={styles.posModalBody}>
              <div className={styles.alertBoxRose}>
                <strong>Giá niêm yết đã thay đổi trong lúc thao tác!</strong>
                <p>
                  Hệ thống không tự động bán giá cũ và yêu cầu xác nhận giá mới từ
                  máy chủ.
                </p>
              </div>

              <div className={styles.priceDiffList}>
                {priceConflictVm.changedItems.map((item) => (
                  <div key={item.productId} className={styles.priceDiffCard}>
                    <div className={styles.priceDiffCardHeader}>
                      <strong>
                        {item.name}
                        {item.sku ? ` (Mã: ${item.sku})` : ''}
                      </strong>
                      <span>Số lượng: {item.quantity}</span>
                    </div>
                    <div className={styles.priceMetricGrid}>
                      <div className={styles.priceMetricBox}>
                        <span className={styles.priceMetricLabel}>
                          GIÁ CŨ LÚC CHỌN
                        </span>
                        <strong className={styles.priceMetricOld}>
                          {formatVnd(item.oldPriceVnd)}
                        </strong>
                      </div>
                      <div className={styles.priceMetricBox}>
                        <span className={styles.priceMetricLabel}>
                          GIÁ MỚI MÁY CHỦ
                        </span>
                        <strong className={styles.priceMetricNew}>
                          {formatVnd(item.newPriceVnd)}
                        </strong>
                      </div>
                      <div className={styles.priceMetricBox}>
                        <span className={styles.priceMetricLabel}>CHÊNH LỆCH</span>
                        <strong className={styles.priceMetricDelta}>
                          {item.diffVnd >= 0 ? '+' : ''}
                          {formatVnd(item.diffVnd)}
                        </strong>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className={styles.updatedTotalBar}>
                <span>Tổng tiền giỏ sau cập nhật:</span>
                <div className={styles.updatedTotalValues}>
                  <span className={styles.strikethroughTotal}>
                    {formatVnd(priceConflictVm.oldTotalVnd)}
                  </span>
                  <strong>{formatVnd(priceConflictVm.newTotalVnd)}</strong>
                </div>
              </div>
            </div>

            <div className={styles.posModalFooterRight}>
              <button
                type="button"
                className={styles.compactSecondaryBtn}
                onClick={handleCancelPriceChanged}
              >
                <span>Hủy bỏ thanh toán</span>
              </button>
              <button
                type="button"
                className={styles.compactPrimaryBtn}
                onClick={handleAcceptNewPrices}
              >
                <span>Chấp nhận giá mới &amp; Xem lại giỏ hàng</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: Xác nhận bán hàng thành công (HTTP 201 OrderRead) — dữ liệu thật từ Backend */}
      {completedOrder && (
        <div
          className={styles.posModalOverlay}
          role="dialog"
          aria-modal="true"
          aria-labelledby="pos-order-success-title"
        >
          <div className={styles.posModalCard}>
            <div className={styles.posModalHeader}>
              <div className={styles.posModalTitleRow}>
                <span className={styles.posModalIconSuccess} aria-hidden="true">
                  ✓
                </span>
                <div>
                  <h2 id="pos-order-success-title" className={styles.posModalTitle}>
                    Xác nhận bán hàng thành công
                  </h2>
                  <p className={styles.posModalSubtitle}>
                    Đơn hàng #{completedOrder.id} • Trạng thái:{' '}
                    <strong>{completedOrder.status}</strong>
                  </p>
                </div>
              </div>
              <button
                type="button"
                className={styles.posModalCloseBtn}
                onClick={() => setCompletedOrder(null)}
                aria-label="Đóng xác nhận đơn hàng"
              >
                ✕
              </button>
            </div>

            <div className={styles.posModalBody}>
              <div className={styles.conflictTableWrap}>
                <table className={styles.conflictTable}>
                  <thead>
                    <tr>
                      <th>MẶT HÀNG</th>
                      <th className={styles.alignRight}>SL × ĐƠN GIÁ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {completedOrder.items.map((line) => (
                      <tr key={`${line.product_id}-${line.sku_snapshot}`}>
                        <td>
                          <div className={styles.receiptItemName}>
                            {line.product_name_snapshot}
                          </div>
                          <div className={styles.receiptItemSub}>
                            SKU: {line.sku_snapshot}
                          </div>
                        </td>
                        <td className={styles.alignRight}>
                          <div className={styles.receiptUnitExpr}>
                            {line.quantity} × {formatVnd(line.unit_price_vnd)}
                          </div>
                          <div className={styles.receiptLineTotal}>
                            {formatVnd(line.line_total_vnd)}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <ul className={styles.orderRuleChecklist}>
                <li>Chỉ bán sản phẩm trạng thái Đang bán</li>
                <li>Giá bán nguyên số VND</li>
                <li>Đã ghi nhận trừ tồn kho trên máy chủ</li>
              </ul>
            </div>

            <div className={styles.posModalFooterBetween}>
              <div className={styles.completedOrderTotalBox}>
                <span>Tổng tiền ({completedOrder.items.length} món):</span>
                <strong>{formatVnd(completedOrder.total_vnd)}</strong>
              </div>
              <div className={styles.completedModalActions}>
                <button
                  type="button"
                  className={styles.compactSecondaryBtn}
                  onClick={() => {
                    if (typeof window !== 'undefined' && typeof window.print === 'function') {
                      window.print();
                    }
                  }}
                  data-testid="pos-print-receipt-btn"
                >
                  In hóa đơn
                </button>
                <button
                  type="button"
                  className={styles.compactPrimaryBtn}
                  onClick={() => setCompletedOrder(null)}
                >
                  <span>✓ Đơn hàng mới</span>
                </button>
              </div>
            </div>
          </div>
          <PrintableReceipt
            order={completedOrder}
            actorLabel={
              user?.full_name
                ? `${user.full_name}${user?.role === 'ADMIN' ? ' (Admin)' : ''}`
                : user?.email || ''
            }
            cashReceivedVnd={completedPaymentMeta?.cashReceivedVnd ?? null}
            changeDueVnd={completedPaymentMeta?.changeDueVnd ?? null}
          />
        </div>
      )}
    </div>
  );
}
