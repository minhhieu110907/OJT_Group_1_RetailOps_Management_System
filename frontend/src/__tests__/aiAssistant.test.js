import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient, { invalidateSession, transitionAuthMode } from '../api/axiosClient.js';
import {
  AI_QUERY_MAX_LENGTH,
  aiApi,
  classifyAiError,
  isAiRequestCanceled,
  validateAiAskResponse,
  validateAiEvidence,
  validateAiMessageInput,
} from '../api/aiApi.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TEST_DEV_ENV = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };

describe('aiApi — T04AB25 OpenAPI contract & AI-04 fail-closed behavior', () => {
  beforeEach(() => {
    transitionAuthMode(false, TEST_DEV_ENV);
    invalidateSession();
  });

  test('fails closed when isMockMode=true without calling axiosClient.post', async () => {
    let called = false;
    const origPost = axiosClient.post;
    axiosClient.post = async () => {
      called = true;
      return { data: {} };
    };

    try {
      await assert.rejects(
        () => aiApi.ask({ isMockMode: true, message: 'Doanh thu hôm nay?' }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      assert.equal(called, false);
    } finally {
      axiosClient.post = origPost;
    }
  });

  test('validates AIAskRequest length (1..4000) and sends exact { message } payload', async () => {
    assert.equal(validateAiMessageInput('   ').isValid, false);
    assert.equal(validateAiMessageInput('a'.repeat(AI_QUERY_MAX_LENGTH + 1)).isValid, false);
    assert.equal(validateAiMessageInput('  Top sản phẩm bán chạy  ').value, 'Top sản phẩm bán chạy');

    let capturedUrl = null;
    let capturedBody = null;
    const origPost = axiosClient.post;
    axiosClient.post = async (url, body) => {
      capturedUrl = url;
      capturedBody = body;
      return {
        data: {
          answer: 'Top sản phẩm bán chạy gồm Coca Cola.',
          evidence: [
            {
              source: 'analytics.top_products',
              period: '30 ngày qua',
              summary: 'Coca Cola bán 120 lon',
            },
          ],
          insufficient_data: false,
        },
      };
    };

    try {
      const result = await aiApi.ask({ message: '  Top sản phẩm?  ' });
      assert.equal(capturedUrl, '/ai/query');
      assert.deepEqual(capturedBody, { message: 'Top sản phẩm?' });
      assert.equal(result.insufficient_data, false);
      assert.equal(result.evidence.length, 1);
    } finally {
      axiosClient.post = origPost;
    }
  });

  test('validates AIAskResponse and AIEvidence strictly (fail-closed, additionalProperties: false)', () => {
    assert.throws(() => validateAiAskResponse(null));
    assert.throws(() =>
      validateAiAskResponse({ answer: '', evidence: [], insufficient_data: false })
    );
    assert.throws(() =>
      validateAiAskResponse({ answer: 'OK', evidence: 'bad', insufficient_data: false })
    );
    assert.throws(() =>
      validateAiAskResponse({ answer: 'OK', evidence: [], insufficient_data: 'no' })
    );
    // Missing required fields
    assert.throws(() => validateAiAskResponse({ evidence: [], insufficient_data: false }));
    assert.throws(() => validateAiAskResponse({ answer: 'OK', insufficient_data: false }));
    assert.throws(() => validateAiAskResponse({ answer: 'OK', evidence: [] }));

    // Extra field on AIAskResponse (additionalProperties: false)
    assert.throws(
      () =>
        validateAiAskResponse({
          answer: 'OK',
          evidence: [],
          insufficient_data: false,
          extra_debug_sql: 'SELECT * FROM orders',
        }),
      /unexpected field/
    );

    // Extra field on AIEvidence (additionalProperties: false)
    assert.throws(
      () =>
        validateAiEvidence({
          source: 'inventory',
          period: null,
          summary: 'Còn 3 sản phẩm',
          raw_row_id: 99,
        }),
      /unexpected field/
    );

    // Missing required period field on AIEvidence
    assert.throws(
      () =>
        validateAiEvidence({
          source: 'inventory',
          summary: 'Còn 3 sản phẩm',
        }),
      /missing required period/
    );

    assert.throws(() =>
      validateAiEvidence({ source: 'sales', period: 123, summary: 'test' })
    );

    const validNullPeriod = validateAiEvidence({
      source: 'inventory',
      period: null,
      summary: 'Còn 3 sản phẩm sắp hết',
    });
    assert.equal(validNullPeriod.period, null);
  });

  test('classifyAiError never exposes untrusted backend details (500 SQL/stack, 400/422) and handles cancel', () => {
    const c500 = classifyAiError({
      response: {
        status: 500,
        data: {
          detail: 'Traceback: SELECT * FROM users WHERE sk-secret-key; mysql://internal-db:3306',
          message: 'SQL syntax error near SELECT',
        },
      },
    });
    assert.equal(c500.kind, 'error');
    assert.equal(c500.retryable, true);
    assert.doesNotMatch(c500.message, /SELECT|Traceback|sk-secret|internal-db|SQL/i);

    const c422 = classifyAiError({
      response: {
        status: 422,
        data: { detail: 'Internal Pydantic Traceback at app/modules/ai/schemas.py' },
      },
    });
    assert.equal(c422.kind, 'validation');
    assert.equal(c422.retryable, false);
    assert.doesNotMatch(c422.message, /Pydantic|Traceback|schemas\.py/i);

    const c400 = classifyAiError({
      response: { status: 400, data: { message: 'raw internal provider error' } },
    });
    assert.equal(c400.kind, 'validation');
    assert.doesNotMatch(c400.message, /raw internal provider/i);

    const c502 = classifyAiError({ response: { status: 502 } });
    assert.equal(c502.kind, 'unavailable');

    const cNetwork = classifyAiError(new Error('Network Error'));
    assert.equal(cNetwork.kind, 'unavailable');

    assert.equal(isAiRequestCanceled({ name: 'CanceledError' }), true);
    assert.equal(isAiRequestCanceled({ name: 'AbortError' }), true);
    assert.equal(isAiRequestCanceled({ code: 'ERR_CANCELED' }), true);
    assert.equal(isAiRequestCanceled({ response: { status: 500 } }), false);
  });

  test('classifyAiError maps 401/403, 429 quota, timeout, 503 unavailable, and 422 safely', () => {
    const c401 = classifyAiError({ response: { status: 401 } });
    assert.equal(c401.kind, 'denied');
    assert.equal(c401.actionType, 'dismiss');
    assert.equal(c401.retryable, false);

    const c403 = classifyAiError({ response: { status: 403 } });
    assert.equal(c403.kind, 'denied');
    assert.equal(c403.actionType, 'dismiss');
    assert.equal(c403.retryable, false);

    const c429 = classifyAiError({ response: { status: 429, data: { detail: 'Rate limit' } } });
    assert.equal(c429.kind, 'quota');
    assert.equal(c429.actionType, 'dismiss');
    assert.equal(c429.retryable, false);
    assert.doesNotMatch(c429.message, /HTTP 429/);

    const cTimeout = classifyAiError({ code: 'ECONNABORTED' });
    assert.equal(cTimeout.kind, 'timeout');
    assert.equal(cTimeout.actionType, 'retry');
    assert.equal(cTimeout.retryable, true);

    const c504 = classifyAiError({ response: { status: 504 } });
    assert.equal(c504.kind, 'timeout');
    assert.equal(c504.actionType, 'retry');
    assert.equal(c504.retryable, true);

    const c503 = classifyAiError({ response: { status: 503 } });
    assert.equal(c503.kind, 'unavailable');
    assert.equal(c503.actionType, 'retry');
    assert.equal(c503.retryable, true);
  });

  test('App.jsx wires /ai-assistant to <AiAssistant /> under ADMIN ProtectedRoute', () => {
    const appPath = path.resolve(__dirname, '../App.jsx');
    const appSource = fs.readFileSync(appPath, 'utf8');
    assert.match(appSource, /import AiAssistant from '\.\/pages\/AiAssistant\/AiAssistant'/);
    assert.match(appSource, /<Route path="\/ai-assistant" element=\{<AiAssistant \/>\} \/>/);
    assert.doesNotMatch(appSource, /PlaceholderPage title="Trợ lý AI \(RetailOps AI\)"/);
  });
});
