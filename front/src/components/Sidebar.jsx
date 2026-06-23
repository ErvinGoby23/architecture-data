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
  granularite = 'arrondissement',
  onGranulariteChange,
}) {
  const activeColor = activeIndicateur?.color || '#4f8ef7'

  const selectedData = (selected !== null && Array.isArray(scores))
    ? (() => {
        const matches = scores.filter(s => {
          if (s.code_quartier !== undefined)
            return parseInt(s.code_quartier) === parseInt(selected)
          if (s.arrondissement !== undefined)
            return parseInt(s.arrondissement) === parseInt(selected)
          if (s.code_postal !== undefined)
            return parseInt(s.code_postal) === 75000 + parseInt(selected)
          return false
        })
        if (!matches.length) return null
        if (year) return matches.find(s => s.annee === year) ?? null
        if (matches[0]?.annee === undefined) return matches[0] ?? null
        return matches.reduce((a, b) => a.annee > b.annee ? a : b)
      })()
    : null

  const scoreBars  = (selectedData && activeIndicateur?.scoreBars) ? activeIndicateur.scoreBars(selectedData) : []
  const isQuartier = granularite === 'quartier'
  const totalZones = isQuartier ? 80 : 20

  // Label zone sélectionnée
  const zoneLabel = selectedData
    ? selectedData.nom_quartier
      ? `${selectedData.nom_quartier}`
      : `Paris ${selectedData.arrondissement ?? (selectedData.code_postal - 75000)}e`
    : null

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

      {/* 2. GRANULARITÉ — uniquement pour mobilité */}
      {onGranulariteChange && (
        <div className="sidebar-section">
          <p className="sidebar-section-title">Granularité</p>
          <div className="year-filter">
            <button
              className={`preset-btn ${!isQuartier ? 'active' : ''}`}
              onClick={() => onGranulariteChange('arrondissement')}
            >
              20 arr.
            </button>
            <button
              className={`preset-btn ${isQuartier ? 'active' : ''}`}
              onClick={() => onGranulariteChange('quartier')}
            >
              80 qtrs
            </button>
          </div>
        </div>
      )}

      {/* 3. ANNÉE */}
      {activeIndicateur.hasYearFilter && (
        <YearFilter year={year} onChange={onYearChange} />
      )}

      {/* 4. COUCHES */}
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

      {/* 5. LÉGENDE */}
      <div className="sidebar-section">
        <p className="sidebar-section-title">Légende</p>
        <div className="legend">
          {[
            { label: 'Score élevé',  color: '#00d4aa' },
            { label: 'Score moyen',  color: '#f7934f' },
            { label: 'Score faible', color: '#ef4444' },
          ].map((l, i) => (
            <div className="legend-item" key={i}>
              <div className="legend-swatch" style={{ background: l.color }} />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
      </div>
      {/* 6. DÉTAIL ZONE */}
      <div className="sidebar-section" style={{ flex: 1 }}>
        <p className="sidebar-section-title">
          Détail {isQuartier ? 'quartier' : 'arrondissement'}
        </p>
        {!selectedData ? (
          <p className="detail-empty">
            Cliquez sur<br />{isQuartier ? 'un quartier' : 'un arrondissement'}
          </p>
        ) : (
          <div style={{ '--active-color': activeColor }}>
            <div className="detail-header">
              <div className="detail-arrond">{zoneLabel}</div>
              <div className="detail-score-big">{selectedData[activeIndicateur.scoreKey] ?? '—'}</div>
              <div className="detail-score-label">/ 100</div>
              <div className="detail-badge">{selectedData.categorie || '—'}</div>
              {selectedData.rang && (
                <div className="detail-rang">Rang #{selectedData.rang} / {totalZones}</div>
              )}
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
