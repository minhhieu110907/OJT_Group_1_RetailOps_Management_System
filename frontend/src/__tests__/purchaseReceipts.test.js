import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient from '../api/axiosClient.js';
import {
  receiptsApi,
  validateReceiptLineRead,
  validateReceiptRead,
  validateReceiptPage,
  normalizeAndValidateReceiptLines,
  isValidIsoTimestamp,
  VALID_RECEIPT_STATUSES,
} from '../api/receiptsApi.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const VALID_RECEIPT_ITEM = {
  product_id: 12,
  sku_snapshot: 'SKU12',
  product_name_snapshot: 'Dầu ăn Tường An 1L',
  quantity: 2,
  unit_cost_vnd: 47000,
  line_total_vnd: 94000,
};

const VALID_RECEIPT_FIXTURE = {
  id: 9,
  supplier_id: 4,
  supplier_name_snapshot: 'NCC Vinamilk',
  status: 'DRAFT',
  draft_version: 1,
  total_vnd: 94000,
  created_by: 1,
  closed_by: null,
  created_at: '2026-11-10T01:00:00.000Z',
  updated_at: '2026-11-10T01:00:00.000Z',
  closed_at: null,
  items: [VALID_RECEIPT_ITEM],
};

describe('T04A7C3 & T04A8B7 Purchase Receipts Management Suite', () => {
  beforeEach(() => {
    delete axiosClient.get;
    delete axiosClient.post;
    delete axiosClient.patch;
  });

  // ==========================================================================
  // 1. F01: ReceiptRead & ReceiptLineRead Validation (Fail-Closed)
  // ==========================================================================
  describe('F01: ReceiptRead & ReceiptLineRead Schema Validation (Fail-Closed)', () => {
    test('validates ISO timestamps accurately with timezone & leap year check', () => {
      assert.equal(isValidIsoTimestamp('2026-11-10T01:00:00.000Z'), true);
      assert.equal(isValidIsoTimestamp('2024-02-29T12:00:00Z'), true);
      assert.equal(isValidIsoTimestamp('2026-02-29T12:00:00Z'), false);
      assert.equal(isValidIsoTimestamp('not-valid'), false);
      assert.equal(isValidIsoTimestamp(null), false);
    });

    test('validates VALID_RECEIPT_STATUSES directly (DRAFT, CONFIRMED, CANCELLED)', () => {
      assert.equal(VALID_RECEIPT_STATUSES.has('DRAFT'), true);
      assert.equal(VALID_RECEIPT_STATUSES.has('CONFIRMED'), true);
      assert.equal(VALID_RECEIPT_STATUSES.has('CANCELLED'), true);
      assert.equal(VALID_RECEIPT_STATUSES.has('PENDING'), false);
    });

    test('validates ReceiptLineRead fields correctly', () => {
      const validated = validateReceiptLineRead(VALID_RECEIPT_ITEM);
      assert.equal(validated.product_id, 12);
      assert.equal(validated.sku_snapshot, 'SKU12');
      assert.equal(validated.product_name_snapshot, 'Dầu ăn Tường An 1L');
      assert.equal(validated.quantity, 2);
      assert.equal(validated.unit_cost_vnd, 47000);
      assert.equal(validated.line_total_vnd, 94000);
    });

    test('rejects ReceiptLineRead with non-positive quantity or negative cost', () => {
      assert.throws(
        () => validateReceiptLineRead({ ...VALID_RECEIPT_ITEM, quantity: 0 }),
        /Receipt item quantity must be a positive integer/
      );
      assert.throws(
        () => validateReceiptLineRead({ ...VALID_RECEIPT_ITEM, unit_cost_vnd: -100 }),
        /Receipt item unit_cost_vnd must be a non-negative integer/
      );
    });

    test('validates complete ReceiptRead structure', () => {
      const validated = validateReceiptRead(VALID_RECEIPT_FIXTURE);
      assert.equal(validated.id, 9);
      assert.equal(validated.supplier_id, 4);
      assert.equal(validated.status, 'DRAFT');
      assert.equal(validated.draft_version, 1);
      assert.equal(validated.items.length, 1);

      const paged = validateReceiptPage({
        items: [VALID_RECEIPT_FIXTURE],
        total: 1,
        page: 1,
        page_size: 10,
      });
      assert.equal(paged.total, 1);
      assert.equal(paged.items.length, 1);
    });

    test('rejects ReceiptRead with invalid status or negative total', () => {
      assert.throws(
        () => validateReceiptRead({ ...VALID_RECEIPT_FIXTURE, status: 'UNKNOWN' }),
        /Invalid receipt status/
      );
      assert.throws(
        () => validateReceiptRead({ ...VALID_RECEIPT_FIXTURE, total_vnd: -500 }),
        /Invalid total_vnd/
      );
    });
  });

  // ==========================================================================
  // 2. F02: Business Rules PUR-01 & PUR-02: Merging & Duplicate Validation
  // ==========================================================================
  describe('F02: Business Rules PUR-01 & PUR-02: Merging & Duplicate Validation', () => {
    test('PUR-01: auto-merges duplicate product lines with same unit_cost_vnd by summing quantity', () => {
      const rawLines = [
        { product_id: 12, quantity: 3, unit_cost_vnd: 40000 },
        { product_id: 12, quantity: 2, unit_cost_vnd: 40000 },
      ];
      const merged = normalizeAndValidateReceiptLines(rawLines);
      assert.equal(merged.length, 1);
      assert.equal(merged[0].product_id, 12);
      assert.equal(merged[0].quantity, 5);
      assert.equal(merged[0].unit_cost_vnd, 40000);
    });

    test('PUR-02: throws client validation error when duplicate product lines have different unit_cost_vnd', () => {
      const rawLines = [
        { product_id: 12, quantity: 3, unit_cost_vnd: 40000 },
        { product_id: 12, quantity: 2, unit_cost_vnd: 45000 },
      ];
      assert.throws(
        () => normalizeAndValidateReceiptLines(rawLines),
        /xuất hiện nhiều dòng với đơn giá nhập khác nhau/
      );
    });

    test('rejects empty receipt items array', () => {
      assert.throws(
        () => normalizeAndValidateReceiptLines([]),
        /Danh sách sản phẩm nhập không được để trống/
      );
    });
  });

  // ==========================================================================
  // 3. F03: receiptsApi Query Parameters & Strict CF-03 Contract
  // ==========================================================================
  describe('F03: receiptsApi Query Parameters & Strict CF-03 Contract', () => {
    test('receiptsApi.list sends server-side pagination and filters without client filtering', async () => {
      let capturedUrl = null;
      let capturedConfig = null;

      axiosClient.get = async (url, config) => {
        capturedUrl = url;
        capturedConfig = config;
        return {
          data: {
            items: [VALID_RECEIPT_FIXTURE],
            total: 1,
            page: 1,
            page_size: 10,
          },
        };
      };

      const result = await receiptsApi.list({
        page: 2,
        pageSize: 15,
        status: 'DRAFT',
        supplierId: 4,
        fromDate: '2026-11-01',
        toDate: '2026-11-15',
      });

      assert.equal(capturedUrl, '/purchase-receipts');
      assert.equal(capturedConfig.params.page, 2);
      assert.equal(capturedConfig.params.page_size, 15);
      assert.equal(capturedConfig.params.status, 'DRAFT');
      assert.equal(capturedConfig.params.supplier_id, 4);
      assert.equal(capturedConfig.params.from_date, '2026-11-01');
      assert.equal(capturedConfig.params.to_date, '2026-11-15');
      assert.equal(result.items.length, 1);
    });

    test('receiptsApi.get fetches single receipt by ID', async () => {
      axiosClient.get = async (url) => {
        assert.equal(url, '/purchase-receipts/9');
        return { data: VALID_RECEIPT_FIXTURE };
      };

      const receipt = await receiptsApi.get(9);
      assert.equal(receipt.id, 9);
      assert.equal(receipt.status, 'DRAFT');
    });

    test('receiptsApi.createDraft posts supplier_id and items without ID', async () => {
      let capturedBody = null;
      axiosClient.post = async (url, body) => {
        assert.equal(url, '/purchase-receipts');
        capturedBody = body;
        return { data: VALID_RECEIPT_FIXTURE };
      };

      await receiptsApi.createDraft({
        supplier_id: 4,
        items: [{ product_id: 12, quantity: 2, unit_cost_vnd: 47000 }],
      });

      assert.equal(capturedBody.supplier_id, 4);
      assert.equal(capturedBody.items.length, 1);
      assert.equal(capturedBody.items[0].product_id, 12);
      assert.equal(capturedBody.id, undefined); // ID is never sent from client in create mode
    });

    test('receiptsApi.updateDraft sends PATCH /purchase-receipts/:id with expected_draft_version', async () => {
      let capturedUrl = null;
      let capturedBody = null;

      axiosClient.patch = async (url, body) => {
        capturedUrl = url;
        capturedBody = body;
        return { data: { ...VALID_RECEIPT_FIXTURE, draft_version: 2 } };
      };

      const res = await receiptsApi.updateDraft(9, {
        expected_draft_version: 1,
        supplier_id: 4,
        items: [{ product_id: 12, quantity: 5, unit_cost_vnd: 47000 }],
      });

      assert.equal(capturedUrl, '/purchase-receipts/9');
      assert.equal(capturedBody.expected_draft_version, 1);
      assert.equal(capturedBody.items[0].quantity, 5);
      assert.equal(res.draft_version, 2);
    });

    test('receiptsApi.confirm sends POST /purchase-receipts/:id/confirm with Idempotency-Key header', async () => {
      let capturedUrl = null;
      let capturedBody = null;
      let capturedConfig = null;

      axiosClient.post = async (url, body, config) => {
        capturedUrl = url;
        capturedBody = body;
        capturedConfig = config;
        return {
          data: {
            ...VALID_RECEIPT_FIXTURE,
            status: 'CONFIRMED',
            draft_version: 2,
            closed_by: 1,
            closed_at: '2026-11-10T02:00:00.000Z',
          },
        };
      };

      const idempotencyKey = 'test-idempotency-key-12345';
      const confirmed = await receiptsApi.confirm(9, {
        expected_draft_version: 1,
        idempotencyKey,
      });

      assert.equal(capturedUrl, '/purchase-receipts/9/confirm');
      assert.equal(capturedBody.expected_draft_version, 1);
      assert.equal(capturedConfig.headers['Idempotency-Key'], idempotencyKey);
      assert.equal(confirmed.status, 'CONFIRMED');
    });

    test('receiptsApi.cancel sends POST /purchase-receipts/:id/cancel with expected_draft_version', async () => {
      let capturedUrl = null;
      let capturedBody = null;

      axiosClient.post = async (url, body) => {
        capturedUrl = url;
        capturedBody = body;
        return {
          data: {
            ...VALID_RECEIPT_FIXTURE,
            status: 'CANCELLED',
            draft_version: 1,
            closed_by: 1,
            closed_at: '2026-11-10T02:00:00.000Z',
          },
        };
      };

      const cancelled = await receiptsApi.cancel(9, {
        expected_draft_version: 1,
      });

      assert.equal(capturedUrl, '/purchase-receipts/9/cancel');
      assert.equal(capturedBody.expected_draft_version, 1);
      assert.equal(cancelled.status, 'CANCELLED');
    });
  });

  // ==========================================================================
  // 4. F04: Error Handling & 409 Conflict Invariants
  // ==========================================================================
  describe('F04: Error Handling & 409 Conflict Invariants', () => {
    test('handles 409 RECEIPT_VERSION_CONFLICT error transparently', async () => {
      axiosClient.patch = async () => {
        const err = new Error('Request failed with status code 409');
        err.response = {
          status: 409,
          data: {
            code: 'RECEIPT_VERSION_CONFLICT',
            message: 'Phiếu nhập đã được thay đổi. Vui lòng tải lại.',
            details: { current_draft_version: 3 },
          },
        };
        throw err;
      };

      try {
        await receiptsApi.updateDraft(9, { expected_draft_version: 1 });
        assert.fail('Should have thrown 409 error');
      } catch (err) {
        assert.equal(err.response.status, 409);
        assert.equal(err.response.data.code, 'RECEIPT_VERSION_CONFLICT');
      }
    });
  });

  // ==========================================================================
  // 5. F05: Security, RBAC & File Invariants
  // ==========================================================================
  describe('F05: Security, RBAC & File Invariants', () => {
    test('PurchaseList.jsx strictly guards access with ADMIN role checking', () => {
      const filePath = path.resolve(__dirname, '../pages/Purchases/PurchaseList.jsx');
      const content = fs.readFileSync(filePath, 'utf-8');
      assert.match(content, /useAuth/);
      assert.match(content, /user\?.role === 'ADMIN'/);
      assert.match(content, /Chức năng dành riêng cho Quản trị viên \(ADMIN\)/);
    });

    test('PurchaseList.jsx does not store tokens in localStorage', () => {
      const filePath = path.resolve(__dirname, '../pages/Purchases/PurchaseList.jsx');
      const content = fs.readFileSync(filePath, 'utf-8');
      assert.equal(content.includes('localStorage.setItem'), false);
    });

    test('receiptsApi.js is fail-closed and contains zero silent mock fallbacks', () => {
      const filePath = path.resolve(__dirname, '../api/receiptsApi.js');
      const content = fs.readFileSync(filePath, 'utf-8');
      assert.equal(content.includes('localStorage'), false);
      assert.equal(content.includes('mockReceipts'), false);
    });
  });
});
