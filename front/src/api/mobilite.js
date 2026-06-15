const API = 'http://localhost:8000'
const headers = { 'X-API-Key': import.meta.env.VITE_API_KEY }

export async function fetchScoresMobilite() {
  const res = await fetch(`${API}/mobilite`, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}

export async function fetchPointsMobilite(codePostal = null) {
  const url = codePostal
    ? `${API}/mobilite/points/geojson?code_postal=${codePostal}`
    : `${API}/mobilite/points/geojson`
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`Erreur ${res.status}`)
  return res.json()
}