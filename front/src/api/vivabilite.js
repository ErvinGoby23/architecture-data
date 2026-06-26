const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }


// ==========================================================================
// VIVABILITÉ
// ==========================================================================

/**
 * Scores vivabilité agrégés.
 * @param {object} params - { granularite: 'arrondissement'|'quartier', arrondissement?, code_quartier? }
 */
export async function fetchScoresVivabilite({ granularite = 'arrondissement', arrondissement = null, code_quartier = null } = {}) {
  const base = granularite === 'quartier' ? `${API}/vivabilite/quartier` : `${API}/vivabilite`
  const qs   = new URLSearchParams()
  if (arrondissement) qs.set('arrondissement', arrondissement)
  if (code_quartier)  qs.set('code_quartier', code_quartier)
  const url = qs.toString() ? `${base}?${qs}` : base
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

/**
 * Points géospatiaux vivabilité (GeoJSON).
 * @param {object} params - { granularite, arrondissement?, code_quartier?, type_point? }
 */
export async function fetchPointsVivabilite({
  granularite    = 'arrondissement',
  arrondissement = null,
  code_quartier  = null,
  type_point     = null,
} = {}) {
  const qs = new URLSearchParams()
  if (granularite === 'quartier' && code_quartier)   qs.set('code_quartier',  code_quartier)
  if (granularite === 'arrondissement' && arrondissement) qs.set('arrondissement', arrondissement)
  if (type_point) qs.set('type_point', type_point)
  const url = `${API}/vivabilite/points/geojson${qs.toString() ? `?${qs}` : ''}`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}