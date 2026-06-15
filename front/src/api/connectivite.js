const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

export async function fetchScoresConnectivite() {
  const res = await fetch(`${API}/connectivite`, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

export async function fetchPointsConnectivite(codePostal = null) {
  const url = codePostal
    ? `${API}/connectivite/points/geojson?code_postal=${codePostal}`
    : `${API}/connectivite/points/geojson`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}