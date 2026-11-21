import { useCallback, useEffect, useRef, useState } from 'react';
import { useInRouterContext, useNavigate } from 'react-router-dom';
import {
  AI_QUERY_MAX_LENGTH,
  aiApi,
  classifyAiError,
  isAiRequestCanceled,
  validateAiMessageInput,
} from '../../api/aiApi';
import { analyticsApi } from '../../api/analyticsApi';
import { getApiErrorMessage } from '../../api/axiosClient';
import { inventoryApi } from '../../api/inventoryApi';
import { receiptsApi } from '../../api/receiptsApi';
import { suppliersApi } from '../../api/suppliersApi';
import { useAuth } from '../../context/AuthContext';
import {
  buildDraftReceiptPayload,
  buildPrefillDraftState,
  buildReorderSuggestions,
  getDraftActionGuidance,
  parseStrictInteger,
} from '../../utils/reorderSuggestions';
import styles from './AiAssistant.module.css';

function RouterNavigateBridge({ children }) {
  const navigate = useNavigate();
  return children(navigate);
}

const SUGGESTED_PROMPTS = [
  'Doanh thu và số đơn hoàn tất 7 ngày gần nhất như thế nào?',
  'Những sản phẩm nào bán chạy nhất trong 30 ngày qua?',
  'Sản phẩm nào đang sắp hết hàng và cần gợi ý nhập thêm?',
  'Sản phẩm nào bán chậm cần xem xét kế hoạch nhập hàng?',
];

function formatMessageTime() {
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Ho_Chi_Minh',
  }).format(new Date());
}

function renderInlineMarkdown(text, keyPrefix) {
  if (!text) return null;
  const tokens = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return tokens.map((part, idx) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={`${keyPrefix}-b-${idx}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={`${keyPrefix}-c-${idx}`} className={styles.inlineCode}>
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function parseTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function isTableSeparatorLine(line) {
  const trimmed = line.trim();
  if (!trimmed.includes('|') || !trimmed.includes('-')) return false;
  return /^\|?(\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/.test(trimmed);
}

function renderFormattedAnswer(answerText) {
  const raw = String(answerText || '').trim();
  if (!raw) return null;

  const lines = raw.split(/\r?\n/);
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    // Markdown table: header line with | followed by separator line
    if (
      trimmed.includes('|') &&
      i + 1 < lines.length &&
      isTableSeparatorLine(lines[i + 1])
    ) {
      const headers = parseTableRow(lines[i]);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim().includes('|') && lines[i].trim() !== '') {
        rows.push(parseTableRow(lines[i]));
        i += 1;
      }
      blocks.push(
        <div key={`tbl-${i}`} className={styles.answerTableWrap}>
          <table className={styles.answerTable}>
            <thead>
              <tr>
                {headers.map((h, hIdx) => (
                  <th key={`th-${hIdx}`}>{renderInlineMarkdown(h, `th-${i}-${hIdx}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, rIdx) => (
                <tr key={`tr-${rIdx}`}>
                  {headers.map((_, cIdx) => (
                    <td key={`td-${rIdx}-${cIdx}`}>
                      {renderInlineMarkdown(r[cIdx] ?? '', `td-${i}-${rIdx}-${cIdx}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Unordered list
    if (/^[-*•]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ul key={`ul-${i}`} className={styles.answerList}>
          {items.map((item, idx) => (
            <li key={`li-${idx}`}>{renderInlineMarkdown(item, `ul-${i}-${idx}`)}</li>
          ))}
        </ul>
      );
      continue;
    }

    // Ordered list
    if (/^\d+\.\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ol key={`ol-${i}`} className={styles.answerList}>
          {items.map((item, idx) => (
            <li key={`oli-${idx}`}>{renderInlineMarkdown(item, `ol-${i}-${idx}`)}</li>
          ))}
        </ol>
      );
      continue;
    }

    // Heading (### / ##)
    if (/^#{1,4}\s+/.test(trimmed)) {
      const headingText = trimmed.replace(/^#{1,4}\s+/, '');
      blocks.push(
        <h4 key={`h-${i}`} className={styles.answerSubheading}>
          {renderInlineMarkdown(headingText, `h-${i}`)}
        </h4>
      );
      i += 1;
      continue;
    }

    // Paragraph (group consecutive plain lines until blank/table/list/heading)
    const paraLines = [];
    while (i < lines.length) {
      const cur = lines[i].trim();
      if (
        !cur ||
        /^[-*•]\s+/.test(cur) ||
        /^\d+\.\s+/.test(cur) ||
        /^#{1,4}\s+/.test(cur) ||
        (cur.includes('|') && i + 1 < lines.length && isTableSeparatorLine(lines[i + 1]))
      ) {
        break;
      }
      paraLines.push(lines[i]);
      i += 1;
    }
    blocks.push(
      <p key={`p-${i}`} className={styles.answerText}>
        {renderInlineMarkdown(paraLines.join('\n'), `p-${i}`)}
      </p>
    );
  }

  return <div className={styles.answerRich}>{blocks}</div>;
}

export default function AiAssistant() {
  const { user, isMockMode } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const inRouter = useInRouterContext();

  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [inputError, setInputError] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);

  // T3C9F16 — Smart Reorder Suggestions -> DRAFT Purchase Receipt state
  const [reorderRows, setReorderRows] = useState([]);
  const [reorderSuppliers, setReorderSuppliers] = useState([]);
  const [reorderMeta, setReorderMeta] = useState({
    lowStockTotal: 0,
    lowStockLoaded: 0,
    topProductsTotal: 0,
    topProductsLoaded: 0,
    topProductsFailed: false,
    slowProductsFailed: false,
    suppliersFailed: false,
  });
  const [selectedSupplierId, setSelectedSupplierId] = useState('');
  const [selectedProductIds, setSelectedProductIds] = useState([]);
  const [isReorderLoading, setIsReorderLoading] = useState(false);
  const [reorderLoadError, setReorderLoadError] = useState('');
  const [reorderReloadSeq, setReorderReloadSeq] = useState(0);
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const [draftActionError, setDraftActionError] = useState('');
  const [createdDraftReceipt, setCreatedDraftReceipt] = useState(null);
  const reorderReqSeqRef = useRef(0);
  const draftCreateLockRef = useRef(false);

  const reqSeqRef = useRef(0);
  const inFlightRef = useRef(false);
  const nextIdRef = useRef(1);
  const isMountedRef = useRef(true);
  const abortControllerRef = useRef(null);
  const messagesAreaRef = useRef(null);
  const textareaRef = useRef(null);
  const sessionKeyRef = useRef(`${user?.id ?? 'anon'}:${user?.role ?? 'none'}:${isMockMode}`);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      inFlightRef.current = false;
      reqSeqRef.current += 1;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Invalidate any pending AI request immediately if auth session, role, or mode changes
  useEffect(() => {
    const nextKey = `${user?.id ?? 'anon'}:${user?.role ?? 'none'}:${isMockMode}`;
    if (sessionKeyRef.current !== nextKey) {
      sessionKeyRef.current = nextKey;
      reqSeqRef.current += 1;
      inFlightRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      setIsProcessing(false);
      setMessages([]);
      setInputError('');
    }
  }, [user?.id, user?.role, isMockMode]);

  useEffect(() => {
    if (messages.length === 0) return;
    const container = messagesAreaRef.current;
    if (!container) return;
    if (typeof container.scrollTo === 'function') {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    } else {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages]);

  const runAskQuery = useCallback(
    async ({ promptText, replaceMessageId = null }) => {
      if (!isAdmin || inFlightRef.current || isProcessing) return;

      const check = validateAiMessageInput(promptText);
      if (!check.isValid) {
        setInputError(check.error);
        return;
      }

      inFlightRef.current = true;
      setInputError('');
      setIsProcessing(true);

      const currentSeq = ++reqSeqRef.current;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const nowLabel = formatMessageTime();
      const assistantId = replaceMessageId || `assistant-${nextIdRef.current++}`;

      if (replaceMessageId) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === replaceMessageId
              ? {
                  ...msg,
                  status: 'processing',
                  errorInfo: null,
                  response: null,
                  timestamp: nowLabel,
                }
              : msg
          )
        );
      } else {
        const userId = `user-${nextIdRef.current++}`;
        setInputValue('');
        setMessages((prev) => [
          ...prev,
          {
            id: userId,
            role: 'user',
            text: check.value,
            timestamp: nowLabel,
          },
          {
            id: assistantId,
            role: 'assistant',
            status: 'processing',
            promptText: check.value,
            response: null,
            errorInfo: null,
            timestamp: nowLabel,
          },
        ]);
      }

      try {
        const data = await aiApi.ask({
          isMockMode,
          message: check.value,
          signal: controller.signal,
        });

        if (!isMountedRef.current || currentSeq !== reqSeqRef.current) return;

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  status: data.insufficient_data ? 'insufficient_data' : 'success',
                  response: data,
                  errorInfo: null,
                  timestamp: formatMessageTime(),
                }
              : msg
          )
        );
      } catch (err) {
        if (!isMountedRef.current || currentSeq !== reqSeqRef.current) return;
        if (isAiRequestCanceled(err)) return;

        const classified = classifyAiError(err);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  status: 'error',
                  response: null,
                  errorInfo: classified,
                  timestamp: formatMessageTime(),
                }
              : msg
          )
        );
      } finally {
        if (currentSeq === reqSeqRef.current) {
          inFlightRef.current = false;
          if (isMountedRef.current) {
            setIsProcessing(false);
          }
        }
      }
    },
    [isAdmin, isMockMode, isProcessing]
  );

  const handleSubmit = (e) => {
    e.preventDefault();
    runAskQuery({ promptText: inputValue });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      runAskQuery({ promptText: inputValue });
    }
  };

  const handleResetConversation = () => {
    reqSeqRef.current += 1;
    inFlightRef.current = false;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsProcessing(false);
    setMessages([]);
    setInputError('');
  };

  const handleNarrowQuestion = (promptText) => {
    if (!inputValue.trim() && promptText) {
      setInputValue(promptText);
    }
    setInputError('');
    if (textareaRef.current && typeof textareaRef.current.focus === 'function') {
      textareaRef.current.focus();
    }
  };

  const handleDismissError = (messageId) => {
    setMessages((prev) => prev.filter((msg) => msg.id !== messageId));
  };

  // T3C9F16 — Load Low Stock, 30-day Top Products & Active Suppliers in parallel
  useEffect(() => {
    if (!isAdmin || isMockMode) {
      reorderReqSeqRef.current += 1;
      setReorderRows([]);
      setReorderSuppliers([]);
      setSelectedProductIds([]);
      setIsReorderLoading(false);
      setReorderLoadError('');
      return undefined;
    }

    const currentSeq = ++reorderReqSeqRef.current;
    setIsReorderLoading(true);
    setReorderLoadError('');

    const fetchReorderData = async () => {
      try {
        const [lowResult, topResult, slowResult, supResult] = await Promise.allSettled([
          inventoryApi.getLowStock({ page: 1, pageSize: 20 }),
          analyticsApi.getTopProducts({
            isMockMode,
            page: 1,
            page_size: 20,
            days: 30,
          }),
          analyticsApi.getSlowProducts({
            isMockMode,
            page: 1,
            page_size: 100,
          }),
          suppliersApi.getActiveSuppliers({
            page: 1,
            pageSize: 100,
            fetchAll: true,
            maxPages: 5,
          }),
        ]);

        if (!isMountedRef.current || currentSeq !== reorderReqSeqRef.current) {
          return;
        }

        if (lowResult.status === 'rejected') {
          setReorderRows([]);
          setSelectedProductIds([]);
          setReorderLoadError(
            getApiErrorMessage(
              lowResult.reason,
              'Không thể tải danh sách sản phẩm tồn kho thấp để gợi ý nhập hàng.'
            )
          );
          return;
        }

        const lowData = lowResult.value || {};
        const lowItems = lowData.items || [];
        const lowTotal = Number(lowData.total) || lowItems.length;

        const topFailed = topResult.status === 'rejected';
        const topData = !topFailed ? topResult.value || {} : {};
        const topItems = !topFailed ? topData.items || [] : [];
        const topTotal = !topFailed
          ? Number(topData.total) || topItems.length
          : 0;

        const slowFailed = slowResult.status === 'rejected';
        const slowData = !slowFailed ? slowResult.value || {} : {};
        const slowItems = !slowFailed ? slowData.items || [] : [];

        const supFailed = supResult.status === 'rejected';
        const activeSups = !supFailed ? supResult.value?.items || [] : [];

        const builtSuggestions = buildReorderSuggestions(
          lowItems,
          topFailed ? null : topItems,
          slowFailed ? null : slowItems
        );
        setReorderRows(builtSuggestions);
        setReorderSuppliers(activeSups);
        setReorderMeta({
          lowStockTotal: Math.max(lowTotal, builtSuggestions.length),
          lowStockLoaded: builtSuggestions.length,
          topProductsTotal: Math.max(topTotal, topItems.length),
          topProductsLoaded: topItems.length,
          topProductsFailed: topFailed,
          slowProductsFailed: slowFailed,
          suppliersFailed: supFailed,
        });
        setSelectedProductIds((prev) => {
          const validIdSet = new Set(builtSuggestions.map((r) => r.product_id));
          return prev.filter((id) => validIdSet.has(id));
        });
      } catch (err) {
        if (!isMountedRef.current || currentSeq !== reorderReqSeqRef.current) {
          return;
        }
        setReorderLoadError(
          getApiErrorMessage(
            err,
            'Không thể tải dữ liệu gợi ý nhập hàng từ máy chủ.'
          )
        );
      } finally {
        if (isMountedRef.current && currentSeq === reorderReqSeqRef.current) {
          setIsReorderLoading(false);
        }
      }
    };

    fetchReorderData();
    return () => {
      reorderReqSeqRef.current += 1;
    };
  }, [isAdmin, isMockMode, reorderReloadSeq]);

  const isAllSuggestionsSelected =
    reorderRows.length > 0 && selectedProductIds.length === reorderRows.length;

  const handleToggleAllSuggestions = () => {
    setDraftActionError('');
    if (isAllSuggestionsSelected) {
      setSelectedProductIds([]);
    } else {
      setSelectedProductIds(reorderRows.map((r) => r.product_id));
    }
  };

  const handleToggleSuggestionRow = (productId) => {
    const pid = Number(productId);
    setDraftActionError('');
    setSelectedProductIds((prev) =>
      prev.includes(pid) ? prev.filter((id) => id !== pid) : [...prev, pid]
    );
  };

  const handleUpdateSuggestionRow = (productId, field, rawValue) => {
    const pid = Number(productId);
    setDraftActionError('');
    setReorderRows((prev) =>
      prev.map((row) => {
        if (row.product_id !== pid) return row;
        return {
          ...row,
          [field]: rawValue ?? '',
        };
      })
    );
  };

  const handleCreateDraftDirect = async () => {
    if (draftCreateLockRef.current || isCreatingDraft) return;
    setDraftActionError('');
    setCreatedDraftReceipt(null);

    const { payload, error } = buildDraftReceiptPayload({
      supplierId: selectedSupplierId,
      rows: reorderRows,
      selectedIds: selectedProductIds,
    });

    if (error || !payload) {
      setDraftActionError(error || 'Dữ liệu tạo phiếu nhập nháp chưa hợp lệ.');
      return;
    }

    draftCreateLockRef.current = true;
    setIsCreatingDraft(true);
    try {
      const created = await receiptsApi.createDraft(payload);
      if (!isMountedRef.current) return;
      setCreatedDraftReceipt(created);
      setDraftActionError('');
    } catch (err) {
      if (!isMountedRef.current) return;
      setDraftActionError(
        getApiErrorMessage(err, 'Không thể tạo phiếu nhập nháp từ gợi ý AI.')
      );
    } finally {
      draftCreateLockRef.current = false;
      if (isMountedRef.current) {
        setIsCreatingDraft(false);
      }
    }
  };

  const handleOpenPrefillPurchaseForm = (navigateFn) => {
    setDraftActionError('');
    const { prefillDraft, error } = buildPrefillDraftState({
      supplierId: selectedSupplierId,
      rows: reorderRows,
      selectedIds: selectedProductIds,
    });

    if (error || !prefillDraft) {
      setDraftActionError(error || 'Dữ liệu sản phẩm gợi ý chưa hợp lệ.');
      return;
    }

    if (typeof navigateFn === 'function') {
      navigateFn('/purchases', { state: { prefillDraft } });
    }
  };

  const handleInspectCreatedDraft = (navigateFn) => {
    if (!createdDraftReceipt?.id) return;
    if (typeof navigateFn === 'function') {
      navigateFn('/purchases', {
        state: { openReceiptId: Number(createdDraftReceipt.id) },
      });
    }
  };

  const renderReorderSuggestionsSection = (navigateFn) => (
    <section
      className={styles.reorderCard}
      aria-label="Bảng gợi ý nhập hàng thông minh"
      data-testid="ai-reorder-suggestions-panel"
    >
      <div className={styles.reorderHeader}>
        <div className={styles.reorderTitleGroup}>
          <div className={styles.reorderTitleRow}>
            <h2 className={styles.reorderTitle}>
              Bảng gợi ý nhập hàng thông minh
            </h2>
            <span className={styles.draftOnlyBadge}>
              Chỉ tạo BẢN NHÁP (DRAFT)
            </span>
          </div>
          <p className={styles.reorderSubtitle}>
            Gợi ý định lượng theo quy tắc tồn kho (
            <code>max(2 × ngưỡng − tồn hiện tại, ⌈lượng bán Top 30 ngày / 2⌉, 5)</code>
            ) từ danh sách tồn thấp (≤ 5) đối chiếu với Top sản phẩm bán chạy 30
            ngày. Các mặt hàng ngoài danh sách Top được ghi rõ &ldquo;Chưa có dữ
            liệu bán hàng đầy đủ&rdquo; và chỉ tính theo ngưỡng tồn. Phiếu sinh
            ra ở trạng thái DRAFT, chưa cộng tồn kho.
          </p>
        </div>

        <button
          type="button"
          className={styles.refreshSuggestionsBtn}
          disabled={isReorderLoading || isCreatingDraft}
          onClick={() => setReorderReloadSeq((seq) => seq + 1)}
        >
          {isReorderLoading ? 'Đang tải gợi ý...' : 'Làm mới gợi ý'}
        </button>
      </div>

      {createdDraftReceipt && (
        <div
          className={styles.reorderSuccessBanner}
          role="status"
          data-testid="draft-created-banner"
        >
          <span>
            Đã tạo phiếu nhập nháp{' '}
            <strong>#{createdDraftReceipt.id}</strong> (trạng thái{' '}
            <strong>DRAFT</strong> — chưa cộng tồn kho). Vui lòng kiểm tra đơn
            giá và xác nhận phiếu khi hàng về kho.
          </span>
          <button
            type="button"
            className={styles.inspectDraftBtn}
            onClick={() => handleInspectCreatedDraft(navigateFn)}
          >
            Kiểm tra &amp; Xác nhận phiếu nháp
          </button>
        </div>
      )}

      {(reorderMeta.topProductsFailed ||
        reorderMeta.slowProductsFailed ||
        reorderMeta.suppliersFailed) && (
        <div
          className={styles.reorderEmptyBox}
          role="status"
          data-testid="reorder-degraded-notice"
        >
          <span>
            {reorderMeta.topProductsFailed &&
              'Chưa tải được dữ liệu Top sản phẩm bán chạy 30 ngày; hệ thống đang gợi ý thuần theo ngưỡng tồn kho (chưa có dữ liệu bán hàng đầy đủ). '}
            {reorderMeta.slowProductsFailed &&
              'Chưa đối chiếu được danh sách sản phẩm bán chậm 30 ngày. '}
            {reorderMeta.suppliersFailed &&
              'Chưa tải được danh sách nhà cung cấp hoạt động; bạn vẫn có thể chọn sản phẩm và bấm "Mở form tạo phiếu" để chọn nhà cung cấp tại trang Quản lý nhập hàng.'}
          </span>
        </div>
      )}

      {reorderRows.length > 0 &&
        (reorderMeta.lowStockTotal > reorderRows.length ||
          (!reorderMeta.topProductsFailed &&
            reorderMeta.topProductsTotal > reorderMeta.topProductsLoaded)) && (
          <div
            className={styles.reorderEmptyBox}
            role="status"
            data-testid="reorder-pagination-notice"
          >
            <span>
              {reorderMeta.lowStockTotal > reorderRows.length &&
                `Đang hiển thị ${reorderRows.length}/${reorderMeta.lowStockTotal} sản phẩm tồn thấp. `}
              {!reorderMeta.topProductsFailed &&
                reorderMeta.topProductsTotal > reorderMeta.topProductsLoaded &&
                `Dữ liệu bán hàng đối chiếu trên Top ${reorderMeta.topProductsLoaded}/${reorderMeta.topProductsTotal} sản phẩm bán chạy 30 ngày.`}
            </span>
          </div>
        )}

      {draftActionError && (
        <div
          className={styles.reorderFeedbackErr}
          role="status"
          data-testid="draft-action-error"
        >
          <span>{draftActionError}</span>
        </div>
      )}

      {reorderLoadError ? (
        <div
          className={styles.reorderFeedbackErr}
          role="status"
          data-testid="reorder-load-error"
        >
          <span>{reorderLoadError}</span>
        </div>
      ) : isReorderLoading && reorderRows.length === 0 ? (
        <div className={styles.reorderEmptyBox} role="status">
          <span>Đang tổng hợp danh sách sản phẩm gợi ý nhập hàng...</span>
        </div>
      ) : reorderRows.length === 0 ? (
        <div className={styles.reorderEmptyBox} role="status">
          <span>
            Hiện không có sản phẩm nào dưới ngưỡng tồn kho an toàn cần gợi ý
            nhập thêm.
          </span>
        </div>
      ) : (
        (() => {
          const zeroCostSelectedCount = reorderRows.filter(
            (r) =>
              selectedProductIds.includes(r.product_id) &&
              parseStrictInteger(r.unit_cost_vnd) === 0
          ).length;
          const guidance = getDraftActionGuidance({
            selectedCount: selectedProductIds.length,
            supplierId: selectedSupplierId,
            suppliersCount: reorderSuppliers.length,
            suppliersFailed: reorderMeta.suppliersFailed,
            isCreatingDraft,
            zeroCostSelectedCount,
          });
          const guidanceClass =
            guidance.tone === 'ready'
              ? `${styles.actionGuidanceBar} ${styles.actionGuidanceReady}`
              : guidance.tone === 'warning'
              ? `${styles.actionGuidanceBar} ${styles.actionGuidanceWarn}`
              : styles.actionGuidanceBar;

          return (
            <>
              <div className={styles.reorderToolbar}>
                <div className={styles.supplierField}>
                  <label
                    htmlFor="ai-reorder-supplier-select"
                    className={styles.supplierLabel}
                  >
                    Nhà cung cấp dự kiến *
                  </label>
                  <select
                    id="ai-reorder-supplier-select"
                    aria-label="Chọn nhà cung cấp cho phiếu nhập nháp"
                    className={styles.supplierSelect}
                    value={selectedSupplierId}
                    disabled={isCreatingDraft}
                    onChange={(e) => {
                      setSelectedSupplierId(e.target.value);
                      setDraftActionError('');
                    }}
                  >
                    <option value="">-- Chọn nhà cung cấp --</option>
                    {reorderSuppliers.map((sup) => (
                      <option key={sup.id} value={sup.id}>
                        {sup.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className={styles.toolbarActions}>
                  <button
                    type="button"
                    className={styles.openFormBtn}
                    title={guidance.openFormTooltip}
                    disabled={selectedProductIds.length === 0 || isCreatingDraft}
                    onClick={() => handleOpenPrefillPurchaseForm(navigateFn)}
                  >
                    Mở form tạo phiếu
                  </button>

                  <button
                    type="button"
                    className={styles.createDraftBtn}
                    title={guidance.createDraftTooltip}
                    disabled={
                      selectedProductIds.length === 0 ||
                      !selectedSupplierId ||
                      isCreatingDraft
                    }
                    onClick={handleCreateDraftDirect}
                  >
                    {isCreatingDraft
                      ? 'Đang tạo phiếu nháp...'
                      : `Tạo phiếu nháp (${selectedProductIds.length} sản phẩm)`}
                  </button>
                </div>
              </div>

              <div
                className={guidanceClass}
                role="status"
                data-testid="reorder-action-guidance"
              >
                <span>{guidance.message}</span>
              </div>

              <div className={styles.reorderTableWrap}>
                <table className={styles.reorderTable}>
                  <thead>
                    <tr>
                      <th>
                        <input
                          type="checkbox"
                          aria-label="Chọn tất cả sản phẩm gợi ý"
                          checked={isAllSuggestionsSelected}
                          onChange={handleToggleAllSuggestions}
                        />
                      </th>
                      <th>SKU</th>
                      <th>Tên sản phẩm</th>
                      <th>Tồn hiện tại / Ngưỡng</th>
                      <th>Đã bán (30 ngày)</th>
                      <th>Phân loại &amp; Lý do gợi ý</th>
                      <th>Số lượng nhập</th>
                      <th>Đơn giá dự kiến (VND)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reorderRows.map((row) => {
                      const isChecked = selectedProductIds.includes(row.product_id);
                      const badgeMeta =
                        row.classification === 'SLOW_MOVING_HOLD'
                          ? {
                              label: 'Bán chậm · Cân nhắc giữ',
                              className: styles.slowHoldBadge,
                            }
                          : row.classification === 'PRIORITY_RESTOCK'
                          ? {
                              label: 'Ưu tiên nhập',
                              className: styles.priorityBadge,
                            }
                          : {
                              label: 'Cần kiểm tra nhu cầu',
                              className: styles.checkDemandBadge,
                            };

                      return (
                        <tr
                          key={row.product_id}
                          className={isChecked ? styles.reorderRowSelected : ''}
                          onClick={(e) => {
                            if (e.target.closest('input, button, select, textarea, a, label')) return;
                            handleToggleSuggestionRow(row.product_id);
                          }}
                        >
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Chọn sản phẩm ${row.sku}`}
                              checked={isChecked}
                              onChange={() =>
                                handleToggleSuggestionRow(row.product_id)
                              }
                            />
                          </td>
                          <td className={styles.skuCell}>{row.sku}</td>
                          <td>
                            <strong>{row.name}</strong>
                          </td>
                          <td>
                            <span
                              className={
                                row.quantity === 0
                                  ? styles.stockBadgeOut
                                  : styles.stockBadgeLow
                              }
                            >
                              {row.quantity} / {row.threshold}
                            </span>
                          </td>
                          <td>
                            {row.sold_units === null
                              ? 'Chưa có dữ liệu bán hàng đầy đủ'
                              : `${row.sold_units.toLocaleString('vi-VN')} SP`}
                          </td>
                          <td className={styles.reasonCell}>
                            <span className={badgeMeta.className}>
                              {badgeMeta.label}
                            </span>
                            <span className={styles.reasonText}>{row.reason}</span>
                          </td>
                          <td>
                            <input
                              type="number"
                              min={1}
                              step={1}
                              aria-label={`Số lượng nhập ${row.sku}`}
                              className={styles.cellInput}
                              value={row.suggested_quantity}
                              onChange={(e) =>
                                handleUpdateSuggestionRow(
                                  row.product_id,
                                  'suggested_quantity',
                                  e.target.value
                                )
                              }
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              min={0}
                              step={1000}
                              aria-label={`Đơn giá dự kiến ${row.sku}`}
                              className={styles.cellInput}
                              value={row.unit_cost_vnd}
                              onChange={(e) =>
                                handleUpdateSuggestionRow(
                                  row.product_id,
                                  'unit_cost_vnd',
                                  e.target.value
                                )
                              }
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          );
        })()
      )}
    </section>
  );

  if (!isAdmin) {
    return (
      <div className={styles.pageContainer}>
        <div className={styles.stateCard} role="alert">
          <h2 className={styles.pageTitle}>Không có quyền truy cập</h2>
          <p className={styles.pageSubtitle}>
            Trợ lý AI RetailOps chỉ dành cho tài khoản Quản trị viên.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.pageContainer}>
      <header className={styles.pageHeader}>
        <div className={styles.titleGroup}>
          <div className={styles.titleRow}>
            <h1 className={styles.pageTitle}>Trợ lý AI RetailOps</h1>
          </div>
          <p className={styles.pageSubtitle}>
            Phân tích doanh thu, sản phẩm bán chạy/chậm và gợi ý nhập hàng dựa trên dữ liệu đã ghi
            nhận trong hệ thống.
          </p>
        </div>

        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.newChatBtn}
            onClick={handleResetConversation}
            disabled={messages.length === 0 && !isProcessing}
          >
            Cuộc trò chuyện mới
          </button>
        </div>
      </header>

      <div className={styles.safetyBanner}>
        <span>
          Trợ lý AI chỉ sử dụng dữ liệu bán hàng và tồn kho ở chế độ chỉ đọc; mọi câu trả lời đều
          kèm nguồn dẫn chứng và chỉ mang tính gợi ý.
        </span>
      </div>

      <section className={styles.chatShell} aria-label="Khung trò chuyện Trợ lý AI">
        <div ref={messagesAreaRef} className={styles.messagesArea} aria-live="polite">
          {messages.length === 0 ? (
            <div className={styles.welcomeCard}>
              <h2 className={styles.welcomeTitle}>Bắt đầu hỏi đáp kinh doanh</h2>
              <p className={styles.welcomeDesc}>
                Chọn một câu hỏi gợi ý bên dưới hoặc nhập câu hỏi của bạn về doanh thu, đơn hàng và
                tồn kho:
              </p>
              <div className={styles.promptGrid}>
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className={styles.promptChip}
                    disabled={isProcessing}
                    onClick={() => runAskQuery({ promptText: prompt })}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => {
              if (msg.role === 'user') {
                return (
                  <div key={msg.id} className={styles.messageRowUser}>
                    <div className={styles.userBubble}>{msg.text}</div>
                  </div>
                );
              }

              const isWarningError =
                msg.errorInfo?.kind === 'quota' || msg.errorInfo?.kind === 'timeout';

              return (
                <div key={msg.id} className={styles.messageRowAssistant}>
                  <article className={styles.assistantCard}>
                    <div className={styles.assistantHeader}>
                      <span className={styles.assistantAuthor}>Trợ lý AI RetailOps</span>
                      <span className={styles.messageTime}>{msg.timestamp}</span>
                    </div>

                    {msg.status === 'processing' && (
                      <div className={styles.processingRow} role="status">
                        <span className={styles.spinner} aria-hidden="true" />
                        <span>Đang phân tích dữ liệu bán hàng và tồn kho...</span>
                      </div>
                    )}

                    {(msg.status === 'success' || msg.status === 'insufficient_data') &&
                      msg.response && (
                        <>
                          {msg.status === 'insufficient_data' && (
                            <span className={styles.insufficientBadge}>
                              Chưa đủ dữ liệu kết luận
                            </span>
                          )}

                          {renderFormattedAnswer(msg.response.answer)}

                          {msg.status === 'insufficient_data' && (
                            <>
                              <p className={styles.insufficientHint}>
                                Gợi ý: Câu hỏi quá rộng hoặc dữ liệu nằm ngoài phạm vi thời gian
                                đã ghi nhận.
                              </p>
                              <button
                                type="button"
                                className={styles.narrowBtn}
                                disabled={isProcessing}
                                onClick={() => handleNarrowQuestion(msg.promptText)}
                              >
                                Thu hẹp câu hỏi
                              </button>
                            </>
                          )}

                          {msg.response.evidence.length > 0 && (
                            <details className={styles.evidenceSection}>
                              <summary className={styles.evidenceToggle}>
                                Nguồn dữ liệu &amp; Dẫn chứng ({msg.response.evidence.length})
                              </summary>
                              <div className={styles.evidenceList}>
                                {msg.response.evidence.map((ev, idx) => (
                                  <div
                                    key={`${msg.id}-ev-${idx}`}
                                    className={styles.evidenceCard}
                                  >
                                    <div className={styles.evidenceMeta}>
                                      <span className={styles.evidenceSource}>{ev.source}</span>
                                      <span className={styles.evidencePeriod}>
                                        {ev.period ? ev.period : 'Dữ liệu hiện tại'}
                                      </span>
                                    </div>
                                    <p className={styles.evidenceSummary}>{ev.summary}</p>
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}

                          <p className={styles.suggestionNote}>
                            Lưu ý: Nội dung chỉ mang tính gợi ý tham khảo, không tự động thay đổi
                            dữ liệu tồn kho hay phiếu nhập.
                          </p>
                        </>
                      )}

                    {msg.status === 'error' && msg.errorInfo && (
                      <div
                        className={`${styles.errorBox} ${
                          isWarningError ? styles.errorBoxWarning : ''
                        }`}
                        role="alert"
                        data-error-kind={msg.errorInfo.kind}
                      >
                        <p className={styles.errorTitle}>{msg.errorInfo.title}</p>
                        <p className={styles.errorMessage}>{msg.errorInfo.message}</p>
                        {msg.errorInfo.hint && (
                          <p className={styles.errorHint}>{msg.errorInfo.hint}</p>
                        )}
                        {msg.errorInfo.actionType === 'retry' ? (
                          <button
                            type="button"
                            className={styles.retryBtn}
                            disabled={isProcessing}
                            onClick={() =>
                              runAskQuery({
                                promptText: msg.promptText,
                                replaceMessageId: msg.id,
                              })
                            }
                          >
                            Thử lại
                          </button>
                        ) : (
                          <button
                            type="button"
                            className={styles.dismissBtn}
                            disabled={isProcessing}
                            onClick={() => handleDismissError(msg.id)}
                          >
                            Đóng
                          </button>
                        )}
                      </div>
                    )}
                  </article>
                </div>
              );
            })
          )}
        </div>

        <form className={styles.composer} onSubmit={handleSubmit}>
          {inputError && (
            <p className={styles.inputError} role="alert">
              {inputError}
            </p>
          )}
          <div className={styles.composerRow}>
            <textarea
              ref={textareaRef}
              className={styles.textarea}
              aria-label="Nhập câu hỏi cho Trợ lý AI"
              placeholder="Ví dụ: Top 5 sản phẩm bán chạy 30 ngày qua hoặc sản phẩm nào cần nhập thêm?"
              value={inputValue}
              maxLength={AI_QUERY_MAX_LENGTH}
              disabled={isProcessing}
              onChange={(e) => {
                setInputValue(e.target.value);
                if (inputError) setInputError('');
              }}
              onKeyDown={handleKeyDown}
              rows={2}
            />
            <button
              type="submit"
              className={styles.sendBtn}
              disabled={isProcessing || !inputValue.trim()}
            >
              {isProcessing ? 'Đang xử lý...' : 'Gửi câu hỏi'}
            </button>
          </div>
          <div className={styles.composerFooter}>
            <span>Nhấn Enter để gửi, Shift + Enter để xuống dòng</span>
            <span>
              {inputValue.length.toLocaleString('vi-VN')} /{' '}
              {AI_QUERY_MAX_LENGTH.toLocaleString('vi-VN')}
            </span>
          </div>
        </form>
      </section>

      {inRouter ? (
        <RouterNavigateBridge>
          {(navigateFn) => renderReorderSuggestionsSection(navigateFn)}
        </RouterNavigateBridge>
      ) : (
        renderReorderSuggestionsSection(null)
      )}
    </div>
  );
}
