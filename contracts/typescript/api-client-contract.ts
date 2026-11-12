/** CF-2.3 — Contract frontend chỉ để tham chiếu; không phải API client production đã sinh sẵn. */
export type ApiError = {
  code: string;
  message: string;
  details: unknown;
};
export type Page<T> = {items:T[]; total:number; page:number; page_size:number};
export type ProductRead = {
  id:number; category_id:number; sku:string; name:string;
  status:'ACTIVE'|'INACTIVE'; sale_price_vnd:number;
  quantity:number; stock_version:number; created_at:string;updated_at:string;
};
export type CheckoutLine = {
  product_id:number;quantity:number;viewed_unit_price_vnd:number;
};
export type CheckoutRequest = {items:CheckoutLine[]};
export type OrderLine = {
  product_id:number;sku_snapshot:string;product_name_snapshot:string;
  quantity:number;unit_price_vnd:number;line_total_vnd:number;
};
export type OrderRead = {
  id:number; status:'COMPLETED'|'CANCELLED'; total_vnd:number;created_by:number;
  sold_at:string;cancelled_by:number|null;cancelled_at:string|null;
  cancel_reason:string|null;items:OrderLine[];
};
export type ReceiptLine = {product_id:number;quantity:number;unit_cost_vnd:number};
export type ReceiptDraftRequest = {supplier_id:number;items:ReceiptLine[]};
export type ReceiptUpdateRequest = {
  expected_draft_version: number;
  supplier_id?: number;
  items?: ReceiptLine[];
};
export type ReceiptRead = {
  id:number;supplier_id:number;supplier_name_snapshot:string|null;
  status:'DRAFT'|'CONFIRMED'|'CANCELLED';draft_version:number;
  total_vnd:number;created_by:number;closed_by:number|null;
  created_at:string;updated_at:string;closed_at:string|null;
  items:Array<ReceiptLine & {sku_snapshot:string;product_name_snapshot:string;line_total_vnd:number}>;
};
export type SalesSummary = {period_start:string;period_end_exclusive:string;
  revenue_vnd:number;completed_orders:number;cancelled_orders:number;aov_vnd:number};
export type AIEvidence = {source:string;period:string|null;summary:string};
export type AIAnswer = {answer:string;evidence:AIEvidence[];insufficient_data:boolean};

/** Chỉ API adapter được phép biết transport đang dùng mock hay API thật. */
export interface RetailOpsApi {
  listProducts(query?:URLSearchParams):Promise<Page<ProductRead>>;
  checkout(payload:CheckoutRequest, idempotencyKey:string):Promise<OrderRead>;
  cancelOrder(orderId:number, reason:string, idempotencyKey:string):Promise<OrderRead>;
  createReceipt(payload:ReceiptDraftRequest):Promise<ReceiptRead>;
  updateReceipt(receiptId:number, payload:ReceiptUpdateRequest):Promise<ReceiptRead>;
  confirmReceipt(receiptId:number, expectedDraftVersion:number, idempotencyKey:string):Promise<ReceiptRead>;
  getSalesAnalytics(query?:URLSearchParams):Promise<SalesSummary>;
  askAI(message:string):Promise<AIAnswer>;
}
// Quan trọng: retry cùng ý định Checkout sau timeout không rõ kết quả phải giữ NGUYÊN key và payload.
// PRICE_CHANGED: yêu cầu người dùng xác nhận giá mới, sau đó tạo payload MỚI và key MỚI.
// Khi đã chọn chế độ API thật, KHÔNG âm thầm chuyển sang mock nếu gặp lỗi 4xx/5xx/network.
// Ẩn nút ở frontend không bao giờ thay thế kiểm tra quyền tại backend.


/** GET /products đã triển khai trên develop; dùng `search`, không dùng `q`. */
export type ProductSort = 'name_asc'|'name_desc'|'sku_asc'|'sku_desc'|'created_desc';
export type ProductListQuery = {
  search?:string; category_id?:number; status?:'ACTIVE'|'INACTIVE';
  sort?:ProductSort; page?:number; page_size?:number;
};
/** Chuyển ngày YYYY-MM-DD theo Asia/Ho_Chi_Minh tại backend; client không tự đổi sang UTC. */
export type DateRangeVN = {from_date?:string; to_date?:string};
export type ReceiptListQuery = DateRangeVN & {
  status?:'DRAFT'|'CONFIRMED'|'CANCELLED'; supplier_id?:number; page?:number; page_size?:number;
};
export type OrderListQuery = DateRangeVN & {
  status?:'COMPLETED'|'CANCELLED'; search?:string; page?:number; page_size?:number;
};
export type PriceChangedError = {
  code:'PRICE_CHANGED'; message:string;
  details:{changed_items:Array<{product_id:number;viewed_unit_price_vnd:number;current_unit_price_vnd:number}>};
};
/** FE xem mọi Order, nhưng không tự suy ra quyền hủy từ việc được phép xem. */
export interface RetailOpsReadApi {
  listProducts(query?:ProductListQuery):Promise<Page<ProductRead>>;
  listReceipts(query?:ReceiptListQuery):Promise<Page<ReceiptRead>>;
  listOrders(query?:OrderListQuery):Promise<Page<OrderRead>>;
}
