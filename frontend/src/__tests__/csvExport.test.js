import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  downloadCsvReport,
  extractFilenameFromHeader,
  parseBlobErrorMessage,
  triggerBlobDownload,
} from '../utils/csvDownload.js';
import { ordersApi } from '../api/ordersApi.js';
import { analyticsApi } from '../api/analyticsApi.js';
import { inventoryApi } from '../api/inventoryApi.js';
import axiosClient from '../api/axiosClient.js';

describe('T3C9F4A — CSV Export Utility & Integration Suite', () => {
  describe('extractFilenameFromHeader', () => {
    it('extracts filename from quoted standard Content-Disposition', () => {
      const header = 'attachment; filename="orders_export_20261119.csv"';
      assert.strictEqual(
        extractFilenameFromHeader(header, 'default.csv'),
        'orders_export_20261119.csv'
      );
    });

    it('extracts filename from unquoted Content-Disposition', () => {
      const header = 'attachment; filename=daily_sales_20261119.csv';
      assert.strictEqual(
        extractFilenameFromHeader(header, 'default.csv'),
        'daily_sales_20261119.csv'
      );
    });

    it('extracts RFC 5987 UTF-8 encoded filename', () => {
      const header = "attachment; filename*=UTF-8''orders%20report%20vn.csv";
      assert.strictEqual(
        extractFilenameFromHeader(header, 'default.csv'),
        'orders report vn.csv'
      );
    });

    it('falls back to default filename when header is missing or invalid', () => {
      assert.strictEqual(extractFilenameFromHeader(null, 'fallback.csv'), 'fallback.csv');
      assert.strictEqual(extractFilenameFromHeader('', 'fallback.csv'), 'fallback.csv');
      assert.strictEqual(
        extractFilenameFromHeader('attachment; other=val', 'fallback.csv'),
        'fallback.csv'
      );
    });
  });

  describe('parseBlobErrorMessage', () => {
    it('decodes JSON error message from Blob', async () => {
      const errorJson = JSON.stringify({
        code: 'VALIDATION_ERROR',
        message: 'Số lượng bản ghi (5001) vượt quá giới hạn xuất tối đa 5000.',
      });
      const blob = new Blob([errorJson], { type: 'application/json' });
      const error = { response: { data: blob, status: 422 } };

      const msg = await parseBlobErrorMessage(error);
      assert.strictEqual(
        msg,
        'Số lượng bản ghi (5001) vượt quá giới hạn xuất tối đa 5000.'
      );
    });

    it('decodes detail message from Blob when message is not present', async () => {
      const errorJson = JSON.stringify({
        detail: 'Định dạng from_date không hợp lệ.',
      });
      const blob = new Blob([errorJson], { type: 'application/json' });
      const error = { response: { data: blob, status: 422 } };

      const msg = await parseBlobErrorMessage(error);
      assert.strictEqual(msg, 'Định dạng from_date không hợp lệ.');
    });

    it('falls back gracefully when response data is not a Blob', async () => {
      const error = {
        response: { data: { message: 'Lỗi máy chủ' }, status: 500 },
      };
      const msg = await parseBlobErrorMessage(error);
      assert.strictEqual(msg, 'Lỗi máy chủ');
    });
  });

  describe('triggerBlobDownload & downloadCsvReport', () => {
    it('creates object URL and triggers download on DOM anchor', async () => {
      let createdUrl = null;
      let revokedUrl = null;
      let clicked = false;
      let downloadAttr = null;

      const originalWindow = globalThis.window;
      const originalDocument = globalThis.document;

      globalThis.window = {
        URL: {
          createObjectURL: (blob) => {
            createdUrl = 'blob:http://localhost/test-uuid';
            return createdUrl;
          },
          revokeObjectURL: (url) => {
            revokedUrl = url;
          },
        },
      };

      globalThis.document = {
        body: {
          appendChild: () => {},
        },
        createElement: (tag) => {
          if (tag === 'a') {
            return {
              style: {},
              click: () => {
                clicked = true;
              },
              remove: () => {},
              set download(val) {
                downloadAttr = val;
              },
              set href(val) {},
            };
          }
          return {};
        },
      };

      try {
        const testBlob = new Blob(['sample,data\r\n'], { type: 'text/csv' });
        const mockResponse = {
          data: testBlob,
          headers: {
            'content-disposition': 'attachment; filename="test_export.csv"',
          },
        };

        await downloadCsvReport(async () => mockResponse, 'default.csv');

        assert.strictEqual(clicked, true);
        assert.strictEqual(downloadAttr, 'test_export.csv');
        assert.strictEqual(revokedUrl, 'blob:http://localhost/test-uuid');
      } finally {
        globalThis.window = originalWindow;
        globalThis.document = originalDocument;
      }
    });

    it('rejects with decoded error message on API failure', async () => {
      const errorJson = JSON.stringify({
        message: 'Chỉ quản trị viên mới có quyền thực hiện thao tác.',
      });
      const error = {
        response: {
          data: new Blob([errorJson], { type: 'application/json' }),
          status: 403,
        },
      };

      await assert.rejects(
        async () => {
          await downloadCsvReport(async () => {
            throw error;
          });
        },
        (err) => {
          assert.strictEqual(
            err.message,
            'Chỉ quản trị viên mới có quyền thực hiện thao tác.'
          );
          return true;
        }
      );
    });
  });

  describe('API Export Wrappers', () => {
    it('ordersApi.exportOrdersCsv calls /orders/export/csv with responseType: blob', async () => {
      let requestedUrl = null;
      let requestedConfig = null;

      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        requestedUrl = url;
        requestedConfig = config;
        return { data: new Blob(['']), headers: {} };
      };

      try {
        await ordersApi.exportOrdersCsv({
          status: 'COMPLETED',
          fromDate: '2026-11-01',
          toDate: '2026-11-19',
          search: '123',
        });

        assert.strictEqual(requestedUrl, '/orders/export/csv');
        assert.strictEqual(requestedConfig.responseType, 'blob');
        assert.deepStrictEqual(requestedConfig.params, {
          status: 'COMPLETED',
          from_date: '2026-11-01',
          to_date: '2026-11-19',
          search: '123',
        });
      } finally {
        axiosClient.get = originalGet;
      }
    });

    it('analyticsApi.exportDailySalesCsv calls /analytics/sales/daily/export/csv with responseType: blob', async () => {
      let requestedUrl = null;
      let requestedConfig = null;

      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        requestedUrl = url;
        requestedConfig = config;
        return { data: new Blob(['']), headers: {} };
      };

      try {
        await analyticsApi.exportDailySalesCsv({
          from: '2026-10-01',
          to: '2026-10-31',
        });

        assert.strictEqual(requestedUrl, '/analytics/sales/daily/export/csv');
        assert.strictEqual(requestedConfig.responseType, 'blob');
        assert.deepStrictEqual(requestedConfig.params, {
          from: '2026-10-01',
          to: '2026-10-31',
        });
      } finally {
        axiosClient.get = originalGet;
      }
    });

    it('inventoryApi.exportInventoryCsv calls /inventory/export/csv with responseType: blob', async () => {
      let requestedUrl = null;
      let requestedConfig = null;

      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        requestedUrl = url;
        requestedConfig = config;
        return { data: new Blob(['']), headers: {} };
      };

      try {
        await inventoryApi.exportInventoryCsv({
          categoryId: 5,
          status: 'ACTIVE',
          inStock: true,
          lowStockOnly: true,
        });

        assert.strictEqual(requestedUrl, '/inventory/export/csv');
        assert.strictEqual(requestedConfig.responseType, 'blob');
        assert.deepStrictEqual(requestedConfig.params, {
          category_id: 5,
          status: 'ACTIVE',
          in_stock: true,
          low_stock_only: true,
        });
      } finally {
        axiosClient.get = originalGet;
      }
    });
  });
});

