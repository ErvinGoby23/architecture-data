export default function IndicateurBtn({ indicateur, isActive, onClick }) {
  return (
    <button
      className={`indicateur-btn ${isActive ? 'active' : ''}`}
      style={{
        '--active-color': indicateur.color,
        opacity: indicateur.disabled ? 0.4 : 1,
        cursor: indicateur.disabled ? 'not-allowed' : 'pointer'
      }}
      onClick={() => !indicateur.disabled && onClick(indicateur)}
    >
      <span className="indicateur-dot" />
      <div>
        <div className="indicateur-label">{indicateur.label}</div>
        <div className="indicateur-sub">{indicateur.sub}</div>
      </div>
    </button>
  )
}