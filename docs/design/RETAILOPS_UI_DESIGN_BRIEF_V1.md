# RetailOps V1.0 — UI Design Brief & DESIGN.md-Compatible Guidance

**Status:** Visual direction proposed / approved in conversation for exploration; NOT an approved Figma screen set or replacement for SRS.  
**Date:** 2026-11-04  
**Product:** RetailOps V1.0 — one store, one warehouse  
**Audience:** Google Stitch, Figma designers, React frontend team  
**Working language for every screen:** Vietnamese (`vi-VN`)

> **Core design statement:** Quiet Utility — Green. A calm, credible, highly usable retail operations application. Prefer clear actions and accurate information to decoration. Minimal UI means minimal *visual noise*, NOT removal of essential business information.

## 0. How to use this document

1. Upload or paste this brief into Stitch as project context; if Stitch expects its native `DESIGN.md` schema, use the token/pattern sections below to populate or refine that file rather than assuming this brief is a validated schema implementation.
2. Optionally attach **two** approved visual *references*: the AFTER Quiet Utility concept (general UI) and the AI Assistant concept (AI screen only). Treat image content as illustrative, not authoritative.
3. Create screens in coherent batches, reusing one shared design system. Review each batch before moving to the next.
4. Send selected screens to Figma using the available Stitch-to-Figma mechanism in the currently accessible Stitch UI; verify whether layers, fonts and components remain editable.
5. In Figma refine auto-layout, components/variants, design tokens, states and flow diagrams. React implementation is a separate engineering stage.
6. When a concept, screenshot or prompt conflicts with SRS V1.3, SRS wins. Ask Product Owner for any additional business decisions; do not silently add scope.

## 1. Product and permission boundaries — MUST NOT change

RetailOps is an internal desktop-first, single-store/single-warehouse retail operations application with exactly two business roles: ADMIN and STAFF. Frontend React, backend FastAPI, database MySQL 8. Read-only AI is for Admin. V1 uses integer VND; there is no online payment gateway or actual payment integration.

- ADMIN: employee registration approval; master data (products/categories/suppliers); purchasing; stock counting and adjustment; POS; all orders and allowed cancellations; Dashboard/Analytics; read-only AI.
- STAFF: POS; product search/detail; inventory read; permitted filtered stock movement history; order list/detail; own-order cancellation subject to business rules. **No Dashboard, Analytics or AI. No supplier/purchasing administration or employee administration.**
- Never display or fetch for Staff: purchase unit costs, cost of goods, internal adjustment reasons, or other sensitive Admin-only fields.
- UI navigation and routing must reflect access permissions, but backend remains the authority for authentication, RBAC, ownership, resource and field-level security.
- Registration/approval/login/reset flows are in V1. Public Staff account requests require Admin approval.
- Business dates display in `Asia/Ho_Chi_Minh`; timestamps persisted in UTC by backend.
- P1 only after P0 quality gate: per-product low-stock threshold (INV-05), ANA-05, and ENG-10. Avoid designs that rely on P1 functionality to make P0 usable.

**Explicitly out of scope:** multi-store/multi-warehouse, online sales, real payment processing, discounts/promotions/tax accounting, returns/refunds, loyalty, forecasting, advanced AI actions, vector database, AI write operations, automatic purchasing, unapproved bulk actions and arbitrary product-management extras.

## 2. Design principles — NON-NEGOTIABLE

1. **Action first.** Primary task is evident within seconds. One dominant CTA per action-oriented screen. Read-only screens may have no dominant CTA.
2. **Quiet UI.** No gradients, glassmorphism, neon, giant decorative icons, excessive rounded cards, unneeded animation or nested card stacks.
3. **High information clarity.** Align numbers; use consistent headings, whitespace and dividers; retain essential operational fields.
4. **Progressive disclosure.** Secondary/dangerous operations through context menus or appropriate dialogs; do not hide frequent actions.
5. **Accessible by design.** Keyboard access, clear labels/focus, meaningful status text, sufficient contrast, responsive overflow.
6. **Consistency over novelty.** Same navigation/sidebar, button behaviors, statuses, tables, modal conventions, skeletons and toasts on all modules.
7. **Trustworthy state.** No optimistic implication of a completed transaction before server confirmation; explicitly handle conflicts, retries and unknown outcomes.
8. **Vietnamese-first.** Short labels, Vietnamese diacritics, precise VND formatting and intelligible error wording. Do not surface backend method names, function identifiers or raw stack traces.
9. **Implementation practicality.** No one-off animations or complex custom widgets that require disproportionate effort for a six-student team in 21 days.

### Avoid the generic 'AI-generated SaaS' look

- Do not cover pages with colorful stat cards and pointless icon badges.
- Do not use a gradient/blur-heavy visual language.
- Do not increase UI density simply to fill empty canvas.
- Do not make destructive actions as prominent as successful primary business actions.
- Do not invent a floating AI chatbot on every page; the AI has a dedicated Admin page.

## 3. Brand identity and token guidance

**Theme:** Quiet Utility — Green, bright neutral canvas, confident dark typography, restrained emerald actions.

| Token | Suggested value | Purpose |
|---|---|---|
| `color.brand.primary` | `#087F5B` | Primary CTA, active navigation, targeted emphasis |
| `color.brand.hover` | `#06694B` | Hover/pressed primary action |
| `color.brand.soft` | `#E7F4ED` | Selected nav item and subtle green backgrounds |
| `color.background` | `#F8F9FA` | App canvas |
| `color.surface` | `#FFFFFF` | Tables, forms, content panels |
| `color.border` | `#E2E5E9` | Neutral separators and edges |
| `color.text.primary` | `#242A30` | Headings, core body content |
| `color.text.secondary` | `#586574` | Descriptions, metadata |
| `color.success` | `#17603A` | Success status text |
| `color.warning` | `#965900` | Warning text (pair with readable tint) |
| `color.danger` | `#A8201A` | Error/destructive text (pair with readable tint) |
| `color.info` | `#2453A6` | Informational status |

**Contrast:** Above are starting tokens, not a blanket WCAG guarantee; validate actual foreground/background pairs against WCAG 2.2 AA: normal text >=4.5:1, large text >=3:1, interactive boundaries and focus as applicable. Do not rely on color alone.

**Typography:** `Inter` with `Be Vietnam Pro` as acceptable Vietnamese-first alternative; support Vietnamese diacritics. Body 14px with legible line height (~1.45–1.55), table 13–14px, secondary 12–13px (only where appropriate), section heading 18px/600, page heading 24px/650–700. Numeric columns: right aligned, tabular-nums.

**Spacing:** 4/8/12/16/24/32px. Main content horizontal padding 24px desktop; 16px on constrained widths. Vertical grouping 16–24px. Favor breathing room between sections rather than excessive padding inside every row.

**Radii:** Controls 6–8px; panels 8–10px. **Shadows:** mostly absent; use 1px borders and dividers. Reserve subtle shadow for overlay/dropdown/dialog.

**Desktop reference frames:** 1440×900 canonical review; also check 1366×768, 1280×800 and 1024 wide. Desktop-first, not a mobile-first storefront. Handle overflow and collapsible sidebar rather than shrinking text until unreadable. Browser zoom 125% and keyboard-only QA.

**Navigation:** Admin sidebar width approximately 224–232px, header about 56px; contextual section headings and active-item highlight in a soft green. Staff sidebar is substantially simpler, with POS first. Avoid cramped icon-only navigation as default.

**Tables:** neutral header, 44–48px comfortable body rows, stable numeric alignment, filters/search in a compact toolbar, pagination, well-defined empty state, horizontal overflow as necessary; do not make all data editable inline.

**Controls:** primary solid green (one clear action); secondary white with border; tertiary quiet text; destructive separated and red with confirmation when appropriate. Primary button height ~40px, forms 40px controls, large POS submit 44–48px. Disable duplicate submission while request is in-flight; do not hide why disabled.

**Status:** use text + subtle tinted background; statuses such as ACTIVE/INACTIVE, DRAFT/CONFIRMED/CANCELLED, COMPLETED/CANCELLED, pending approval, low stock, out of stock. Distinguish product operational state from inventory condition.

**Feedback:** dialogs for destructive/irreversible actions; toast for confirmed non-critical success; inline validation beside fields; skeleton for loading; clear empty, no-results, 401, 403, 409, 422, 429, 503, timeout, and unknown checkout outcome states. Errors should describe next safe action.

## 4. Shared information architecture

ADMIN navigation (labels are UX proposals, grouping may be adjusted without changing scope):
- Tổng quan
- Bán hàng (POS)
- Sản phẩm
- Danh mục
- Nhà cung cấp
- Nhập hàng
- Tồn kho (includes allowed stock movement and adjustments)
- Đơn hàng
- Nhân viên (registration approval)
- Phân tích
- Trợ lý AI

STAFF navigation:
- Bán hàng (POS) [default landing after login]
- Sản phẩm
- Tồn kho
- Đơn hàng

Account/profile area and logout must be visible and consistent. Do not show prohibited navigation items for Staff, and do not substitute visibility rules for backend permission checks.

## 5. Screen-by-screen contracts

### 5.1 Authentication and Staff approval

- Login, Staff registration, forgot/reset password, pending approval, rejected/reapply when allowed, session expired; Admin review queue and approve/reject.
- No public Admin registration. Do not reveal whether an email is registered when public flows require generic feedback.
- **Primary CTA:** Đăng nhập / Gửi đăng ký / Duyệt or Từ chối within respective context.
- Form labels, validation and status messages in Vietnamese. Pending approval is not an authenticated business access state.
- Avoid a marketing-style full-bleed hero distracting from login.

### 5.2 Dashboard — Admin only

- Goal: quickly understand relevant business activity and inspect important exceptions; not a decoration gallery.
- Layout: page title + report period / timezone, a restrained row of core KPIs within SRS, a primary trend panel, a secondary low-stock panel, and appropriately scoped operational summaries.
- Keep charts limited; no arbitrary extra metrics. Do not silently assume that revenue, number of orders or cancellation ratios can be calculated without the contract's exact period definition.
- **Primary CTA:** often none. Low-stock 'Xem tồn kho' is a contextual link, not a dominant button.
- Show report period and timezone; preserve sales-period attribution rules when displaying canceled order statistics per SRS.

### 5.3 Product Management / Category Management

- Table-first: SKU, product, category, selling price VND, current stock, status, allowed operations. Admin may create/edit/activate/deactivate; Staff may search and view only.
- Search/filter/sort/paginate; the only controls rendered should map to SRS. Real tables with 5–10 plausible illustrative rows, not fake dense noise.
- **Admin primary CTA:** Thêm sản phẩm. **Staff primary task:** search, not creation.
- Stock is **READ-ONLY** on Product form; inventory changes through designated business operations only.
- Product INACTIVE is not sellable or purchasable anew but retains historical references.
- Category INACTIVE cannot be assigned to a new product; no cascade-delete illusion.

### 5.4 Supplier Management

- Admin-only table, search and form; active/inactive supplier state; no deletion of immutable history links.
- **Primary CTA:** Thêm nhà cung cấp. Avoid promotions, supplier scoring or new sourcing workflows.

### 5.5 Purchasing

- Receipt list/table with status, supplier, creation date, total VND; actions and details only where allowed.
- Draft editor: supplier, product lines, positive integer qty, integer VND unit cost >=0, line total and receipt total, expected `draft_version`.
- Within one DRAFT: same product + same unit cost must merge quantities; same product + different unit cost must show validation error; no averaging costs. DRAFT does not change inventory.
- **Primary CTA:** Tạo phiếu nhập on list; Lưu nháp in draft editor; Xác nhận phiếu on an eligible draft with confirmation dialog and explicit risk.
- Confirm uses current version + idempotency key, can become CONFLICT 409; CONFIRMED is immutable. DRAFT may be canceled with correct version.
- No edit/cancel action on CONFIRMED receipt. Do not invent a purchase reversal flow.

### 5.6 Inventory & Stock Movements

- Product inventory read table with current stock, status, category and low stock markers; small operational counters only if SRS supports them.
- P0 low-stock threshold is DEFAULT 5 for active products; product-specific thresholds belong to P1 and should not be exposed in P0 designs.
- Admin adjustment form: *actual counted stock*, mandatory reason, expected_stock_version; the backend computes delta. A version conflict 409 must request refresh/recount. Count equal to current stock is a no-op movement with audit only.
- Staff stock movement view must exclude cost prices, private reasons and unnecessary personal information. Admin views full scope.
- **Primary CTA:** Admin contextual 'Điều chỉnh tồn kho', not an accidental edit field in every row.
- No arbitrary stock export or batch adjustment unless explicitly in SRS.

### 5.7 POS — Admin and Staff

- Dedicated, transaction-first workspace: left ~60–65% for search/filter/product lookup; right ~35–40% persistent cart. Rebalance for narrower laptop layouts to preserve cart usability.
- Search by supported product fields; compact products and unambiguous add action. Shopping cart quantity is positive integer; adding duplicate product combines lines. Cart is **not stock reservation**.
- Only ACTIVE products; show selling price VND and available quantity as current indicative data, not guaranteed stock.
- **ONE dominant CTA:** `Xác nhận bán hàng` (or `Xác nhận bán`), not a payment-gateway action. Server creates COMPLETED order on success.
- Checkout pending: disable duplicate submission. On `409 PRICE_CHANGED` show changed item(s), old and new selling price, require conscious acceptance and new checkout intent. On low stock show exact affected lines. On unknown result/timeout do not blindly resubmit as a new order; reconcile with server/idempotency behavior.
- Show confirmed order ID only after server confirmation. Don't create loyalty, customer profile, discount, tax, scanning hardware integration or other features unless in SRS.
- **Focus:** SKU/product search first, then line quantity, then persistent total and checkout CTA.

### 5.8 Order History / Cancellation

- Admin and Staff can view permitted order list and detail, with search, date, status and pagination.
- Staff can cancel **only own COMPLETED orders**, within **15 minutes** and **same Vietnam business day**; Admin can cancel eligible COMPLETED orders within the same sale day. Cancellation reason required. Cancellation must not be misleadingly shown as universally available.
- Use destructive confirmation dialog explaining why, requiring reason; after server success show CANCELLED with restored stock reflected according to backend.
- Never visually delete the order record, and don't imply returns/refunds.
- **Primary task:** find/view orders. Cancellation is conditional and not the page-wide primary CTA.

### 5.9 Staff Management / Approvals — Admin only

- Pending request queue, detail, approve/reject with clear state transitions. If someone else resolves the same request, show conflict/current status rather than false success.
- Registration notices for Admin are part of the product; avoid building an extensive notification center beyond specified scope.
- No account suspension/reactivation V1.

### 5.10 Analytics — Admin only

- Reporting/evidence driven; date range and timezone explicit; only SRS-approved metrics. Do not add automatic prediction, advanced forecasting, profit/cost reports outside approved contract.
- Readability over multiple chart types. Provide meaningful empty/insufficient data states.

### 5.11 AI Assistant — Admin only; largely KEEP prior concept

- Keep established conversation page layout: calm left sidebar, heading `Trợ lý AI RetailOps`, user bubble, assistant response card, evidence/details area, suggestion prompts if permitted by SRS, bottom input.
- AI operates via read-only business tools; it cannot execute modifying operations. Show business data source, report period/timezone and limitations/insufficient evidence when appropriate.
- **Specific approved UI refinement:** When backend/tool execution occurs, display a friendly neutral progress message such as `Đang xử lý dữ liệu...` or `Đang tra cứu thông tin...` with a subtle loading indicator. **Never expose raw function names, tool identifiers, SQL, internal service names or internal arguments to the user.**
- Only show completed metrics once validated data is available. Loading, timeout, quota, forbidden and insufficient evidence states need separate UI, not fabricated output.
- No global floating assistant overlay; keep a dedicated Admin AI workspace.

## 6. Visual hierarchy and CTA rules

- Page heading at top-left, time/filter controls at top-right where relevant.
- Content immediately below heading: search/filter for list pages; summary KPIs for dashboard; product search for POS; chat input/states for AI.
- Only one filled brand-green primary action per prominent action zone. Secondary actions use neutral outlined/text styling.
- Destructive operations red but not disproportionately large. Present near affected record or within an action menu and confirm when required.
- Use icons only when helpful; pair important icons with Vietnamese labels. No oversized decorative illustrations in operational views.
- Buttons use verbs and object context: `Thêm sản phẩm`, `Tạo phiếu nhập`, `Xác nhận bán hàng`, `Điều chỉnh tồn kho`. Avoid vague `Submit`, `Continue`, `Process`.
- Use right-aligned VND and quantities, dates in Vietnamese locale.

## 7. Required components / Figma handoff

Design as a **small shared system**:
- AppShell; role-aware SideNavigation; Header / PageHeader; Breadcrumb only if justified.
- Button primary/secondary/tertiary/destructive; IconButton; TextInput; PasswordInput; Select; Search; DateRange control if required.
- DataTable with loading/empty/no-results/pagination/filtering and optional row actions.
- StatBlock, TrendChart only where needed; StatusBadge, Alert, InlineError.
- Dialog (confirm/destructive/conflict), Toast, Skeleton, Spinner, EmptyState, ErrorState, PermissionDenied, SessionExpired.
- POS ProductSearch/ProductRow or compact tile, CartLine, CartSummary, CheckoutConfirm/Conflict.
- AI ChatMessage, EvidenceSummary, SuggestedQuestion (only when consistent with AI contract), AssistantProcessingState.

For every important screen in Figma include: default, loading, empty, validation error, forbidden/expired, conflict 409 where applicable, server unavailable, and success only after confirmed API result. For high-impact flows include disabled and keyboard/focus states. Avoid producing 11 glossy mockups while skipping the 409 states.

**Component naming and portability:** Use neutral naming suitable for React, readable variants and consistent tokens. Do not assume a generated screen automatically becomes a production-ready React component or a Figma component library.

## 8. Stitch generation instructions / starter prompt

Use this text together with the above brief:

> Design a coherent desktop-first Vietnamese internal retail operations web application named RetailOps V1.0. Apply the supplied **Quiet Utility — Green** tokens and rules strictly. It should look like a calm, trustworthy real operations tool, not a generic AI SaaS template: minimal ornament, white/off-white background, subtle gray borders, dark readable text and a restrained deep-green primary CTA. Optimize user task flow and information hierarchy. All mockup content must be in Vietnamese. Desktop review frame 1440x900; also account for 1366x768. Use the exact ADMIN/STAFF permissions and business boundaries in the brief. Generate the selected screens with consistent sidebar, header, tables, forms, buttons, statuses and feedback patterns. Prioritize the main user action on each screen and keep all operational data needed for decisions. Do not introduce any feature, filter, chart, shortcut, export action, external payment workflow or AI capability unless specified in SRS. In the AI assistant screen, never reveal tool/function names; use `Đang xử lý dữ liệu...` as user-facing processing status. These are UI concepts to be refined in Figma, not completed implementation.

**Generation sequence:**

**Batch A — UI foundation / first approval:** Admin Dashboard, Product Management (Admin), POS (Staff), Purchasing list + eligible DRAFT editor, AI Assistant. Review actual font legibility and CTA prioritization before continuing.

**Batch B — Domain completeness:** Categories, Suppliers, Inventory list, Stock Movements, Stock Adjustment, Order History/Detail, Cancellation dialog, Staff approval queue, Analytics.

**Batch C — Flow/edge state completeness:** Login, Staff register, pending/rejected/reset, confirmation dialogs, 409 PRICE_CHANGED, 409 stale purchase draft/stock version, checkout unknown result, error/empty/loading/permission/session states.

The batch split is for review efficiency, **not** a change to SRS or deliverables.

## 9. Image reference handling

- OPTIONAL reference image A: approved-after-direction composite board (for general theme, Admin dashboard, Product, POS and purchase list).
- OPTIONAL reference image B: AI assistant processing state screen (AI page only).
- Images are **not** specification: some visual details are AI hallucinations, e.g., invented customer selection, product sorting by popularity, export Excel, or keyboard shortcuts. Never copy such features unless SRS explicitly approves them.
- If textual requirements and images conflict, use the text and SRS. If images differ in saturation, choose the calmer neutral design in this document.

## 10. Review / acceptance checklist

- [ ] Vietnamese text is readable on 1440x900 and 1366x768 without visually crammed controls.
- [ ] Every page has an obvious primary task; primary CTA only where appropriate.
- [ ] Default components, table density, statuses and colors remain consistent across modules.
- [ ] Admin and Staff navigation/data access are correctly segregated.
- [ ] Staff never sees purchase prices, costs, private adjustment reasons, AI or Admin-only sections.
- [ ] POS cart and checkout CTA remain visible and usable; no accidental extra order on retry.
- [ ] Purchasing, stock adjustment and cancellation show version/conflict/destructive states.
- [ ] AI progress shows friendly wording, never internal tool names.
- [ ] No unsupported functionality from image mockups is treated as approved requirement.
- [ ] Figma contains editable frames, consistent styles/tokens and reusable variants.
- [ ] Design validated with actual task walkthroughs, not only aesthetic impressions.

## 11. Authority and assumptions

**Authoritative business source:** `RetailOps_SRS_V1.3_Approval_Candidate.docx`, dated 2026-11-03, 63-task baseline; document itself retains the title Approval Candidate. Product Owner discussion-level decisions remain relevant, but this brief is *not* a new SRS or change request.

**Proposed, not PO-approved technical design:** Exact tokens, 228px sidebar, component dimensions, default density, screen batching, and suggested CTA copy. Treat these as visual design proposals to validate in Stitch/Figma.

**Review ownership:** Product Owner approves UI direction; Frontend Lead checks React feasibility; Backend Lead validates permissions, API state machine, errors, concurrency/idempotency invariants and source-of-truth semantics; Scrum/Documentation owner tracks SRS mapping and revisions.
