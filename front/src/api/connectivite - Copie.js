const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

export async function fetchScoresConnectivite(annee = null) {
  const url = annee
    ? `${API}/connectivite?annee=${annee}`
    : `${API}/connectivite`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

export async function fetchPointsConnectivite({ arrondissement = null } = {}) {
  const cp = arrondissement ? 75000 + parseInt(arrondissement) : null
  const url = cp
    ? `${API}/connectivite/points/geojson?code_postal=${cp}`
    : `${API}/connectivite/points/geojson`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}