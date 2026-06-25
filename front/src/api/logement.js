const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

// ==========================================================================
// LOGEMENT
// ==========================================================================

/**
 * Scores d'accessibilité logement agrégés.
 * @param {object} params - { granularite: 'arrondissement'|'quartier', arrondissement?, code_quartier?, annee? }
 */
export async function fetchScoresLogement({
  granularite = 'arrondissement',
  arrondissement = null,
  code_quartier = null,
  annee = null,
  year = null,
} = {}) {
  const an = annee ?? year   // accepte 'year' (App) comme 'annee'
  const base = granularite === 'quartier' ? `${API}/logement/quartier` : `${API}/logement`

  const qs = new URLSearchParams()
  if (granularite === 'quartier') {
    if (code_quartier) qs.set('code_quartier', code_quartier)
    else if (arrondissement) qs.set('arrondissement', arrondissement)
  } else if (arrondissement) {
    qs.set('arrondissement', arrondissement)
  }
  if (an) qs.set('annee', an)

  const queryStr = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${base}${queryStr}`, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}
/**
 * Série temporelle d'un arrondissement (pour la timeline).
 * @param {object} params - { arrondissement }
 */
export async function fetchTimelineLogement({ arrondissement } = {}) {
  const url = `${API}/logement/timeline?arrondissement=${arrondissement}`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

/**
 * Points géospatiaux logement (GeoJSON) : transactions DVF + programmes sociaux.
 * @param {object} params - { arrondissement?, code_quartier?, annee?, type? }
 *                          type : 'transaction' | 'logement_social'
 */
export async function fetchPointsLogement({
  arrondissement = null,
  code_quartier = null,
  annee = null,
  type = null,
} = {}) {
  const qs = new URLSearchParams()
  if (code_quartier) qs.set('code_quartier', code_quartier)
  else if (arrondissement) qs.set('arrondissement', arrondissement)
  if (annee) qs.set('annee', annee)
  if (type) qs.set('type', type)

  const queryStr = qs.toString() ? `?${qs.toString()}` : ''
  const url = `${API}/logement/points/geojson${queryStr}`

  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}