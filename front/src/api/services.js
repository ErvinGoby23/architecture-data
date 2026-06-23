// src/api/services.js

const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

// --------------------------------------------------------------------------
// SCORES
// --------------------------------------------------------------------------
// Le MapView appelle fetcher({ granularite, year }).
// - arrondissement -> GET /services
// - quartier       -> GET /services/quartier
export async function fetchScoresServices({ granularite = 'arrondissement' } = {}) {
  const url = granularite === 'quartier'
    ? `${API}/services/quartier`
    : `${API}/services`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

// --------------------------------------------------------------------------
// POINTS GEOJSON
// --------------------------------------------------------------------------
// Le MapView appelle :
//   { granularite: 'quartier',       code_quartier:  selected }
//   { granularite: 'arrondissement', arrondissement: selected }
export async function fetchPointsServices(params = {}) {
  // Rétro-compat : si on reçoit un simple nombre (ancien appel codePostal)
  if (typeof params === 'number') {
    params = { granularite: 'arrondissement', arrondissement: params - 75000 }
  }

  const { granularite = 'arrondissement', code_quartier, arrondissement } = params

  let url = `${API}/services/points/geojson`
  if (granularite === 'quartier' && code_quartier != null) {
    url += `?code_quartier=${code_quartier}`
  } else if (arrondissement != null) {
    url += `?arrondissement=${arrondissement}`
  }

  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}