/** CF-2.0 FRONTEND CONTRACT; reference only, not a generated production client. */
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

/** API adapter is the ONLY layer allowed to know mock or real transport. */
export interface RetailOpsApi {
  listProducts(query?:URLSearchParams):Promise<Page<ProductRead>>;
  checkout(payload:CheckoutRequest, idempotencyKey:string):Promise<OrderRead>;
  cancelOrder(orderId:number, reason:string, idempotencyKey:string):Promise<OrderRead>;
  createReceipt(payload:ReceiptDraftRequest):Promise<ReceiptRead>;
  confirmReceipt(receiptId:number, expectedDraftVersion:number, idempotencyKey:string):Promise<ReceiptRead>;
  getSalesAnalytics(query?:URLSearchParams):Promise<SalesSummary>;
  askAI(message:string):Promise<AIAnswer>;
}
// Critical: same checkout intent must retain SAME key + payload after uncertain timeout.
// PRICE_CHANGED: ask user confirmation, generate NEW payload + NEW key.
// When REAL mode is selected, NEVER fallback silently to mock on 4xx/5xx/network errors.
// Client side hiding a button is never a replacement for server-side authorization.
