const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

// ==========================================================================
// CONNECTIVITÉ
// ==========================================================================

/**
 * Scores connectivité agrégés.
 * @param {object} params - { granularite: 'arrondissement'|'quartier' }
 */
export async function fetchScoresConnectivite({ granularite = 'arrondissement' } = {}) {
  const base = granularite === 'quartier' ? `${API}/connectivite/quartier` : `${API}/connectivite`
  const res = await fetch(base, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

/**
 * Points géospatiaux connectivité (GeoJSON).
 * @param {object} params - { arrondissement?, code_quartier? }
 */
export async function fetchPointsConnectivite({ arrondissement = null, code_quartier = null } = {}) {
  const qs = new URLSearchParams()
  if (code_quartier)   qs.set('code_quartier',  code_quartier)
  else if (arrondissement) qs.set('arrondissement', arrondissement)
  
  const queryStr = qs.toString() ? `?${qs.toString()}` : ''
  const url = `${API}/connectivite/points/geojson${queryStr}`
  
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}