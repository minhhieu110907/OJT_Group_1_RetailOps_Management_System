import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient from '../api/axiosClient.js';
import {
  PRODUCT_IMAGE_URL_MAX_LENGTH,
  parseAndValidateProductImageUrl,
  productsApi,
  validateProductRead,
} from '../api/productsApi.js';

const BASE_PRODUCT = {
  id: 10,
  category_id: 2,
  sku: 'SP0010',
  name: 'Nước xả vải Comfort',
  status: 'ACTIVE',
  sale_price_vnd: 45000,
  quantity: 12,
  stock_version: 3,
  created_at: '2026-11-16T08:00:00Z',
  updated_at: '2026-11-16T08:00:00Z',
};

describe('Product Image URL — Validation, API Contract & Fail-Closed Suite', () => {
  let originalPost;
  let originalPatch;

  beforeEach(() => {
    originalPost = axiosClient.post;
    originalPatch = axiosClient.patch;
  });

  test('parseAndValidateProductImageUrl accepts null/empty as null and valid HTTPS URLs', () => {
    assert.deepEqual(parseAndValidateProductImageUrl(undefined), {
      isValid: true,
      value: null,
      error: '',
    });
    assert.deepEqual(parseAndValidateProductImageUrl(null), {
      isValid: true,
      value: null,
      error: '',
    });
    assert.deepEqual(parseAndValidateProductImageUrl('   '), {
      isValid: true,
      value: null,
      error: '',
    });

    const valid = parseAndValidateProductImageUrl(
      '  https://cdn.example.com/products/sp0010.png?v=1  '
    );
    assert.equal(valid.isValid, true);
    assert.equal(valid.value, 'https://cdn.example.com/products/sp0010.png?v=1');
  });

  test('parseAndValidateProductImageUrl rejects HTTP, javascript, data, relative paths, whitespace, and >500 chars', () => {
    for (const bad of [
      'http://cdn.example.com/a.png',
      'javascript:alert(1)',
      'data:image/png;base64,AAAA',
      '/images/local.png',
      'https://cdn.example.com/my image.png',
      `https://cdn.example.com/${'a'.repeat(PRODUCT_IMAGE_URL_MAX_LENGTH)}`,
    ]) {
      const res = parseAndValidateProductImageUrl(bad);
      assert.equal(res.isValid, false, `Expected invalid for: ${bad}`);
      assert.ok(res.error.length > 0);
    }
  });

  test('createProduct sends valid trimmed HTTPS image_url, omits when empty, and rejects invalid URL', async () => {
    const capturedPayloads = [];
    axiosClient.post = async (_url, payload) => {
      capturedPayloads.push(payload);
      return {
        data: {
          ...BASE_PRODUCT,
          image_url: payload.image_url ?? null,
        },
      };
    };

    try {
      const createdWithImg = await productsApi.createProduct({
        isMockMode: false,
        data: {
          sku: 'SP0010',
          name: 'Nước xả vải Comfort',
          category_id: 2,
          sale_price_vnd: 45000,
          image_url: '  https://cdn.example.com/comfort.png  ',
        },
      });
      assert.equal(
        capturedPayloads[0].image_url,
        'https://cdn.example.com/comfort.png'
      );
      assert.equal(createdWithImg.image_url, 'https://cdn.example.com/comfort.png');

      const createdNoImg = await productsApi.createProduct({
        isMockMode: false,
        data: {
          sku: 'SP0011',
          name: 'Bột giặt OMO',
          category_id: 2,
          sale_price_vnd: 55000,
          image_url: '   ',
        },
      });
      assert.equal('image_url' in capturedPayloads[1], false);
      assert.equal(createdNoImg.image_url, null);

      await assert.rejects(
        () =>
          productsApi.createProduct({
            isMockMode: false,
            data: {
              sku: 'SP0012',
              name: 'Test',
              category_id: 2,
              sale_price_vnd: 10000,
              image_url: 'http://insecure.example.com/a.png',
            },
          }),
        (err) => err.isClientValidation === true
      );
    } finally {
      axiosClient.post = originalPost;
    }
  });

  test('updateProduct distinguishes undefined (omitted) vs null (clear) vs HTTPS URL and blocks forbidden fields', async () => {
    const capturedPatches = [];
    axiosClient.patch = async (_url, payload) => {
      capturedPatches.push(payload);
      return {
        data: {
          ...BASE_PRODUCT,
          image_url: payload.image_url === undefined ? BASE_PRODUCT.image_url ?? null : payload.image_url,
        },
      };
    };

    try {
      // 1. Update URL
      await productsApi.updateProduct({
        isMockMode: false,
        id: 10,
        data: {
          name: 'Nước xả vải Comfort',
          category_id: 2,
          sale_price_vnd: 45000,
          image_url: 'https://cdn.example.com/new.png',
          sku: 'SHOULD_STRIP',
          status: 'INACTIVE',
          quantity: 999,
          stock_version: 99,
        },
      });
      assert.equal(capturedPatches[0].image_url, 'https://cdn.example.com/new.png');
      assert.equal('sku' in capturedPatches[0], false);
      assert.equal('status' in capturedPatches[0], false);
      assert.equal('quantity' in capturedPatches[0], false);
      assert.equal('stock_version' in capturedPatches[0], false);

      // 2. Clear URL -> sends explicit null
      await productsApi.updateProduct({
        isMockMode: false,
        id: 10,
        data: {
          image_url: null,
        },
      });
      assert.equal('image_url' in capturedPatches[1], true);
      assert.equal(capturedPatches[1].image_url, null);

      // 3. Unchanged URL -> omitted from PATCH
      await productsApi.updateProduct({
        isMockMode: false,
        id: 10,
        data: {
          name: 'Tên mới',
        },
      });
      assert.equal('image_url' in capturedPatches[2], false);
    } finally {
      axiosClient.patch = originalPatch;
    }
  });

  test('validateProductRead preserves valid/null image_url and fails closed on invalid image_url', () => {
    const withImg = validateProductRead({
      ...BASE_PRODUCT,
      image_url: 'https://cdn.example.com/item.webp',
    });
    assert.equal(withImg.image_url, 'https://cdn.example.com/item.webp');

    const withNull = validateProductRead({ ...BASE_PRODUCT, image_url: null });
    assert.equal(withNull.image_url, null);

    const legacyOmitted = validateProductRead({ ...BASE_PRODUCT });
    assert.equal(legacyOmitted.image_url, null);

    assert.throws(() =>
      validateProductRead({
        ...BASE_PRODUCT,
        image_url: 'http://not-https.example.com/a.png',
      })
    );
  });

  test('productsApi fails closed when isMockMode=true on createProduct and updateProduct', async () => {
    await assert.rejects(
      () => productsApi.createProduct({ isMockMode: true, data: {} }),
      (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
    );
    await assert.rejects(
      () => productsApi.updateProduct({ isMockMode: true, id: 1, data: {} }),
      (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
    );
  });
});

describe('ProductList & PosPage — UI Integration, Dirty-State, Preview & POS Lifecycle Checks', () => {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const productListPath = path.resolve(__dirname, '../pages/Products/ProductList.jsx');
  const posPagePath = path.resolve(__dirname, '../pages/Pos/PosPage.jsx');

  test('ProductList.jsx integrates image_url input, live preview, dirty-state check, and RBAC guard', () => {
    const src = fs.readFileSync(productListPath, 'utf8');
    assert.match(src, /LINK ẢNH SẢN PHẨM \(TÙY CHỌN\)/);
    assert.match(src, /placeholder="https:\/\/\.\.\."/);
    assert.match(src, /maxLength=\{PRODUCT_IMAGE_URL_MAX_LENGTH\}/);
    assert.match(src, /parseAndValidateProductImageUrl/);
    assert.match(src, /isImageUrlSame/);
    assert.match(src, /if \(!isImageUrlSame\) \{\s*updatePayload\.image_url = normalizedImageUrl;/);
    assert.match(src, /setImagePreviewState/);
    assert.match(src, /const isStaff = user\?\.role !== 'ADMIN';/);
  });

  test('PosPage.jsx resets image error state when product.image_url changes and falls back safely', () => {
    const src = fs.readFileSync(posPagePath, 'utf8');
    assert.match(src, /const \[failedImageUrl, setFailedImageUrl\] = useState\(''\);/);
    assert.match(src, /const hasImageError = isValidHttpsImage && failedImageUrl === imageUrl;/);
    assert.match(src, /key=\{imageUrl\}/);
    assert.match(src, /onError=\{\(\) => setFailedImageUrl\(imageUrl\)\}/);
    assert.match(src, /styles\.imagePlaceholder/);
  });
});
