import IndicateurBtn from './IndicateurBtn'
import YearFilter from './YearFilter'

export default function Sidebar({ 
  indicateurs = [], 
  activeIndicateur, 
  onSelectIndicateur, 
  selected, 
  scores = [], 
  visibleTypes = [], 
  onToggleType,
  year,
  onYearChange,
}) {
  const activeColor  = activeIndicateur?.color || '#4f8ef7'
  const selectedData = (selected && Array.isArray(scores)) ? scores.find(s => s.code_postal === selected) : null
  const scoreBars    = (selectedData && activeIndicateur?.scoreBars) ? activeIndicateur.scoreBars(selectedData) : []
  const stats        = (selectedData && activeIndicateur?.stats) ? activeIndicateur.stats(selectedData) : []
  console.log('selected:', selected, typeof selected)
console.log('scores[0]:', scores[0])

  if (!activeIndicateur) {
    return <aside className="sidebar"><p className="detail-empty">Chargement...</p></aside>
  }

  return (
    <aside className="sidebar">

      {/* 1. INDICATEURS */}
      <div className="sidebar-section">
        <p className="sidebar-section-title">Indicateurs</p>
        {indicateurs.map(ind => (
          <IndicateurBtn
            key={ind.id}
            indicateur={ind}
            isActive={activeIndicateur.id === ind.id}
            onClick={onSelectIndicateur}
          />
        ))}
      </div>

      {/* 2. ANNÉE */}
      {activeIndicateur.hasYearFilter && (
        <YearFilter year={year} onChange={onYearChange} />
      )}

      {/* 3. COUCHES */}
      {activeIndicateur.pointTypes?.length > 0 && (
        <div className="sidebar-section">
          <p className="sidebar-section-title">Couches</p>
          {activeIndicateur.pointTypes.map(pt => {
            const isVisible = visibleTypes.includes(pt.id)
            return (
              <button
                key={pt.id}
                className={`layer-btn ${isVisible ? 'active' : ''}`}
                style={{ '--layer-color': pt.color }}
                onClick={() => onToggleType(pt.id)}
              >
                <span className="layer-dot" style={{ background: isVisible ? pt.color : 'transparent', borderColor: pt.color }} />
                <span className="layer-label">{pt.label}</span>
                <span className="layer-toggle">{isVisible ? '●' : '○'}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* 4. LÉGENDE */}
      <div className="sidebar-section">
        <p className="sidebar-section-title">Légende</p>
        <div className="legend">
          {[
            { label: 'Score élevé',  opacity: 1 },
            { label: 'Score moyen',  opacity: 0.6 },
            { label: 'Score faible', opacity: 0.25 },
          ].map((l, i) => (
            <div className="legend-item" key={i}>
              <div className="legend-swatch" style={{ background: activeColor, opacity: l.opacity }} />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 5. DÉTAIL ARRONDISSEMENT */}
      <div className="sidebar-section" style={{ flex: 1 }}>
        <p className="sidebar-section-title">Détail arrondissement</p>
        {!selectedData ? (
          <p className="detail-empty">Cliquez sur<br />un arrondissement</p>
        ) : (
          <div style={{ '--active-color': activeColor }}>
            <div className="detail-header">
              <div className="detail-arrond">Paris {selectedData.arrondissement}e</div>
              <div className="detail-score-big">{selectedData[activeIndicateur.scoreKey] ?? '—'}</div>
              <div className="detail-score-label">/ 100</div>
              <div className="detail-badge">{selectedData.categorie || '—'}</div>
              {selectedData.rang && <div className="detail-rang">Rang #{selectedData.rang} / 20</div>}
            </div>

            <div className="score-bars">
              {scoreBars.map(bar => (
                <div className="score-row" key={bar.label}>
                  <div className="score-row-header">
                    <span className="score-row-label">{bar.label}</span>
                    <span className="score-row-value">{(bar.value * 100).toFixed(0)}</span>
                  </div>
                  <div className="score-bar-bg">
                    <div className="score-bar-fill" style={{ width: `${bar.value * 100}%`, background: activeColor }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

    </aside>
  )
}