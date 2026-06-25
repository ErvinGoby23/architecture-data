import { useMemo } from 'react'

/**
 * Bandeau horizontal en haut de la carte, spécifique à l'indicateur logement.
 * - Timeline : slider/boutons d'années (rejoue l'évolution du marché)
 * - KPI prix : prix/m² médian, variation, surface, ventes pour la zone+année courante
 *
 * Props :
 *   years        : number[]   liste des années disponibles (ex: [2021..2025])
 *   year         : number     année active
 *   onYearChange : (y)=>void
 *   selectedData : object|null  ligne du score pour la zone sélectionnée + année active
 *   prevData     : object|null  même zone, année précédente (pour la variation)
 *   zoneLabel    : string|null  libellé de la zone sélectionnée
 */
export default function BandeauLogement({
  years = [],
  year,
  onYearChange,
  selectedData = null,
  prevData = null,
  zoneLabel = null,
}) {
  const variation = useMemo(() => {
    if (!selectedData?.prix_m2_median || !prevData?.prix_m2_median) return null
    const v = ((selectedData.prix_m2_median - prevData.prix_m2_median) / prevData.prix_m2_median) * 100
    return Math.round(v * 10) / 10
  }, [selectedData, prevData])

  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat('fr-FR').format(Math.round(n)))

  return (
    <div className="bandeau-logement">

      {/* TIMELINE */}
      <div className="bandeau-timeline">
        <span className="bandeau-timeline-title">Évolution</span>
        <div className="bandeau-years">
          {years.map((y) => (
            <button
              key={y}
              className={`bandeau-year-btn ${y === year ? 'active' : ''}`}
              onClick={() => onYearChange(y)}
            >
              {y}
            </button>
          ))}
        </div>
        {years.length > 1 && (
          <input
            className="bandeau-slider"
            type="range"
            min={years[0]}
            max={years[years.length - 1]}
            step={1}
            value={year ?? years[years.length - 1]}
            onChange={(e) => onYearChange(parseInt(e.target.value))}
          />
        )}
      </div>

      {/* KPI PRIX */}
      <div className="bandeau-kpis">
        {zoneLabel && <div className="bandeau-zone">{zoneLabel}</div>}

        <div className="bandeau-kpi">
          <span className="bandeau-kpi-val">{fmt(selectedData?.prix_m2_median)} €</span>
          <span className="bandeau-kpi-lbl">Prix/m² médian</span>
        </div>

        {variation != null && (
          <div className="bandeau-kpi">
            <span className={`bandeau-kpi-val ${variation >= 0 ? 'up' : 'down'}`}>
              {variation >= 0 ? '+' : ''}{variation}%
            </span>
            <span className="bandeau-kpi-lbl">vs {year - 1}</span>
          </div>
        )}

        <div className="bandeau-kpi">
          <span className="bandeau-kpi-val">{fmt(selectedData?.nb_ventes)}</span>
          <span className="bandeau-kpi-lbl">Ventes</span>
        </div>

        <div className="bandeau-kpi">
          <span className="bandeau-kpi-val">{selectedData?.surface_mediane ?? '—'} m²</span>
          <span className="bandeau-kpi-lbl">Surface méd.</span>
        </div>

        {selectedData?.taux_effort_achat != null && (
          <div className="bandeau-kpi">
            <span className="bandeau-kpi-val">{selectedData.taux_effort_achat}</span>
            <span className="bandeau-kpi-lbl">Effort (années)</span>
          </div>
        )}
      </div>
    </div>
  )
}
