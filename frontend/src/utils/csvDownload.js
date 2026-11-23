/**
 * CSV & Styled Excel (.xlsx) download utilities for RetailOps V1.0.
 * Handles Blob streaming, Content-Disposition header extraction,
 * Excel UTF-8 BOM compatibility, styled Excel workbook generation with
 * auto-sized columns, color-coded badges, KPI summary, and visual bar charts.
 */
import ExcelJS from 'exceljs';

const STATUS_LABELS_VN = {
  COMPLETED: 'Hoàn tất',
  CANCELLED: 'Đã hủy',
  ACTIVE: 'Đang bán',
  INACTIVE: 'Ngừng bán',
};

/**
 * Parse RFC-4180 CSV text (supporting quoted fields, escaped quotes, and BOM)
 * into an array of row arrays.
 * @param {string} rawText
 * @returns {string[][]}
 */
export function parseCsvRows(rawText) {
  if (!rawText || typeof rawText !== 'string') {
    return [];
  }
  const text = rawText.replace(/^\ufeff/, '');
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(cell);
      cell = '';
    } else if (ch === '\r' && next === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      i += 1;
    } else if (ch === '\n' || ch === '\r') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += ch;
    }
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  return rows;
}

/**
 * Serialize a 2D array of cells back into an Excel-compatible UTF-8 BOM CSV string.
 * @param {string[][]} rows
 * @returns {string}
 */
export function serializeCsvRows(rows) {
  const escapeCell = (val) => {
    const str = val === null || val === undefined ? '' : String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const body = rows.map((r) => r.map(escapeCell).join(',')).join('\r\n');
  return `\ufeff${body}\r\n`;
}

/**
 * Format an ISO date/datetime string (`YYYY-MM-DD` or `YYYY-MM-DD HH:mm:ss`)
 * into a clean Vietnamese display string (`DD/MM/YYYY` or `DD/MM/YYYY HH:mm:ss`)
 * using non-breaking space padding (`\u00A0`) so Excel treats it as a text label
 * and never collapses the date into `#######`.
 * @param {string} raw
 * @returns {string}
 */
function formatDateForExcel(raw) {
  const trimmed = (raw || '').trim();
  if (!trimmed) return '—';
  const dtMatch = /^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?$/.exec(trimmed);
  if (!dtMatch) return trimmed;
  const [, yyyy, mm, dd, timePart] = dtMatch;
  const nbsp = '\u00A0';
  return timePart
    ? `${nbsp}${dd}/${mm}/${yyyy} ${timePart}${nbsp}`
    : `${nbsp}${dd}/${mm}/${yyyy}${nbsp}`;
}

/**
 * Format an ISO date/datetime string cleanly without NBSP for native `.xlsx` cells.
 * @param {string} raw
 * @returns {string}
 */
function formatDateCleanVN(raw) {
  const trimmed = (raw || '').trim();
  if (!trimmed) return '—';
  const dtMatch = /^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?$/.exec(trimmed);
  if (!dtMatch) return trimmed;
  const [, yyyy, mm, dd, timePart] = dtMatch;
  return timePart ? `${dd}/${mm}/${yyyy} ${timePart}` : `${dd}/${mm}/${yyyy}`;
}

/**
 * Format an integer VND string with Vietnamese thousand separators (e.g. `100000` -> `100.000 ₫`).
 * @param {string} raw
 * @returns {string}
 */
function formatVndForExcel(raw) {
  const trimmed = (raw || '').trim();
  if (!trimmed) return '0 ₫';
  const num = Number(trimmed);
  if (!Number.isFinite(num)) return trimmed;
  return `${Math.round(num).toLocaleString('vi-VN')} ₫`;
}

/**
 * Transform raw backend CSV text into a human-friendly, spaciously formatted
 * CSV for Microsoft Excel.
 * @param {string} rawCsvText
 * @returns {string}
 */
export function beautifyCsvForExcel(rawCsvText) {
  if (!rawCsvText || typeof rawCsvText !== 'string') {
    return rawCsvText;
  }

  const rows = parseCsvRows(rawCsvText);
  if (rows.length === 0) {
    return rawCsvText;
  }

  const rawHeaders = rows[0].map((h) => (h || '').trim());
  if (rawHeaders.length < 2) {
    return rawCsvText;
  }

  const formattedHeaders = rawHeaders.map((header) => `  ${header.toUpperCase()}  `);

  const formattedDataRows = rows.slice(1).map((row) =>
    rawHeaders.map((header, colIdx) => {
      const cell = row[colIdx] !== undefined ? String(row[colIdx]) : '';
      const trimmed = cell.trim();
      const headerLower = header.toLowerCase();

      if (headerLower === 'mã đơn' && /^\d+$/.test(trimmed)) {
        return `#HD-${trimmed}`;
      }
      if (headerLower === 'mã sp' && /^\d+$/.test(trimmed)) {
        return `#SP-${trimmed}`;
      }
      if (headerLower === 'trạng thái') {
        return STATUS_LABELS_VN[trimmed.toUpperCase()] || trimmed;
      }
      if (headerLower.startsWith('ngày')) {
        return formatDateForExcel(trimmed);
      }
      if (headerLower.includes('(vnđ)')) {
        return formatVndForExcel(trimmed);
      }
      if (headerLower === 'lý do hủy' && !trimmed) {
        return '—';
      }
      return cell;
    })
  );

  return serializeCsvRows([formattedHeaders, ...formattedDataRows]);
}

/**
 * Build an visual 16-block bar chart string for Excel cells.
 * @param {number} value
 * @param {number} maxValue
 * @returns {string}
 */
function buildVisualChartBar(value, maxValue) {
  const safeVal = Math.max(0, Number(value) || 0);
  const safeMax = Math.max(1, Number(maxValue) || 1);
  const ratio = Math.min(1, safeVal / safeMax);
  const pct = Math.round(ratio * 100);
  const totalBlocks = 14;
  const filledBlocks = safeVal > 0 ? Math.max(1, Math.round(ratio * totalBlocks)) : 0;
  const emptyBlocks = Math.max(0, totalBlocks - filledBlocks);
  const bar = `${'█'.repeat(filledBlocks)}${'░'.repeat(emptyBlocks)}`;
  return `${bar}  ${pct}%`;
}

/**
 * Detect report type and visual chart metric from CSV headers.
 * @param {string[]} headers
 */
function resolveReportMeta(headers) {
  const lower = headers.map((h) => h.toLowerCase());
  if (lower.includes('doanh thu thuần (vnđ)')) {
    return {
      type: 'DAILY_SALES',
      sheetName: 'Báo cáo Doanh thu',
      title: 'BÁO CÁO PHÂN TÍCH DOANH THU THEO NGÀY — RETAILOPS',
      subtitle: 'Tổng hợp doanh thu thuần, số lượng đơn hàng và biểu đồ trực quan theo ngày',
      chartHeader: 'BIỂU ĐỒ TỶ TRỌNG DOANH THU',
      metricColIdx: lower.indexOf('doanh thu thuần (vnđ)'),
    };
  }
  if (lower.includes('mã đơn')) {
    return {
      type: 'ORDERS',
      sheetName: 'Báo cáo Đơn hàng',
      title: 'BÁO CÁO CHI TIẾT LỊCH SỬ ĐƠN HÀNG — RETAILOPS',
      subtitle: 'Chi tiết mặt hàng, trạng thái đơn, nhân viên tạo và biểu đồ giá trị dòng hàng',
      chartHeader: 'BIỂU ĐỒ TỶ TRỌNG THÀNH TIỀN',
      metricColIdx: lower.indexOf('thành tiền (vnđ)'),
    };
  }
  if (lower.includes('tồn kho hiện tại')) {
    return {
      type: 'INVENTORY',
      sheetName: 'Báo cáo Tồn kho',
      title: 'BÁO CÁO QUẢN LÝ TỒN KHO SẢN PHẨM — RETAILOPS',
      subtitle: 'Danh sách mặt hàng, giá bán niêm yết, cảnh báo mức tồn và biểu đồ lượng tồn',
      chartHeader: 'BIỂU ĐỒ MỨC TỒN KHO',
      metricColIdx: lower.indexOf('tồn kho hiện tại'),
    };
  }
  if (lower.includes('mã phiếu nhập')) {
    return {
      type: 'PURCHASES',
      sheetName: 'Báo cáo Nhập hàng',
      title: 'BÁO CÁO DANH SÁCH PHIẾU NHẬP HÀNG — RETAILOPS',
      subtitle: 'Tổng hợp phiếu nhập kho từ nhà cung cấp, trạng thái và giá trị nhập',
      chartHeader: 'BIỂU ĐỒ GIÁ TRỊ NHẬP',
      metricColIdx: lower.indexOf('tổng tiền (vnđ)'),
    };
  }
  if (lower.includes('loại biến động')) {
    return {
      type: 'STOCK_MOVEMENTS',
      sheetName: 'Báo cáo Biến động kho',
      title: 'BÁO CÁO LỊCH SỬ BIẾN ĐỘNG KHO — RETAILOPS',
      subtitle: 'Chi tiết xuất nhập kho, điều chỉnh kiểm kê và chứng từ tham chiếu',
      chartHeader: null,
      metricColIdx: -1,
    };
  }
  return {
    type: 'GENERIC',
    sheetName: 'Báo cáo RetailOps',
    title: 'BÁO CÁO DỮ LIỆU HỆ THỐNG — RETAILOPS',
    subtitle: 'Dữ liệu trích xuất từ hệ thống quản lý bán lẻ RetailOps',
    chartHeader: null,
    metricColIdx: -1,
  };
}

/**
 * Convert raw CSV content into a richly styled Excel (.xlsx) Blob with:
 * - Teal branded title banner & export timestamp
 * - KPI Summary highlight bar
 * - Wide, auto-fitted columns (guaranteed never to truncate or show `#######`)
 * - Color-coded status badges (Green for Completed/Active, Red for Cancelled/Out of stock)
 * - In-cell Visual Bar Chart column (`█` / `░` + percentage) for immediate visual analysis
 * - Totals / Averages summary footer row
 * @param {string} rawCsvText
 * @returns {Promise<Blob>}
 */
export async function generateStyledExcelFromCsv(rawCsvText) {
  const rows = parseCsvRows(rawCsvText);
  const rawHeaders = rows.length > 0 ? rows[0].map((h) => (h || '').trim()) : ['Dữ liệu'];
  const dataRows = rows.slice(1);
  const meta = resolveReportMeta(rawHeaders);

  const hasChartCol = meta.chartHeader !== null && meta.metricColIdx >= 0;
  const finalHeaders = hasChartCol ? [...rawHeaders, meta.chartHeader] : [...rawHeaders];
  const totalCols = finalHeaders.length;

  let maxMetricVal = 0;
  if (hasChartCol) {
    for (const r of dataRows) {
      const val = Number((r[meta.metricColIdx] || '').trim());
      if (Number.isFinite(val) && val > maxMetricVal) {
        maxMetricVal = val;
      }
    }
  }

  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'RetailOps Management System';
  workbook.created = new Date();

  const sheet = workbook.addWorksheet(meta.sheetName, {
    views: [{ state: 'frozen', ySplit: 5 }],
  });

  const thinBorder = {
    top: { style: 'thin', color: { argb: 'FFE2E8F0' } },
    left: { style: 'thin', color: { argb: 'FFE2E8F0' } },
    bottom: { style: 'thin', color: { argb: 'FFE2E8F0' } },
    right: { style: 'thin', color: { argb: 'FFE2E8F0' } },
  };

  // 1. Title Banner (Row 1)
  const titleRow = sheet.addRow([meta.title]);
  titleRow.height = 32;
  sheet.mergeCells(1, 1, 1, totalCols);
  const titleCell = sheet.getCell(1, 1);
  titleCell.font = { name: 'Segoe UI', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  titleCell.fill = {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb: 'FF0F766E' }, // Deep Emerald/Teal
  };
  titleCell.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };

  // 2. Subtitle & Export Timestamp (Row 2)
  const nowStr = new Date().toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
  const subRow = sheet.addRow([`${meta.subtitle}   •   Thời điểm xuất: ${nowStr}`]);
  subRow.height = 22;
  sheet.mergeCells(2, 1, 2, totalCols);
  const subCell = sheet.getCell(2, 1);
  subCell.font = { name: 'Segoe UI', size: 10, italic: true, color: { argb: 'FF334155' } };
  subCell.fill = {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb: 'FFF0FDFA' }, // Soft Mint Tint
  };
  subCell.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };

  // 3. KPI Quick Summary Strip (Row 3)
  let kpiSummaryText = `Tổng số dòng dữ liệu: ${dataRows.length}`;
  if (meta.type === 'DAILY_SALES') {
    const totalRev = dataRows.reduce((acc, r) => acc + (Number(r[1]) || 0), 0);
    const totalComp = dataRows.reduce((acc, r) => acc + (Number(r[2]) || 0), 0);
    const totalCanc = dataRows.reduce((acc, r) => acc + (Number(r[3]) || 0), 0);
    const peakRow = dataRows.reduce(
      (best, r) => ((Number(r[1]) || 0) > (Number(best?.[1]) || 0) ? r : best),
      dataRows[0]
    );
    const peakDate = peakRow ? formatDateCleanVN(peakRow[0]) : '—';
    kpiSummaryText =
      `📊 TỔNG QUAN KỲ:   Tổng doanh thu thuần: ${totalRev.toLocaleString('vi-VN')} ₫` +
      `   |   Tổng đơn hoàn tất: ${totalComp} đơn` +
      `   |   Tổng đơn hủy: ${totalCanc} đơn` +
      `   |   Ngày đỉnh doanh thu: ${peakDate} (${maxMetricVal.toLocaleString('vi-VN')} ₫)`;
  } else if (meta.type === 'ORDERS') {
    const totalQty = dataRows.reduce((acc, r) => acc + (Number(r[5]) || 0), 0);
    const totalLineVnd = dataRows.reduce((acc, r) => acc + (Number(r[7]) || 0), 0);
    kpiSummaryText =
      `📊 TỔNG QUAN ĐƠN HÀNG:   Số dòng chi tiết: ${dataRows.length}` +
      `   |   Tổng sản lượng: ${totalQty.toLocaleString('vi-VN')} SP` +
      `   |   Tổng giá trị dòng hàng: ${totalLineVnd.toLocaleString('vi-VN')} ₫`;
  } else if (meta.type === 'INVENTORY') {
    const totalStock = dataRows.reduce((acc, r) => acc + (Number(r[5]) || 0), 0);
    const lowStockCount = dataRows.filter((r) => (Number(r[5]) || 0) <= 5).length;
    kpiSummaryText =
      `📊 TỔNG QUAN KHO:   Tổng số mã SP: ${dataRows.length}` +
      `   |   Tổng số lượng tồn: ${totalStock.toLocaleString('vi-VN')} đơn vị` +
      `   |   Số mã cảnh báo tồn thấp (≤ 5): ${lowStockCount} mã`;
  }

  const kpiRow = sheet.addRow([kpiSummaryText]);
  kpiRow.height = 24;
  sheet.mergeCells(3, 1, 3, totalCols);
  const kpiCell = sheet.getCell(3, 1);
  kpiCell.font = { name: 'Segoe UI', size: 10, bold: true, color: { argb: 'FF0F766E' } };
  kpiCell.fill = {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb: 'FFCCFBF1' },
  };
  kpiCell.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };

  // 4. Spacer Row (Row 4)
  const spacerRow = sheet.addRow([]);
  spacerRow.height = 8;

  // 5. Table Header Row (Row 5)
  const headerLabels = finalHeaders.map((h) => h.toUpperCase());
  const headerRow = sheet.addRow(headerLabels);
  headerRow.height = 28;
  headerRow.eachCell((cell, colNumber) => {
    const hLower = finalHeaders[colNumber - 1].toLowerCase();
    const isRight =
      hLower.includes('(vnđ)') ||
      hLower.includes('số lượng') ||
      hLower.includes('số đơn') ||
      hLower.includes('tồn kho');
    const isCenter =
      hLower === 'ngày' ||
      hLower.startsWith('ngày ') ||
      hLower === 'trạng thái' ||
      hLower === 'mã đơn' ||
      hLower === 'mã sp' ||
      hLower === 'sku';

    cell.font = { name: 'Segoe UI', size: 10.5, bold: true, color: { argb: 'FFFFFFFF' } };
    cell.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FF1E293B' }, // Slate 800
    };
    cell.alignment = {
      vertical: 'middle',
      horizontal: isRight ? 'right' : isCenter ? 'center' : 'left',
      wrapText: false,
    };
    cell.border = thinBorder;
  });

  // Track column character lengths for generous auto-width
  const colMaxLengths = finalHeaders.map((h) => Math.max(h.length + 6, 16));

  // 6. Data Rows
  const numericTotals = new Array(totalCols).fill(0);
  const isSummableCol = new Array(totalCols).fill(false);

  dataRows.forEach((rawRow, rowIdx) => {
    const rowValues = [];
    const cellMeta = [];

    rawHeaders.forEach((header, colIdx) => {
      const rawVal = rawRow[colIdx] !== undefined ? String(rawRow[colIdx]) : '';
      const trimmed = rawVal.trim();
      const hLower = header.toLowerCase();

      if (hLower === 'mã đơn' && /^\d+$/.test(trimmed)) {
        rowValues.push(`#HD-${trimmed}`);
        cellMeta.push({ align: 'center', bold: true, color: 'FF0F172A' });
      } else if (hLower === 'mã sp' && /^\d+$/.test(trimmed)) {
        rowValues.push(`#SP-${trimmed}`);
        cellMeta.push({ align: 'center', bold: true, color: 'FF0F172A' });
      } else if (hLower === 'trạng thái') {
        const label = STATUS_LABELS_VN[trimmed.toUpperCase()] || trimmed;
        const isPositive =
          trimmed.toUpperCase() === 'COMPLETED' || trimmed.toUpperCase() === 'ACTIVE';
        rowValues.push(label);
        cellMeta.push({
          align: 'center',
          bold: true,
          color: isPositive ? 'FF15803D' : 'FFB91C1C',
          bg: isPositive ? 'FFDCFCE7' : 'FFFEE2E2',
        });
      } else if (hLower.startsWith('ngày')) {
        rowValues.push(formatDateCleanVN(trimmed));
        cellMeta.push({ align: 'center', bold: false, color: 'FF1E293B' });
      } else if (hLower.includes('(vnđ)')) {
        const num = Number(trimmed);
        if (Number.isFinite(num)) {
          rowValues.push(num);
          numericTotals[colIdx] += num;
          isSummableCol[colIdx] = hLower !== 'đơn giá (vnđ)' && hLower !== 'giá bán niêm yết (vnđ)';
          cellMeta.push({
            align: 'right',
            numFmt: '#,##0 "₫"',
            bold: hLower.includes('doanh thu') || hLower.includes('thành tiền') || hLower.includes('tổng đơn'),
            color: 'FF0F766E',
          });
        } else {
          rowValues.push(trimmed);
          cellMeta.push({ align: 'right' });
        }
      } else if (
        hLower.includes('số lượng') ||
        hLower.includes('số đơn') ||
        hLower.includes('tồn kho')
      ) {
        const num = Number(trimmed);
        if (Number.isFinite(num)) {
          rowValues.push(num);
          numericTotals[colIdx] += num;
          isSummableCol[colIdx] = true;
          const isCancelOrLow =
            (hLower.includes('đơn hủy') && num > 0) ||
            (hLower.includes('tồn kho') && num <= 5);
          cellMeta.push({
            align: 'right',
            numFmt: '#,##0',
            bold: isCancelOrLow,
            color: isCancelOrLow ? 'FFB91C1C' : 'FF1E293B',
            bg: isCancelOrLow ? 'FFFEF2F2' : undefined,
          });
        } else {
          rowValues.push(trimmed);
          cellMeta.push({ align: 'right' });
        }
      } else if (hLower === 'lý do hủy') {
        rowValues.push(trimmed || '—');
        cellMeta.push({ align: 'left', color: trimmed ? 'FFB91C1C' : 'FF94A3B8' });
      } else {
        rowValues.push(rawVal);
        cellMeta.push({
          align: hLower === 'sku' ? 'center' : 'left',
          bold: hLower === 'tên sản phẩm',
          color: 'FF1E293B',
        });
      }
    });

    if (hasChartCol) {
      const metricVal = Number((rawRow[meta.metricColIdx] || '').trim()) || 0;
      const barStr = buildVisualChartBar(metricVal, maxMetricVal);
      rowValues.push(barStr);
      cellMeta.push({
        align: 'left',
        bold: true,
        fontName: 'Consolas',
        color: metricVal > 0 && metricVal === maxMetricVal ? 'FF0F766E' : 'FF0284C7',
        bg: metricVal > 0 && metricVal === maxMetricVal ? 'FFCCFBF1' : undefined,
      });
    }

    const excelRow = sheet.addRow(rowValues);
    excelRow.height = 23;
    const isEven = rowIdx % 2 === 1;

    excelRow.eachCell({ includeEmpty: true }, (cell, colNumber) => {
      const cIdx = colNumber - 1;
      const m = cellMeta[cIdx] || {};
      const displayStr =
        typeof cell.value === 'number'
          ? `${cell.value.toLocaleString('vi-VN')} ₫`
          : String(cell.value ?? '');
      colMaxLengths[cIdx] = Math.max(colMaxLengths[cIdx] || 16, displayStr.length + 6);

      cell.font = {
        name: m.fontName || 'Segoe UI',
        size: 10,
        bold: Boolean(m.bold),
        color: { argb: m.color || 'FF1E293B' },
      };
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: m.bg || (isEven ? 'FFF8FAFC' : 'FFFFFFFF') },
      };
      cell.alignment = {
        vertical: 'middle',
        horizontal: m.align || 'left',
      };
      if (m.numFmt) {
        cell.numFmt = m.numFmt;
      }
      cell.border = thinBorder;
    });
  });

  // 7. Summary / Total Footer Row (if there are data rows)
  if (dataRows.length > 0) {
    const footerValues = new Array(totalCols).fill('');
    footerValues[0] = 'TỔNG CỘNG / TRUNG BÌNH';

    rawHeaders.forEach((header, colIdx) => {
      if (colIdx === 0) return;
      const hLower = header.toLowerCase();
      if (hLower === 'giá trị trung bình đơn (vnđ)' && meta.type === 'DAILY_SALES') {
        const totalRev = numericTotals[1] || 0;
        const totalComp = numericTotals[2] || 0;
        footerValues[colIdx] = totalComp > 0 ? Math.round(totalRev / totalComp) : 0;
      } else if (isSummableCol[colIdx]) {
        footerValues[colIdx] = numericTotals[colIdx];
      }
    });

    if (hasChartCol) {
      footerValues[totalCols - 1] = `Đỉnh: ${maxMetricVal.toLocaleString('vi-VN')}${
        meta.type === 'INVENTORY' ? ' ĐV' : ' ₫'
      }`;
    }

    const footerRow = sheet.addRow(footerValues);
    footerRow.height = 26;
    footerRow.eachCell({ includeEmpty: true }, (cell, colNumber) => {
      const cIdx = colNumber - 1;
      const hLower = (finalHeaders[cIdx] || '').toLowerCase();
      const isCurrency = hLower.includes('(vnđ)');
      const isNumeric = typeof cell.value === 'number';

      cell.font = {
        name: 'Segoe UI',
        size: 10.5,
        bold: true,
        color: { argb: 'FF0F172A' },
      };
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FFE2E8F0' },
      };
      cell.alignment = {
        vertical: 'middle',
        horizontal: cIdx === 0 ? 'center' : isNumeric ? 'right' : 'left',
      };
      if (isNumeric) {
        cell.numFmt = isCurrency ? '#,##0 "₫"' : '#,##0';
      }
      cell.border = {
        top: { style: 'medium', color: { argb: 'FF0F766E' } },
        bottom: { style: 'double', color: { argb: 'FF0F766E' } },
        left: { style: 'thin', color: { argb: 'FFCBD5E1' } },
        right: { style: 'thin', color: { argb: 'FFCBD5E1' } },
      };
    });
  }

  // 8. Apply generous column widths so no column is ever cramped or shows `#######`
  sheet.columns.forEach((column, idx) => {
    const calculated = colMaxLengths[idx] || 18;
    column.width = Math.min(Math.max(calculated, 18), 46);
  });

  const buffer = await workbook.xlsx.writeBuffer();
  return new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

/**
 * Extract filename from Content-Disposition header or use fallback.
 * @param {string|null|undefined} contentDisposition
 * @param {string} fallback
 * @returns {string}
 */
export function extractFilenameFromHeader(contentDisposition, fallback = 'report.csv') {
  if (!contentDisposition || typeof contentDisposition !== 'string') {
    return fallback;
  }

  const utf8Match = /filename\*=UTF-8''([^;\s]+)/i.exec(contentDisposition);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1].replace(/["']/g, ''));
    } catch {
      return utf8Match[1].replace(/["']/g, '');
    }
  }

  const standardMatch = /filename=["']?([^"';\n]+)["']?/i.exec(contentDisposition);
  if (standardMatch && standardMatch[1]) {
    return standardMatch[1].trim();
  }

  return fallback;
}

/**
 * Decode error message from an Axios error where error.response.data is a Blob.
 * @param {any} error
 * @returns {Promise<string>}
 */
export async function parseBlobErrorMessage(error) {
  if (error?.response?.data instanceof Blob) {
    try {
      const text = await error.response.data.text();
      const json = JSON.parse(text);
      if (typeof json.message === 'string' && json.message.trim()) {
        return json.message;
      }
      if (typeof json.detail === 'string' && json.detail.trim()) {
        return json.detail;
      }
    } catch {
      // Fallback below
    }
  }
  return (
    error?.response?.data?.message ||
    error?.response?.data?.detail ||
    error?.message ||
    'Không thể xuất báo cáo. Vui lòng thử lại sau.'
  );
}

/**
 * Trigger browser file download from a Blob or an Axios response.
 * @param {Blob|{ data: Blob, headers?: any }} blobOrResponse
 * @param {string} fallbackFilename
 */
export function triggerBlobDownload(blobOrResponse, fallbackFilename = 'report.csv') {
  let blob;
  let filename = fallbackFilename;

  if (blobOrResponse instanceof Blob) {
    blob = blobOrResponse;
  } else if (blobOrResponse && blobOrResponse.data instanceof Blob) {
    blob = blobOrResponse.data;
    const disposition =
      blobOrResponse.headers?.['content-disposition'] ||
      (typeof blobOrResponse.headers?.get === 'function' &&
        blobOrResponse.headers.get('content-disposition'));
    filename = extractFilenameFromHeader(disposition, fallbackFilename);
  } else {
    throw new Error('Dữ liệu tải về không hợp lệ.');
  }

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

/**
 * Higher-level helper to execute an API call and download the resulting CSV
 * or richly styled Excel (.xlsx) workbook.
 * @param {() => Promise<any>} fetchFn
 * @param {string} fallbackFilename
 * @param {{ format?: 'csv' | 'xlsx' }} [options]
 * @returns {Promise<void>}
 */
export async function downloadCsvReport(
  fetchFn,
  fallbackFilename = 'report.csv',
  options = {}
) {
  try {
    const response = await fetchFn();
    let finalPayload = response;

    const rawBlob =
      response instanceof Blob
        ? response
        : response && response.data instanceof Blob
        ? response.data
        : null;

    const wantExcel =
      options.format === 'xlsx' || /\.xlsx$/i.test(fallbackFilename);

    if (rawBlob && typeof rawBlob.text === 'function') {
      try {
        const rawText = await rawBlob.text();
        if (wantExcel) {
          const excelBlob = await generateStyledExcelFromCsv(rawText);
          const disposition =
            response?.headers?.['content-disposition'] ||
            (typeof response?.headers?.get === 'function' &&
              response.headers.get('content-disposition'));
          const extractedName = extractFilenameFromHeader(
            disposition,
            fallbackFilename
          ).replace(/\.csv$/i, '.xlsx');

          triggerBlobDownload(
            {
              data: excelBlob,
              headers: {
                'content-disposition': `attachment; filename="${extractedName}"`,
              },
            },
            fallbackFilename.replace(/\.csv$/i, '.xlsx')
          );
          return;
        }

        const beautifiedText = beautifyCsvForExcel(rawText);
        const beautifiedBlob = new Blob([beautifiedText], {
          type: 'text/csv; charset=utf-8',
        });
        finalPayload =
          response instanceof Blob
            ? beautifiedBlob
            : { ...response, data: beautifiedBlob };
      } catch {
        // Fallback to raw response if Blob transformation fails
      }
    }

    triggerBlobDownload(finalPayload, fallbackFilename);
  } catch (error) {
    const errorMsg = await parseBlobErrorMessage(error);
    const customErr = new Error(errorMsg);
    customErr.originalError = error;
    throw customErr;
  }
}

/**
 * Generate and download a styled Excel (.xlsx) workbook directly from a 2D array
 * of rows (header row + data rows).
 * @param {Array<Array<string | number>>} rows
 * @param {string} fallbackFilename
 * @returns {Promise<void>}
 */
export async function downloadStyledExcelRows(rows, fallbackFilename = 'report.xlsx') {
  const csvText = serializeCsvRows(rows);
  const excelBlob = await generateStyledExcelFromCsv(csvText);
  const finalName = /\.xlsx$/i.test(fallbackFilename)
    ? fallbackFilename
    : `${fallbackFilename.replace(/\.csv$/i, '')}.xlsx`;
  triggerBlobDownload(
    {
      data: excelBlob,
      headers: {
        'content-disposition': `attachment; filename="${finalName}"`,
      },
    },
    finalName
  );
}
