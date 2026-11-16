import styles from './Table.module.css';

/**
 * Component Bảng dữ liệu động (Data-driven Table) dùng chung cho RetailOps v1.0
 * @param {Array} columns - Cấu hình cột: [{ key, title, align = 'left', width, render }]
 * @param {Array} data - Mảng dữ liệu các dòng
 * @param {string} rowKey - Tên trường khóa chính của dòng (mặc định: 'id')
 * @param {boolean} isLoading - Trạng thái đang tải dữ liệu
 * @param {string} emptyText - Nội dung hiển thị khi mảng data rỗng
 */
export default function Table({
  columns = [],
  data = [],
  rowKey = 'id',
  isLoading = false,
  emptyText = 'Không có dữ liệu hiển thị',
  rowClassName,
}) {
  const colSpan = columns.length || 1;

  return (
    <div className={styles.tableContainer}>
      <table className={styles.table}>
        {/* 1. Phần Header (thead) */}
        <thead className={styles.thead}>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={styles.th}
                style={{
                  textAlign: col.align || 'left',
                  width: col.width || 'auto',
                }}
              >
                {col.title}
              </th>
            ))}
          </tr>
        </thead>

        {/* 2. Phần Body (tbody) */}
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={colSpan} className={styles.stateCell}>
                <div className={styles.loadingWrap}>
                  <span className={styles.spinner} aria-hidden="true" />
                  <span>Đang tải dữ liệu...</span>
                </div>
              </td>
            </tr>
          ) : !data || data.length === 0 ? (
            <tr>
              <td colSpan={colSpan} className={styles.stateCell}>
                {emptyText}
              </td>
            </tr>
          ) : (
            data.map((row, rowIndex) => {
              const key = row[rowKey] !== undefined ? row[rowKey] : rowIndex;
              const extraRowClass =
                typeof rowClassName === 'function'
                  ? rowClassName(row, rowIndex)
                  : typeof rowClassName === 'string'
                  ? rowClassName
                  : '';
              const trClassName = extraRowClass
                ? `${styles.tr} ${extraRowClass}`
                : styles.tr;
              return (
                <tr key={key} className={trClassName}>
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={styles.td}
                      style={{ textAlign: col.align || 'left' }}
                    >
                      {typeof col.render === 'function'
                        ? col.render(row, rowIndex)
                        : row[col.key]}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

