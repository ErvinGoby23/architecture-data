const YEARS = [2022, 2023, 2024, 2025]

export default function YearFilter({ year, onChange }) {
  return (
    <div className="sidebar-section">
      <p className="sidebar-section-title">Année</p>
      <div className="year-filter">
        {YEARS.map(y => (
          <button
            key={y}
            className={`preset-btn ${year === y ? 'active' : ''}`}
            onClick={() => onChange(y === year ? null : y)}
          >
            {y}
          </button>
        ))}
      </div>
    </div>
  )
}