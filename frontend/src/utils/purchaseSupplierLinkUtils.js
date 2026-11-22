/**
 * Pure helpers for 2-way Supplier <-> Category <-> Product filtering
 * on Purchase Receipt Create / Edit forms (UX hint only; never restricts backend PUR rules).
 */

/**
 * Filter products for the receipt product dropdown when a supplier is selected
 * and has linked category_ids. Always preserves already-selected product IDs
 * in the current lines so existing selections never disappear.
 */
export function filterProductsBySupplierCategories({
  products = [],
  selectedSupplier = null,
  selectedProductIds = [],
  showAllProducts = false,
}) {
  if (
    showAllProducts ||
    !selectedSupplier ||
    !Array.isArray(selectedSupplier.category_ids) ||
    selectedSupplier.category_ids.length === 0
  ) {
    return products;
  }

  const allowedCategoryIds = new Set(selectedSupplier.category_ids.map(Number));
  const preservedIds = new Set(
    selectedProductIds.map(Number).filter((id) => Number.isInteger(id) && id > 0)
  );

  return products.filter(
    (product) =>
      allowedCategoryIds.has(Number(product.category_id)) ||
      preservedIds.has(Number(product.id))
  );
}

/**
 * Filter suppliers for the receipt supplier dropdown when products are already
 * chosen before a supplier is selected. Matches suppliers whose category_ids
 * cover ALL selected products' category_ids. If no supplier matches all or
 * showAllSuppliers is true, falls back to all active suppliers.
 */
export function filterSuppliersBySelectedProducts({
  suppliers = [],
  selectedProductCategoryIds = [],
  showAllSuppliers = false,
}) {
  const requiredCategories = Array.from(
    new Set(
      selectedProductCategoryIds
        .map(Number)
        .filter((cid) => Number.isInteger(cid) && cid > 0)
    )
  );

  if (showAllSuppliers || requiredCategories.length === 0) {
    return suppliers;
  }

  return suppliers.filter((supplier) => {
    if (!Array.isArray(supplier.category_ids) || supplier.category_ids.length === 0) {
      return false;
    }
    const supCats = new Set(supplier.category_ids.map(Number));
    return requiredCategories.every((cid) => supCats.has(cid));
  });
}

/**
 * When a user picks a product while no supplier is selected yet, return the
 * single matching ACTIVE supplier to auto-fill (if exactly 1 supplier provides
 * that product's category), or null otherwise.
 */
export function findAutoFillSupplierForProduct({
  suppliers = [],
  product = null,
  currentSupplierId = '',
}) {
  if (currentSupplierId || !product || !product.category_id) {
    return null;
  }

  const categoryId = Number(product.category_id);
  const matching = suppliers.filter(
    (s) =>
      Array.isArray(s.category_ids) &&
      s.category_ids.some((cid) => Number(cid) === categoryId)
  );

  return matching.length === 1 ? matching[0] : null;
}

/**
 * When switching to another supplier that has linked category_ids, reset
 * product_id to '' on lines whose currently selected product does not belong
 * to the new supplier's categories (unless showAllProducts is true).
 */
export function resetIncompatibleProductLines({
  lines = [],
  selectedSupplier = null,
  productById = new Map(),
  showAllProducts = false,
}) {
  if (showAllProducts) {
    return lines;
  }

  if (!selectedSupplier) {
    return lines.map((line) => (line.product_id ? { ...line, product_id: '' } : line));
  }

  if (
    !Array.isArray(selectedSupplier.category_ids) ||
    selectedSupplier.category_ids.length === 0
  ) {
    return lines;
  }

  const allowedCategoryIds = new Set(selectedSupplier.category_ids.map(Number));
  return lines.map((line) => {
    if (!line.product_id) return line;
    const product = productById.get(Number(line.product_id));
    if (!product || !allowedCategoryIds.has(Number(product.category_id))) {
      return { ...line, product_id: '' };
    }
    return line;
  });
}
