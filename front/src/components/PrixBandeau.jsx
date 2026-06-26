import { useMemo } from 'react'

/**
 * Bandeau flottant en haut-centre de la carte : prix de la zone sélectionnée.
 * Spécifique logement. N'affiche rien si aucune zone n'est sélectionnée.
 *
 * Props :
 *   selectedData : object|null  ligne du score (zone + année active)
 *   prevData     : object|null  même zone, année précédente (variation)
 *   zoneLabel    : string|null  libellé de la zone
 *   year         : number
 */
export default function PrixBandeau({ selectedData = null, prevData = null, zoneLabel = null, year }) {
  const variation = useMemo(() => {
    if (!selectedData?.prix_m2_median || !prevData?.prix_m2_median) return null
    const v = ((selectedData.prix_m2_median - prevData.prix_m2_median) / prevData.prix_m2_median) * 100
    return Math.round(v * 10) / 10
  }, [selectedData, prevData])

  if (!selectedData) return null

  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat('fr-FR').format(Math.round(n)))

  return (
    <div className="prix-bandeau">
      <div className="prix-bandeau-zone">
        <span className="prix-bandeau-zone-name">{zoneLabel ?? '—'}</span>
        <span className="prix-bandeau-zone-year">{year}</span>
      </div>

      <div className="prix-bandeau-main">
        <span className="prix-bandeau-value">{fmt(selectedData.prix_m2_median)}</span>
        <span className="prix-bandeau-unit">€/m²</span>
        {variation != null && (
          <span className={`prix-bandeau-var ${variation >= 0 ? 'up' : 'down'}`}>
            {variation >= 0 ? '▲' : '▼'} {Math.abs(variation)}%
          </span>
        )}
      </div>

      <div className="prix-bandeau-sub">
        <div className="prix-bandeau-kpi">
          <span className="prix-bandeau-kpi-val">{fmt(selectedData.nb_ventes)}</span>
          <span className="prix-bandeau-kpi-lbl">ventes</span>
        </div>
        <div className="prix-bandeau-sep" />
        <div className="prix-bandeau-kpi">
          <span className="prix-bandeau-kpi-val">{selectedData.surface_mediane ?? '—'} m²</span>
          <span className="prix-bandeau-kpi-lbl">surface méd.</span>
        </div>
        {selectedData.taux_effort_achat != null && (
          <>
            <div className="prix-bandeau-sep" />
            <div className="prix-bandeau-kpi">
              <span className="prix-bandeau-kpi-val">{selectedData.taux_effort_achat}</span>
              <span className="prix-bandeau-kpi-lbl">ans d'effort</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
