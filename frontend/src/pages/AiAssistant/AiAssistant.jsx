import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AI_QUERY_MAX_LENGTH,
  aiApi,
  classifyAiError,
  validateAiMessageInput,
} from '../../api/aiApi';
import { useAuth } from '../../context/AuthContext';
import styles from './AiAssistant.module.css';

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

export default function AiAssistant() {
  const { user, isMockMode } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [inputError, setInputError] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);

  const reqSeqRef = useRef(0);
  const nextIdRef = useRef(1);
  const isMountedRef = useRef(true);
  const abortControllerRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const runAskQuery = useCallback(
    async ({ promptText, replaceMessageId = null }) => {
      if (!isAdmin || isProcessing) return;

      const check = validateAiMessageInput(promptText);
      if (!check.isValid) {
        setInputError(check.error);
        return;
      }

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
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;

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
        if (isMountedRef.current && currentSeq === reqSeqRef.current) {
          setIsProcessing(false);
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
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsProcessing(false);
    setMessages([]);
    setInputError('');
  };

  if (!isAdmin) {
    return (
      <div className={styles.pageContainer}>
        <div className={styles.stateCard} role="alert">
          <h2 className={styles.pageTitle}>Không có quyền truy cập</h2>
          <p className={styles.pageSubtitle}>
            Trợ lý AI RetailOps chỉ dành cho tài khoản Quản trị viên (ADMIN).
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
        <div className={styles.messagesArea} aria-live="polite">
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

                          <p className={styles.answerText}>{msg.response.answer}</p>

                          {msg.status === 'insufficient_data' && (
                            <p className={styles.insufficientHint}>
                              Hệ thống chưa đủ bằng chứng dữ liệu để đưa ra kết luận chắc chắn. Bạn
                              có thể thử thu hẹp khoảng thời gian hoặc kiểm tra lại dữ liệu giao
                              dịch/tồn kho.
                            </p>
                          )}

                          {msg.response.evidence.length > 0 && (
                            <div className={styles.evidenceSection}>
                              <h3 className={styles.evidenceHeading}>
                                Nguồn dữ liệu &amp; Dẫn chứng ({msg.response.evidence.length})
                              </h3>
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
                            </div>
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
                        {msg.errorInfo.retryable && (
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
                        )}
                      </div>
                    )}
                  </article>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        <form className={styles.composer} onSubmit={handleSubmit}>
          {inputError && (
            <p className={styles.inputError} role="alert">
              {inputError}
            </p>
          )}
          <div className={styles.composerRow}>
            <textarea
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
    </div>
  );
}
