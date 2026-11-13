/**
 * Kiểm tra xem người dùng có được phép đóng Modal chi tiết hồ sơ (X, Đóng, Escape, backdrop) hay không.
 * Chặn đóng thủ công khi yêu cầu approve/reject đang gửi lên Backend.
 */
export function canUserCloseApprovalModal({
  isSubmittingDecision = false,
  isDecisionPending = false,
} = {}) {
  return !isSubmittingDecision && !isDecisionPending;
}

/**
 * Thực thi luồng quyết định duyệt/từ chối hồ sơ Staff.
 * Tách biệt rõ:
 * - Khi POST thành công: gọi closeModalProgrammatic() bất kể isSubmittingDecision đang true, sau đó refresh.
 * - Khi 409/404: đánh dấu modal stale, giữ modal mở để người dùng thấy thông báo, refresh danh sách, không retry POST.
 * - Khi 422/401/403/5xx/network: giữ nguyên rejectReason để người dùng sửa và hiển thị lỗi phù hợp.
 */
export async function executeStaffApprovalDecision({
  action,
  isMockMode,
  selectedApproval,
  isModalStale,
  isDecisionPendingRef,
  rejectReason = '',
  validateRejectReason,
  staffApprovalsApi,
  getApiErrorMessage,
  setIsSubmittingDecision,
  setModalError,
  setIsModalStale,
  onInvalidReason,
  onSuccessToast,
  closeModalProgrammatic,
  onRefresh,
}) {
  if (!selectedApproval || isModalStale || isDecisionPendingRef.current) {
    return { status: 'ignored' };
  }

  let normalizedReason = '';
  if (action === 'reject') {
    const reasonValidation = validateRejectReason(rejectReason);
    if (!reasonValidation.isValid) {
      setModalError(reasonValidation.error);
      if (typeof onInvalidReason === 'function') {
        onInvalidReason();
      }
      return { status: 'validation_error' };
    }
    normalizedReason = reasonValidation.normalized;
  }

  isDecisionPendingRef.current = true;
  setIsSubmittingDecision(true);
  setModalError('');

  try {
    if (action === 'approve') {
      await staffApprovalsApi.approveStaff({
        isMockMode,
        id: selectedApproval.id,
      });
    } else {
      await staffApprovalsApi.rejectStaff({
        isMockMode,
        id: selectedApproval.id,
        reason: normalizedReason,
      });
    }

    onSuccessToast(selectedApproval);
    closeModalProgrammatic();
    onRefresh();
    return { status: 'success' };
  } catch (error) {
    const httpStatus = error?.response?.status;
    if (httpStatus === 409) {
      setIsModalStale(true);
      setModalError(
        action === 'approve'
          ? 'Hồ sơ này không còn ở trạng thái chờ duyệt (HTTP 409 Conflict). Danh sách đã được làm mới — vui lòng đóng hộp thoại.'
          : 'Hồ sơ này đã được xử lý trước đó (HTTP 409 Conflict). Danh sách đã được làm mới — vui lòng đóng hộp thoại.'
      );
      onRefresh();
      return { status: 'conflict' };
    }
    if (httpStatus === 404) {
      setIsModalStale(true);
      setModalError(
        'Yêu cầu xét duyệt không tồn tại (HTTP 404). Danh sách đã được làm mới — vui lòng đóng hộp thoại.'
      );
      onRefresh();
      return { status: 'not_found' };
    }
    if (httpStatus === 403) {
      setModalError(
        action === 'approve'
          ? 'Bạn không có quyền thực hiện phê duyệt nhân viên (HTTP 403 Forbidden).'
          : 'Bạn không có quyền từ chối hồ sơ nhân viên (HTTP 403 Forbidden).'
      );
      return { status: 'forbidden' };
    }
    if (httpStatus === 401) {
      setModalError(
        'Phiên đăng nhập đã hết hạn (HTTP 401). Vui lòng đăng nhập lại.'
      );
      return { status: 'unauthorized' };
    }

    setModalError(
      getApiErrorMessage(error) ||
        (action === 'approve'
          ? 'Không thể phê duyệt hồ sơ nhân viên. Vui lòng thử lại.'
          : 'Không thể từ chối hồ sơ nhân viên. Vui lòng thử lại.')
    );
    return { status: 'error' };
  } finally {
    isDecisionPendingRef.current = false;
    setIsSubmittingDecision(false);
  }
}
