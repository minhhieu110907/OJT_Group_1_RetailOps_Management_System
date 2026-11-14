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
  compareReceiptsByCreatedAtDesc,
  parseReceiptSearchInput,
  doesReceiptMatchActiveFilters,
  createConfirmIntentTracker,
  createDetailRequestGuard,
  generateSecureIdempotencyKey,
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

function makeReceiptFixture(overrides = {}) {
  return {
    ...VALID_RECEIPT_FIXTURE,
    ...overrides,
    items: overrides.items || [VALID_RECEIPT_ITEM],
  };
}

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
      assert.equal(capturedBody.id, undefined);
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
  // 5. P1 Corrective: Purchase History Pagination (Interleaved, Tie-break, Fail-Closed)
  // ==========================================================================
  describe('P1 Corrective: Purchase History Pagination (ALL_HISTORY)', () => {
    test('paginates interleaved CONFIRMED and CANCELLED receipts sorted by (created_at DESC, id DESC) across pages 1 -> 2 -> 3 without duplicates or 2x pageSize overflow', async () => {
      // 4 CONFIRMED and 4 CANCELLED = 8 total receipts; pageSize = 3 => 3 pages (3, 3, 2)
      // Includes a timestamp tie on 2026-11-10T05:00:00Z between id=102 (CANCELLED) and id=105 (CONFIRMED)
      const confirmedAll = [
        makeReceiptFixture({ id: 108, status: 'CONFIRMED', created_at: '2026-11-10T08:00:00Z', closed_at: '2026-11-10T08:05:00Z', closed_by: 1 }),
        makeReceiptFixture({ id: 105, status: 'CONFIRMED', created_at: '2026-11-10T05:00:00Z', closed_at: '2026-11-10T05:05:00Z', closed_by: 1 }),
        makeReceiptFixture({ id: 103, status: 'CONFIRMED', created_at: '2026-11-10T03:00:00Z', closed_at: '2026-11-10T03:05:00Z', closed_by: 1 }),
        makeReceiptFixture({ id: 101, status: 'CONFIRMED', created_at: '2026-11-10T01:00:00Z', closed_at: '2026-11-10T01:05:00Z', closed_by: 1 }),
      ];
      const cancelledAll = [
        makeReceiptFixture({ id: 107, status: 'CANCELLED', created_at: '2026-11-10T07:00:00Z', closed_at: '2026-11-10T07:05:00Z', closed_by: 1 }),
        makeReceiptFixture({ id: 106, status: 'CANCELLED', created_at: '2026-11-10T06:00:00Z', closed_at: '2026-11-10T06:05:00Z', closed_by: 1 }),
        makeReceiptFixture({ id: 102, status: 'CANCELLED', created_at: '2026-11-10T05:00:00Z', closed_at: '2026-11-10T05:05:00Z', closed_by: 1 }),
        makeReceiptFixture({ id: 104, status: 'CANCELLED', created_at: '2026-11-10T02:00:00Z', closed_at: '2026-11-10T02:05:00Z', closed_by: 1 }),
      ];

      axiosClient.get = async (_url, { params }) => {
        const source = params.status === 'CONFIRMED' ? confirmedAll : cancelledAll;
        const start = (params.page - 1) * params.page_size;
        const sliced = source.slice(start, start + params.page_size);
        return {
          data: {
            items: sliced,
            total: source.length,
            page: params.page,
            page_size: params.page_size,
          },
        };
      };

      const page1 = await receiptsApi.listHistory({ page: 1, pageSize: 3 });
      const page2 = await receiptsApi.listHistory({ page: 2, pageSize: 3 });
      const page3 = await receiptsApi.listHistory({ page: 3, pageSize: 3 });

      assert.equal(page1.total, 8);
      assert.equal(page1.total_pages, 3);
      assert.equal(page1.items.length, 3); // Never 6 items!
      assert.equal(page2.items.length, 3);
      assert.equal(page3.items.length, 2);

      // Expected global order by (created_at DESC, id DESC):
      // 108 (08:00), 107 (07:00), 106 (06:00) | 105 (05:00, id=105), 102 (05:00, id=102), 103 (03:00) | 104 (02:00), 101 (01:00)
      assert.deepEqual(page1.items.map((r) => r.id), [108, 107, 106]);
      assert.deepEqual(page2.items.map((r) => r.id), [105, 102, 103]);
      assert.deepEqual(page3.items.map((r) => r.id), [104, 101]);

      const allSeenIds = [...page1.items, ...page2.items, ...page3.items].map((r) => r.id);
      assert.equal(new Set(allSeenIds).size, 8);
    });

    test('fails closed when one status request fails (never swallows error into fake total=0)', async () => {
      axiosClient.get = async (_url, { params }) => {
        if (params.status === 'CONFIRMED') {
          return {
            data: {
              items: [makeReceiptFixture({ id: 50, status: 'CONFIRMED', closed_by: 1, closed_at: '2026-11-10T02:00:00Z' })],
              total: 1,
              page: 1,
              page_size: 10,
            },
          };
        }
        const err = new Error('Service Unavailable');
        err.response = { status: 503, data: { code: 'DEPENDENCY_UNAVAILABLE', message: 'DB timeout' } };
        throw err;
      };

      await assert.rejects(
        () => receiptsApi.listHistory({ page: 1, pageSize: 10 }),
        (err) => err.response?.status === 503
      );
    });

    test('compareReceiptsByCreatedAtDesc sorts by created_at DESC then id DESC', () => {
      const a = { id: 10, created_at: '2026-11-10T05:00:00Z' };
      const b = { id: 25, created_at: '2026-11-10T05:00:00Z' };
      const c = { id: 5, created_at: '2026-11-10T06:00:00Z' };
      const sorted = [a, b, c].sort(compareReceiptsByCreatedAtDesc);
      assert.deepEqual(sorted.map((x) => x.id), [5, 25, 10]);
    });

    test('listHistory enforces maxMergedItems window limit and flags is_window_capped when database total exceeds window', async () => {
      axiosClient.get = async (_url, { params }) => {
        return {
          data: {
            items: [makeReceiptFixture({ id: params.page, status: params.status })],
            total: 300, // 300 CONFIRMED + 300 CANCELLED = 600 total > 500 window
            page: params.page,
            page_size: params.page_size,
          },
        };
      };

      // Test with maxMergedItems=20 window for testing
      const result = await receiptsApi.listHistory({ page: 1, pageSize: 10, maxMergedItems: 20 });
      assert.equal(result.total, 600); // authoritative database count
      assert.equal(result.effective_total, 20); // capped effective window
      assert.equal(result.total_pages, 2); // 20 / 10 = 2 pages
      assert.equal(result.is_window_capped, true);

      // Requesting beyond window throws ERR_HISTORY_WINDOW_EXCEEDED
      await assert.rejects(
        () => receiptsApi.listHistory({ page: 3, pageSize: 10, maxMergedItems: 20 }),
        (err) => err.code === 'ERR_HISTORY_WINDOW_EXCEEDED'
      );
    });
  });

  // ==========================================================================
  // 6. P1 Corrective: Receipt Search Scope (Exact ID vs Unsupported Text)
  // ==========================================================================
  describe('P1 Corrective: Receipt Search Scope', () => {
    test('parseReceiptSearchInput distinguishes exact ID (#12, 12) from unsupported free-text query', () => {
      assert.deepEqual(parseReceiptSearchInput(''), { mode: 'NONE', receiptId: null, error: null });
      assert.deepEqual(parseReceiptSearchInput('  #42 '), { mode: 'EXACT_ID', receiptId: 42, error: null });
      assert.deepEqual(parseReceiptSearchInput('105'), { mode: 'EXACT_ID', receiptId: 105, error: null });

      const textSearch = parseReceiptSearchInput('Vinamilk');
      assert.equal(textSearch.mode, 'UNSUPPORTED_QUERY');
      assert.match(textSearch.error, /Mã phiếu chính xác/);
    });

    test('findByExactId retrieves receipt from GET /purchase-receipts/:id and applies active filters', async () => {
      axiosClient.get = async (url) => {
        assert.equal(url, '/purchase-receipts/77');
        return {
          data: makeReceiptFixture({
            id: 77,
            supplier_id: 4,
            status: 'CONFIRMED',
            created_at: '2026-11-10T03:00:00Z',
            closed_at: '2026-11-10T04:00:00Z',
            closed_by: 1,
          }),
        };
      };

      const matched = await receiptsApi.findByExactId(77, {
        topTab: 'HISTORY',
        activeTab: 'ALL_HISTORY',
        supplierId: 4,
      });
      assert.equal(matched.total, 1);
      assert.equal(matched.items[0].id, 77);

      const filteredOut = await receiptsApi.findByExactId(77, {
        topTab: 'RECEIPTS',
        activeTab: 'DRAFT',
      });
      assert.equal(filteredOut.total, 0);
      assert.equal(filteredOut.items.length, 0);
    });

    test('findByExactId returns empty on 404 but rethrows 500/403 fail-closed', async () => {
      axiosClient.get = async () => {
        const err = new Error('Not found');
        err.response = { status: 404, data: { code: 'RESOURCE_NOT_FOUND' } };
        throw err;
      };
      const notFoundRes = await receiptsApi.findByExactId(9999);
      assert.equal(notFoundRes.total, 0);
      assert.equal(notFoundRes.items.length, 0);

      axiosClient.get = async () => {
        const err = new Error('Internal Server Error');
        err.response = { status: 500 };
        throw err;
      };
      await assert.rejects(() => receiptsApi.findByExactId(9999), /Internal Server Error/);
    });

    test('doesReceiptMatchActiveFilters checks Vietnam date boundaries accurately', () => {
      const receipt = makeReceiptFixture({
        id: 15,
        status: 'DRAFT',
        supplier_id: 4,
        created_at: '2026-11-10T18:30:00Z', // 2026-11-11 01:30 in Asia/Ho_Chi_Minh (+07:00)
      });
      assert.equal(
        doesReceiptMatchActiveFilters(receipt, {
          topTab: 'RECEIPTS',
          activeTab: 'DRAFT',
          fromDate: '2026-11-11',
          toDate: '2026-11-11',
        }),
        true
      );
      assert.equal(
        doesReceiptMatchActiveFilters(receipt, {
          topTab: 'RECEIPTS',
          activeTab: 'DRAFT',
          fromDate: '2026-11-10',
          toDate: '2026-11-10',
        }),
        false
      );
    });
  });

  // ==========================================================================
  // 7. P1 Corrective: Confirm Receipt Idempotency Intent
  // ==========================================================================
  describe('P1 Corrective: Confirm Receipt Idempotency Intent', () => {
    test('rapid double-click sends only one logical request while in-flight', async () => {
      const tracker = createConfirmIntentTracker();
      let callCount = 0;
      let resolveConfirm;

      const confirmPromise = new Promise((resolve) => {
        resolveConfirm = resolve;
      });

      const confirmFn = async () => {
        callCount += 1;
        return confirmPromise;
      };

      const firstAttempt = tracker.executeConfirm(9, 1, { confirmFn });
      const secondAttempt = await tracker.executeConfirm(9, 1, { confirmFn });

      assert.equal(secondAttempt.outcome, 'IGNORED_IN_FLIGHT');
      assert.equal(callCount, 1);

      resolveConfirm(makeReceiptFixture({ id: 9, status: 'CONFIRMED', draft_version: 2 }));
      const firstResult = await firstAttempt;
      assert.equal(firstResult.outcome, 'CONFIRMED');
      assert.equal(callCount, 1);
    });

    test('same intent retry after timeout reuses the exact same Idempotency-Key and payload, while new version/receipt gets a new key', async () => {
      const tracker = createConfirmIntentTracker();
      const capturedCalls = [];

      let shouldTimeout = true;
      const confirmFn = async (id, { expected_draft_version, idempotencyKey }) => {
        capturedCalls.push({ id, expected_draft_version, idempotencyKey });
        if (shouldTimeout) {
          const timeoutErr = new Error('Network timeout');
          timeoutErr.code = 'ECONNABORTED';
          throw timeoutErr;
        }
        return makeReceiptFixture({ id, status: 'CONFIRMED', draft_version: expected_draft_version + 1 });
      };

      await assert.rejects(() => tracker.executeConfirm(9, 2, { confirmFn }), /Network timeout/);
      shouldTimeout = false;
      const retryRes = await tracker.executeConfirm(9, 2, { confirmFn });

      assert.equal(retryRes.outcome, 'CONFIRMED');
      assert.equal(capturedCalls.length, 2);
      assert.equal(capturedCalls[0].idempotencyKey, capturedCalls[1].idempotencyKey);
      assert.equal(capturedCalls[0].expected_draft_version, 2);
      assert.equal(capturedCalls[1].expected_draft_version, 2);

      // New version on same receipt or new receipt -> new key
      const newVersionKey = tracker.getOrCreateKey(9, 3);
      assert.notEqual(newVersionKey, capturedCalls[0].idempotencyKey);
      const newReceiptKey = tracker.getOrCreateKey(10, 1);
      assert.notEqual(newReceiptKey, newVersionKey);
    });

    test('409 conflict reconciles authoritative ReceiptRead without re-submitting confirm', async () => {
      const tracker = createConfirmIntentTracker();
      let confirmCount = 0;
      let getCount = 0;

      const confirmFn = async () => {
        confirmCount += 1;
        const err = new Error('Conflict');
        err.response = {
          status: 409,
          data: { code: 'RECEIPT_VERSION_CONFLICT', message: 'Version mismatch' },
        };
        throw err;
      };

      const getFn = async (id) => {
        getCount += 1;
        return makeReceiptFixture({ id, status: 'DRAFT', draft_version: 4 });
      };

      const result = await tracker.executeConfirm(9, 1, { confirmFn, getFn });
      assert.equal(result.outcome, 'CONFLICT_STALE');
      assert.equal(confirmCount, 1);
      assert.equal(getCount, 1);
      assert.equal(result.receipt.draft_version, 4);
      assert.equal(tracker.getCurrentIntent(), null);
    });

    test('reconciles RECONCILED_CONFIRMED when 409 conflict reveals receipt is already CONFIRMED', async () => {
      const tracker = createConfirmIntentTracker();
      let confirmCount = 0;
      let getCount = 0;

      const confirmFn = async () => {
        confirmCount += 1;
        const err = new Error('Conflict');
        err.response = {
          status: 409,
          data: { code: 'INVALID_STATE', message: 'Phiếu đã ở trạng thái CONFIRMED' },
        };
        throw err;
      };

      const getFn = async (id) => {
        getCount += 1;
        return makeReceiptFixture({ id, status: 'CONFIRMED', draft_version: 2, closed_by: 1 });
      };

      const result = await tracker.executeConfirm(9, 1, { confirmFn, getFn });
      assert.equal(result.outcome, 'RECONCILED_CONFIRMED');
      assert.equal(confirmCount, 1);
      assert.equal(getCount, 1);
      assert.equal(result.receipt.status, 'CONFIRMED');
      assert.equal(tracker.getCurrentIntent(), null);
    });

    test('generateSecureIdempotencyKey produces valid RFC4122 UUID matching OpenAPI pattern', () => {
      const key = generateSecureIdempotencyKey();
      assert.match(key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    });
  });

  // ==========================================================================
  // 8. P1 Corrective: Async Race & Stale Receipt Detail Guard
  // ==========================================================================
  describe('P1 Corrective: Async Race & Stale Receipt Detail Guard', () => {
    test('ignores late response or error from Receipt A after switching to Receipt B or closing modal', () => {
      const guard = createDetailRequestGuard();

      const reqA = guard.begin(101);
      assert.equal(guard.isCurrent(reqA, 101), true);

      // User switches to Receipt B (102) before A finishes
      const reqB = guard.begin(102);
      assert.equal(guard.isCurrent(reqA, 101), false);
      assert.equal(guard.isCurrent(reqB, 102), true);

      // User closes modal while B is still loading
      guard.invalidate();
      assert.equal(guard.isCurrent(reqB, 102), false);
      assert.equal(guard.getActiveReceiptId(), null);
    });
  });

  // ==========================================================================
  // 9. F05: Security, RBAC & File Invariants
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

    test('PurchaseList.jsx is fail-closed and free of 404/405 empty fallback or post-pagination client filtering', () => {
      const filePath = path.resolve(__dirname, '../pages/Purchases/PurchaseList.jsx');
      const content = fs.readFileSync(filePath, 'utf-8');
      assert.equal(content.includes('err.response?.status === 404 || err.response?.status === 405'), false);
      assert.equal(content.includes('.catch(() => ({ items: [], total: 0 }))'), false);
      assert.equal(content.includes('activeSuppliers.find('), false);
    });

    test('receiptsApi.js is fail-closed and contains zero silent mock fallbacks', () => {
      const filePath = path.resolve(__dirname, '../api/receiptsApi.js');
      const content = fs.readFileSync(filePath, 'utf-8');
      assert.equal(content.includes('localStorage'), false);
      assert.equal(content.includes('mockReceipts'), false);
    });
  });
});
